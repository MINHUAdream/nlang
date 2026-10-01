# -*- coding: utf-8 -*-
"""tl v0.13 —— tl 内核子集：kernels.tl 解析器 + AST + 参考 VM（语义基准）。
内核用 tl 语言自己写（for/var/下标/标量算术/if），本模块给出参考执行器，
tl_emit.py 把同一 AST 编译为自研 x86-64 机器码（零 C/Rust/LLVM）。
"""
import re

# ---------------- 词法 ----------------
TOKEN_RE = re.compile(r"\s+|(?P<num>\d+(?:\.\d+)?)|(?P<name>[A-Za-z_]\w*)|(?P<op>>=|<=|==|>|<|\+|-|\*|/|=|,|\(|\)|\{|\}|\[|\])")

class Tok:
    __slots__ = ("kind", "val", "pos")
    def __init__(self, kind, val, pos):
        self.kind, self.val, self.pos = kind, val, pos
    def __repr__(self):
        return f"Tok({self.kind},{self.val!r})"

def tokenize(src):
    src = re.sub(r"#[^\n]*", "", src)  # 剥注释
    toks = []
    for m in TOKEN_RE.finditer(src):
        if m.group("num") is not None:
            toks.append(Tok("num", float(m.group("num")), m.start()))
        elif m.group("name") is not None:
            toks.append(Tok("name", m.group("name"), m.start()))
        elif m.group("op") is not None:
            toks.append(Tok("op", m.group("op"), m.start()))
    return toks

# ---------------- AST ----------------
class Kernel:
    def __init__(self, name, params, body):
        self.name, self.params, self.body = name, params, body  # params: [id]
    def __repr__(self):
        return f"Kernel({self.name}, {self.params})"

class For:
    def __init__(self, var, hi, body):
        self.var, self.hi, self.body = var, hi, body
class Var:
    def __init__(self, name, expr):
        self.name, self.expr = name, expr
class Assign:
    def __init__(self, name, idx, expr):
        self.name, self.idx, self.expr = name, idx, expr  # idx None -> 标量 var
class If:
    def __init__(self, cond, then, els):
        self.cond, self.then, self.els = cond, then, els
class Num:
    def __init__(self, v): self.v = v
class Name:
    def __init__(self, n): self.n = n
class Arr:
    def __init__(self, n, i): self.n, self.i = n, i
class Bin:
    def __init__(self, op, l, r): self.op, self.l, self.r = op, l, r
class Neg:
    def __init__(self, e): self.e = e
class Cmp:
    def __init__(self, op, l, r): self.op, self.l, self.r = op, l, r

# ---------------- 解析器 ----------------
class Parser:
    def __init__(self, toks):
        self.t = toks
        self.i = 0
    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else Tok("eof", None, -1)
    def next(self):
        tok = self.peek(); self.i += 1; return tok
    def expect_op(self, op):
        t = self.next()
        assert t.kind == "op" and t.val == op, f"期望 '{op}'，遇到 {t}"
        return t
    def expect_name(self):
        t = self.next()
        assert t.kind == "name", f"期望名字，遇到 {t}"
        return t.val
    def parse_kernel(self):
        assert self.next().val == "kernel"
        name = self.expect_name()
        self.expect_op("(")
        params = []
        while self.peek().val != ")":
            params.append(self.expect_name())
            if self.peek().val == ",":
                self.next()
        self.expect_op(")")
        self.expect_op("{")
        body = self.parse_stmts("}")
        self.expect_op("}")
        return Kernel(name, params, body)
    def parse_stmts(self, end):
        stmts = []
        while self.peek().val != end and self.peek().kind != "eof":
            stmts.append(self.parse_stmt())
        return stmts
    def parse_stmt(self):
        t = self.peek()
        if t.val == "for":
            self.next()
            var = self.expect_name()
            assert self.next().val == "in"
            assert self.next().val == "range"
            self.expect_op("(")
            hi = self.parse_expr()
            self.expect_op(")")
            self.expect_op("{")
            body = self.parse_stmts("}")
            self.expect_op("}")
            return For(var, hi, body)
        if t.val == "var":
            self.next()
            name = self.expect_name()
            self.expect_op("=")
            expr = self.parse_expr()
            return Var(name, expr)
        if t.val == "if":
            self.next()
            cond = self.parse_expr()
            self.expect_op("{")
            then = self.parse_stmts("}")
            self.expect_op("}")
            els = None
            if self.peek().val == "else":
                self.next()
                self.expect_op("{")
                els = self.parse_stmts("}")
                self.expect_op("}")
            return If(cond, then, els)
        # assign
        name = self.expect_name()
        idx = None
        if self.peek().val == "[":
            self.next()
            idx = self.parse_expr()
            self.expect_op("]")
        self.expect_op("=")
        expr = self.parse_expr()
        return Assign(name, idx, expr)
    def parse_expr(self):
        return self.parse_cmp()
    def parse_cmp(self):
        l = self.parse_add()
        while self.peek().kind == "op" and self.peek().val in (">", "<", ">=", "<=", "=="):
            op = self.next().val
            r = self.parse_add()
            l = Cmp(op, l, r)
        return l
    def parse_add(self):
        l = self.parse_mul()
        while self.peek().kind == "op" and self.peek().val in ("+", "-"):
            op = self.next().val
            r = self.parse_mul()
            l = Bin(op, l, r)
        return l
    def parse_mul(self):
        l = self.parse_atom()
        while self.peek().kind == "op" and self.peek().val in ("*", "/"):
            op = self.next().val
            r = self.parse_atom()
            l = Bin(op, l, r)
        return l
    def parse_atom(self):
        t = self.next()
        if t.kind == "num":
            return Num(t.val)
        if t.kind == "name":
            if self.peek().val == "[":
                self.next()
                i = self.parse_expr()
                self.expect_op("]")
                return Arr(t.val, i)
            return Name(t.val)
        if t.val == "(":
            e = self.parse_expr()
            self.expect_op(")")
            return e
        if t.val == "-":
            return Neg(self.parse_atom())
        raise AssertionError(f"意外 token {t}")

def parse(src):
    toks = tokenize(src)
    p = Parser(toks)
    kernels = []
    while p.peek().kind != "eof":
        kernels.append(p.parse_kernel())
    return kernels

# ---------------- 参考 VM（Python 执行 kernels.tl 语义） ----------------
def _eval(e, env):
    if isinstance(e, Num):
        return e.v
    if isinstance(e, Name):
        return env[e.n]
    if isinstance(e, Arr):
        return env[e.n][int(_eval(e.i, env))]
    if isinstance(e, Bin):
        l, r = _eval(e.l, env), _eval(e.r, env)
        if e.op == "+": return l + r
        if e.op == "-": return l - r
        if e.op == "*": return l * r
        if e.op == "/": return l / r
    if isinstance(e, Neg):
        return -_eval(e.e, env)
    if isinstance(e, Cmp):
        l, r = _eval(e.l, env), _eval(e.r, env)
        if e.op == ">": return l > r
        if e.op == "<": return l < r
        if e.op == ">=": return l >= r
        if e.op == "<=": return l <= r
        if e.op == "==": return l == r
    raise AssertionError(f"未知表达式 {e}")

def run_kernel(kern, args):
    """args：与 params 对应的值列表（指针参数传 flat list，int 传 int，double 传 float）。"""
    env = {}
    for name, val in zip(kern.params, args):
        env[name] = val
    _exec_stmts(kern.body, env)
    return env

def _exec_stmts(stmts, env):
    for s in stmts:
        if isinstance(s, For):
            hi = int(_eval(s.hi, env))
            for v in range(hi):
                env[s.var] = v
                _exec_stmts(s.body, env)
        elif isinstance(s, Var):
            env[s.name] = _eval(s.expr, env)
        elif isinstance(s, If):
            if _eval(s.cond, env):
                _exec_stmts(s.then, env)
            elif s.els:
                _exec_stmts(s.els, env)
        elif isinstance(s, Assign):
            val = _eval(s.expr, env)
            if s.idx is None:
                env[s.name] = val
            else:
                env[s.name][int(_eval(s.idx, env))] = val
