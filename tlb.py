# -*- coding: utf-8 -*-
"""tl v0.9 —— 全自研后端：tl 字节码（.tlb）+ 自研编译器 pass + 自研虚拟机。

革命点：编译目标从"Python 对象图 / AST 解释"换成**自研指令集**——
  槽位分配（编译器）→ 嵌套表达式展开（编译器）→ fwd/back 指令（自研指令集）
  → VM 执行（自研虚拟机）。零 LLVM、零第三方。数值内核与后端算子执行体
  全部自研（复用 tl 模块仅用于前端编译：lex/parse/check/plan）。

.tlb 文本格式（可审计、可版本化）：
  #tl-bc v1
  slot <id> <name> <shape...> <kind:input|param|mid>
  const <id> <name> <shape...> <json>            # 输入字面量初值
  fwd  <dest> <op> <src...>                      # 前向指令
  back <dest> <op> <src...>                      # 反向指令（fwd 逆序）
  update <id>                                    # 训练更新参数（默认全集）
  loss <id>                                      # 损失槽（反向梯度种子）

数值约定：槽 value/grad 为裸嵌套 list 或标量 float；VM 自研算子执行体，
与前端 eval/backward 语义逐位一致（由 run_v09.py 验证）。
"""
import io
import json
import math
import ctypes

import tl

# v0.11：原生内核后端开关（NativeKernels 加载 kernels.dll，可选加速器）
_NK = None
# v0.12：Buf 扁平化快路径（槽值存连续 double buffer，零 _flat/_unflat 直通 C）
_BUF = True
_Buf = None      # tl_native.Buf（_enable_native 时绑定）
_BK = None       # tl_native._BufKernels（Buf 版内核）

def _enable_native(dll_path=None):
    """启用原生内核后端。返回 NativeKernels 或 None（加载失败则静默回退）。

    v0.14：_BK（Buf 热路径）已切换为 MachineBufKernels——全部内核由
    tl_emit 在内存发射 x86-64 机器码，不再依赖 kernels.dll；_NK（list
    接口）仍由 kernels.dll 提供，作为 list 包装层保留。"""
    global _NK, _Buf, _BK
    try:
        from tl_native import NativeKernels, Buf
        from tl_machine import MachineBufKernels
        if dll_path is None:
            import os
            dll_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "kernels.dll")
        _NK = NativeKernels(dll_path)
        _Buf = Buf
        _BK = MachineBufKernels()
    except Exception:
        _NK = None
    return _NK

def _is_buf(v):
    return _Buf is not None and isinstance(v, _Buf)

def _scalar(v):
    """标量提取：Buf / 单元素 list / 裸标量 -> float（与前端 `c[0]` 语义一致）。"""
    if _is_buf(v):
        return v.arr[0]
    if isinstance(v, list):
        return v[0]
    return v

def _to_buf(v, shape):
    return _Buf.from_list(v, shape)


# ======================================================================
# 一、自研数值内核（tlb 后端自带，与 tl.py 前端数值引擎独立实现）
# ======================================================================

def _zeros(shape):
    if len(shape) == 0:
        return 0.0
    if len(shape) == 1:
        return [0.0] * shape[0]
    return [_zeros(shape[1:]) for _ in range(shape[0])]


def _shape_of(v):
    s = []
    while isinstance(v, list):
        s.append(len(v))
        v = v[0] if v else []
    return tuple(s)


def _same_shape2(a, b):
    return _shape_of(a) == _shape_of(b)


def _elemwise2(a, b, f):
    """同形状逐元素二元运算（裸 list）。v0.11：模块级 op（add/sub/mul）走原生。"""
    if _NK is not None and f in (_add2, _sub2, _mul2):
        if _is_buf(a) and _is_buf(b):
            return _BK.elem2(a, b, 0 if f is _add2 else (1 if f is _sub2 else 2))
        return _NK.elem2(a, b, 0 if f is _add2 else (1 if f is _sub2 else 2))
    if _same_shape2(a, b):
        if isinstance(a, list):
            return [_elemwise2(x, y, f) for x, y in zip(a, b)]
        return f(a, b)
    raise ValueError("elemwise 形状不匹配 %s vs %s" % (_shape_of(a), _shape_of(b)))


def _rec_map(v, f):
    if _is_buf(v):
        arr = [_rec_map(x, f) for x in v.arr]
        out = (ctypes.c_double * v.n)(*arr)
        return _Buf(out, v.shape)
    if isinstance(v, list):
        return [_rec_map(x, f) for x in v]
    return f(v)


def _rec_zip2(a, b, f):
    if isinstance(a, list):
        return [_rec_zip2(x, y, f) for x, y in zip(a, b)]
    return f(a, b)


def _matmul2(a, b):
    """a[M,K] x b[K,N] -> [M,N]。
    与前端 matmul2 完全一致的朴素累加（s += 循环；不用内置 sum——
    Python 3.12+ 的 sum() 是补偿求和，逐位不同 -> 训练漂移）。
    v0.11：原生内核优先（kernels.dll，逐位一致）。"""
    if _NK is not None:
        if _is_buf(a) and _is_buf(b):
            return _BK.mm2(a, b)
        return _NK.mm2(a, b)
    M = len(a)
    K = len(a[0]) if M else 0
    N = len(b[0]) if (b and b[0] is not None) else 0
    out = [[0.0] * N for _ in range(M)]
    for m, row_a in enumerate(a):
        for n in range(N):
            s = 0.0
            for k in range(K):
                s += row_a[k] * b[k][n]
            out[m][n] = s
    return out


def _matmul2v(a, b):
    """a[M,K] x b[K] -> [M]（朴素循环累加，与前端 matmul2v 一致）。"""
    if _NK is not None:
        if _is_buf(a) and _is_buf(b):
            return _BK.mm2v(a, b)
        return _NK.mm2v(a, b)
    M = len(a)
    K = len(b)
    out = [0.0] * M
    for m in range(M):
        s = 0.0
        for k in range(K):
            s += a[m][k] * b[k]
        out[m] = s
    return out


def _transpose2(a):
    if _NK is not None:
        if _is_buf(a):
            return _BK.transpose(a)
        return _NK.transpose(a)
    M = len(a)
    N = len(a[0]) if M else 0
    return [[a[i][j] for i in range(M)] for j in range(N)]


_TL_EXP_COEFS = (
    4.7794773323873853e-14, 7.6471637318198164e-13,
    1.1470745597729725e-11, 1.6059043836821613e-10,
    2.08767569878681e-09,   2.505210838544172e-08,
    2.7557319223985888e-07, 2.7557319223985893e-06,
    2.4801587301587302e-05, 0.00019841269841269841,
    0.0013888888888888889,  0.0083333333333333332,
    0.041666666666666664,   0.16666666666666666,
    0.5, 1.0,
)

def _tl_exp(x):
    """自研 exp：x = k*ln2 + r（|r|<=ln2/2），exp(r) 16 阶 Taylor（Horner），
    2^k 用 ldexp。与 C 内核 tl_exp 同一算法——全自研数值内核，不依赖 libm。"""
    if x != x:
        return x
    if x == math.inf:
        return math.inf
    if x == -math.inf:
        return 0.0
    k = int(math.floor(x * 1.4426950408889634 + 0.5))
    if k > 1023:
        return math.inf
    r = x - k * 0.6931471805599453
    p = _TL_EXP_COEFS[0]
    for c in _TL_EXP_COEFS[1:]:
        p = p * r + c
    p = p * r + 1.0
    return math.ldexp(p, k)

def _row_softmax(row):
    m = max(row)
    ex = [_tl_exp(v - m) for v in row]
    s = sum(ex)
    return [e / s for e in ex]


def _rows_softmax(nested):
    if _is_buf(nested):
        if len(nested.shape) == 2:
            return _BK.rows_softmax(nested)
        return _rows_softmax(nested.to_list())
    if isinstance(nested[0], list):
        if _NK is not None and not isinstance(nested[0][0], list):
            return _NK.softmax(nested)      # 2D：一次性原生
        return [_rows_softmax(r) for r in nested]
    if _NK is not None:
        return _NK.softmax([nested])[0]     # 单行：包成 1×N 2D
    return _row_softmax(nested)


def _total(v):
    if _NK is not None:
        if _is_buf(v):
            return _BK.total(v)
        return _NK.total(v)
    if isinstance(v, list):
        return sum(_total(i) for i in v)
    return v


def _cnt(v):
    if _is_buf(v):
        return v.n
    if isinstance(v, list):
        return sum(_cnt(i) for i in v)
    return 1


def _broadcast_like(v, g):
    """把标量梯度 g 广播到 v 的形状。"""
    if _is_buf(v):
        out = (ctypes.c_double * v.n)(*([g] * v.n))
        return _Buf(out, v.shape)
    if isinstance(v, list):
        return [_broadcast_like(x, g) for x in v]
    return g


def _colsum(g, ncols):
    """行广播反向：a[M,N]+b[N] -> b 梯度 = 列和。"""
    if _NK is not None:
        if _is_buf(g):
            return _BK.colsum(g, ncols)
        return _NK.colsum(g, ncols)
    return [sum(g[m][n] for m in range(len(g))) for n in range(ncols)]


def _softmax_grad(s, g):
    if _is_buf(s):
        if len(s.shape) == 2:
            return _BK.softmax_grad(s, g)
        return _softmax_grad(s.to_list(), g.to_list() if _is_buf(g) else g)
    if isinstance(s[0], list):
        if _NK is not None and not isinstance(s[0][0], list):
            return _NK.softmax_grad(s, g)      # 2D：一次性原生
        return [_softmax_grad(a, b) for a, b in zip(s, g)]
    if _NK is not None:
        return _NK.softmax_grad([s], [g])[0]   # 单行：包成 1×N 2D
    dot = sum(a * b for a, b in zip(s, g))
    return [si * (gi - dot) for si, gi in zip(s, g)]


def _relu(v):
    if _NK is not None:
        if _is_buf(v):
            return _BK.relu(v)
        return _NK.relu(v)
    if isinstance(v, list):
        return [_relu(x) for x in v]
    return v if v > 0 else 0.0


def _relu_mask(x, g):
    if _NK is not None:
        if _is_buf(x) and _is_buf(g):
            return _BK.relu_mask(x, g)
        return _NK.relu_mask(x, g)
    if isinstance(x, list):
        return [_relu_mask(a, b) for a, b in zip(x, g)]
    return g if x > 0 else 0.0


def _sqg(x, g):
    if _NK is not None:
        if _is_buf(x) and _is_buf(g):
            return _BK.sqg(x, g)
        return _NK.sqg(x, g)
    if isinstance(x, list):
        return [_sqg(a, b) for a, b in zip(x, g)]
    return 2.0 * x * g


def _scg(x, g, cv):
    if _NK is not None:
        if _is_buf(g):
            return _BK.scg(g, cv)
        return _NK.scg(g, cv)
    if isinstance(x, list):
        return [_scg(a, b, cv) for a, b in zip(x, g)]
    return g / cv


def _upd(v, g, lr):
    if _NK is not None:
        if _is_buf(v) and _is_buf(g):
            return _BK.upd(v, g, lr)
        return _NK.upd(v, g, lr)
    if isinstance(v, list):
        return [_upd(a, b, lr) for a, b in zip(v, g)]
    return v - lr * g


# ======================================================================
# 二、字节码程序结构（槽 / 常量 / 指令）
# ======================================================================

class Slot:
    __slots__ = ("id", "name", "shape", "kind", "init", "value", "grad")

    def __init__(self, sid, name, shape, kind, init=None):
        self.id = sid
        self.name = name
        self.shape = tuple(shape)
        self.kind = kind          # input | param | mid
        self.init = init          # input 初值（裸 list）；param/mid 为 None
        self.value = None
        self.grad = None

    def fresh(self):
        s = Slot(self.id, self.name, self.shape, self.kind, self.init)
        return s


class Insn:
    __slots__ = ("op", "dest", "srcs")

    def __init__(self, op, dest, srcs):
        self.op = op
        self.dest = dest          # 槽 id
        self.srcs = tuple(srcs)   # 槽 id 元组


class BytecodeProgram:
    """tl 字节码程序：槽表 + 常量 + fwd/back 指令 + update + loss。"""

    def __init__(self):
        self.slots = []          # 按 id 顺序
        self.fwd = []            # [Insn]
        self.back = []           # [Insn]（fwd 逆序）
        self.updates = []        # 参数槽 id
        self.loss_id = None

    # ---- 序列化 .tlb ----
    def to_text(self):
        lines = ["#tl-bc v1"]
        for s in self.slots:
            lines.append("slot %d %s %s %s" % (s.id, s.name,
                                               " ".join(str(d) for d in s.shape),
                                               s.kind))
            if s.init is not None:
                lines.append("const %d %s %s" % (s.id, s.name, json.dumps(s.init)))
        for ins in self.fwd:
            lines.append("fwd %d %s %s" % (ins.dest, ins.op,
                                           " ".join(str(x) for x in ins.srcs)))
        for ins in self.back:
            lines.append("back %d %s %s" % (ins.dest, ins.op,
                                            " ".join(str(x) for x in ins.srcs)))
        for u in self.updates:
            lines.append("update %d" % u)
        lines.append("loss %d" % self.loss_id)
        return "\n".join(lines) + "\n"

    @staticmethod
    def from_text(text):
        prog = BytecodeProgram()
        slot_by_id = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if parts[0] == "slot":
                sid = int(parts[1])
                name = parts[2]
                shape = tuple(int(x) for x in parts[3:-1])
                kind = parts[-1]
                s = Slot(sid, name, shape, kind)
                slot_by_id[sid] = s
                prog.slots.append(s)
            elif parts[0] == "const":
                cp = line.split(None, 3)          # ['const', id, name, json...]
                sid = int(cp[1])
                slot_by_id[sid].init = json.loads(cp[3])
            elif parts[0] == "fwd":
                dest = int(parts[1])
                op = parts[2]
                srcs = tuple(int(x) for x in parts[3:])
                prog.fwd.append(Insn(op, dest, srcs))
            elif parts[0] == "back":
                dest = int(parts[1])
                op = parts[2]
                srcs = tuple(int(x) for x in parts[3:])
                prog.back.append(Insn(op, dest, srcs))
            elif parts[0] == "update":
                prog.updates.append(int(parts[1]))
            elif parts[0] == "loss":
                prog.loss_id = int(parts[1])
        return prog

    def dump(self):
        print("  slots:", [(s.id, s.name, s.shape, s.kind) for s in self.slots])
        print("  fwd:", [(i.op, i.dest, i.srcs) for i in self.fwd])
        print("  back:", [(i.op, i.dest, i.srcs) for i in self.back])
        print("  update:", self.updates, "loss:", self.loss_id)


# ======================================================================
# 三、编译器 pass：TrainingPlan → BytecodeProgram
# ======================================================================

def compile_to_bytecode(plan):
    """前端计划 -> 自研字节码：
    - 槽位分配：全部 let 名（输入/参数/中间）+ 嵌套展开出的临时槽
    - 嵌套表达式提升：与前端 eval 的求值顺序一致（深度优先、从左到右）
    - back 指令 = fwd 逆序（梯度从 loss 逆推）
    """
    prog = BytecodeProgram()
    fwd_lets = [st for st in plan.fwd if isinstance(st, tl.LetStmt)]
    slots = {}
    sid = 0

    def new_slot(name, shape, kind, init=None):
        nonlocal sid
        s = Slot(sid, name, shape, kind, init)
        slots[name] = s
        prog.slots.append(s)
        sid += 1
        return s

    # 第一遍：命名槽（形状来自 checker 环境）
    chk_shapes = getattr(plan, "shapes", None) or {}
    for st in fwd_lets:
        shape = _slot_shape(st, chk_shapes)
        kind = "param" if st.name in plan.params else (
            "input" if _is_input_expr(st.expr) else "mid")
        s = new_slot(st.name, shape, kind)
        if kind == "input":
            s.init = _lit_value(st.expr)

    # 第二遍：展开嵌套表达式 → fwd 指令
    tmp_counter = [0]

    def flat(expr, dest_name):
        """展开一个 Call：递归处理参数（保持 eval 求值顺序），返回 (op, dest, srcs)。"""
        srcs = []
        for a in expr.args:
            if isinstance(a, tl.VarRef):
                srcs.append(slots[a.name].id)
            elif isinstance(a, tl.TensorLit):
                # 字面量直接参数 → 提升常量槽
                nm = "_c%d" % tmp_counter[0]
                tmp_counter[0] += 1
                s = new_slot(nm, _shape_of(a.values), "mid", init=_lit_value(a))
                srcs.append(s.id)
            elif isinstance(a, tl.ParamLit):
                nm = "_p%d" % tmp_counter[0]
                tmp_counter[0] += 1
                s = new_slot(nm, tuple(a.dims), "param")
                srcs.append(s.id)
            elif isinstance(a, tl.Call):
                sub = flat(a, None)
                prog.fwd.append(Insn(sub[0], sub[1], sub[2]))   # 子指令先入队（eval 顺序）
                srcs.append(sub[1])
            else:
                raise ValueError("无法指令化的参数: %r" % (a,))
        if dest_name is None:
            nm = "_t%d" % tmp_counter[0]
            tmp_counter[0] += 1
            shape = _expr_shape(expr, chk_shapes)
            new_slot(nm, shape, "mid")
            dest = slots[nm].id
        else:
            dest = slots[dest_name].id
        return (expr.fn, dest, srcs)

    for st in fwd_lets:
        e = st.expr
        if isinstance(e, tl.TensorLit) or isinstance(e, tl.ParamLit):
            continue
        if isinstance(e, tl.Call) and e.fn == "tensor":
            continue
        op, dest, srcs = flat(e, st.name)
        prog.fwd.append(Insn(op, dest, srcs))

    # back：fwd 逆序
    prog.back = [Insn(i.op, i.dest, i.srcs) for i in reversed(prog.fwd)]

    # update / loss
    prog.updates = [slots[p].id for p in plan.params]
    loss_names = sorted(plan.loss_names)
    if not loss_names:
        raise ValueError("训练计划缺少损失（sum/mean 标量）")
    prog.loss_id = slots[loss_names[-1]].id
    return prog


def _is_input_expr(e):
    return isinstance(e, tl.TensorLit) or (isinstance(e, tl.Call) and e.fn == "tensor")


def _lit_value(e):
    if isinstance(e, tl.TensorLit):
        return e.values
    if isinstance(e, tl.Call) and e.fn == "tensor":
        return e.args[0].values if e.args else []
    return None


def _slot_shape(st, chk_shapes):
    """let 的形状：优先 checker 形状环境，其次从字面量推断。"""
    if chk_shapes and st.name in chk_shapes:
        return tuple(chk_shapes[st.name])
    e = st.expr
    if isinstance(e, tl.TensorLit):
        return _shape_of(e.values)
    if isinstance(e, tl.ParamLit):
        return tuple(e.dims)
    return _expr_shape(e, chk_shapes)


def _expr_shape(e, shape_map=None):
    """运行期推断 expr 形状（仅用于槽声明；checker 已保证形状正确）。"""
    shape_map = shape_map or {}
    if isinstance(e, tl.VarRef):
        return tuple(shape_map.get(e.name, (0,)))
    if isinstance(e, tl.TensorLit):
        return _shape_of(e.values)
    if isinstance(e, tl.ParamLit):
        return tuple(e.dims)
    if isinstance(e, tl.Call):
        shapes = [_expr_shape(a, shape_map) for a in e.args]
        fn = e.fn
        if fn == "matmul":
            a, b = shapes[0], shapes[1]
            if len(a) == 2 and len(b) == 2:
                return (a[0], b[1])
            if len(a) == 2 and len(b) == 1:
                return (a[0],)
            if len(a) == 3 and len(b) == 3:
                return (a[0], a[1], b[2])
        if fn in ("add", "sub", "mul"):
            a, b = shapes[0], shapes[1]
            if a == b:
                return a
            if len(a) == 2 and len(b) == 1 and a[1] == b[0]:
                return a
            if len(b) == 2 and len(a) == 1 and b[1] == a[0]:
                return b
            if b in ((), (1,)):
                return a
            if a in ((), (1,)):
                return b
        if fn in ("relu", "square", "softmax", "scale"):
            return shapes[0]
        if fn in ("transpose",):
            a = shapes[0]
            return (a[1], a[0]) if len(a) == 2 else (a[0], a[2], a[1])
        if fn in ("sum", "mean"):
            return ()
        if fn in ("scaled_mm", "scaled_mm_t"):
            a, b = shapes[0], shapes[1]
            if len(a) == 2 and len(b) == 2:
                return (a[0], b[1])
            if len(a) == 3 and len(b) == 3:
                return (a[0], a[1], b[2])
        if fn in ("affine", "bias_relu"):
            a, b = shapes[0], shapes[1]
            if len(a) == 2 and len(b) == 2:
                return (a[0], b[1])
            if len(a) == 3 and len(b) == 3:
                return (a[0], a[1], b[2])
            if len(a) == 2 and len(b) == 1:
                return (a[0],)
        if fn == "tensor":
            return _shape_of(e.args[0].values) if e.args else ()
    return ()


# ======================================================================
# 四、自研 VM：字节码执行（fwd/back/update）
# ======================================================================

class BytecodeVM:
    def __init__(self, prog, kernels=None):
        self.prog = prog
        self.slots = {s.id: s.fresh() for s in prog.slots}
        # v0.10：预编译 kernel 调度（编译期形状分支绑定）
        if kernels is None:
            kernels = compile_kernels(prog)
        self.fwd_k, self.back_k = kernels
        # v0.11：原生内核后端（构造时捕获，融合 kernel 用 vm.nk 分支）
        self.nk = _NK

    # ---- 前向指令执行体 ----
    def _fwd_op(self, op, dest, srcs):
        v = [self.slots[x].value for x in srcs]
        a, b = v[0], (v[1] if len(v) > 1 else None)
        c = (v[2] if len(v) > 2 else None)

        if op == "matmul":
            if len(_shape_of(a)) == 3:
                out = [_matmul2(a[i], b[i]) for i in range(len(a))]
            elif len(_shape_of(b)) == 1:
                out = _matmul2v(a, b)
            else:
                out = _matmul2(a, b)
        elif op in ("add", "sub"):
            f = (lambda x, y: x + y) if op == "add" else (lambda x, y: x - y)
            sa, sb = _shape_of(a), _shape_of(b)
            if sa == sb:
                out = _elemwise2(a, b, f)
            elif len(sa) == 2 and len(sb) == 1 and sa[1] == sb[0]:
                out = [[f(a[m][n], b[n]) for n in range(sa[1])] for m in range(sa[0])]
            elif len(sb) == 2 and len(sa) == 1 and sb[1] == sa[0]:
                out = [[f(a[n], b[m][n]) for n in range(sb[1])] for m in range(sb[0])]
            elif sb in ((), (1,)):
                cv = b if sb == () else b[0]
                out = _rec_map(a, lambda x: f(x, cv))
            elif sa in ((), (1,)):
                cv = a if sa == () else a[0]
                out = _rec_map(b, lambda x: f(cv, x))
            else:
                raise ValueError("add/sub 形状 %s vs %s" % (sa, sb))
        elif op == "mul":
            out = _elemwise2(a, b, lambda x, y: x * y)
        elif op == "relu":
            out = _relu(a)
        elif op == "square":
            out = _elemwise2(a, a, lambda x, y: x * y)
        elif op == "sum":
            out = _total(a)
        elif op == "mean":
            out = _total(a) / _cnt(a)
        elif op == "transpose":
            out = _transpose2(a) if len(_shape_of(a)) == 2 else [
                _transpose2(a[i]) for i in range(len(a))]
        elif op == "scale":
            cv = c if _shape_of(c) == () else c[0]
            out = _rec_map(a, lambda x: x / cv)
        elif op == "softmax":
            out = _rows_softmax(a)
        elif op in ("scaled_mm", "scaled_mm_t"):
            cv = c if _shape_of(c) == () else c[0]
            if len(_shape_of(a)) == 3:
                out = []
                for i in range(len(a)):
                    if op == "scaled_mm":
                        mb = _matmul2(a[i], b[i])
                    else:
                        # 与前端 fused_call 一致：内积用内置 sum()（补偿求和）
                        mb = [[sum(a[i][m][k] * b[i][n][k] for k in range(len(a[i][0])))
                               for n in range(len(b[i]))] for m in range(len(a[i]))]
                    out.append([[e / cv for e in row] for row in mb])
            else:
                if op == "scaled_mm":
                    mb = _matmul2(a, b)
                else:
                    mb = [[sum(a[m][k] * b[n][k] for k in range(len(a[0])))
                           for n in range(len(b))] for m in range(len(a))]
                out = [[e / cv for e in row] for row in mb]
        elif op in ("affine", "bias_relu"):
            out = self._affine_fwd(op, a, b, c)
        elif op == "tensor":
            out = self.slots[dest].init
        else:
            raise ValueError("未知前向指令 %s" % op)
        self.slots[dest].value = out

    def _affine_fwd(self, op, a, b, bias):
        """affine/bias_relu 前向：z = a@b + bias（行广播/标量），bias_relu 再 relu。"""
        if len(_shape_of(a)) == 3:
            out = []
            for bb in range(len(a)):
                row = self._affine_fwd(op, a[bb], b[bb], bias)
                out.append(row)
            return out
        if len(_shape_of(b)) == 1:
            # 2D×1D：z[m] = a[m]·b + bias（同长或标量）
            sa, sb = _shape_of(a), _shape_of(b)
            if sb == (sa[0],):
                z = [_matmul2v(a, b)[m] + bias[m] for m in range(sa[0])]
            else:
                cv = bias if _shape_of(bias) == () else bias[0]
                z = [x + cv for x in _matmul2v(a, b)]
        else:
            M, N = len(a), len(b[0])
            z = [[sum(a[m][k] * b[k][n] for k in range(len(b))) for n in range(N)]
                 for m in range(M)]
            if _shape_of(bias) == (N,):
                z = [[z[m][n] + bias[n] for n in range(N)] for m in range(M)]
            else:
                cv = bias if _shape_of(bias) == () else bias[0]
                z = [[z[m][n] + cv for n in range(N)] for m in range(M)]
        if op == "affine":
            return z
        return [[max(0.0, v) for v in row] for row in z]

    # ---- 反向指令执行体：返回与 srcs 对齐的梯度列表（裸 list/float） ----
    def _back_op(self, op, dest, srcs):
        g = self.slots[dest].grad
        v = [self.slots[x].value for x in srcs]
        a, b = v[0], (v[1] if len(v) > 1 else None)
        c = (v[2] if len(v) > 2 else None)

        if op == "matmul":
            sa = _shape_of(a)
            if len(sa) == 3:
                ga = []
                gb = []
                for i in range(len(a)):
                    bt = _transpose2(b[i])
                    at = _transpose2(a[i])
                    ga.append(_matmul2(g[i], bt))
                    gb.append(_matmul2(at, g[i]))
            elif len(_shape_of(b)) == 1:
                ga = [[g[m] * b[k] for k in range(len(b))] for m in range(len(a))]
                gb = [sum(a[m][k] * g[m] for m in range(len(a))) for k in range(len(b))]
            else:
                bt = _transpose2(b)
                at = _transpose2(a)
                ga = _matmul2(g, bt)
                gb = _matmul2(at, g)
            return [ga, gb]
        if op in ("add", "sub"):
            sa, sb = _shape_of(a), _shape_of(b)
            sign = 1.0 if op == "add" else -1.0
            if sa == sb:
                return [g, _rec_map(g, lambda x: sign * x)]
            if len(sa) == 2 and len(sb) == 1 and sa[1] == sb[0]:
                gb = _colsum(g, sb[0])
                return [g, [sign * x for x in gb]]
            if len(sb) == 2 and len(sa) == 1 and sb[1] == sa[0]:
                ga = _colsum(g, sa[0])
                return [[sign * x for x in ga], g]
            if sb in ((), (1,)):
                return [g, None]
            if sa in ((), (1,)):
                return [None, g]
            raise ValueError("add/sub 反向形状 %s vs %s" % (sa, sb))
        if op == "mul":
            return [_elemwise2(b, g, lambda x, y: x * y),
                    _elemwise2(a, g, lambda x, y: x * y)]
        if op == "relu":
            return [_relu_mask(a, g)]
        if op == "square":
            return [_sqg(a, g)]
        if op == "sum":
            return [_broadcast_like(a, g)]
        if op == "mean":
            return [_broadcast_like(a, g / _cnt(a))]
        if op == "transpose":
            return [_transpose2(g) if len(_shape_of(a)) == 2 else
                    [_transpose2(g[i]) for i in range(len(a))]]
        if op == "scale":
            cv = c if _shape_of(c) == () else c[0]
            return [_rec_map(g, lambda x: x / cv)]
        if op == "softmax":
            return [_softmax_grad(self.slots[dest].value, g)]
        if op in ("scaled_mm", "scaled_mm_t"):
            return self._scaled_back(op, a, b, c, g, self.slots[dest].value)
        if op in ("affine", "bias_relu"):
            return self._affine_back(op, a, b, c, g)
        if op == "tensor":
            return []
        raise ValueError("未知反向指令 %s" % op)

    def _scaled_back(self, op, a, b, c, g, out):
        """scaled_mm/scaled_mm_t 反向（2D/3D），与前端 fused_call 语义一致。"""
        cv = c if _shape_of(c) == () else c[0]
        sa = _shape_of(a)
        if len(sa) == 3:
            ga, gb, dc = [], [], 0.0
            for i in range(len(a)):
                if op == "scaled_mm":
                    mvi = _matmul2(a[i], b[i])
                    bt = _transpose2(b[i])
                    at = _transpose2(a[i])
                    ga.append(_matmul2([[e / cv for e in row] for row in g[i]], bt))
                    gb.append(_matmul2(at, [[e / cv for e in row] for row in g[i]]))
                else:
                    mvi = _matmul2(a[i], _transpose2(b[i]))
                    ga.append([[
                        sum(g[i][m][n] * b[i][n][k] for n in range(len(b[i]))) / cv
                        for k in range(len(b[i][0]))] for m in range(len(a[i]))])
                    gb.append([[
                        sum(g[i][m][n] * a[i][m][k] for m in range(len(a[i]))) / cv
                        for k in range(len(b[i][0]))] for n in range(len(b[i]))])
                dc += -sum(g[i][m][n] * mvi[m][n]
                           for m in range(len(g[i])) for n in range(len(g[i][0]))) / (cv * cv)
            return [ga, gb, dc]
        if op == "scaled_mm":
            mvi = _matmul2(a, b)
            bt = _transpose2(b)
            at = _transpose2(a)
            ga = _matmul2([[e / cv for e in row] for row in g], bt)
            gb = _matmul2(at, [[e / cv for e in row] for row in g])
        else:
            mvi = _matmul2(a, _transpose2(b))
            ga = [[sum(g[m][n] * b[n][k] for n in range(len(b))) / cv
                   for k in range(len(b[0]))] for m in range(len(a))]
            gb = [[sum(g[m][n] * a[m][k] for m in range(len(a))) / cv
                   for k in range(len(b[0]))] for n in range(len(b))]
        dc = -sum(g[m][n] * mvi[m][n]
                  for m in range(len(g)) for n in range(len(g[0]))) / (cv * cv)
        return [ga, gb, dc]

    def _affine_back(self, op, a, b, bias, g):
        """affine/bias_relu 反向（2D×2D / 3D×3D / 2D×1D），z 按需重算（值未变，与前端一致）。"""
        sa = _shape_of(a)
        if len(sa) == 3:
            z = self._affine_fwd(op, a, b, bias)
            g2 = g if op == "affine" else [
                [[(gi if zi > 0 else 0.0) for zi, gi in zip(zz, gg)]
                 for zz, gg in zip(bb, g[i])]
                for i, bb in enumerate(z)]
            ga = [[[sum(g2[i][m][n] * b[i][k][n] for n in range(len(b[i][0])))
                    for k in range(len(b[i]))] for m in range(len(a[i]))]
                  for i in range(len(a))]
            gb = [[[sum(a[i][m][k] * g2[i][m][n] for m in range(len(a[i])))
                    for n in range(len(b[i][0]))] for k in range(len(b[i]))]
                  for i in range(len(a))]
            if _shape_of(bias) == (len(b[0][0]),):
                gb_bias = [sum(g2[i][m][n]
                               for i in range(len(a)) for m in range(len(a[i])))
                           for n in range(len(b[0][0]))]
            else:
                gb_bias = sum(g2[i][m][n]
                              for i in range(len(a)) for m in range(len(a[i]))
                              for n in range(len(b[i][0])))
            return [ga, gb, gb_bias]
        if len(_shape_of(b)) == 1:
            z = self._affine_fwd(op, a, b, bias)
            g2 = [gi if zi > 0 else 0.0 for zi, gi in zip(z, g)] if op == "bias_relu" else g
            ga = [[g2[m] * b[k] for k in range(len(b))] for m in range(len(a))]
            gb = [sum(a[m][k] * g2[m] for m in range(len(a))) for k in range(len(b))]
            if _shape_of(bias) == (len(a),):
                gb_bias = list(g2)
            else:
                gb_bias = sum(g2)
            return [ga, gb, gb_bias]
        z = self._affine_fwd(op, a, b, bias)
        g2 = [[(gi if zi > 0 else 0.0) for zi, gi in zip(zz, gg)]
              for zz, gg in zip(z, g)] if op == "bias_relu" else g
        bt = _transpose2(b)
        at = _transpose2(a)
        ga = _matmul2(g2, bt)
        gb = _matmul2(at, g2)
        if _shape_of(bias) == (len(b[0]),):
            gb_bias = _colsum(g2, len(b[0]))
        else:
            gb_bias = sum(g2[m][n] for m in range(len(g2)) for n in range(len(g2[0])))
        return [ga, gb, gb_bias]

    # ---- 梯度累积（与前端 accum 语义一致：None -> 直接设；否则逐元素加） ----
    def _accum(self, sid, grad):
        if grad is None:
            return
        slot = self.slots[sid]
        if slot.grad is None:
            slot.grad = grad
        else:
            if _is_buf(slot.grad) and _is_buf(grad) and _NK is not None:
                slot.grad = _BK.elem2(slot.grad, grad, 0)
            else:
                slot.grad = _elemwise2(slot.grad, grad, lambda x, y: x + y)

    # ---- 执行 ----
    def forward(self):
        if self.fwd_k:
            for k, d, s in self.fwd_k:
                k(self, d, s)
        else:
            for ins in self.prog.fwd:
                self._fwd_op(ins.op, ins.dest, ins.srcs)

    def backward(self):
        for s in self.slots.values():
            s.grad = None
        self.slots[self.prog.loss_id].grad = 1.0
        if self.back_k:
            for k, d, s in self.back_k:
                grads = k(self, d, s)
                for sid, gr in zip(s, grads):
                    self._accum(sid, gr)
        else:
            for ins in self.prog.back:
                grads = self._back_op(ins.op, ins.dest, ins.srcs)
                for sid, gr in zip(ins.srcs, grads):
                    self._accum(sid, gr)

    def run(self, epochs, lr=0.2, seed=None, update=None):
        """训练循环：forward → backward → update（update 参数集可选）。"""
        import random
        for s in self.slots.values():
            if s.kind == "input":
                s.value = s.init
            elif s.kind == "param":
                s.value = _zeros(s.shape)
        if seed is not None:
            rnd = random.Random(seed)
            for s in self.slots.values():
                if s.kind == "param":
                    s.value = _rec_map(_zeros(s.shape), lambda _: rnd.uniform(-0.3, 0.3))
        id_of = {s.name: s.id for s in self.prog.slots}
        if update is not None:
            updates = [u if isinstance(u, int) else id_of[u] for u in update]
        else:
            updates = self.prog.updates
        # v0.12：Buf 扁平化（input/param 槽转连续 buffer，热路径零拷贝）
        if _BUF and _Buf is not None and _NK is not None:
            for s in self.slots.values():
                if s.kind in ("input", "param"):
                    s.value = _to_buf(s.value, s.shape)
        losses = []
        for _ in range(epochs):
            self.forward()
            self.backward()
            for uid in updates:
                sl = self.slots[uid]
                sl.value = _upd(sl.value, sl.grad, lr)
            losses.append(self.slots[self.prog.loss_id].value)
        return losses


# ======================================================================
# 五、高层入口
# ======================================================================

def build_program(code, do_optimize=True):
    """.tl 源码 -> BytecodeProgram（前端编译 + 后端编译）。"""
    plan = tl.compile_training(code, do_optimize=do_optimize)
    return compile_to_bytecode(plan), plan


def train_bytecode(prog, epochs, lr=0.2, seed=None, update=None):
    vm = BytecodeVM(prog)
    return vm.run(epochs, lr=lr, seed=seed, update=update), vm


# ======================================================================
# 六、v0.10 调度器编译：编译期形状分支绑定（零运行时判断）
# ======================================================================
# 字节码编译期槽表已知全部形状——把每条指令的形状分支在编译期选好，
# 生成专用 kernel（签名 k(vm, dest, srcs)）。运行时不查形状、不做
# if-elif dispatch、无 Insn 属性访问。kernel 数值表达式与
# _fwd_op/_back_op 对应分支逐字一致 -> 与 v0.9 逐位一致（由 run_v10 验证）。
# 意义：形状系统从"编译期检查"升级为"代码生成器"——语言级优化的兑现。

def _add2(x, y):
    return x + y


def _sub2(x, y):
    return x - y


def _mul2(x, y):
    return x * y


# ---------------- 前向 kernels ----------------
def _k_matmul2(vm, dest, srcs):
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    vm.slots[dest].value = _matmul2(a, b)


def _k_matmul2v(vm, dest, srcs):
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    vm.slots[dest].value = _matmul2v(a, b)


def _k_matmul3(vm, dest, srcs):
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    vm.slots[dest].value = [_matmul2(a[i], b[i]) for i in range(len(a))]


def _k_bin_same(f):
    def k(vm, dest, srcs):
        a = vm.slots[srcs[0]].value
        b = vm.slots[srcs[1]].value
        vm.slots[dest].value = _elemwise2(a, b, f)
    return k


def _k_bin_row2(f):
    """2D op 1D 行广播：out[m][n] = f(a[m][n], b[n])。"""
    def k(vm, dest, srcs):
        a = vm.slots[srcs[0]].value
        b = vm.slots[srcs[1]].value
        vm.slots[dest].value = [[f(a[m][n], b[n]) for n in range(len(b))]
                               for m in range(len(a))]
    return k


def _k_bin_col2(f):
    """1D op 2D 列广播：out[m][n] = f(a[n], b[m][n])。"""
    def k(vm, dest, srcs):
        a = vm.slots[srcs[0]].value
        b = vm.slots[srcs[1]].value
        vm.slots[dest].value = [[f(a[n], b[m][n]) for n in range(len(a))]
                               for m in range(len(b))]
    return k


def _mk_bin_scalar_b(f):
    """2D/ND op 标量 b。"""
    def k(vm, dest, srcs):
        a = vm.slots[srcs[0]].value
        b = vm.slots[srcs[1]].value
        cv = b if not isinstance(b, list) else b[0]
        vm.slots[dest].value = _rec_map(a, lambda x: f(x, cv))
    return k


def _mk_bin_scalar_a(f):
    """标量 a op b。"""
    def k(vm, dest, srcs):
        a = vm.slots[srcs[0]].value
        b = vm.slots[srcs[1]].value
        cv = a if not isinstance(a, list) else a[0]
        vm.slots[dest].value = _rec_map(b, lambda x: f(cv, x))
    return k


def _k_relu(vm, dest, srcs):
    vm.slots[dest].value = _relu(vm.slots[srcs[0]].value)


def _k_square(vm, dest, srcs):
    a = vm.slots[srcs[0]].value
    vm.slots[dest].value = _elemwise2(a, a, _mul2)


def _k_total(vm, dest, srcs):
    vm.slots[dest].value = _total(vm.slots[srcs[0]].value)


def _k_mean(vm, dest, srcs):
    a = vm.slots[srcs[0]].value
    vm.slots[dest].value = _total(a) / _cnt(a)


def _k_transpose2(vm, dest, srcs):
    vm.slots[dest].value = _transpose2(vm.slots[srcs[0]].value)


def _k_transpose3(vm, dest, srcs):
    a = vm.slots[srcs[0]].value
    vm.slots[dest].value = [_transpose2(a[i]) for i in range(len(a))]


def _k_scale(vm, dest, srcs):
    a = vm.slots[srcs[0]].value
    c = vm.slots[srcs[2]].value
    cv = c if not isinstance(c, list) else c[0]
    vm.slots[dest].value = _rec_map(a, lambda x: x / cv)


def _k_softmax(vm, dest, srcs):
    vm.slots[dest].value = _rows_softmax(vm.slots[srcs[0]].value)


def _k_scaled_mm2(vm, dest, srcs):
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    c = vm.slots[srcs[2]].value
    if _is_buf(a) and _is_buf(b) and _NK is not None:
        vm.slots[dest].value = _BK.scaled_mm(a, b, _scalar(c))
        return
    cv = _scalar(c)
    if vm.nk is not None:
        vm.slots[dest].value = vm.nk.scaled_mm(a, b, cv)
        return
    vm.slots[dest].value = [[e / cv for e in row]
                           for row in _matmul2(a, b)]


def _k_scaled_mm3(vm, dest, srcs):
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    c = vm.slots[srcs[2]].value
    cv = c if not isinstance(c, list) else c[0]
    vm.slots[dest].value = [[[e / cv for e in row]
                             for row in _matmul2(a[i], b[i])]
                            for i in range(len(a))]


def _k_scaled_mm_t2(vm, dest, srcs):
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    c = vm.slots[srcs[2]].value
    if _is_buf(a) and _is_buf(b) and _NK is not None:
        vm.slots[dest].value = _BK.scaled_mm_t(a, b, _scalar(c))
        return
    cv = _scalar(c)
    if vm.nk is not None:
        vm.slots[dest].value = vm.nk.scaled_mm_t(a, b, cv)
        return
    mb = [[sum(a[m][k] * b[n][k] for k in range(len(a[0])))
           for n in range(len(b))] for m in range(len(a))]
    vm.slots[dest].value = [[e / cv for e in row] for row in mb]


def _k_scaled_mm_t3(vm, dest, srcs):
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    c = vm.slots[srcs[2]].value
    cv = c if not isinstance(c, list) else c[0]
    out = []
    for i in range(len(a)):
        mb = [[sum(a[i][m][k] * b[i][n][k] for k in range(len(a[i][0])))
               for n in range(len(b[i]))] for m in range(len(a[i]))]
        out.append([[e / cv for e in row] for row in mb])
    vm.slots[dest].value = out


def _k_affine2(vm, dest, srcs):
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    bias = vm.slots[srcs[2]].value
    if _is_buf(a) and _is_buf(b) and _NK is not None:
        vm.slots[dest].value = _BK.affine2(a, b, bias, False)
        return
    if vm.nk is not None:
        vm.slots[dest].value = vm.nk.affine2(a, b, bias, False)
        return
    M, N = len(a), len(b[0])
    z = [[sum(a[m][k] * b[k][n] for k in range(len(b))) for n in range(N)]
         for m in range(M)]
    if not isinstance(bias, list):
        z = [[z[m][n] + bias for n in range(N)] for m in range(M)]
    else:
        z = [[z[m][n] + bias[n] for n in range(N)] for m in range(M)]
    vm.slots[dest].value = z


def _k_affine2v(vm, dest, srcs):
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    bias = vm.slots[srcs[2]].value
    sa = (len(a), len(b))
    z = [_matmul2v(a, b)[m] + bias[m] for m in range(sa[0])]
    vm.slots[dest].value = z


def _k_bias_relu2(vm, dest, srcs):
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    bias = vm.slots[srcs[2]].value
    if _is_buf(a) and _is_buf(b) and _NK is not None:
        vm.slots[dest].value = _BK.affine2(a, b, bias, True)
        return
    if vm.nk is not None:
        vm.slots[dest].value = vm.nk.affine2(a, b, bias, True)
        return
    M, N = len(a), len(b[0])
    z = [[sum(a[m][k] * b[k][n] for k in range(len(b))) for n in range(N)]
         for m in range(M)]
    if not isinstance(bias, list):
        z = [[max(0.0, z[m][n] + bias) for n in range(N)] for m in range(M)]
    else:
        z = [[max(0.0, z[m][n] + bias[n]) for n in range(N)] for m in range(M)]
    vm.slots[dest].value = z


def _k_tensor(vm, dest, srcs):
    vm.slots[dest].value = vm.slots[dest].init


# ---------------- 反向 kernels（返回与 srcs 对齐的梯度列表） ----------------
def _k_back_matmul2(vm, dest, srcs):
    g = vm.slots[dest].grad
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    bt = _transpose2(b)
    at = _transpose2(a)
    return [_matmul2(g, bt), _matmul2(at, g)]


def _k_back_matmul2v(vm, dest, srcs):
    g = vm.slots[dest].grad
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    ga = [[g[m] * b[k] for k in range(len(b))] for m in range(len(a))]
    gb = [sum(a[m][k] * g[m] for m in range(len(a))) for k in range(len(b))]
    return [ga, gb]


def _k_back_matmul3(vm, dest, srcs):
    g = vm.slots[dest].grad
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    ga, gb = [], []
    for i in range(len(a)):
        bt = _transpose2(b[i])
        at = _transpose2(a[i])
        ga.append(_matmul2(g[i], bt))
        gb.append(_matmul2(at, g[i]))
    return [ga, gb]


def _k_back_bin_same(f):
    def k(vm, dest, srcs):
        g = vm.slots[dest].grad
        a = vm.slots[srcs[0]].value
        return [g, _rec_map(g, f)]
    return k


def _k_back_bin_row2(f):
    """2D op 1D：gb = colsum(g)；ga = g。"""
    def k(vm, dest, srcs):
        g = vm.slots[dest].grad
        a = vm.slots[srcs[0]].value
        sb = vm.slots[srcs[1]].shape
        gb = _colsum(g, sb[0])
        return [g, [f(x) for x in gb]]
    return k


def _k_back_bin_col2(f):
    """1D op 2D：ga = colsum(g)；gb = g。"""
    def k(vm, dest, srcs):
        g = vm.slots[dest].grad
        a = vm.slots[srcs[0]].value
        sa = vm.slots[srcs[0]].shape
        ga = _colsum(g, sa[0])
        return [[f(x) for x in ga], g]
    return k


def _k_back_bin_scalar_b(vm, dest, srcs):
    g = vm.slots[dest].grad
    return [g, None]


def _k_back_bin_scalar_a(vm, dest, srcs):
    g = vm.slots[dest].grad
    return [None, g]


def _k_back_mul(vm, dest, srcs):
    g = vm.slots[dest].grad
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    return [_elemwise2(b, g, _mul2), _elemwise2(a, g, _mul2)]


def _k_back_relu(vm, dest, srcs):
    g = vm.slots[dest].grad
    a = vm.slots[srcs[0]].value
    return [_relu_mask(a, g)]


def _k_back_square(vm, dest, srcs):
    g = vm.slots[dest].grad
    a = vm.slots[srcs[0]].value
    return [_sqg(a, g)]


def _k_back_sum(vm, dest, srcs):
    g = vm.slots[dest].grad
    a = vm.slots[srcs[0]].value
    return [_broadcast_like(a, g)]


def _k_back_mean(vm, dest, srcs):
    g = vm.slots[dest].grad
    a = vm.slots[srcs[0]].value
    return [_broadcast_like(a, g / _cnt(a))]


def _k_back_transpose2(vm, dest, srcs):
    g = vm.slots[dest].grad
    return [_transpose2(g)]


def _k_back_transpose3(vm, dest, srcs):
    g = vm.slots[dest].grad
    return [[_transpose2(g[i]) for i in range(len(g))]]


def _k_back_scale(vm, dest, srcs):
    g = vm.slots[dest].grad
    c = vm.slots[srcs[2]].value
    cv = c if not isinstance(c, list) else c[0]
    return [_rec_map(g, lambda x: x / cv)]


def _k_back_softmax(vm, dest, srcs):
    g = vm.slots[dest].grad
    out = vm.slots[dest].value
    return [_softmax_grad(out, g)]


def _k_back_scaled_mm2(vm, dest, srcs):
    g = vm.slots[dest].grad
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    c = vm.slots[srcs[2]].value
    if _is_buf(a) and _is_buf(b) and _is_buf(g) and _NK is not None:
        return _BK.scaled_mm_back(a, b, g, _scalar(c))
    cv = _scalar(c)
    if vm.nk is not None:
        return vm.nk.scaled_mm_back(a, b, g, cv)
    mvi = _matmul2(a, b)
    bt = _transpose2(b)
    at = _transpose2(a)
    ga = _matmul2([[e / cv for e in row] for row in g], bt)
    gb = _matmul2(at, [[e / cv for e in row] for row in g])
    dc = -sum(g[m][n] * mvi[m][n]
              for m in range(len(g)) for n in range(len(g[0]))) / (cv * cv)
    return [ga, gb, dc]


def _k_back_scaled_mm3(vm, dest, srcs):
    g = vm.slots[dest].grad
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    c = vm.slots[srcs[2]].value
    cv = c if not isinstance(c, list) else c[0]
    ga, gb, dc = [], [], 0.0
    for i in range(len(a)):
        mvi = _matmul2(a[i], b[i])
        bt = _transpose2(b[i])
        at = _transpose2(a[i])
        ga.append(_matmul2([[e / cv for e in row] for row in g[i]], bt))
        gb.append(_matmul2(at, [[e / cv for e in row] for row in g[i]]))
        dc += -sum(g[i][m][n] * mvi[m][n]
                   for m in range(len(g[i])) for n in range(len(g[i][0]))) / (cv * cv)
    return [ga, gb, dc]


def _k_back_scaled_mm_t2(vm, dest, srcs):
    g = vm.slots[dest].grad
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    c = vm.slots[srcs[2]].value
    if _is_buf(a) and _is_buf(b) and _is_buf(g) and _NK is not None:
        return _BK.scaled_mm_t_back(a, b, g, _scalar(c))
    cv = _scalar(c)
    if vm.nk is not None:
        return vm.nk.scaled_mm_t_back(a, b, g, cv)
    mvi = _matmul2(a, _transpose2(b))
    ga = [[sum(g[m][n] * b[n][k] for n in range(len(b))) / cv
           for k in range(len(b[0]))] for m in range(len(a))]
    gb = [[sum(g[m][n] * a[m][k] for m in range(len(a))) / cv
           for k in range(len(b[0]))] for n in range(len(b))]
    dc = -sum(g[m][n] * mvi[m][n]
              for m in range(len(g)) for n in range(len(g[0]))) / (cv * cv)
    return [ga, gb, dc]


def _k_back_scaled_mm_t3(vm, dest, srcs):
    g = vm.slots[dest].grad
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    c = vm.slots[srcs[2]].value
    cv = c if not isinstance(c, list) else c[0]
    ga, gb, dc = [], [], 0.0
    for i in range(len(a)):
        mvi = _matmul2(a[i], _transpose2(b[i]))
        ga.append([[
            sum(g[i][m][n] * b[i][n][k] for n in range(len(b[i]))) / cv
            for k in range(len(b[i][0]))] for m in range(len(a[i]))])
        gb.append([[
            sum(g[i][m][n] * a[i][m][k] for m in range(len(a[i]))) / cv
            for k in range(len(b[i][0]))] for n in range(len(b[i]))])
        dc += -sum(g[i][m][n] * mvi[m][n]
                   for m in range(len(g[i])) for n in range(len(g[i][0]))) / (cv * cv)
    return [ga, gb, dc]


def _mk_back_affine(relu):
    """affine/bias_relu 反向 2D×2D（z 按需重算）。"""
    def k(vm, dest, srcs):
        g = vm.slots[dest].grad
        a = vm.slots[srcs[0]].value
        b = vm.slots[srcs[1]].value
        bias = vm.slots[srcs[2]].value
        if _is_buf(a) and _is_buf(b) and _is_buf(g) and _NK is not None:
            return _BK.affine2_back(a, b, g, bias, relu)
        if vm.nk is not None:
            return vm.nk.affine2_back(a, b, g, bias, relu)
        N = len(b[0])
        z = [[sum(a[m][k] * b[k][n] for k in range(len(b))) for n in range(N)]
             for m in range(len(a))]
        if not isinstance(bias, list):
            z = [[z[m][n] + bias for n in range(N)] for m in range(len(a))]
        else:
            z = [[z[m][n] + bias[n] for n in range(N)] for m in range(len(a))]
        g2 = g
        if relu:
            g2 = [[(gi if zi > 0 else 0.0) for zi, gi in zip(zz, gg)]
                  for zz, gg in zip(z, g)]
        bt = _transpose2(b)
        at = _transpose2(a)
        ga = _matmul2(g2, bt)
        gb = _matmul2(at, g2)
        if not isinstance(bias, list):
            gb_bias = sum(g2[m][n]
                          for m in range(len(g2)) for n in range(len(g2[0])))
        else:
            gb_bias = _colsum(g2, len(b[0]))
        return [ga, gb, gb_bias]
    return k


def _mk_back_affine2v(relu):
    """affine/bias_relu 反向 2D×1D。"""
    def k(vm, dest, srcs):
        g = vm.slots[dest].grad
        a = vm.slots[srcs[0]].value
        b = vm.slots[srcs[1]].value
        bias = vm.slots[srcs[2]].value
        if _is_buf(a) and _is_buf(b) and _is_buf(g) and _NK is not None:
            return _BK.affine2v_back(a, b, g, bias, relu)
        if vm.nk is not None:
            return vm.nk.affine2v_back(a, b, g, bias, relu)
        z = [_matmul2v(a, b)[m] + bias[m] for m in range(len(a))]
        g2 = [gi if zi > 0 else 0.0 for zi, gi in zip(z, g)] if relu else g
        ga = [[g2[m] * b[k] for k in range(len(b))] for m in range(len(a))]
        gb = [sum(a[m][k] * g2[m] for m in range(len(a))) for k in range(len(b))]
        if not isinstance(bias, list):
            gb_bias = sum(g2)
        else:
            gb_bias = list(g2)
        return [ga, gb, gb_bias]
    return k


def _mk_back_affine3(relu):
    """affine/bias_relu 反向 3D×3D。"""
    def k(vm, dest, srcs):
        g = vm.slots[dest].grad
        a = vm.slots[srcs[0]].value
        b = vm.slots[srcs[1]].value
        bias = vm.slots[srcs[2]].value
        N3 = len(b[0][0])
        z = [[[sum(a[i][m][k] * b[i][k][n] for k in range(len(b[i])))
               for n in range(N3)] for m in range(len(a[i]))]
             for i in range(len(a))]
        if not isinstance(bias, list):
            z = [[[z[i][m][n] + bias for n in range(N3)]
                  for m in range(len(a[i]))] for i in range(len(a))]
        else:
            z = [[[z[i][m][n] + bias[n] for n in range(N3)]
                  for m in range(len(a[i]))] for i in range(len(a))]
        g2 = g
        if relu:
            g2 = [[[(gi if zi > 0 else 0.0) for zi, gi in zip(zz, gg)]
                   for zz, gg in zip(bb, g[i])] for i, bb in enumerate(z)]
        ga = [[[sum(g2[i][m][n] * b[i][k][n] for n in range(N3))
                for k in range(len(b[i]))] for m in range(len(a[i]))]
              for i in range(len(a))]
        gb = [[[sum(a[i][m][k] * g2[i][m][n] for m in range(len(a[i])))
                for n in range(N3)] for k in range(len(b[i]))]
              for i in range(len(a))]
        if not isinstance(bias, list):
            gb_bias = sum(g2[i][m][n]
                          for i in range(len(a)) for m in range(len(a[i]))
                          for n in range(N3))
        else:
            gb_bias = [sum(g2[i][m][n]
                           for i in range(len(a)) for m in range(len(a[i])))
                       for n in range(N3)]
        return [ga, gb, gb_bias]
    return k


def _k_back_tensor(vm, dest, srcs):
    return []


# ---------------- 编译期分支选择 ----------------
def compile_kernels(prog):
    """对每条 fwd/back 指令，用槽表已知形状选择专用 kernel。返回 (fwd_k, back_k)。"""
    shapes = {s.id: s.shape for s in prog.slots}
    fwd_k = []
    for ins in prog.fwd:
        sa = shapes[ins.srcs[0]] if ins.srcs else ()
        sb = shapes[ins.srcs[1]] if len(ins.srcs) > 1 else ()
        sc = shapes[ins.srcs[2]] if len(ins.srcs) > 2 else ()
        op = ins.op
        if op == "matmul":
            if len(sa) == 3:
                k = _k_matmul3
            elif len(sb) == 1:
                k = _k_matmul2v
            else:
                k = _k_matmul2
        elif op in ("add", "sub"):
            f = _add2 if op == "add" else _sub2
            if sa == sb:
                k = _k_bin_same(f)
            elif len(sa) == 2 and len(sb) == 1 and sa[1] == sb[0]:
                k = _k_bin_row2(f)
            elif len(sb) == 2 and len(sa) == 1 and sb[1] == sa[0]:
                k = _k_bin_col2(f)
            elif sb in ((), (1,)):
                k = _mk_bin_scalar_b(f)
            elif sa in ((), (1,)):
                k = _mk_bin_scalar_a(f)
            else:
                raise ValueError("add/sub 形状 %s vs %s" % (sa, sb))
        elif op == "mul":
            k = _k_bin_same(_mul2)
        elif op == "relu":
            k = _k_relu
        elif op == "square":
            k = _k_square
        elif op == "sum":
            k = _k_total
        elif op == "mean":
            k = _k_mean
        elif op == "transpose":
            k = _k_transpose2 if len(sa) == 2 else _k_transpose3
        elif op == "scale":
            k = _k_scale
        elif op == "softmax":
            k = _k_softmax
        elif op == "scaled_mm":
            k = _k_scaled_mm3 if len(sa) == 3 else _k_scaled_mm2
        elif op == "scaled_mm_t":
            k = _k_scaled_mm_t3 if len(sa) == 3 else _k_scaled_mm_t2
        elif op in ("affine", "bias_relu"):
            if len(sa) == 3:
                k = _k_affine3 if op == "affine" else _k_bias_relu3
            elif len(sb) == 1:
                k = _k_affine2v if op == "affine" else _k_bias_relu2v
            else:
                k = _k_affine2 if op == "affine" else _k_bias_relu2
        elif op == "tensor":
            k = _k_tensor
        else:
            raise ValueError("未知前向指令 %s" % op)
        fwd_k.append((k, ins.dest, tuple(ins.srcs)))
    back_k = []
    for ins in prog.back:
        sa = shapes[ins.srcs[0]] if ins.srcs else ()
        sb = shapes[ins.srcs[1]] if len(ins.srcs) > 1 else ()
        op = ins.op
        if op == "matmul":
            if len(sa) == 3:
                k = _k_back_matmul3
            elif len(sb) == 1:
                k = _k_back_matmul2v
            else:
                k = _k_back_matmul2
        elif op in ("add", "sub"):
            f = (lambda x: x) if op == "add" else (lambda x: -x)
            if sa == sb:
                k = _k_back_bin_same(f)
            elif len(sa) == 2 and len(sb) == 1 and sa[1] == sb[0]:
                k = _k_back_bin_row2(f)
            elif len(sb) == 2 and len(sa) == 1 and sb[1] == sa[0]:
                k = _k_back_bin_col2(f)
            elif sb in ((), (1,)):
                k = _k_back_bin_scalar_b
            elif sa in ((), (1,)):
                k = _k_back_bin_scalar_a
            else:
                raise ValueError("add/sub 反向形状 %s vs %s" % (sa, sb))
        elif op == "mul":
            k = _k_back_mul
        elif op == "relu":
            k = _k_back_relu
        elif op == "square":
            k = _k_back_square
        elif op == "sum":
            k = _k_back_sum
        elif op == "mean":
            k = _k_back_mean
        elif op == "transpose":
            k = _k_back_transpose2 if len(sa) == 2 else _k_back_transpose3
        elif op == "scale":
            k = _k_back_scale
        elif op == "softmax":
            k = _k_back_softmax
        elif op == "scaled_mm":
            k = _k_back_scaled_mm3 if len(sa) == 3 else _k_back_scaled_mm2
        elif op == "scaled_mm_t":
            k = _k_back_scaled_mm_t3 if len(sa) == 3 else _k_back_scaled_mm_t2
        elif op in ("affine", "bias_relu"):
            relu = op == "bias_relu"
            if len(sa) == 3:
                k = _mk_back_affine3(relu)
            elif len(sb) == 1:
                k = _mk_back_affine2v(relu)
            else:
                k = _mk_back_affine(relu)
        elif op == "tensor":
            k = _k_back_tensor
        else:
            raise ValueError("未知反向指令 %s" % op)
        back_k.append((k, ins.dest, tuple(ins.srcs)))
    return fwd_k, back_k


# affine/bias_relu 3D 与 2D×1D 的前向 kernel（循环引用补全，定义于分支选择之后）
def _k_affine3(vm, dest, srcs):
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    bias = vm.slots[srcs[2]].value
    N3 = len(b[0][0])
    z = [[[sum(a[i][m][k] * b[i][k][n] for k in range(len(b[i])))
           for n in range(N3)] for m in range(len(a[i]))]
         for i in range(len(a))]
    if not isinstance(bias, list):
        z = [[[z[i][m][n] + bias for n in range(N3)]
              for m in range(len(a[i]))] for i in range(len(a))]
    else:
        z = [[[z[i][m][n] + bias[n] for n in range(N3)]
              for m in range(len(a[i]))] for i in range(len(a))]
    vm.slots[dest].value = z


def _k_bias_relu3(vm, dest, srcs):
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    bias = vm.slots[srcs[2]].value
    N3 = len(b[0][0])
    z = [[[sum(a[i][m][k] * b[i][k][n] for k in range(len(b[i])))
           for n in range(N3)] for m in range(len(a[i]))]
         for i in range(len(a))]
    if not isinstance(bias, list):
        z = [[[max(0.0, z[i][m][n] + bias) for n in range(N3)]
              for m in range(len(a[i]))] for i in range(len(a))]
    else:
        z = [[[max(0.0, z[i][m][n] + bias[n]) for n in range(N3)]
              for m in range(len(a[i]))] for i in range(len(a))]
    vm.slots[dest].value = z


def _k_affine2v(vm, dest, srcs):
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    bias = vm.slots[srcs[2]].value
    if _is_buf(a) and _is_buf(b) and _NK is not None:
        vm.slots[dest].value = _BK.affine2v(a, b, bias, False)
        return
    if vm.nk is not None:
        vm.slots[dest].value = vm.nk.affine2v(a, b, bias, False)
        return
    sa0 = len(a)
    z0 = _matmul2v(a, b)
    if not isinstance(bias, list):
        z = [x + bias for x in z0]
    else:
        cv = bias[0] if len(bias) == 1 else None
        z = [z0[m] + (cv if cv is not None else bias[m]) for m in range(sa0)]
    vm.slots[dest].value = z


def _k_bias_relu2v(vm, dest, srcs):
    a = vm.slots[srcs[0]].value
    b = vm.slots[srcs[1]].value
    bias = vm.slots[srcs[2]].value
    if _is_buf(a) and _is_buf(b) and _NK is not None:
        vm.slots[dest].value = _BK.affine2v(a, b, bias, True)
        return
    if vm.nk is not None:
        vm.slots[dest].value = vm.nk.affine2v(a, b, bias, True)
        return
    sa0 = len(a)
    z0 = _matmul2v(a, b)
    if not isinstance(bias, list):
        z = [max(0.0, x + bias) for x in z0]
    else:
        cv = bias[0] if len(bias) == 1 else None
        z = [max(0.0, z0[m] + (cv if cv is not None else bias[m])) for m in range(sa0)]
    vm.slots[dest].value = z


def train_bytecode(prog, epochs, lr=0.2, seed=None, update=None, kernels=None):
    vm = BytecodeVM(prog, kernels=kernels)
    return vm.run(epochs, lr=lr, seed=seed, update=update), vm
