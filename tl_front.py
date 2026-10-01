# -*- coding: utf-8 -*-
"""tl_front.py —— B 线第三步：前端 tl 化落地替换。

编译管线 lexer/parser 全部走 .tl 程序：
    src_text → boot_lex.tl（词法+符号表）→ token 流 → boot_parse.tl（AST 构建）
    → flat AST → Python AST 对象（喂给 Checker/Engine/后端）

Python 侧不再负责 lex/parse 规则本身，只负责：
    1) 宿主执行 .tl 程序（Engine 是 tl 语义的实现）
    2) 反序列化 flat AST 为 AST 对象
"""
import io, re, sys, contextlib

sys.path.insert(0, ".")
import tl
import front_mach

LEX_PATH = "boot_lex_v6.tl"
PARSE_PATH = "boot_parse.tl"
_fm = None


def _get_fm():
    global _fm
    if _fm is None:
        _fm = front_mach.FrontMach()
    return _fm

# 反序列化映射（与 boot_parse.tl / _run_parse.py 参考序列化器同一编码约定）
# 节点 type: 0=块哨兵 1=let 2=print 3=for 4=if 5=while 6=break 7=def 8=return
#            9=update 11=NumLit 12=VarRef 13=Call 14=tensor_lit 15=param_lit
#            16=Global 20=param


def exec_tl(src_text, ext_inputs=None):
    """宿主执行一段 .tl 源码，返回全部 print 输出。ext_inputs 供 ext_in 原语读取。
    前端（词法+解析）走机器码（front_mach），Checker/Engine 仍为 Python 语义实现。"""
    tl.EXT_INPUTS = ext_inputs or []
    ast_list, _, _, _ = parse(src_text)
    tl.Checker().check(ast_list)
    eng = tl.Engine()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        eng.run(ast_list, quiet=False)
    return buf.getvalue()


def _nums(s):
    m = re.search(r"\[(.*?)\]", s, re.S)
    if not m:
        raise ValueError("无数组输出: %r" % s[:200])
    return [int(float(x)) for x in m.group(1).split(",")]


def _inject_src_tensor(src_text, template):
    """把 src_text 字节注入模板的 `let src = tensor([...])` 占位。"""
    src_bytes = ",".join(str(b) for b in src_text.encode("utf-8"))
    new = "let src = tensor([%s])" % src_bytes
    return re.sub(r"let src = tensor\(\[[^\]]*\]\)", new, template, count=1)


def run_boot_lex(src_text):
    """src_text → (token 流, id→名字符号表)。词法机器码执行（脱离 Python 宿主）。"""
    return _get_fm().lex_names(src_text.encode("utf-8"))


def run_boot_parse(toks):
    """token 流 → (flat AST 数组, 块表)。解析机器码执行（脱离 Python 宿主）。"""
    return _get_fm().parse(toks)


def parse_blks(blks):
    """块表 [len0, idx..., len1, idx...] → [(block_no, [stmt_idx...])]"""
    out = []
    i = 0
    no = 0
    while i < len(blks):
        L = blks[i]
        idxs = blks[i + 1:i + 1 + L]
        out.append((no, idxs))
        no += 1
        i += 1 + L
    return out


def deserialize(flat, blks, names):
    """flat AST + 块表 → Python AST 对象列表。"""
    n = len(flat)
    blk_map = dict(parse_blks(blks))

    def _nm(sid):
        if sid not in names:
            raise ValueError("符号 id %d 不在符号表（表大小 %d）" % (sid, len(names)))
        return names[sid]

    def block(no):
        """块号 → 语句列表（索引导航，不依赖物理顺序）。"""
        return [node(i) for i in blk_map[no]]

    def params(idx):
        """def 参数块：20 节点序列 + 0 哨兵（物理顺序，p_start 起始）。"""
        ps = []
        while idx < n and flat[idx] != 0:
            assert flat[idx] == 20, "参数块含 type %d" % flat[idx]
            ps.append(_nm(flat[idx + 1]))
            idx += 4
        return ps

    def node(idx):
        tp, a, b, c = flat[idx], flat[idx + 1], flat[idx + 2], flat[idx + 3]
        if tp == 1:    # let
            return tl.LetStmt(_nm(a), node(b))
        if tp == 2:    # print
            return tl.PrintStmt(node(a))
        if tp == 3:    # for
            return tl.ForStmt(_nm(a), node(b), block(c))
        if tp == 4:    # if
            b2 = block(c) if c else None
            return tl.IfStmt(node(a), block(b), b2)
        if tp == 5:    # while
            return tl.WhileStmt(node(a), block(b))
        if tp == 6:    # break
            return tl.BreakStmt()
        if tp == 7:    # def
            return tl.DefStmt(_nm(a), params(b), block(c))
        if tp == 8:    # return
            return tl.ReturnStmt(node(a))
        if tp == 9:    # update
            return tl.UpdateStmt(_nm(a), float(b))
        if tp == 11:   # NumLit（_num 语义：hex→int，其余→float）
            return tl.NumLit(float(a))
        if tp == 12:   # VarRef
            return tl.VarRef(_nm(a))
        if tp == 13:   # Call: a=fn_id, b=参数块号（块表导航，支持任意参数数）
            return tl.Call(_nm(a), block(b))
        if tp == 14:   # tensor_lit: a=元素数, b=元素块号（元素为 NumLit 节点）
            return tl.TensorLit([float(node(i).value) for i in blk_map[b]])
        if tp == 15:   # param_lit: a=d0, b=d1
            return tl.ParamLit([a, b])
        if tp == 16:   # Global: a=cnt, b=n0, c=n1
            nms = []
            if a >= 1:
                nms.append(_nm(b))
            if a >= 2:
                nms.append(_nm(c))
            return tl.GlobalStmt(nms)
        if tp == 17:   # ExpressionStmt（裸调用语句）
            return tl.ExpressionStmt(node(a))
        if tp == 20:   # param（仅 def 参数块内）
            return tl.VarRef(_nm(a))
        raise ValueError("未知节点 type %d @槽 %d" % (tp, idx))

    top_no = len(blk_map) - 1  # 顶层 = 最后登记的块
    return block(top_no)


def parse(src_text):
    """纯 tl 前端：src_text → (Python AST 列表, flat AST, token 流, 块表 blks)。"""
    toks, names = run_boot_lex(src_text)
    flat, blks = run_boot_parse(toks)
    return deserialize(flat, blks, names), flat, toks, blks


# ---- AST 结构比较（用于验证） ----
def ast_key(x):
    if isinstance(x, tl.NumLit):
        return ("NumLit", int(x.value))
    if isinstance(x, tl.VarRef):
        return ("VarRef", x.name)
    if isinstance(x, tl.Call):
        return ("Call", x.fn, tuple(ast_key(a) for a in x.args))
    if isinstance(x, tl.TensorLit):
        return ("TensorLit", tuple(int(v) for v in x.values))
    if isinstance(x, tl.ParamLit):
        return ("ParamLit", tuple(x.dims))
    if isinstance(x, tl.LetStmt):
        return ("Let", x.name, ast_key(x.expr))
    if isinstance(x, tl.PrintStmt):
        return ("Print", ast_key(x.expr))
    if isinstance(x, tl.UpdateStmt):
        return ("Update", x.name, x.lr)
    if isinstance(x, tl.ForStmt):
        return ("For", x.var, ast_key(x.iter_expr), tuple(ast_key(s) for s in x.body))
    if isinstance(x, tl.IfStmt):
        return ("If", ast_key(x.cond), tuple(ast_key(s) for s in x.body),
                tuple(ast_key(s) for s in x.body2) if x.body2 else ())
    if isinstance(x, tl.WhileStmt):
        return ("While", ast_key(x.cond), tuple(ast_key(s) for s in x.body))
    if isinstance(x, tl.BreakStmt):
        return ("Break",)
    if isinstance(x, tl.DefStmt):
        return ("Def", x.name, tuple(x.params), tuple(ast_key(s) for s in x.body))
    if isinstance(x, tl.ReturnStmt):
        return ("Return", ast_key(x.expr))
    if isinstance(x, tl.GlobalStmt):
        return ("Global", tuple(x.names))
    if isinstance(x, tl.ExpressionStmt):
        return ("ExprStmt", ast_key(x.expr))
    raise ValueError("未知 AST %r" % (x,))


def asts_equal(a, b):
    return ast_key(a) == ast_key(b)
