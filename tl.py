# -*- coding: utf-8 -*-
"""
tl v0.1 —— 一门"张量一等公民 + 自动微分原生 + 形状编译期检查"的迷你语言原型
=====================================================================
零第三方依赖。四个阶段：
  1. lexer    词法分析
  2. parser   递归下降 -> AST
  3. checker  编译期形状推断（形状不匹配在"编译"时直接报错）
  4. engine   数值执行 + 反向模式自动微分

这对应"新语言重构 LLM"作战地图的【阶段 1 语言核心】的第一块基石：
先把"语言级 AD + 编译期形状检查"做真、做可验证，而不是先搭完整编译器。
"""

import sys
import itertools
import math

# 自研 exp（与 tlb.py / kernels.c 同源）——数值内核全自研，不依赖 libm
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
    2^k 用 ldexp。与 C 内核 tl_exp 同一算法——逐位一致。"""
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

# ---------------------------------------------------------------------------
# 0. 极简 NDArray：张量 = value(嵌套 list) + shape(tuple)
#    不依赖 numpy，自己实现形状工具与朴素矩阵乘
# ---------------------------------------------------------------------------

class Tensor:
    __slots__ = ("value", "shape", "grad", "_backward", "_op", "trainable", "name",
                 "_parents", "_b_a", "_b_b", "_recompute")

    def __init__(self, value, shape, grad=None, _backward=None, _op="", trainable=False, name=""):
        self.value = value            # 嵌套 list
        self.shape = shape            # tuple，如 (2,3)
        self.grad = grad              # 反向传播后累积的梯度（同形状嵌套 list 或 None）
        self._backward = _backward    # 反向闭包：调用后把梯度传给父节点
        self._op = _op
        self.trainable = trainable
        self.name = name
        self._parents = ()            # 计算图父节点
        self._recompute = None        # v0.6 检查点：从父输入重算自己的值

    def zero_grad(self):
        if self.trainable:
            self.grad = zeros_like(self.shape)


def zeros(shape):
    """按形状生成全零嵌套 list。"""
    if len(shape) == 0:
        return 0.0
    if len(shape) == 1:
        return [0.0] * shape[0]
    return [zeros(shape[1:]) for _ in range(shape[0])]


def zeros_like(shape):
    return zeros(shape)


def shape_of(value):
    """从嵌套 list 推断形状。"""
    s = []
    v = value
    while isinstance(v, list):
        s.append(len(v))
        v = v[0]
    return tuple(s)


def elemwise(a, b, f, fba=None, fbb=None):
    """同形状逐元素二元运算；返回结果 Tensor（含对 a/b 的梯度函数）。"""
    if a.shape != b.shape:
        raise ShapeError(f"逐元素运算形状不匹配：{a.shape} vs {b.shape}")

    def rec(va, vb):
        if isinstance(va, list):
            return [rec(x, y) for x, y in zip(va, vb)]
        return f(va, vb)

    out = rec(a.value, b.value)
    t = Tensor(out, a.shape)

    if fba is not None:
        def _b_a():
            def rec2(va, vb, g):
                if isinstance(va, list):
                    return [rec2(x, y, z) for x, y, z in zip(va, vb, g)]
                return fba(va, vb) * g
            return rec2(a.value, b.value, t.grad)
        t._b_a = _b_a
    if fbb is not None:
        def _b_b():
            def rec3(va, vb, g):
                if isinstance(va, list):
                    return [rec3(x, y, z) for x, y, z in zip(va, vb, g)]
                return fbb(va, vb) * g
            return rec3(a.value, b.value, t.grad)
        t._b_b = _b_b
    return t


def matmul2(a, b):
    """朴素矩阵乘：a[M,K] x b[K,N] -> [M,N]（三重循环，原型够用）。"""
    M, K = a.shape
    K2, N = b.shape
    if K != K2:
        raise ShapeError(f"matmul 内维不匹配：{a.shape} 与 {b.shape}")
    out = zeros((M, N))
    for m in range(M):
        for n in range(N):
            s = 0.0
            for k in range(K):
                s += a.value[m][k] * b.value[k][n]
            out[m][n] = s
    return out


def matmul2v(a, b):
    """a[M,K] x b[K] -> [M]。"""
    M, K = a.shape
    (K2,) = b.shape
    if K != K2:
        raise ShapeError(f"matmul 内维不匹配：{a.shape} 与 {b.shape}")
    out = [0.0] * M
    for m in range(M):
        s = 0.0
        for k in range(K):
            s += a.value[m][k] * b.value[k]
        out[m] = s
    return out


# ---------------------------------------------------------------------------
# 1. 词法分析
# ---------------------------------------------------------------------------

class T:
    LET, PRINT, ID, NUM, LPAREN, RPAREN, COMMA, LBRACKET, RBRACKET, ASSIGN, EOF = \
        range(11)
    FOR, IN, IF, ELSE, LBRACE, RBRACE = range(11, 17)
    WHILE, BREAK = range(17, 19)
    DEF, RETURN = range(19, 21)
    GLOBAL = 21
    names = ["LET", "PRINT", "ID", "NUM", "LPAREN", "RPAREN", "COMMA",
             "LBRACKET", "RBRACKET", "ASSIGN", "EOF",
             "FOR", "IN", "IF", "ELSE", "LBRACE", "RBRACE",
             "WHILE", "BREAK", "DEF", "RETURN", "GLOBAL"]


class Token:
    __slots__ = ("kind", "text", "pos")
    def __init__(self, kind, text, pos):
        self.kind, self.text, self.pos = kind, text, pos

    def __repr__(self):
        return f"{T.names[self.kind]}({self.text!r})"


KEYWORDS = {"let": T.LET, "print": T.PRINT, "for": T.FOR, "in": T.IN, "if": T.IF, "else": T.ELSE,
                "while": T.WHILE, "break": T.BREAK, "def": T.DEF, "return": T.RETURN,
                "global": T.GLOBAL}


def _num(text):
    if text[:2] in ("0x", "0X"):
        return int(text, 16)
    return float(text)


def lex(code):
    toks = []
    i, n = 0, len(code)
    while i < n:
        c = code[i]
        if c in " \t\r\n":
            i += 1
        elif c == "#":
            while i < n and code[i] != "\n":
                i += 1
        elif c == "0" and i + 1 < n and code[i + 1] in ("x", "X"):
            # hex literal: 0x56 / 0xFF (machine-code emission)
            j = i + 2
            while j < n and (code[j].isdigit() or code[j] in "abcdefABCDEF"):
                j += 1
            toks.append(Token(T.NUM, code[i:j], i))
            i = j
        elif c.isdigit() or (c == "." and i + 1 < n and code[i + 1].isdigit()):
            j = i
            while j < n and (code[j].isdigit() or code[j] == "."):
                j += 1
            toks.append(Token(T.NUM, code[i:j], i))
            i = j
        elif c == "-" and i + 1 < n and (
                code[i + 1].isdigit()
                or (code[i + 1] == "." and i + 2 < n and code[i + 2].isdigit())):
            # 负数字面量：-5 / -0.5 / -3.14
            j = i + 1
            while j < n and (code[j].isdigit() or code[j] == "."):
                j += 1
            toks.append(Token(T.NUM, code[i:j], i))
            i = j
        elif c.isalpha() or c == "_":
            j = i
            while j < n and (code[j].isalnum() or code[j] == "_"):
                j += 1
            word = code[i:j]
            toks.append(Token(KEYWORDS.get(word, T.ID), word, i))
            i = j
        elif c == "(":
            toks.append(Token(T.LPAREN, c, i)); i += 1
        elif c == ")":
            toks.append(Token(T.RPAREN, c, i)); i += 1
        elif c == ",":
            toks.append(Token(T.COMMA, c, i)); i += 1
        elif c == "[":
            toks.append(Token(T.LBRACKET, c, i)); i += 1
        elif c == "]":
            toks.append(Token(T.RBRACKET, c, i)); i += 1
        elif c == "{":
            toks.append(Token(T.LBRACE, c, i)); i += 1
        elif c == "}":
            toks.append(Token(T.RBRACE, c, i)); i += 1
        elif c == "=":
            toks.append(Token(T.ASSIGN, c, i)); i += 1
        else:
            raise TLError(f"无法识别的字符 '{c}'（位置 {i}）")
    toks.append(Token(T.EOF, "", n))
    return toks


# ---------------------------------------------------------------------------
# 2. 语法分析（递归下降）
# ---------------------------------------------------------------------------

class AST:
    pass


class LetStmt(AST):
    def __init__(self, name, expr):
        self.name, self.expr = name, expr


class PrintStmt(AST):
    def __init__(self, expr):
        self.expr = expr


class UpdateStmt(AST):
    """update(W, 0.01) —— 一步 SGD：重算 forward → 反向 → 更新参数。"""
    def __init__(self, name, lr):
        self.name, self.lr = name, lr


class TensorLit(AST):
    """tensor([1.0, 2.0, ...])"""
    def __init__(self, values):
        self.values = values


class ParamLit(AST):
    """param([2, 3]) —— 可训练参数"""
    def __init__(self, dims):
        self.dims = dims


class VarRef(AST):
    def __init__(self, name):
        self.name = name


class ForStmt(AST):
    """for i in expr { body }——expr 求值为 1D 张量，i 逐次绑定为标量。"""
    def __init__(self, var, iter_expr, body):
        self.var, self.iter_expr, self.body = var, iter_expr, body


class IfStmt(AST):
    """if cond { body } else { body2 }——cond 为标量（非 0 即真）。"""
    def __init__(self, cond, body, body2=None):
        self.cond, self.body, self.body2 = cond, body, body2


class _Break(Exception):
    """while/for 体内的 break 信号：只跳出最近一层循环。"""
    pass


class WhileStmt(AST):
    """while cond { body }——cond 标量非 0 即真。"""
    def __init__(self, cond, body):
        self.cond, self.body = cond, body


class BreakStmt(AST):
    """break——跳出最近一层 while/for。"""
    pass


class _Return(Exception):
    """return 信号：携带返回值，跳出最近一层函数体。"""
    def __init__(self, value):
        self.value = value


class DefStmt(AST):
    """def name(a, b) { body }——函数定义。"""
    def __init__(self, name, params, body):
        self.name, self.params, self.body = name, params, body


class ReturnStmt(AST):
    """return expr——函数返回值。"""
    def __init__(self, expr):
        self.expr = expr


class GlobalStmt(AST):
    """global a b——声明名字写全局（函数内默认写局部帧）。"""
    def __init__(self, names):
        self.names = names


class ExpressionStmt(AST):
    """表达式语句：裸函数调用，执行并丢弃返回值。"""
    def __init__(self, expr):
        self.expr = expr


class NumLit(AST):
    """数字字面量表达式（v0.15：机器码发射的标量参数，如 band(x, 255)）。"""
    def __init__(self, value):
        self.value = value


class Call(AST):
    def __init__(self, fn, args):
        self.fn, self.args = fn, args


class Parser:
    def __init__(self, toks):
        self.toks = toks
        self.pos = 0

    def peek(self):
        return self.toks[self.pos]

    def next(self):
        t = self.toks[self.pos]
        self.pos += 1
        return t

    def expect(self, kind):
        t = self.next()
        if t.kind != kind:
            raise TLError(f"期望 {T.names[kind]}，得到 {T.names[t.kind]}（'{t.text}'，位置 {t.pos}）")
        return t

    def parse(self):
        stmts = []
        while self.peek().kind != T.EOF:
            stmts.append(self.stmt())
        return stmts

    def stmt(self):
        t = self.peek()
        if t.kind == T.LET:
            self.next()
            name = self.expect(T.ID).text
            self.expect(T.ASSIGN)
            e = self.expr()
            return LetStmt(name, e)
        if t.kind == T.PRINT:
            self.next()
            self.expect(T.LPAREN)
            e = self.expr()
            self.expect(T.RPAREN)
            return PrintStmt(e)
        if t.kind == T.FOR:
            self.next()
            var = self.expect(T.ID).text
            self.expect(T.IN)
            it = self.expr()
            self.expect(T.LBRACE)
            body = []
            while self.peek().kind != T.RBRACE:
                body.append(self.stmt())
            self.expect(T.RBRACE)
            return ForStmt(var, it, body)
        if t.kind == T.IF:
            self.next()
            cond = self.expr()
            self.expect(T.LBRACE)
            body = []
            while self.peek().kind != T.RBRACE:
                body.append(self.stmt())
            self.expect(T.RBRACE)
            body2 = None
            if self.peek().kind == T.ELSE:
                self.next()
                self.expect(T.LBRACE)
                body2 = []
                while self.peek().kind != T.RBRACE:
                    body2.append(self.stmt())
                self.expect(T.RBRACE)
            return IfStmt(cond, body, body2)
        if t.kind == T.WHILE:
            self.next()
            cond = self.expr()
            self.expect(T.LBRACE)
            body = []
            while self.peek().kind != T.RBRACE:
                body.append(self.stmt())
            self.expect(T.RBRACE)
            return WhileStmt(cond, body)
        if t.kind == T.BREAK:
            self.next()
            return BreakStmt()
        if t.kind == T.DEF:
            self.next()
            name = self.expect(T.ID).text
            self.expect(T.LPAREN)
            params = []
            if self.peek().kind != T.RPAREN:
                params.append(self.expect(T.ID).text)
                while self.peek().kind == T.COMMA:
                    self.next()
                    params.append(self.expect(T.ID).text)
            self.expect(T.RPAREN)
            self.expect(T.LBRACE)
            body = []
            while self.peek().kind != T.RBRACE:
                body.append(self.stmt())
            self.expect(T.RBRACE)
            return DefStmt(name, params, body)
        if t.kind == T.RETURN:
            self.next()
            e = self.expr()
            return ReturnStmt(e)
        if t.kind == T.GLOBAL:
            self.next()
            names = []
            if self.peek().kind == T.ID:
                names.append(self.expect(T.ID).text)
                while self.peek().kind == T.ID:
                    names.append(self.expect(T.ID).text)
            return GlobalStmt(names)
        if t.kind == T.ID and t.text == "update":
            # update(NAME, LR)
            self.next()
            self.expect(T.LPAREN)
            name = self.expect(T.ID).text
            self.expect(T.COMMA)
            lr = _num(self.expect(T.NUM).text)
            self.expect(T.RPAREN)
            return UpdateStmt(name, lr)
        if t.kind == T.ID and self.pos + 1 < len(self.toks) \
                and self.toks[self.pos + 1].kind == T.LPAREN:
            # 表达式语句：裸函数调用
            self.next()
            self.expect(T.LPAREN)
            args = []
            if self.peek().kind != T.RPAREN:
                args.append(self.expr())
                while self.peek().kind == T.COMMA:
                    self.next()
                    args.append(self.expr())
            self.expect(T.RPAREN)
            return ExpressionStmt(Call(t.text, args))
        raise TLError(f"顶层语句必须以 let / print / update 开头（位置 {t.pos}）")

    def expr(self):
        t = self.peek()
        if t.kind == T.NUM:
            self.next()
            return NumLit(_num(t.text))
        if t.kind == T.ID:
            if t.text == "tensor":
                self.next()
                return self.tensor_lit()
            if t.text == "param":
                self.next()
                return self.param_lit()
            # 下一个 token 是 '(' 则为函数调用，否则为变量引用
            if self.pos + 1 < len(self.toks) and self.toks[self.pos + 1].kind == T.LPAREN:
                self.next()
                self.expect(T.LPAREN)
                args = []
                if self.peek().kind != T.RPAREN:
                    args.append(self.expr())
                    while self.peek().kind == T.COMMA:
                        self.next()
                        args.append(self.expr())
                self.expect(T.RPAREN)
                return Call(t.text, args)
            self.next()
            return VarRef(t.text)
        raise TLError(f"表达式必须以标识符开头（位置 {t.pos}）")

    def tensor_lit(self):
        self.expect(T.LPAREN)
        vals = self.parse_nested()
        self.expect(T.RPAREN)
        return TensorLit(vals)

    def parse_nested(self):
        """递归解析嵌套列表：[] / [a,b] / [[a,b],[c,d]] / 3D+。"""
        self.expect(T.LBRACKET)
        if self.peek().kind == T.LBRACKET:
            items = [self.parse_nested()]
            while self.peek().kind == T.COMMA:
                self.next()
                items.append(self.parse_nested())
        else:
            items = []
            if self.peek().kind != T.RBRACKET:
                items.append(_num(self.expect(T.NUM).text))
                while self.peek().kind == T.COMMA:
                    self.next()
                    items.append(_num(self.expect(T.NUM).text))
        self.expect(T.RBRACKET)
        return items

    def param_lit(self):
        self.expect(T.LPAREN)
        self.expect(T.LBRACKET)
        dims = []
        if self.peek().kind != T.RBRACKET:
            dims.append(int(self.expect(T.NUM).text))
            while self.peek().kind == T.COMMA:
                self.next()
                dims.append(int(self.expect(T.NUM).text))
        self.expect(T.RBRACKET)
        self.expect(T.RPAREN)
        return ParamLit(dims)


# ---------------------------------------------------------------------------
# 3. 编译期形状检查（类型系统雏形：张量形状跟踪）
# ---------------------------------------------------------------------------

class TLEnv:
    def __init__(self):
        self.shapes = {}     # name -> shape tuple
        self.trainable = {}  # name -> bool
        self.funcs = {}      # name -> (params, body)（用户函数）


BINOPS = {"add": ("add", "add"), "sub": ("sub", "sub"), "mul": ("mul", "mul")}


class Checker:
    def __init__(self):
        self.env = TLEnv()

    def check(self, stmts):
        # 第一遍：先收集全部函数定义（支持先调用后定义）
        def collect(s):
            if isinstance(s, DefStmt):
                self.env.funcs[s.name] = (s.params, s.body)
                for b in s.body:
                    collect(b)
            elif isinstance(s, ForStmt):
                for b in s.body:
                    collect(b)
            elif isinstance(s, IfStmt):
                for b in s.body:
                    collect(b)
                if s.body2 is not None:
                    for b in s.body2:
                        collect(b)
            elif isinstance(s, WhileStmt):
                for b in s.body:
                    collect(b)
        for st in stmts:
            collect(st)
        # 第二遍：逐条检查
        for st in stmts:
            self.check_stmt(st)

    def check_stmt(self, st):
        if isinstance(st, LetStmt):
            shape = self.check_expr(st.expr)
            self.env.shapes[st.name] = shape
            self.env.trainable[st.name] = isinstance(st.expr, ParamLit)
        elif isinstance(st, PrintStmt):
            self.check_expr(st.expr)
        elif isinstance(st, UpdateStmt):
            if st.name not in self.env.shapes:
                raise TLError(f"update 目标未定义：'{st.name}'")
            if not self.env.trainable.get(st.name, False):
                raise TLError(f"update 目标必须是可训练参数：'{st.name}'")
            if st.lr <= 0:
                raise TLError(f"学习率必须为正：{st.lr}")
        elif isinstance(st, ForStmt):
            self.env.shapes[st.var] = ()
            for b in st.body:
                self.check_stmt(b)
            self.env.shapes.pop(st.var, None)
        elif isinstance(st, IfStmt):
            self.check_expr(st.cond)
            for b in st.body:
                self.check_stmt(b)
            if st.body2 is not None:
                for b in st.body2:
                    self.check_stmt(b)
        elif isinstance(st, WhileStmt):
            self.check_expr(st.cond)
            for b in st.body:
                self.check_stmt(b)
        elif isinstance(st, BreakStmt):
            pass
        elif isinstance(st, DefStmt):
            for p in st.params:
                self.env.shapes[p] = ()
            self.env.funcs[st.name] = (st.params, st.body)
            for b in st.body:
                self.check_stmt(b)
        elif isinstance(st, ReturnStmt):
            self.check_expr(st.expr)
        elif isinstance(st, GlobalStmt):
            pass
        elif isinstance(st, ExpressionStmt):
            self.check_expr(st.expr)
        else:
            raise TLError(f"未知语句 {st}")

    def check_expr(self, e):
        if isinstance(e, TensorLit):
            if not e.values:
                raise ShapeError("tensor 字面量不能为空")
            return shape_of(e.values)
        if isinstance(e, ParamLit):
            if len(e.dims) not in (1, 2):
                raise ShapeError(f"param 只支持 1D/2D，收到 {e.dims}")
            return tuple(e.dims)
        if isinstance(e, NumLit):
            return ()
        if isinstance(e, VarRef):
            if e.name not in self.env.shapes:
                raise TLError(f"未定义的变量 '{e.name}'")
            return self.env.shapes[e.name]
        if isinstance(e, Call):
            fn, args = e.fn, e.args
            shapes = [self.check_expr(a) for a in args]
            if fn in _SYS_PRIMS:
                if fn == "cat" or fn == "app":
                    d0 = shapes[0][0] if len(shapes[0]) else 0
                    d1 = shapes[1][0] if len(shapes[1]) else 0
                    return (d0 + d1,)
                if fn == "pack32":
                    return (4,)
                if fn == "pack64":
                    return (8,)
                if fn == "mk":
                    return (1,)
                if fn == "range":
                    return (int(shapes[0][0]) if shapes[0] else 0,)
                if fn == "empty":
                    return (0,)
                if fn == "ext_in":
                    return (1,)
                if fn == "dbl64":
                    return (8,)
                if fn == "alloc":
                    return (int(shapes[0][0]) if shapes[0] else 0,)
                if fn == "set1":
                    return shapes[0]
                if fn == "dblbits":
                    return ()
                if fn == "intpart":
                    return ()
                return ()
            if fn in ("add", "sub", "mul"):
                if len(shapes) != 2:
                    raise TLError(f"{fn} 需要两个参数")
                if shapes[0] == shapes[1]:
                    return shapes[0]
                if fn == "mul":
                    raise ShapeError(f"mul 形状不匹配：{shapes[0]} vs {shapes[1]}")
                # add/sub 支持广播：行广播（1D↔2D 尾部匹配）与标量（()/[1]）
                if len(shapes[0]) == 2 and len(shapes[1]) == 1 \
                        and shapes[0][1] == shapes[1][0]:
                    return shapes[0]
                if len(shapes[1]) == 2 and len(shapes[0]) == 1 \
                        and shapes[1][1] == shapes[0][0]:
                    return shapes[1]
                if shapes[1] in ((), (1,)):
                    return shapes[0]
                if shapes[0] in ((), (1,)):
                    return shapes[1]
                raise ShapeError(f"{fn} 形状不匹配：{shapes[0]} vs {shapes[1]}")
            if fn == "matmul":
                if len(shapes) != 2:
                    raise TLError("matmul 需要两个参数")
                a, b = shapes
                if len(a) == 2 and len(b) == 2:
                    if a[1] != b[0]:
                        raise ShapeError(f"matmul 内维不匹配：{a} x {b}")
                    return (a[0], b[1])
                if len(a) == 2 and len(b) == 1:
                    if a[1] != b[0]:
                        raise ShapeError(f"matmul 内维不匹配：{a} x {b}")
                    return (a[0],)
                if len(a) == 3 and len(b) == 3:
                    if a[0] != b[0]:
                        raise ShapeError(f"matmul batch 维不匹配：{a} x {b}")
                    if a[2] != b[1]:
                        raise ShapeError(f"matmul 内维不匹配：{a} x {b}")
                    return (a[0], a[1], b[2])
                raise ShapeError(f"matmul 目前支持 2D x 2D / 2D x 1D / 3D x 3D，收到 {a} x {b}")
            if fn == "relu":
                if len(shapes) != 1:
                    raise TLError("relu 需要一个参数")
                return shapes[0]
            if fn == "sum":
                if len(shapes) != 1:
                    raise TLError("sum 需要一个参数")
                return ()
            if fn == "mean":
                if len(shapes) != 1:
                    raise TLError("mean 需要一个参数")
                return ()
            if fn == "square":
                if len(shapes) != 1:
                    raise TLError("square 需要一个参数")
                return shapes[0]
            if fn == "transpose":
                if len(shapes) != 1 or len(shapes[0]) not in (2, 3):
                    raise ShapeError(f"transpose 目前只支持 2D/3D，收到 {shapes}")
                s = shapes[0]
                return (s[0], s[2], s[1]) if len(s) == 3 else (s[1], s[0])
            if fn == "scale":
                if len(shapes) != 2:
                    raise TLError("scale 需要两个参数：张量、标量")
                if shapes[1] not in ((), (1,)):
                    raise ShapeError(f"scale 的第二参数必须是标量，收到 {shapes[1]}")
                return shapes[0]
            if fn == "softmax":
                if len(shapes) != 1 or len(shapes[0]) not in (1, 2, 3):
                    raise ShapeError(f"softmax 目前只支持 1D/2D/3D，收到 {shapes}")
                return shapes[0]
            # ---- v0.4 融合算子：形状规则 = 展开为等价基础算子组合后检查 ----
            if fn in ("scaled_mm_t", "scaled_mm", "affine", "bias_relu"):
                if fn == "scaled_mm_t":
                    inner = Call("matmul", [args[0], Call("transpose", [args[1]])])
                else:
                    inner = Call("matmul", [args[0], args[1]])
                if fn in ("scaled_mm_t", "scaled_mm"):
                    if shapes[2] not in ((), (1,)):
                        raise ShapeError(f"{fn} 的第三参数必须是标量，收到 {shapes[2]}")
                    return self.check_expr(inner)
                inner = Call("add", [inner, args[2]])
                if fn == "affine":
                    return self.check_expr(inner)
                return self.check_expr(Call("relu", [inner]))
            if fn in self.env.funcs:
                return ()
            raise TLError(f"未知算子 '{fn}'")
        raise TLError(f"未知表达式 {e}")


# ---------------------------------------------------------------------------
# 4. 数值执行 + 反向模式自动微分
# ---------------------------------------------------------------------------



# v0.15 系统原语：张量 DSL -> 机器码发射所需的最小系统能力
# byte/mk/get/len/cat/band/bor/bxor/bshl/bshr/pack32
EXT_INPUTS = []
_SYS_PRIMS = frozenset(("ext_in", "byte", "mk", "get", "len", "cat", "app",
                        "band", "bor", "bxor", "bshl", "bshr", "pack32", "pack64",
                        "dblbits", "intpart", "dbl64",
                        "range", "empty", "get2", "set1", "eq", "ge", "lt", "gt", "le",
                        "div", "mod", "alloc"))

class Engine:
    def __init__(self):
        self.vars = {}
        self.funcs = {}     # name -> (params, body)（用户函数）
        self.frames = []    # 调用帧栈（参数名 -> Tensor）
        self.globals = set()  # global 声明的名字（写全局）
        self.last_loss = None       # 最近定义的标量损失（供 update 反向）
        self._skip_update = False   # exec_update 重算时跳过 update 语句
        # v0.6 内存账本：当前驻留 / 峰值 / 释放池（口径：let 张量，8B/元素）
        # 池模型 = 真实后端的显存 arena：释放字节回池，新分配先复用池，
        # 否则重算会瞬时双驻留（新分配 + 旧释放未发生）虚高峰值。
        self.mem_cur = 0.0
        self.mem_peak = 0.0
        self.mem_pool = 0.0

    # ---------------- v0.6 内存账本 ----------------
    def _bytes(self, t):
        n = 1
        for d in t.shape:
            n *= d
        return n * 8.0

    def _mem_add(self, t):
        b = self._bytes(t)
        take = min(b, self.mem_pool)     # 先复用释放池
        self.mem_pool -= take
        self.mem_cur += b - take
        if self.mem_cur > self.mem_peak:
            self.mem_peak = self.mem_cur

    def _mem_sub(self, t):
        self.mem_cur -= self._bytes(t)
        if self.mem_cur < 0:
            self.mem_cur = 0.0

    def _free(self, name):
        """按编译器规划释放一个 let 张量的值（对象保留，反向需要时由检查点恢复）。"""
        t = self.vars.get(name)
        if t is not None and isinstance(t, Tensor) and t.value is not None:
            self._mem_sub(t)
            self.mem_pool += self._bytes(t)
            t.value = None

    def _free_obj(self, t):
        """对象级释放（backward_ckpt 用前即弃）。"""
        if t.value is not None:
            self._mem_sub(t)
            self.mem_pool += self._bytes(t)
            t.value = None

    def run(self, stmts, quiet=False):
        self.stmts_cache = stmts
        for st in stmts:
            if isinstance(st, LetStmt):
                scope = (self.vars if st.name in self.globals or not self.frames
                         else self.frames[-1])
                old = scope.get(st.name)
                if old is not None and isinstance(old, Tensor) and old.value is not None:
                    self._mem_sub(old)
                t = self.eval(st.expr, st.name)
                scope[st.name] = t
                self._mem_add(t)
                # 跟踪最近定义的标量损失（sum/mean 输出）
                if t.shape == () and t._op in ("sum", "mean"):
                    self.last_loss = t
            elif isinstance(st, ForStmt):
                it = self.eval(st.iter_expr)
                vals = it.value if isinstance(it.value, list) else [it.value]
                for v in vals:
                    self.vars[st.var] = Tensor(v, ())
                    try:
                        self.run(st.body, quiet=True)
                    except _Break:
                        break
            elif isinstance(st, IfStmt):
                cv = self.eval(st.cond)
                cvv = cv.value
                if isinstance(cvv, list):
                    cvv = cvv[0] if len(cvv) else 0.0
                if cvv:
                    self.run(st.body, quiet=True)
                elif st.body2 is not None:
                    self.run(st.body2, quiet=True)
            elif isinstance(st, WhileStmt):
                while True:
                    cv = self.eval(st.cond)
                    cvv = cv.value
                    if isinstance(cvv, list):
                        cvv = cvv[0] if len(cvv) else 0.0
                    if not cvv:
                        break
                    try:
                        self.run(st.body, quiet=True)
                    except _Break:
                        break
            elif isinstance(st, BreakStmt):
                raise _Break()
            elif isinstance(st, DefStmt):
                self.funcs[st.name] = (st.params, st.body)
            elif isinstance(st, ReturnStmt):
                raise _Return(self.eval(st.expr))
            elif isinstance(st, GlobalStmt):
                for nm in st.names:
                    self.globals.add(nm)
            elif isinstance(st, ExpressionStmt):
                self.eval(st.expr)
            elif isinstance(st, PrintStmt):
                t = self.eval(st.expr)
                if not quiet:
                    print(f"  {fmt(t)}  （形状 {t.shape}）")
            elif isinstance(st, UpdateStmt):
                if self._skip_update:
                    continue
                self.exec_update(st.name, st.lr)
            elif isinstance(st, ForStmt):
                self.env.shapes[st.var] = ()
                for b in st.body:
                    self.check_stmt(b)
                self.env.shapes.pop(st.var, None)
            elif isinstance(st, IfStmt):
                self.check_expr(st.cond)
                for b in st.body:
                    self.check_stmt(b)
                if st.body2 is not None:
                    for b in st.body2:
                        self.check_stmt(b)
            else:
                raise TLError(f"未知语句 {st}")

    def run_planned(self, plan, release_set=None, quiet=True):
        """v0.6：按编译器规划执行 forward。
        与 run 的差异：let 按序执行并按 release_map 在 last_use 处释放
        （release_set 命中的名字），且为每个 Call 定义注册检查点重算器。
        """
        let_idx = 0
        for st in plan.fwd:
            if isinstance(st, LetStmt):
                scope = (self.vars if st.name in self.globals or not self.frames
                         else self.frames[-1])
                old = scope.get(st.name)
                if old is not None and isinstance(old, Tensor) and old.value is not None:
                    self._mem_sub(old)
                t = self.eval(st.expr, st.name)
                if isinstance(t, Tensor) and isinstance(st.expr, Call):
                    expr = st.expr
                    obj = t
                    refs = _refs(expr)   # 表达式引用的名字集合（检查点恢复用）

                    def make_recompute(ex, o, rs):
                        def rec():
                            tmp = self.eval(ex)
                            o.value = tmp.value
                        rec.refs = rs
                        return rec
                    t._recompute = make_recompute(expr, t, refs)
                scope[st.name] = t
                self._mem_add(t)
                if t.shape == () and t._op in ("sum", "mean"):
                    self.last_loss = t
                if release_set is not None:
                    for nm in plan.release_map.get(let_idx, []):
                        if nm in release_set:
                            self._free(nm)
                let_idx += 1
            elif isinstance(st, ForStmt):
                it = self.eval(st.iter_expr)
                vals = it.value if isinstance(it.value, list) else [it.value]
                for v in vals:
                    self.vars[st.var] = Tensor(v, ())
                    try:
                        self.run(st.body, quiet=True)
                    except _Break:
                        break
            elif isinstance(st, IfStmt):
                cv = self.eval(st.cond)
                cvv = cv.value
                if isinstance(cvv, list):
                    cvv = cvv[0] if len(cvv) else 0.0
                if cvv:
                    self.run(st.body, quiet=True)
                elif st.body2 is not None:
                    self.run(st.body2, quiet=True)
            elif isinstance(st, WhileStmt):
                while True:
                    cv = self.eval(st.cond)
                    cvv = cv.value
                    if isinstance(cvv, list):
                        cvv = cvv[0] if len(cvv) else 0.0
                    if not cvv:
                        break
                    try:
                        self.run(st.body, quiet=True)
                    except _Break:
                        break
            elif isinstance(st, BreakStmt):
                raise _Break()
            elif isinstance(st, DefStmt):
                self.funcs[st.name] = (st.params, st.body)
            elif isinstance(st, ReturnStmt):
                raise _Return(self.eval(st.expr))
            elif isinstance(st, GlobalStmt):
                for nm in st.names:
                    self.globals.add(nm)
            elif isinstance(st, ExpressionStmt):
                self.eval(st.expr)
            elif isinstance(st, PrintStmt):
                t = self.eval(st.expr)
                if not quiet:
                    print(f"  {fmt(t)}  （形状 {t.shape}）")
            elif isinstance(st, ForStmt):
                self.env.shapes[st.var] = ()
                for b in st.body:
                    self.check_stmt(b)
                self.env.shapes.pop(st.var, None)
            elif isinstance(st, IfStmt):
                self.check_expr(st.cond)
                for b in st.body:
                    self.check_stmt(b)
                if st.body2 is not None:
                    for b in st.body2:
                        self.check_stmt(b)
            else:
                raise TLError(f"未知语句 {st}")

    def exec_update(self, name, lr):
        """一步 SGD（语言内训�语句）：
        1) 复用当前参数重算全程序 forward（跳过 update 语句）
        2) 清零参数梯度 → 对最近损失反向传播
        3) W -= lr * dW
        """
        self._keep = {k: v for k, v in self.vars.items()
                      if isinstance(v, Tensor) and v._op == "param"}
        self._skip_update = True
        try:
            self.run(self.stmts_cache, quiet=True)
        finally:
            self._skip_update = False
            self._keep = None
        for t in self.vars.values():
            if isinstance(t, Tensor) and t.trainable:
                t.grad = zeros_like(t.shape)
        if self.last_loss is None:
            raise TLError("update 之前没有定义损失（sum/mean 标量）")
        backward(self.last_loss)
        t = self.vars[name]

        def upd(v, g):
            if isinstance(v, list):
                return [upd(a, b) for a, b in zip(v, g)]
            return v - lr * g
        t.value = upd(t.value, t.grad)

    def recompute(self, quiet=True):
        """在参数被外部修改后重新执行 forward：同名 param 复用已有对象
        （保留外部注入的 value），其余中间量全部重算。"""
        # 记录当前 param 对象，run 时遇到同名 param 直接复用
        self._keep = {k: v for k, v in self.vars.items()
                      if isinstance(v, Tensor) and v._op == "param"}
        try:
            self.run(self.stmts_cache, quiet=quiet)
        finally:
            self._keep = None

    def keep(self, name, t):
        """run 期间由 eval 调用：是否应复用已有 param。"""
        return getattr(self, "_keep", None) is not None and name in self._keep

    def eval(self, e, name=""):
        if isinstance(e, TensorLit):
            v = list(e.values)
            return Tensor(v, shape_of(v), _op="tensor", name=name)
        if isinstance(e, ParamLit):
            if self.keep(name, e):
                # recompute 模式：复用已注入外部数值的 param 对象
                return self.vars[name]
            v = zeros(tuple(e.dims))
            t = Tensor(v, tuple(e.dims), _op="param", trainable=True, name=name)
            t.grad = zeros_like(t.shape)
            return t
        if isinstance(e, NumLit):
            return Tensor(e.value, ())
        if isinstance(e, VarRef):
            # 函数调用帧优先（参数遮蔽全局）
            for fr in reversed(self.frames):
                if e.name in fr:
                    return fr[e.name]
            if e.name not in self.vars:
                raise TLError(f"未定义的变量 '{e.name}'")
            return self.vars[e.name]
        if isinstance(e, Call):
            return self.call(e, name)
        raise TLError(f"未知表达式 {e}")

    def sys_call(self, fn, ts):
        """系统原语执行：全部返回整数语义的 Tensor（标量 shape=() 或 1D）。"""
        v = [t.value for t in ts]
        if fn == "ext_in":
            arr = EXT_INPUTS[int(v[0])]
            if isinstance(arr, Tensor):
                return arr
            return Tensor(list(arr), (len(arr),))
        if fn == "byte":
            return Tensor(int(v[0]) & 0xFF, ())
        if fn == "mk":
            return Tensor([v[0]], (1,))
        if fn == "get":
            try:
                return Tensor(int(v[0][int(v[1])]), ())
            except IndexError:
                import traceback as _tb
                _tb.print_stack()
                raise TLError("GET-OOB: len=%d idx=%d v0=%r CALLTRACE=%r" % (len(v[0]), int(v[1]), v[0][:20], self._fn_trace[-40:]))
        if fn == "len":
            return Tensor(len(v[0]), ())
        if fn == "cat":
            a, b = v[0], v[1]
            return Tensor(a + b, (len(a) + len(b),))
        if fn == "app":
            a, b = v[0], v[1]
            return Tensor(a + b, (len(a) + len(b),))  # 宿主同 cat（零拷贝是真机优化）
        if fn == "band":
            return Tensor(int(v[0]) & int(v[1]), ())
        if fn == "bor":
            return Tensor(int(v[0]) | int(v[1]), ())
        if fn == "bxor":
            return Tensor(int(v[0]) ^ int(v[1]), ())
        if fn == "bshl":
            return Tensor(int(v[0]) << int(v[1]), ())
        if fn == "bshr":
            return Tensor(int(v[0]) >> int(v[1]), ())
        if fn == "pack32":
            x = int(v[0]) & 0xFFFFFFFF
            return Tensor([(x >> 0) & 0xFF, (x >> 8) & 0xFF,
                           (x >> 16) & 0xFF, (x >> 24) & 0xFF], (4,))
        if fn == "pack64":
            x = int(v[0]) & 0xFFFFFFFFFFFFFFFF
            return Tensor([(x >> i) & 0xFF for i in (0, 8, 16, 24,
                                                     32, 40, 48, 56)], (8,))
        if fn == "range":
            n = int(v[0])
            return Tensor(list(range(n)), (n,))
        if fn == "empty":
            return Tensor([], (0,))
        if fn == "alloc":
            return Tensor([0] * int(v[0]), (int(v[0]),))
        if fn == "get2":
            return Tensor(int(v[0][int(v[1])][int(v[2])]), ())
        if fn == "set1":
            t = v[0]
            data = t.value if hasattr(t, "value") else t
            try:
                _idx = int(v[1])
            except Exception:
                import sys as _s
                _s.stderr.write('SET1-BADIDX v1=%r type=%s\n' % (v[1], type(v[1])))
                _s.stderr.flush()
                raise
            if _idx >= len(data) or _idx < 0:
                import sys as _s
                _s.stderr.write('SET1-OOB len=%d idx=%d v2type=%s\n' % (len(data), _idx, type(v[2])))
                _s.stderr.flush()
            data[_idx] = v[2]
            return Tensor(data, (len(data),))
        if fn == "dblbits":
            import struct as _st
            return Tensor(_st.unpack("<q", _st.pack("<d", float(v[0])))[0], ())
        if fn == "dbl64":
            import struct as _st
            x = _st.unpack("<Q", _st.pack("<d", float(v[0])))[0]
            return Tensor([(x >> i) & 0xFF for i in (0, 8, 16, 24, 32, 40, 48, 56)], (8,))
        if fn == "intpart":
            return Tensor(int(float(v[0])), ())
        if fn == "eq":
            return Tensor(1 if int(v[0]) == int(v[1]) else 0, ())
        if fn == "ge":
            return Tensor(1 if int(v[0]) >= int(v[1]) else 0, ())
        if fn == "lt":
            return Tensor(1 if int(v[0]) < int(v[1]) else 0, ())
        if fn == "gt":
            return Tensor(1 if int(v[0]) > int(v[1]) else 0, ())
        if fn == "le":
            return Tensor(1 if int(v[0]) <= int(v[1]) else 0, ())
        if fn == "div":
            # floor 除法（Python // 语义：-5//3 = -2）
            return Tensor(int(v[0]) // int(v[1]), ())
        if fn == "mod":
            # floor 取模（Python % 语义：-5%3 = 1，非负余数）
            return Tensor(int(v[0]) % int(v[1]), ())
        raise TLError("未知系统原语 '%s'" % fn)

    _fn_trace = []
    def call(self, e, name=""):
        fn, args = e.fn, e.args
        if len(self._fn_trace) < 256:
            self._fn_trace.append(fn)
        ts = [self.eval(a) for a in args]
        if fn in _SYS_PRIMS:
            return self.sys_call(fn, ts)
        if fn in self.funcs:
            params, body = self.funcs[fn]
            if len(params) != len(ts):
                raise TLError(f"函数 {fn} 参数数不匹配：需要 {len(params)}，收到 {len(ts)}")
            self.frames.append(dict(zip(params, ts)))
            try:
                self.run(body, quiet=True)
            except _Return as r:
                return r.value
            finally:
                self.frames.pop()
            raise TLError(f"函数 {fn} 缺 return")

        def accum(parent, contrib):
            """把贡献梯度累加到父节点 grad（非参数节点也接收，用于继续上溯）。"""
            if parent.grad is None:
                parent.grad = contrib.value if isinstance(contrib, Tensor) else contrib
            else:
                if isinstance(contrib, Tensor):
                    contrib = contrib.value
                parent.grad = elemwise(Tensor(parent.grad, parent.shape),
                                       Tensor(contrib, parent.shape),
                                       lambda x, y: x + y).value

        if fn in ("add", "sub", "mul"):
            a, b = ts[0], ts[1]
            if fn == "mul":
                if a.shape != b.shape:
                    raise ShapeError(f"mul 形状不匹配：{a.shape} vs {b.shape}")
                out = elemwise(a, b, lambda x, y: x * y,
                               lambda x, y: y, lambda x, y: x)
                out._op = "mul"
                out._parents = (a, b)
                out.name = name

                def _bw():
                    accum(a, out._b_a())
                    accum(b, out._b_b())
                out._backward = _bw
                return out

            f = (lambda x, y: x + y) if fn == "add" else (lambda x, y: x - y)
            da = 1.0 if fn == "add" else 1.0
            db = 1.0 if fn == "add" else -1.0
            if a.shape == b.shape:
                out = elemwise(a, b, f, lambda x, y: da, lambda x, y: db)
                out._op = fn
                out._parents = (a, b)
                out.name = name

                def _bw1():
                    accum(a, out._b_a())
                    accum(b, out._b_b())
                out._backward = _bw1
                return out
            if len(a.shape) == 2 and len(b.shape) == 1 and a.shape[1] == b.shape[0]:
                # a[M,N] ± b[N]：行广播
                M, N = a.shape
                v = [[f(a.value[m][n], b.value[n]) for n in range(N)] for m in range(M)]
                out = Tensor(v, (M, N), _op=fn, name=name)

                def _bw2():
                    accum(a, Tensor(out.grad, (M, N)))
                    gb = [sum(out.grad[m][n] for m in range(M)) for n in range(N)]
                    accum(b, Tensor(gb, (N,)))
                out._backward = _bw2
                out._parents = (a, b)
                return out
            if len(b.shape) == 2 and len(a.shape) == 1 and b.shape[1] == a.shape[0]:
                # a[N] ± b[M,N]：行广播（对称）
                M, N = b.shape
                v = [[f(a.value[n], b.value[m][n]) for n in range(N)] for m in range(M)]
                out = Tensor(v, (M, N), _op=fn, name=name)

                def _bw3():
                    accum(b, Tensor(out.grad, (M, N)))
                    ga = [sum(out.grad[m][n] for m in range(M)) for n in range(N)]
                    accum(a, Tensor(ga, (N,)))
                out._backward = _bw3
                out._parents = (a, b)
                return out
            if b.shape in ((), (1,)):
                # a ± 标量
                cv = b.value if b.shape == () else b.value[0]

                def bcast(v):
                    if isinstance(v, list):
                        return [bcast(i) for i in v]
                    return f(v, cv)
                out = Tensor(bcast(a.value), a.shape, _op=fn, name=name)

                def _bw4():
                    accum(a, Tensor(out.grad, a.shape))
                out._backward = _bw4
                out._parents = (a, b)
                return out
            if a.shape in ((), (1,)):
                cv = a.value if a.shape == () else a.value[0]

                def bcast2(v):
                    if isinstance(v, list):
                        return [bcast2(i) for i in v]
                    return f(cv, v)
                out = Tensor(bcast2(b.value), b.shape, _op=fn, name=name)

                def _bw5():
                    accum(b, Tensor(out.grad, b.shape))
                out._backward = _bw5
                out._parents = (a, b)
                return out
            raise ShapeError(f"{fn} 形状不匹配：{a.shape} vs {b.shape}")

        if fn in ("scaled_mm_t", "scaled_mm", "affine", "bias_relu"):
            # v0.4 融合算子：单算子执行 + 直接反向（编译器革命第一块真砖）
            return self.fused_call(fn, ts, name)

        if fn == "matmul":
            a, b = ts[0], ts[1]
            if len(a.shape) == 2 and len(b.shape) == 2:
                v = matmul2(a, b)
                out = Tensor(v, (a.shape[0], b.shape[1]), _op="matmul", name=name)

                def _bw():
                    # dA = g @ B^T
                    g = out.grad
                    bt = [[b.value[i][j] for i in range(b.shape[0])] for j in range(b.shape[1])]
                    ga = matmul2(Tensor(g, (a.shape[0], b.shape[1])), Tensor(bt, (b.shape[1], b.shape[0])))
                    # dB = A^T @ g
                    at = [[a.value[i][j] for i in range(a.shape[0])] for j in range(a.shape[1])]
                    gb = matmul2(Tensor(at, (a.shape[1], a.shape[0])), Tensor(out.grad, (a.shape[0], b.shape[1])))
                    accum(a, ga)
                    accum(b, gb)
                out._backward = _bw
                out._parents = (a, b)
                return out
            if len(a.shape) == 2 and len(b.shape) == 1:
                v = matmul2v(a, b)
                out = Tensor(v, (a.shape[0],), _op="matmul", name=name)

                def _bw():
                    # dA = outer(g, B)
                    g = out.grad
                    ga = [[g[m] * b.value[k] for k in range(b.shape[0])] for m in range(a.shape[0])]
                    # dB = A^T @ g
                    gb = [sum(a.value[m][k] * out.grad[m] for m in range(a.shape[0]))
                          for k in range(b.shape[0])]
                    accum(a, Tensor(ga, a.shape))
                    accum(b, Tensor(gb, b.shape))
                out._backward = _bw
                out._parents = (a, b)
                return out
            if len(a.shape) == 3 and len(b.shape) == 3:
                B, M, K = a.shape
                B2, K2, N = b.shape
                if B != B2 or K != K2:
                    raise ShapeError(f"matmul 执行期形状错误：{a.shape} x {b.shape}")
                v = [matmul2(Tensor(a.value[i], (M, K)), Tensor(b.value[i], (K2, N)))
                     for i in range(B)]
                out = Tensor(v, (B, M, N), _op="matmul", name=name)

                def _bw():
                    # 每个 batch 用 2D 规则：dA = g @ Bᵀ；dB = Aᵀ @ g
                    g = out.grad
                    ga_b = []
                    for i in range(B):
                        bt = [[b.value[i][k][n] for k in range(K)] for n in range(N)]
                        ga_b.append(matmul2(Tensor(g[i], (M, N)),
                                            Tensor(bt, (N, K))))
                    gb_b = []
                    for i in range(B):
                        at = [[a.value[i][m][k] for m in range(M)] for k in range(K)]
                        gb_b.append(matmul2(Tensor(at, (K, M)),
                                            Tensor(g[i], (M, N))))
                    accum(a, Tensor(ga_b, (B, M, K)))
                    accum(b, Tensor(gb_b, (B, K, N)))
                out._backward = _bw
                out._parents = (a, b)
                return out
            raise ShapeError(f"matmul 执行期形状错误：{a.shape} x {b.shape}")

        if fn == "relu":
            x = ts[0]

            def relu_rec(v):
                if isinstance(v, list):
                    return [relu_rec(i) for i in v]
                return v if v > 0 else 0.0
            out = Tensor(relu_rec(x.value), x.shape, _op="relu", name=name)

            def _bw():
                def mask(v, g):
                    if isinstance(v, list):
                        return [mask(a, b) for a, b in zip(v, g)]
                    return g if v > 0 else 0.0
                accum(x, Tensor(mask(x.value, out.grad), x.shape))
            out._backward = _bw
            out._parents = (x,)
            return out

        if fn == "sum":
            x = ts[0]

            def total(v):
                if isinstance(v, list):
                    return sum(total(i) for i in v)
                return v
            out = Tensor(total(x.value), (), _op="sum", name=name)

            def _bw():
                def broadcast(v):
                    if isinstance(v, list):
                        return [broadcast(i) for i in v]
                    return out.grad
                accum(x, Tensor(broadcast(x.value), x.shape))
            out._backward = _bw
            out._parents = (x,)
            return out

        if fn == "mean":
            x = ts[0]

            def total2(v):
                if isinstance(v, list):
                    return sum(total2(i) for i in v)
                return v

            def cnt(v):
                if isinstance(v, list):
                    return sum(cnt(i) for i in v)
                return 1
            n = cnt(x.value)
            out = Tensor(total2(x.value) / n, (), _op="mean", name=name)

            def _bw():
                def broadcast(v):
                    if isinstance(v, list):
                        return [broadcast(i) for i in v]
                    return out.grad / n
                accum(x, Tensor(broadcast(x.value), x.shape))
            out._backward = _bw
            out._parents = (x,)
            return out

        if fn == "square":
            x = ts[0]
            out = elemwise(x, x, lambda a, b: a * b)
            out._op = "square"
            out.name = name

            def _bw():
                def sqg(v, g):
                    if isinstance(v, list):
                        return [sqg(a, b) for a, b in zip(v, g)]
                    return 2.0 * v * g
                accum(x, Tensor(sqg(x.value, out.grad), x.shape))
            out._backward = _bw
            out._parents = (x,)
            return out

        if fn == "transpose":
            x = ts[0]
            if len(x.shape) == 3:
                B, M, N = x.shape
                v = [[[x.value[i][m][n] for m in range(M)] for n in range(N)]
                     for i in range(B)]
                out = Tensor(v, (B, N, M), _op="transpose", name=name)

                def _bw():
                    g = out.grad
                    gx = [[[g[i][n][m] for n in range(N)] for m in range(M)]
                          for i in range(B)]
                    accum(x, Tensor(gx, x.shape))
                out._backward = _bw
                out._parents = (x,)
                return out
            M, N = x.shape
            v = [[x.value[i][j] for i in range(M)] for j in range(N)]
            out = Tensor(v, (N, M), _op="transpose", name=name)

            def _bw():
                g = out.grad
                gx = [[g[i][j] for i in range(N)] for j in range(M)]
                accum(x, Tensor(gx, x.shape))
            out._backward = _bw
            out._parents = (x,)
            return out

        if fn == "scale":
            x, c = ts[0], ts[1]
            cv = c.value if c.shape == () else c.value[0]
            out = elemwise(x, x, lambda a, b: a / cv)
            out._op = "scale"
            out.name = name

            def _bw():
                def scg(v, g):
                    if isinstance(v, list):
                        return [scg(a, b) for a, b in zip(v, g)]
                    return g / cv
                accum(x, Tensor(scg(x.value, out.grad), x.shape))
            out._backward = _bw
            out._parents = (x,)
            return out

        if fn == "softmax":
            x = ts[0]

            def row_softmax(row):
                m = max(row)
                ex = [_tl_exp(v - m) for v in row]
                s = sum(ex)
                return [e / s for e in ex]

            def rows_softmax(nested):
                # 递归到最内层：对最后一维做 row softmax（1D/2D/3D 通用）
                if isinstance(nested[0], list):
                    return [rows_softmax(r) for r in nested]
                return row_softmax(nested)

            if x.shape == ():
                raise ShapeError("softmax 需要 1D+ 输入")
            v = rows_softmax(x.value)
            out = Tensor(v, x.shape, _op="softmax", name=name)

            def grad_rows(s, g):
                if isinstance(s[0], list):
                    return [grad_rows(a, b) for a, b in zip(s, g)]
                dot = sum(a * b for a, b in zip(s, g))
                return [si * (gi - dot) for si, gi in zip(s, g)]

            def _bw():
                accum(x, Tensor(grad_rows(out.value, out.grad), x.shape))
            out._backward = _bw
            out._parents = (x,)
            return out

        raise TLError(f"未知算子 '{fn}'")

    def _accum(self, parent, contrib):
        """把贡献梯度累加到父节点 grad（非参数节点也接收，用于继续上溯）。"""
        if parent.grad is None:
            parent.grad = contrib.value if isinstance(contrib, Tensor) else contrib
        else:
            if isinstance(contrib, Tensor):
                contrib = contrib.value
            parent.grad = elemwise(Tensor(parent.grad, parent.shape),
                                   Tensor(contrib, parent.shape),
                                   lambda x, y: x + y).value

    def fused_call(self, fn, ts, name=""):
        """v0.4 融合算子：单算子语义执行 + 直接反向。
        scaled_mm_t(A,B,c) = (A @ Bᵀ) / c        —— 注意力热路径
        scaled_mm(A,B,c)   = (A @ B) / c
        affine(A,B,b)      = (A @ B) + b（b 行广播/标量）
        bias_relu(A,B,b)   = relu((A @ B) + b)
        反向用解析公式直接写（不等价展开，否则失去融合意义）。
        """
        def accum(parent, contrib):
            self._accum(parent, contrib)

        def mm2(a, b):
            return matmul2(a, b)

        def mm2v(a, b):
            return matmul2v(a, b)

        def bval(t):
            return t.value if t.shape == () else t.value[0]

        def bcum(t, vals, shape):
            """把 vals（列表或标量）按 shape 累积给 t。"""
            if shape == ():
                accum(t, Tensor(vals, ()))
            elif shape == (1,):
                accum(t, Tensor([vals], (1,)))
            else:
                accum(t, Tensor(vals, shape))

        # ============ scaled_mm / scaled_mm_t ============
        if fn in ("scaled_mm", "scaled_mm_t"):
            A, B, c = ts
            cv = bval(c)
            if len(A.shape) == 2 and len(B.shape) == 2:
                if fn == "scaled_mm":
                    M, K = A.shape
                    (K2, N) = B.shape
                    Mv = mm2(A, B)
                    outv = [[e / cv for e in row] for row in Mv]
                else:
                    M, K = A.shape
                    N = B.shape[0]
                    Mv = [[sum(A.value[m][k] * B.value[n][k] for k in range(K))
                           for n in range(N)] for m in range(M)]
                    outv = [[e / cv for e in row] for row in Mv]
                out = Tensor(outv, (M, N), _op=fn, name=name)

                def _bw():
                    g = out.grad
                    gc = [[e / cv for e in row] for row in g]
                    if fn == "scaled_mm":
                        bt = [[B.value[i][j] for i in range(K)] for j in range(N)]
                        ga = mm2(Tensor(gc, (M, N)), Tensor(bt, (N, K)))
                        at = [[A.value[i][j] for i in range(M)] for j in range(K)]
                        gb = mm2(Tensor(at, (K, M)), Tensor(gc, (M, N)))
                    else:
                        ga = [[sum(g[m][n] * B.value[n][k] for n in range(N)) / cv
                               for k in range(K)] for m in range(M)]
                        gb = [[sum(g[m][n] * A.value[m][k] for m in range(M)) / cv
                               for k in range(K)] for n in range(N)]
                    accum(A, Tensor(ga, A.shape))
                    accum(B, Tensor(gb, B.shape))
                    dc = -sum(g[m][n] * Mv[m][n]
                              for m in range(M) for n in range(N)) / (cv * cv)
                    bcum(c, dc, c.shape)
                out._backward = _bw
                out._parents = (A, B, c)
                return out
            if len(A.shape) == 3 and len(B.shape) == 3:
                Bd, M, K = A.shape
                if fn == "scaled_mm":
                    (Bd2, K2, N) = B.shape
                    outv = []
                    Mv3 = []
                    for b in range(Bd):
                        mb = mm2(Tensor(A.value[b], (M, K)),
                                 Tensor(B.value[b], (K2, N)))
                        Mv3.append(mb)
                        outv.append([[e / cv for e in row] for row in mb])
                else:
                    N = B.shape[1]
                    outv = []
                    Mv3 = []
                    for b in range(Bd):
                        mb = [[sum(A.value[b][m][k] * B.value[b][n][k]
                                   for k in range(K)) for n in range(N)]
                              for m in range(M)]
                        Mv3.append(mb)
                        outv.append([[e / cv for e in row] for row in mb])
                out = Tensor(outv, (Bd, M, N), _op=fn, name=name)

                def _bw():
                    g = out.grad
                    ga = [[[sum(g[b][m][n] * B.value[b][n][k] for n in range(N)) / cv
                            for k in range(K)] for m in range(M)] for b in range(Bd)]
                    if fn == "scaled_mm":
                        gb = [[[sum(A.value[b][m][k] * g[b][m][n] for m in range(M)) / cv
                                for n in range(N)] for k in range(K)] for b in range(Bd)]
                    else:
                        gb = [[[sum(g[b][m][n] * A.value[b][m][k] for m in range(M)) / cv
                                for n in range(N)] for k in range(K)] for b in range(Bd)]
                    accum(A, Tensor(ga, A.shape))
                    accum(B, Tensor(gb, B.shape))
                    dc = -sum(g[b][m][n] * Mv3[b][m][n]
                              for b in range(Bd) for m in range(M) for n in range(N)) / (cv * cv)
                    bcum(c, dc, c.shape)
                out._backward = _bw
                out._parents = (A, B, c)
                return out
            raise ShapeError(f"{fn} 支持 2D×2D / 3D×3D，收到 {A.shape} x {B.shape}")

        # ============ affine / bias_relu ============
        A, B, b = ts
        # 2D×2D
        if len(A.shape) == 2 and len(B.shape) == 2:
            M, K = A.shape
            (K2, N) = B.shape
            if b.shape == (N,):
                def fwd(mrow):
                    return [s + b.value[n] for n, s in enumerate(mrow)]

                def bias_grad(g):
                    return [sum(g[m][n] for m in range(M)) for n in range(N)]
            else:
                cv = bval(b)

                def fwd(mrow):
                    return [s + cv for s in mrow]

                def bias_grad(g):
                    return sum(g[m][n] for m in range(M) for n in range(N))
            z = [[fwd([sum(A.value[m][k] * B.value[k][n] for k in range(K))
                       for n in range(N)])[n] for n in range(N)]
                 for m in range(M)]
            if fn == "affine":
                out = Tensor(z, (M, N), _op=fn, name=name)

                def _bw():
                    g = out.grad
                    bt = [[B.value[i][j] for i in range(K)] for j in range(N)]
                    ga = mm2(Tensor(g, (M, N)), Tensor(bt, (N, K)))
                    at = [[A.value[i][j] for i in range(M)] for j in range(K)]
                    gb = mm2(Tensor(at, (K, M)), Tensor(g, (M, N)))
                    accum(A, Tensor(ga, A.shape))
                    accum(B, Tensor(gb, B.shape))
                    bcum(b, bias_grad(g), b.shape)
                out._backward = _bw
                out._parents = (A, B, b)
                return out
            outv = [[max(0.0, v) for v in row] for row in z]
            out = Tensor(outv, (M, N), _op=fn, name=name)

            def _bw():
                g2 = [[(gi if zi > 0 else 0.0) for zi, gi in zip(zz, gg)]
                      for zz, gg in zip(z, out.grad)]
                bt = [[B.value[i][j] for i in range(K)] for j in range(N)]
                ga = mm2(Tensor(g2, (M, N)), Tensor(bt, (N, K)))
                at = [[A.value[i][j] for i in range(M)] for j in range(K)]
                gb = mm2(Tensor(at, (K, M)), Tensor(g2, (M, N)))
                accum(A, Tensor(ga, A.shape))
                accum(B, Tensor(gb, B.shape))
                bcum(b, bias_grad(g2), b.shape)
            out._backward = _bw
            out._parents = (A, B, b)
            return out
        # 3D×3D（b 按最后维行广播到每个 batch）
        if len(A.shape) == 3 and len(B.shape) == 3:
            Bd, M, K = A.shape
            (Bd2, K2, N) = B.shape
            if b.shape == (N,):
                def bias_grad3(g):
                    return [sum(g[bb][m][n]
                                for bb in range(Bd) for m in range(M)) for n in range(N)]

                def fwd3(mrow):
                    return [s + b.value[n] for n, s in enumerate(mrow)]
            else:
                cv = bval(b)

                def bias_grad3(g):
                    return sum(g[bb][m][n] for bb in range(Bd) for m in range(M) for n in range(N))

                def fwd3(mrow):
                    return [s + cv for s in mrow]
            z = [[[fwd3([sum(A.value[bb][m][k] * B.value[bb][k][n] for k in range(K))
                        for n in range(N)])[n] for n in range(N)]
                  for m in range(M)] for bb in range(Bd)]
            if fn == "affine":
                out = Tensor(z, (Bd, M, N), _op=fn, name=name)

                def _bw():
                    g = out.grad
                    ga = [[[sum(g[bb][m][n] * B.value[bb][k][n] for n in range(N))
                            for k in range(K)] for m in range(M)] for bb in range(Bd)]
                    gb = [[[sum(A.value[bb][m][k] * g[bb][m][n] for m in range(M))
                            for n in range(N)] for k in range(K)] for bb in range(Bd)]
                    accum(A, Tensor(ga, A.shape))
                    accum(B, Tensor(gb, B.shape))
                    bcum(b, bias_grad3(g), b.shape)
                out._backward = _bw
                out._parents = (A, B, b)
                return out
            outv = [[[max(0.0, v) for v in row] for row in bb] for bb in z]
            out = Tensor(outv, (Bd, M, N), _op=fn, name=name)

            def _bw():
                g2 = [[[gi if zi > 0 else 0.0 for zi, gi in zip(zz, gg)]
                       for zz, gg in zip(bb, out.grad[bdx])]
                      for bdx, bb in enumerate(z)]
                ga = [[[sum(g2[bb][m][n] * B.value[bb][k][n] for n in range(N))
                        for k in range(K)] for m in range(M)] for bb in range(Bd)]
                gb = [[[sum(A.value[bb][m][k] * g2[bb][m][n] for m in range(M))
                        for n in range(N)] for k in range(K)] for bb in range(Bd)]
                accum(A, Tensor(ga, A.shape))
                accum(B, Tensor(gb, B.shape))
                bcum(b, bias_grad3(g2), b.shape)
            out._backward = _bw
            out._parents = (A, B, b)
            return out
        # 2D×1D（b 与结果同长或标量）
        if len(A.shape) == 2 and len(B.shape) == 1:
            M, K = A.shape
            if b.shape == (M,):
                z = [sum(A.value[m][k] * B.value[k] for k in range(K)) + b.value[m]
                     for m in range(M)]

                def bias_grad1(g):
                    return list(g)
            else:
                cv = bval(b)
                z = [sum(A.value[m][k] * B.value[k] for k in range(K)) + cv
                     for m in range(M)]

                def bias_grad1(g):
                    return sum(g)
            if fn == "affine":
                out = Tensor(z, (M,), _op=fn, name=name)

                def _bw():
                    g = out.grad
                    ga = [[g[m] * B.value[k] for k in range(K)] for m in range(M)]
                    gb = [sum(A.value[m][k] * g[m] for m in range(M)) for k in range(K)]
                    accum(A, Tensor(ga, A.shape))
                    accum(B, Tensor(gb, B.shape))
                    bcum(b, bias_grad1(g), b.shape)
                out._backward = _bw
                out._parents = (A, B, b)
                return out
            out = Tensor([max(0.0, v) for v in z], (M,), _op=fn, name=name)

            def _bw():
                g2 = [gi if zi > 0 else 0.0 for zi, gi in zip(z, out.grad)]
                ga = [[g2[m] * B.value[k] for k in range(K)] for m in range(M)]
                gb = [sum(A.value[m][k] * g2[m] for m in range(M)) for k in range(K)]
                accum(A, Tensor(ga, A.shape))
                accum(B, Tensor(gb, B.shape))
                bcum(b, bias_grad1(g2), b.shape)
            out._backward = _bw
            out._parents = (A, B, b)
            return out
        raise ShapeError(f"{fn} 支持 2D×2D / 3D×3D / 2D×1D，收到 {A.shape} x {B.shape}")



def backward(loss):
    """反向传播：从 loss 出发逆拓扑序遍历计算图，依次调用各节点 _backward。

    每个 op 的 _backward 闭包会把上游梯度（self.grad）转成对父节点的梯度
    并累加到父节点的 grad 上。grad 用 0.0 初始化后由闭包累加。
    """
    # 1) 逆拓扑序：DFS 收集节点（先父后子），再倒序
    visited = set()
    order = []

    def dfs(t):
        if id(t) in visited:
            return
        visited.add(id(t))
        for p in t._parents:
            dfs(p)
        order.append(t)

    dfs(loss)
    # 2) 给 loss 置初始梯度 1.0（标量）
    loss.grad = 1.0
    # 3) 逆序调用 _backward
    for t in reversed(order):
        if t._backward is not None:
            t._backward()


def fmt(t):
    """打印张量（标量直接显示数值）。"""
    if t.shape == ():
        return f"{t.value:.6f}"
    return str(t.value)


# ---------------------------------------------------------------------------
# v0.6 检查点反向传播：丢弃的激活用前即弃，按需从父输入重算
# ---------------------------------------------------------------------------
READS_MEM = {"matmul", "scaled_mm_t", "scaled_mm", "affine", "bias_relu",
             "add", "sub", "mul", "relu", "square"}


def _restore(p, eng, dropped_set):
    """递归恢复被丢弃张量的值（先恢复其表达式引用链上被丢弃的名字，再重算自己）。"""
    if p.value is not None:
        return
    refs = getattr(p._recompute, "refs", ())
    for rn in refs:
        robj = eng.vars.get(rn)
        if robj is not None and robj in dropped_set and robj.value is None:
            _restore(robj, eng, dropped_set)
    p._recompute()
    eng._mem_add(p)


def backward_ckpt(loss, eng, dropped_set):
    """检查点模式的反向：逆拓扑序推进，每个反向节点用到的被丢弃激活
    在调用其 _backward 前恢复，用完后按消费者计数立即释放（用前即弃）。
    与 backward(loss) 数值上完全等价（恢复的是同一前向路径的精确值）。
    """
    visited = set()
    order = []

    def dfs(t):
        if id(t) in visited:
            return
        visited.add(id(t))
        for p in t._parents:
            dfs(p)
        order.append(t)

    dfs(loss)
    loss.grad = 1.0
    # 每个被丢弃激活的"反向读值消费者"计数
    counts = {}
    for t in order:
        if t._op in READS_MEM:
            for p in t._parents:
                if p in dropped_set:
                    counts[p] = counts.get(p, 0) + 1
    for t in reversed(order):
        if t._backward is not None:
            for p in t._parents:
                if p in dropped_set and p.value is None and t._op in READS_MEM:
                    _restore(p, eng, dropped_set)
            t._backward()
        for p in t._parents:
            if p in dropped_set:
                counts[p] -= 1
                if counts[p] <= 0:
                    eng._free_obj(p)


# ---------------------------------------------------------------------------
# 顶层入口
# ---------------------------------------------------------------------------

class TLError(Exception):
    pass


class ShapeError(Exception):
    pass


def optimize(ast):
    """图优化（v0.4）：
    1) 算子融合（图重写）：把可融合的算子组合替换成单算子，运行时
       不再创建中间张量——编译器革命的第一块真砖：
         relu(add(matmul(A, B), b))  → bias_relu(A, B, b)
         add(matmul(A, B), b)        → affine(A, B, b)
         scale(matmul(A, transpose(B)), c) → scaled_mm_t(A, B, c)
         scale(matmul(A, B), c)      → scaled_mm(A, B, c)
    2) 常量折叠：纯字面量运算编译期求值成 TensorLit，运行时不再计算。
    自顶向下（preorder）：先匹配完整融合模式，失败才递归子节点，
    保证 bias_relu 不被拆成 affine+relu 两步。
    """
    fused = []

    def match_fuse(expr):
        if not isinstance(expr, Call):
            return None
        # bias_relu：relu(add(matmul(A,B), b))
        if expr.fn == "relu" and isinstance(expr.args[0], Call) \
                and expr.args[0].fn == "add" and len(expr.args[0].args) == 2 \
                and isinstance(expr.args[0].args[0], Call) \
                and expr.args[0].args[0].fn == "matmul":
            mm = expr.args[0].args[0]
            return "bias_relu", [mm.args[0], mm.args[1], expr.args[0].args[1]]
        # affine：add(matmul(A,B), b)
        if expr.fn == "add" and len(expr.args) == 2 \
                and isinstance(expr.args[0], Call) \
                and expr.args[0].fn == "matmul":
            mm = expr.args[0]
            return "affine", [mm.args[0], mm.args[1], expr.args[1]]
        # scaled_mm_t / scaled_mm：scale(matmul(A, transpose(B)), c)
        if expr.fn == "scale" and len(expr.args) == 2 \
                and isinstance(expr.args[0], Call) \
                and expr.args[0].fn == "matmul":
            mm, c = expr.args[0], expr.args[1]
            if len(mm.args) == 2 and isinstance(mm.args[1], Call) \
                    and mm.args[1].fn == "transpose":
                return "scaled_mm_t", [mm.args[0], mm.args[1].args[0], c]
            return "scaled_mm", [mm.args[0], mm.args[1], c]
        return None

    def rewrite(expr):
        if not isinstance(expr, Call):
            return expr
        hit = match_fuse(expr)
        if hit is not None:
            fn, args = hit
            fused.append(f"{fn}({', '.join(a.fn if isinstance(a, Call) else type(a).__name__ for a in args)}) ← 融合")
            return Call(fn, args)
        # 递归子节点 → 常量折叠
        expr.args = [rewrite(a) for a in expr.args]
        if expr.fn in ("add", "sub", "mul", "matmul", "relu", "sum",
                       "mean", "square", "transpose", "scale", "softmax"):
            if all(isinstance(a, TensorLit) for a in expr.args):
                try:
                    eng = Engine()
                    t = eng.eval(expr)
                    return TensorLit(t.value)
                except Exception:
                    pass
        return expr

    new_stmts = []
    for st in ast:
        if isinstance(st, LetStmt):
            new_stmts.append(LetStmt(st.name, rewrite(st.expr)))
        elif isinstance(st, PrintStmt):
            new_stmts.append(PrintStmt(rewrite(st.expr)))
        else:
            new_stmts.append(st)
    return new_stmts, fused


def compile_program(code, do_optimize=False):
    """lex + parse + (optional) optimize + check —— 全部编译期阶段。"""
    toks = lex(code)
    ast = Parser(toks).parse()
    if do_optimize:
        ast, fused = optimize(ast)
    else:
        fused = None
    chk = Checker()
    chk.check(ast)
    return ast, chk, fused


# ---------------------------------------------------------------------------
# v0.5 训练编译器：训练 = 编译目标（新体系）
# ---------------------------------------------------------------------------
#   compile_training(code) → TrainingPlan：
#     - 编译期：融合 / 折叠（复用 optimize）
#     - 内存规划 pass：反向依赖分析 → 激活生命周期 → 峰值内存量化
#     - 训练循环编译：固定 forward 计划 + 每步 backward / update，
#       不再重建 AST / 不再遍历 update 语句 —— 训练从"外部驱动"变成"编译产物"
# ---------------------------------------------------------------------------

def _refs(expr):
    """收集表达式引用的变量名。"""
    out = set()
    if isinstance(expr, VarRef):
        out.add(expr.name)
    elif isinstance(expr, Call):
        for a in expr.args:
            out |= _refs(a)
    return out


def _upd(v, g, lr):
    """一步参数更新：v -= lr * g（递归嵌套）。"""
    if isinstance(v, list):
        return [_upd(a, b, lr) for a, b in zip(v, g)]
    return v - lr * g


def analyze_memory(ast, chk):
    """编译器内存规划 pass（v0.5）：
    1) 反向读值分析：反向传播时，哪些算子的反向需要"读取某张量的值"？
       - 读自己输出的：softmax（grad_rows 用输出值）
       - 读父输入的：matmul / scaled_mm_t / scaled_mm / affine / bias_relu /
         add / sub / mul / relu / square（梯度公式用输入值）
       - 不读值的：sum / mean / transpose / scale（只转发/缩放梯度）
     注意：嵌套表达式（如 square(sub(out,target))）要递归收集 VarRef。
    2) 生命周期与两档量化：
       - 保守规划：只释放"反向不读值"的中间（编译器现在就能做）
       - 检查点理论：反向读值但可从父输入重算的中间 → 丢弃 + 反向重算
         （显存大降、计算增加，留给后端策略；报告候选清单）
    """
    shapes = chk.env.shapes
    trainable = chk.env.trainable
    lets = [st for st in ast if isinstance(st, LetStmt)]
    if not lets:
        return None
    names = [st.name for st in lets]

    def nbytes(nm):
        s = shapes.get(nm)
        if s is None:
            return 0.0
        n = 1
        for d in s:
            n *= d
        return n * 8.0

    def collect_vars(e):
        """递归收集表达式子树中的全部变量引用。"""
        if isinstance(e, VarRef):
            return [e.name]
        if isinstance(e, Call):
            out = []
            for a in e.args:
                out += collect_vars(a)
            return out
        return []

    # 反向"读值"算子与其读取规则
    READS_ALL = {"add", "sub", "mul", "relu", "square", "matmul"}   # 读全部参数
    READS_FIRST2 = {"scaled_mm_t", "scaled_mm"}                     # 读 A、B，不读 scale 常数
    READS_NOFUNC = {"affine", "bias_relu"}                          # 读除激活名外的参数（A、W）
    NO_READ = {"sum", "mean", "transpose", "scale"}                 # 不读值
    keep = set()            # 反向读值 → 保守保留
    softmax_outs = set()

    def walk(e, owner):
        """递归遍历表达式树，按算子语义收集反向读值依赖。"""
        if not isinstance(e, Call):
            return
        if e.fn == "softmax":
            softmax_outs.add(owner)
            keep.add(owner)                      # 反向读自己的输出
        if e.fn in READS_ALL:
            keep.update(collect_vars(e))
        elif e.fn in READS_FIRST2:
            keep.update(set(collect_vars(e)) - set(
                a.name for a in e.args[2:] if isinstance(a, VarRef)))
        elif e.fn in READS_NOFUNC:
            keep.update(collect_vars(e))       # 激活名为字符串，不会命中 VarRef
        for a in e.args:
            if isinstance(a, Call):
                walk(a, owner)

    for st in lets:
        walk(st.expr, st.name)

    last_use = {}
    for i, st in enumerate(lets):
        for r in collect_vars(st.expr):
            last_use[r] = i
    naive = sum(nbytes(nm) for nm in names)

    # 分组：参数 / 输入（tensor 字面量）/ 中间
    params = [nm for nm in names if trainable.get(nm)]

    def is_input_expr(e):
        return isinstance(e, TensorLit) or (isinstance(e, Call) and e.fn == "tensor")
    inputs = [nm for nm in names if not trainable.get(nm) and is_input_expr(
        next(st for st in lets if st.name == nm).expr)]
    middles = [nm for nm in names if nm not in params and nm not in inputs]
    ckpt_cand_set = set(middles) & keep - softmax_outs

    # 释放点：参数全程；反向读值且不检查点的全程；
    # 反向不读值（保守可释放）与检查点候选（丢弃+反向重算）→ 按 last_use 释放
    free_at = {}
    for nm in names:
        if trainable.get(nm) or (nm in keep and nm not in ckpt_cand_set):
            free_at[nm] = 10 ** 9        # 全程存活
        else:
            free_at[nm] = last_use.get(nm, 0)

    # 保守可释放 = 反向不读值（不含检查点候选）
    early = [nm for nm in names
             if free_at[nm] < 10 ** 9 and nm not in ckpt_cand_set]
    planned = naive - sum(nbytes(nm) for nm in early)

    # 检查点理论：保留 = 参数 + 输入 + softmax 输出 + 单块峰值激活（重算时瞬时最大块）
    act_peak = max([nbytes(nm) for nm in middles if nm not in softmax_outs] or [0.0])
    ckpt = (sum(nbytes(nm) for nm in params)
            + sum(nbytes(nm) for nm in inputs)
            + sum(nbytes(nm) for nm in softmax_outs)
            + act_peak)
    return {
        "names": names,
        "naive_bytes": naive,
        "planned_bytes": planned,
        "ckpt_bytes": ckpt,
        "params": params,
        "inputs": inputs,
        "keep_backward": sorted(set(middles) & keep),
        "softmax_outs": sorted(softmax_outs),
        "early_free": sorted(early),
        "ckpt_candidates": sorted(ckpt_cand_set),
        "free_at": free_at,
    }



def analyze_incremental(ast, chk):
    """v0.7 跨 update 增量分析：每个参数的"影响子图"（传递依赖闭包）。

    训练循环采用轮流单参数更新时：未更新的参数值不变 -> 依赖它们的中间
    张量值也不变 -> 可跨步复用（不重算）。每步只需重算"本轮更新参数"
    的影响子图。返回 {参数名: [LetStmt, ...]}（按程序原序）。
    """
    lets = [st for st in ast if isinstance(st, LetStmt)]
    params = [nm for nm, tp in chk.env.trainable.items() if tp]
    dep = {st.name: set(_refs(st.expr)) for st in lets}   # let 的直接引用集
    impact = {}
    for p in params:
        affected = set()
        frontier = {p}
        changed = True
        while changed:
            changed = False
            for st in lets:
                if st.name in affected:
                    continue
                if dep[st.name] & frontier:
                    affected.add(st.name)
                    frontier.add(st.name)
                    changed = True
        impact[p] = [st for st in lets if st.name in affected]  # 保持原序
    return impact




class TrainingPlan:
    """编译后的训练程序：固定 forward 计划 + 内存规划报告 + 编译循环执行。"""

    def __init__(self, ast, chk, fused, mem):
        self.ast = ast
        self.fwd = [st for st in ast if not isinstance(st, UpdateStmt)]
        self.params = [nm for nm, tp in chk.env.trainable.items() if tp]
        self.mem = mem
        self.fused = fused or []
        # v0.6：释放点映射（let 序号 → 该处 last_use 结束的名字）+ 损失名（不可释放）
        lets = [st for st in self.fwd if isinstance(st, LetStmt)]
        self.release_map = {}
        if mem:
            for nm, idx in mem["free_at"].items():
                if idx < 10 ** 9:
                    self.release_map.setdefault(idx, []).append(nm)
        self.loss_names = {st.name for st in lets
                           if isinstance(st.expr, Call) and st.expr.fn in ("sum", "mean")}

        # v0.7：每个参数的增量影响子图（跨 update 复用的依据）
        self.impact_stmts = analyze_incremental(ast, chk)
        # v0.9：形状环境暴露（后端槽位分配用）
        self.shapes = dict(chk.env.shapes)

    def run(self, epochs, lr=0.2, quiet=False, seed=None, mem_strategy="naive"):
        """编译后训练循环，支持三种内存执行策略：
          naive         —— 全保留（v0.5 行为）
          conservative  —— 释放"反向不读值"的中间（编译器证明安全，白拿）
          checkpoint    —— 再丢弃"反向读值但可从父输入重算"的激活，
                           反向按需恢复、用前即弃（真检查点）
        每步 = 固定 forward 计划重算 → 清梯度 → backward(或 backward_ckpt) → 全参数更新。
        """
        import random
        if mem_strategy == "conservative":
            release_set = set(self.mem["early_free"]) - self.loss_names
        elif mem_strategy == "checkpoint":
            release_set = ((set(self.mem["early_free"])
                            | set(self.mem["ckpt_candidates"])) - self.loss_names)
        else:
            release_set = None
        eng = Engine()
        eng.run_planned(self, release_set)
        if seed is not None:
            rnd = random.Random(seed)
            for nm in self.params:
                t = eng.vars[nm]

                def fill(v):
                    if isinstance(v, list):
                        return [fill(i) for i in v]
                    return rnd.uniform(-0.3, 0.3)
                t.value = fill(t.value)
        losses = []
        for _ in range(epochs):
            eng._keep = {k: v for k, v in eng.vars.items()
                         if isinstance(v, Tensor) and v._op == "param"}
            try:
                eng.run_planned(self, release_set)
            finally:
                eng._keep = None
            for t in eng.vars.values():
                if isinstance(t, Tensor) and t.trainable:
                    t.grad = zeros_like(t.shape)
            if eng.last_loss is None:
                raise TLError("训练计划缺少损失（sum/mean 标量）")
            if mem_strategy == "checkpoint" and release_set:
                dropped = {eng.vars[nm] for nm in self.mem["ckpt_candidates"]
                           if nm in eng.vars}
                backward_ckpt(eng.last_loss, eng, dropped)
            else:
                backward(eng.last_loss)
            for nm in self.params:
                t = eng.vars[nm]
                t.value = _upd(t.value, t.grad, lr)
            losses.append(eng.last_loss.value)
        eng.mem_strategy = mem_strategy
        return losses, eng

    def run_incremental(self, epochs, lr=0.2, seed=None, update=None):
        """v0.7 增量训练：每步更新 update 指定参数集（默认全部参数），
        forward 只重算"update 参数的传递影响闭包"（每步相同的静态子图）；
        冻结参数（不在 update 中）的影响闭包在初始 forward 后永久复用——
        编译器静态知道冻结参数不变 -> 依赖它们的中间值永不失效。

        正确性：复用值 == 朴素全量重算值（依赖参数未变 -> 值不变），
        因此与"同样更新序列 + 每步全 forward 重算"的 loss 序列逐位一致。
        反向仍是全图（loss 依赖所有参数），本版不增量反向。
        """
        import random
        if update is None:
            update = self.params
        else:
            update = [p for p in self.params if p in update]
        # 每步重算子图 = update 参数影响并集（静态，与步号无关）
        impact_names = {p: {st.name for st in self.impact_stmts[p]}
                        for p in self.params}
        dirty = set()
        for p in update:
            dirty |= impact_names[p]
        fwd_lets = [st for st in self.fwd if isinstance(st, LetStmt)]
        stmts = [st for st in fwd_lets if st.name in dirty]

        eng = Engine()
        eng.run(self.fwd, quiet=True)
        if seed is not None:
            rnd = random.Random(seed)
            for nm in self.params:
                t = eng.vars[nm]

                def fill(v):
                    if isinstance(v, list):
                        return [fill(i) for i in v]
                    return rnd.uniform(-0.3, 0.3)
                t.value = fill(t.value)
        # 注入后必须全量重算一次 forward：让所有中间基于注入后的参数值
        eng._keep = {k: v for k, v in eng.vars.items()
                     if isinstance(v, Tensor) and v._op == "param"}
        try:
            eng.run(self.fwd, quiet=True)
        finally:
            eng._keep = None

        losses = []
        for _ in range(epochs):
            eng._keep = {k: v for k, v in eng.vars.items()
                         if isinstance(v, Tensor) and v._op == "param"}
            try:
                eng.run(stmts, quiet=True)
            finally:
                eng._keep = None
            for t in eng.vars.values():
                if isinstance(t, Tensor) and t.trainable:
                    t.grad = zeros_like(t.shape)
            backward(eng.last_loss)
            for nm in update:
                t = eng.vars[nm]
                t.value = _upd(t.value, t.grad, lr)
            losses.append(eng.last_loss.value)
        eng.n_fwd_stmts = len(stmts) * epochs
        eng.update_set = update
        return losses, eng


def compile_training(code, do_optimize=True):
    """训练编译器入口：lex + parse + optimize + check + 内存规划 → TrainingPlan。"""
    toks = lex(code)
    ast = Parser(toks).parse()
    fused = None
    if do_optimize:
        ast, fused = optimize(ast)
    chk = Checker()
    chk.check(ast)
    mem = analyze_memory(ast, chk)
    return TrainingPlan(ast, chk, fused, mem)


def run_program(code, quiet=False):
    """compile -> run。返回引擎（可访问各变量与梯度）。"""
    ast, _, _ = compile_program(code)
    eng = Engine()
    eng.run(ast, quiet=quiet)
    return eng


# ---------------------------------------------------------------------------
# v0.8 tl 命令行工具链（语言工程形态：tl 命令直接运行 .tl 文件）
#   python tl.py run   demo.tl          # 编译并执行
#   python tl.py check demo.tl          # 只编译（形状检查 + 优化报告）
#   python tl.py info  transformer_block.tl   # 训练编译报告
#   python tl.py train transformer_block.tl --epochs 24 --mem checkpoint
#   python tl.py train transformer_block.tl --incremental --update W1,b1
# ---------------------------------------------------------------------------
def _fmt_value(v):
    if isinstance(v, list):
        return "[" + ", ".join(_fmt_value(x) for x in v) + "]"
    return "%.6f" % v if isinstance(v, float) else repr(v)


def main(argv=None):
    import argparse
    import io
    import os
    # Shared implementation: expose diagnostics under the invoked command.
    tool = "n" if os.path.basename(sys.argv[0]).lower() in ("n.py", "n.bat", "n") else "tl"
    ap = argparse.ArgumentParser(
        prog=tool,
        description="%s 语言工具链：张量一等公民 + AD 原生 + 训练编译器 + 内存后端 + 增量优化" % tool)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="编译并执行 .tl 程序")
    p_run.add_argument("file")
    p_run.add_argument("--quiet", action="store_true")
    p_check = sub.add_parser("check", help="只编译：形状检查 + 图优化报告")
    p_check.add_argument("file")
    p_build = sub.add_parser("build", help="编译成自研字节码 .tlb（全自研后端 v0.9）")
    p_build.add_argument("file")
    p_build.add_argument("-o", "--output", default=None, help="输出 .tlb 路径（默认同名前缀）")
    p_info = sub.add_parser("info", help="训练编译报告：融合 / 内存规划 / 增量影响")
    p_info.add_argument("file")
    p_train = sub.add_parser("train", help="编译并训练（训练编译器）")
    p_train.add_argument("file")
    p_train.add_argument("--epochs", type=int, default=24)
    p_train.add_argument("--lr", type=float, default=0.2)
    p_train.add_argument("--seed", type=int, default=None)
    p_train.add_argument("--mem", choices=["naive", "conservative", "checkpoint"], default="naive")
    p_train.add_argument("--incremental", action="store_true", help="增量训练（影响子图 + 冻结复用）")
    p_train.add_argument("--update", default=None, help="增量训练只更新的参数，逗号分隔（默认全部）")
    args = ap.parse_args(argv)

    with open(args.file, encoding="utf-8") as f:
        code = f.read()

    if args.cmd == "run" and args.file.endswith(".tlb"):
        import tlb
        prog = tlb.BytecodeProgram.from_text(io.open(args.file, encoding="utf-8").read())
        vm = tlb.BytecodeVM(prog)
        vm.forward()
        print("== %s run: %s（字节码执行）==" % (tool, args.file))
        for s in prog.slots:
            print("  %-8s = %s   形状 %s" % (s.name, _fmt_value(vm.slots[s.id].value),
                                              s.shape))
        return
    if args.cmd == "run":
        eng = run_program(code, quiet=args.quiet)
        print("== %s run: %s ==" % (tool, args.file))
        for nm, v in eng.vars.items():
            print("  %-8s = %s   形状 %s" % (nm, _fmt_value(getattr(v, "value", v)),
                                              getattr(v, "shape", ())))
    elif args.cmd == "check":
        ast, chk, fused = compile_program(code, do_optimize=True)
        params = [nm for nm, tp in chk.env.trainable.items() if tp]
        print("== %s check: %s 编译通过 ==" % (tool, args.file))
        print("  语句数: %d" % len(ast))
        print("  融合: %s" % (fused or "无"))
        print("  参数: %s" % (params or "无"))
        print("  形状环境: %s 个命名张量" % len(chk.env.shapes))
    elif args.cmd == "info":
        plan = compile_training(code)
        m = plan.mem
        print("== %s info: %s 训练编译报告 ==" % (tool, args.file))
        print("  参数: %s" % plan.params)
        print("  融合: %s" % (plan.fused or "无"))
        print("  内存规划: naive %dB / conservative %dB / checkpoint %dB"
              % (m["naive_bytes"], m["planned_bytes"], m["ckpt_bytes"]))
        print("  检查点候选: %s" % m["ckpt_candidates"])
        print("  增量影响（update 参数集 -> 每步重算子图）:")
        for p in plan.params:
            print("    %-4s -> %d 条: %s"
                  % (p, len(plan.impact_stmts[p]),
                     [st.name for st in plan.impact_stmts[p]]))
    elif args.cmd == "build":
        import tlb
        prog, plan = tlb.build_program(code, do_optimize=True)
        # Both historical .tl and the new .n source extension are accepted.
        # splitext avoids producing a malformed name such as `module..tlb`.
        import os
        out = args.output or (os.path.splitext(args.file)[0] + ".tlb")
        with open(out, "w", encoding="utf-8", newline="") as f:
            f.write(prog.to_text())
        print("== %s build: %s -> %s ==" % (tool, args.file, out))
        prog.dump()
        return
    elif args.cmd == "train" and args.file.endswith(".tlb"):
        import tlb
        prog = tlb.BytecodeProgram.from_text(io.open(args.file, encoding="utf-8").read())
        update = None
        if args.update:
            update = [prog.slots[0].id]  # 占位：下面按名字映射
            # 按名字过滤：参数槽 id 由名字映射
            ids = {s.name: s.id for s in prog.slots}
            update = [ids[x.strip()] for x in args.update.split(",")]
        vm = tlb.BytecodeVM(prog)
        losses = vm.run(args.epochs, lr=args.lr, seed=args.seed, update=update)
        print("== %s train (bytecode): %s ==" % (tool, args.file))
        print("  loss: 首 %.9f → 末 %.9f" % (losses[0], losses[-1]))
        step = max(1, args.epochs // 8)
        seq = ", ".join("%.6f" % losses[i] for i in range(0, args.epochs, step))
        print("  loss 序列: %s" % seq)
        return
    elif args.cmd == "train":
        plan = compile_training(code)
        if args.incremental:
            update = None
            if args.update:
                update = [x.strip() for x in args.update.split(",")]
            losses, eng = plan.run_incremental(args.epochs, lr=args.lr,
                                               seed=args.seed, update=update)
            print("== %s train (incremental, update=%s): %s =="
                  % (tool, update or "all", args.file))
            print("  loss: 首 %.9f → 末 %.9f" % (losses[0], losses[-1]))
            print("  前向语句量: %d" % eng.n_fwd_stmts)
        else:
            losses, eng = plan.run(args.epochs, lr=args.lr, seed=args.seed,
                                   mem_strategy=args.mem)
            print("== %s train (mem=%s): %s ==" % (tool, args.mem, args.file))
            print("  loss: 首 %.9f → 末 %.9f" % (losses[0], losses[-1]))
            print("  峰值显存: %sB" % getattr(eng, "mem_peak", "n/a"))
        step = max(1, args.epochs // 8)
        seq = ", ".join("%.6f" % losses[i] for i in range(0, args.epochs, step))
        print("  loss 序列: %s" % seq)


if __name__ == "__main__":
    main()
