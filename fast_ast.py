# -*- coding: utf-8 -*-
"""fast_ast.py —— Python 原生 AST → flat/blks（毫秒级，替代宿主分钟级解析）
复刻 boot_parse_v4.tl 的 emit 顺序与 reg_blk 时机，输出与宿主逐字节一致。
用法: fast_ast.parse(src_text) -> (flat, blks, names)
"""
import io, sys
sys.path.insert(0, ".")
import tl

# ---- 固定符号（31 个，id 12-42，与 boot_lex_v6 lookup 一致）----
FIXED = ["tensor", "range", "eq", "ge", "le", "lt", "add", "sub", "mul", "cat",
         "mk", "get", "len", "empty", "set1", "get2", "pack32", "pack64", "byte",
         "band", "bor", "bxor", "bshl", "bshr", "update", "div", "mod", "ext_in",
         "dbl64", "gt", "app", "alloc"]
FIXED_ID = {n: 12 + i for i, n in enumerate(FIXED)}

class _Builder:
    def __init__(self, dyn_order):
        self.flat = []
        self.blks = []          # 块表 [len, idx...]
        self.blk_cnt = 0
        self.names = {}         # id -> 名字
        self._sym = dict(FIXED_ID)   # 名字 -> id
        # 动态符号按源码 token 流出现顺序（与 boot_lex lookup 一致）：id = 231 + i
        for i, n in enumerate(dyn_order):
            self._sym[n] = 231 + i
        self._dyn = 31 + len(dyn_order)

    def sym(self, name):
        if name not in self._sym:
            # AST 中出现但预扫描遗漏（不应发生）——顺延分配
            self._sym[name] = 200 + self._dyn
            self._dyn += 1
        sid = self._sym[name]
        if sid not in self.names:
            self.names[sid] = name
        return sid

    def emit(self, tp, a, b, c):
        idx = len(self.flat)
        self.flat.extend((tp, a, b, c))
        return idx

    def reg_blk(self, idxs):
        no = self.blk_cnt
        self.blks.append(len(idxs))
        self.blks.extend(idxs)
        self.blk_cnt += 1
        return no

    # ---- 表达式：复刻 parse_expr 的 emit 顺序（先子后父）----
    def walk_expr(self, e):
        if isinstance(e, tl.NumLit):
            return self.emit(11, int(e.value), 0, 0)
        if isinstance(e, tl.VarRef):
            return self.emit(12, self.sym(e.name), 0, 0)
        if isinstance(e, tl.Call):
            arg_idx = [self.walk_expr(a) for a in e.args]
            abl = self.reg_blk(arg_idx)
            return self.emit(13, self.sym(e.fn), abl, 0)
        if isinstance(e, tl.TensorLit):
            el_idx = [self.walk_expr(tl.NumLit(v)) for v in e.values]
            tbl = self.reg_blk(el_idx)
            return self.emit(14, len(el_idx), tbl, 0)
        if isinstance(e, tl.ParamLit):
            return self.emit(15, int(e.dims[0]), int(e.dims[1]) if len(e.dims) > 1 else 0, 0)
        raise ValueError("未知表达式 %r" % (e,))

    # ---- 块：先 emit 语句（子块先注册），最后 reg_blk ----
    def walk_block(self, stmts):
        idxs = []
        for s in stmts:
            si = self.walk_stmt(s)
            if si >= 0:
                idxs.append(si)
        return self.reg_blk(idxs)

    # ---- 语句：复刻 parse_stmt ----
    def walk_stmt(self, s):
        if isinstance(s, tl.LetStmt):
            e = self.walk_expr(s.expr)
            return self.emit(1, self.sym(s.name), e, 0)
        if isinstance(s, tl.PrintStmt):
            e = self.walk_expr(s.expr)
            return self.emit(2, e, 0, 0)
        if isinstance(s, tl.ForStmt):
            it = self.walk_expr(s.iter_expr)
            b = self.walk_block(s.body)
            return self.emit(3, self.sym(s.var), it, b)
        if isinstance(s, tl.IfStmt):
            cond = self.walk_expr(s.cond)
            b1 = self.walk_block(s.body)
            b2 = self.walk_block(s.body2) if s.body2 else 0
            return self.emit(4, cond, b1, b2)
        if isinstance(s, tl.WhileStmt):
            cond = self.walk_expr(s.cond)
            b = self.walk_block(s.body)
            return self.emit(5, cond, b, 0)
        if isinstance(s, tl.BreakStmt):
            return self.emit(6, 0, 0, 0)
        if isinstance(s, tl.DefStmt):
            p_start = len(self.flat)  # 参数块起始 flat 索引（4 的倍数）
            for p in s.params:
                self.emit(20, self.sym(p), 0, 0)
            self.emit(0, 0, 0, 0)
            b = self.walk_block(s.body)
            return self.emit(7, self.sym(s.name), p_start, b)
        if isinstance(s, tl.ReturnStmt):
            e = self.walk_expr(s.expr)
            return self.emit(8, e, 0, 0)
        if isinstance(s, tl.UpdateStmt):
            return self.emit(9, self.sym(s.name), int(s.lr), 0)
        if isinstance(s, tl.GlobalStmt):
            cnt = min(len(s.names), 2)
            n1 = self.sym(s.names[0]) if len(s.names) >= 1 else 0
            n2 = self.sym(s.names[1]) if len(s.names) >= 2 else 0
            return self.emit(16, cnt, n1, n2)
        if isinstance(s, tl.ExpressionStmt):
            e = self.walk_expr(s.expr)
            return self.emit(17, e, 0, 0)
        raise ValueError("不支持语句 %r" % (s,))


def _dyn_order(code):
    """源码 token 流动态符号出现顺序（复刻 boot_lex lookup 的追加顺序）。"""
    seen = set()
    dyn = []
    for t in tl.lex(code):
        if t.kind == tl.T.ID and t.text not in FIXED_ID and t.text not in seen:
            seen.add(t.text)
            dyn.append(t.text)
    return dyn


def parse(src_text):
    """src_text → (flat, blks, names)。flat/blks 与宿主 boot_parse 逐字节一致。"""
    ast = tl.Parser(tl.lex(src_text)).parse()
    b = _Builder(_dyn_order(src_text))
    top = b.walk_block(ast)
    assert top == b.blk_cnt - 1, "顶层必须是最后注册的块"
    return b.flat, b.blks, b.names


if __name__ == "__main__":
    # 自检：与宿主前端对比（小输入）
    import tl_front
    cases = {
        "极简": "let a = 5\nprint(a)\n",
        "复合if": "let a = tensor([1, 2, 3])\nlet b = 0\nif eq(get(a, 0), 1) {\n    let b = 6\n} else {\n    let b = 7\n}\nprint(b)\n",
        "两let": "let x = 1\nlet y = add(x, 2)\nprint(y)\n",
        "def+调用": "def f(a) {\n    return add(a, 1)\n}\nlet z = f(4)\nprint(z)\n",
        "for+while": "let s = 0\nfor i in range(3) {\n    let s = add(s, i)\n}\nwhile lt(s, 10) {\n    let s = add(s, 1)\n}\nprint(s)\n",
        "global": "global a b c\nlet a = 1\nprint(a)\n",
    }
    ok = True
    for name, src in cases.items():
        toks, names = tl_front.run_boot_lex(src)
        tpl = io.open("boot_parse.tl", encoding="utf-8").read()
        payload = ",".join(str(t) for t in toks)
        tpl2 = tpl.replace("tensor([0, 0, 0])", "tensor([%s])" % payload)
        out = tl_front.exec_tl(tpl2)
        lines = out.strip().split("\n")
        f_host = tl_front._nums(lines[0])
        b_host = tl_front._nums(lines[1])
        f_fast, b_fast, nm = parse(src)
        same = f_host == f_fast and b_host == b_fast
        print("%s: host(f=%d,b=%d) vs fast(f=%d,b=%d) %s" % (
            name, len(f_host), len(b_host), len(f_fast), len(b_fast),
            "一致" if same else "不一致!!"))
        if not same:
            ok = False
            for i, (x, y) in enumerate(zip(f_host, f_fast)):
                if x != y:
                    print("  flat 首个差异 @%d: host=%s fast=%s" % (i, x, y))
                    break
            for i, (x, y) in enumerate(zip(b_host, b_fast)):
                if x != y:
                    print("  blks 首个差异 @%d: host=%s fast=%s" % (i, x, y))
                    break
    print("总体: %s" % ("全部一致" if ok else "有差异"))
