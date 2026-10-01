# -*- coding: utf-8 -*-
"""tl v0.14 —— 机器码内核后端 MachineKernels（零 C / 零 LLVM）。

与 tl_native.NativeKernels 同名同语义（逐位一致契约不变），但每个内核的
可执行代码由 tl_emit 的生成器在内存中发射为 x86-64 机器码（VirtualAlloc
RWX + ctypes 直接调用），不再依赖 kernels.dll。

注意：调用参数顺序按各生成器 ABI（tl_emit docstring），与 C 的 tl_* 函数
不尽相同（如 relu 机器码为 (x, out, n) 而非 (x, n, out)）。每方法实现内
按 SIG 布局传参。
"""
import ctypes
from tl_native import Buf
from tl_emit import (MachineKernel, _P, _I, _D,
                     gen_mm2, _gen_sq, _gen_scg, _gen_mm2v, _gen_transpose,
                     _gen_total, _gen_colsum, _gen_softmax, _gen_softmax_grad,
                     _gen_mm2_back, _gen_scaled_mm, _gen_scaled_mm_t,
                     _gen_scaled_mm_back, _gen_scaled_mm_t_back,
                     _gen_affine2, _gen_affine2v, _gen_affine2_back,
                     _gen_affine2v_back, _gen_single_loop,
                     _tl_exp, Enc, _fin, _emit_consts, _neumaier)

_CD = ctypes.c_double


def _gen_exp_test():
    """exp_test(x) → double：xmm0 入出，保护 rbx（_tl_exp 占用）。"""
    e = Enc()
    e.push_r64(3)                       # push rbx
    _tl_exp(e, 0xB)
    e.pop_r64(3)
    e.ret()
    _emit_consts(e)
    return _fin(e)


class _K:
    """惰性构建 + 单例持有 MachineKernel（避免重复发射/分配）。"""
    _cache = {}

    @classmethod
    def get(cls, key, gen, sig):
        if key not in cls._cache:
            cls._cache[key] = MachineKernel(gen(), sig)
        return cls._cache[key]


class MachineKernels:
    """机器码内核全集，接口对齐 NativeKernels。"""

    # ---- 数据转换（与 NativeKernels 相同） ----
    @staticmethod
    def _flat2(a):
        return [x for row in a for x in row]

    @staticmethod
    def _shape(a):
        s = []
        while isinstance(a, list):
            s.append(len(a))
            a = a[0] if a else []
        return tuple(s)

    @staticmethod
    def _flat(a):
        out = []

        def walk(v):
            if isinstance(v, list):
                for i in v:
                    walk(i)
            else:
                out.append(v)
        walk(a)
        return out

    @staticmethod
    def _buf(xs):
        return (_CD * len(xs))(*xs)

    @staticmethod
    def _unflat(vals, shape):
        if len(shape) == 0:
            return vals[0]
        if len(shape) == 1:
            return list(vals)
        n = shape[0]
        step = 1
        for d in shape[1:]:
            step *= d
        return [MachineKernels._unflat(vals[i * step:(i + 1) * step], shape[1:])
                for i in range(n)]

    def _bias_arg(self, bias):
        if isinstance(bias, list):
            if len(bias) > 1:
                return len(bias), self._buf(bias)
            return 0, self._buf([bias[0] if len(bias) else 0.0])
        return 0, self._buf([bias])

    # ---- 内核方法 ----
    def mm2(self, a, b):
        M, K = len(a), len(a[0])
        N = len(b[0])
        A, B = self._buf(self._flat2(a)), self._buf(self._flat2(b))
        out = (_CD * (M * N))()
        _K.get("mm2", gen_mm2, (None, _P, _P, _P, _I, _I, _I)).fn(
            ctypes.addressof(A), ctypes.addressof(B), ctypes.addressof(out),
            M, K, N)
        return self._unflat(out, (M, N))

    def mm2v(self, a, b):
        M, K = len(a), len(a[0])
        A, B = self._buf(self._flat2(a)), self._buf(b)
        out = (_CD * M)()
        _K.get("mm2v", _gen_mm2v, (None, _P, _I, _I, _P, _P)).fn(
            ctypes.addressof(A), M, K, ctypes.addressof(B), ctypes.addressof(out))
        return list(out)

    def mm2_back(self, a, b, g):
        M, K, N = len(a), len(a[0]), len(b[0])
        A, B, G = (self._buf(self._flat2(a)), self._buf(self._flat2(b)),
                   self._buf(self._flat2(g)))
        ga = (_CD * (M * K))()
        gb = (_CD * (K * N))()
        # 与 NativeKernels 相同：转置技巧 (G, M, N, B, K, A)
        _K.get("mm2_back", _gen_mm2_back, (None, _P, _I, _I, _P, _I, _P, _P, _P)).fn(
            ctypes.addressof(G), M, N, ctypes.addressof(B), K,
            ctypes.addressof(A), ctypes.addressof(ga), ctypes.addressof(gb))
        return self._unflat(ga, (M, K)), self._unflat(gb, (K, N))

    def elem2(self, a, b, op):
        n = len(self._flat(a))
        A, B = self._buf(self._flat(a)), self._buf(self._flat(b))
        out = (_CD * n)()
        kind = {0: "add", 1: "sub", 2: "mul"}.get(op, "add")
        _K.get("elem2_" + kind, lambda k=kind: _gen_single_loop(k),
               (None, _P, _P, _P, _I)).fn(
            ctypes.addressof(A), ctypes.addressof(B), ctypes.addressof(out), n)
        return self._unflat(out, self._shape(a))

    def relu(self, a):
        n = len(self._flat(a))
        A = self._buf(self._flat(a))
        out = (_CD * n)()
        _K.get("relu", lambda: _gen_single_loop("relu"), (None, _P, _P, _I)).fn(
            ctypes.addressof(A), ctypes.addressof(out), n)
        return self._unflat(out, self._shape(a))

    def sq(self, a):
        n = len(self._flat(a))
        A = self._buf(self._flat(a))
        out = (_CD * n)()
        _K.get("sq", _gen_sq, (None, _P, _I, _P)).fn(
            ctypes.addressof(A), n, ctypes.addressof(out))
        return self._unflat(out, self._shape(a))

    def scale(self, a, cv):
        n = len(self._flat(a))
        A = self._buf(self._flat(a))
        out = (_CD * n)()
        _K.get("scale", lambda: _gen_single_loop("scale_div"), (None, _P, _P, _I, _D)).fn(
            ctypes.addressof(A), ctypes.addressof(out), n, cv)
        return self._unflat(out, self._shape(a))

    def scg(self, g, cv):
        n = len(self._flat(g))
        G = self._buf(self._flat(g))
        out = (_CD * n)()
        _K.get("scg", _gen_scg, (None, _P, _I, _D, _P)).fn(
            ctypes.addressof(G), n, cv, ctypes.addressof(out))
        return self._unflat(out, self._shape(g))

    def upd(self, v, g, lr):
        n = len(self._flat(v))
        V, G = self._buf(self._flat(v)), self._buf(self._flat(g))
        out = (_CD * n)()
        _K.get("upd", lambda: _gen_single_loop("upd"), (None, _P, _P, _P, _I, _D)).fn(
            ctypes.addressof(V), ctypes.addressof(G), ctypes.addressof(out), n, lr)
        return self._unflat(out, self._shape(v))

    def relu_mask(self, x, g):
        n = len(self._flat(x))
        X, G = self._buf(self._flat(x)), self._buf(self._flat(g))
        out = (_CD * n)()
        _K.get("relu_mask", lambda: _gen_single_loop("relu_mask"),
               (None, _P, _P, _P, _I)).fn(
            ctypes.addressof(X), ctypes.addressof(G), ctypes.addressof(out), n)
        return self._unflat(out, self._shape(x))

    def sqg(self, x, g):
        n = len(self._flat(x))
        X, G = self._buf(self._flat(x)), self._buf(self._flat(g))
        out = (_CD * n)()
        _K.get("sqg", lambda: _gen_single_loop("sqg"), (None, _P, _P, _P, _I)).fn(
            ctypes.addressof(X), ctypes.addressof(G), ctypes.addressof(out), n)
        return self._unflat(out, self._shape(x))

    def softmax(self, a):
        rows, cols = len(a), len(a[0])
        A = self._buf(self._flat2(a))
        out = (_CD * (rows * cols))()
        _K.get("softmax", _gen_softmax, (None, _P, _I, _I, _P)).fn(
            ctypes.addressof(A), rows, cols, ctypes.addressof(out))
        return self._unflat(out, (rows, cols))

    def exp_test(self, x):
        return _K.get("exp_test", _gen_exp_test, (_D, _D)).fn(x)

    def total(self, a):
        if isinstance(a[0], list):
            row_sums = [self.total(row) for row in a]
            A = self._buf(row_sums)
            return _K.get("total", _gen_total, (_D, _P, _I)).fn(
                ctypes.addressof(A), len(row_sums))
        A = self._buf(a)
        return _K.get("total", _gen_total, (_D, _P, _I)).fn(
            ctypes.addressof(A), len(a))

    def softmax_grad(self, s, g):
        rows, cols = len(s), len(s[0])
        S, G = self._buf(self._flat2(s)), self._buf(self._flat2(g))
        out = (_CD * (rows * cols))()
        _K.get("softmax_grad", _gen_softmax_grad, (None, _P, _P, _I, _I, _P)).fn(
            ctypes.addressof(S), ctypes.addressof(G), rows, cols, ctypes.addressof(out))
        return self._unflat(out, (rows, cols))

    def transpose(self, a):
        M, N = len(a), len(a[0])
        A = self._buf(self._flat2(a))
        out = (_CD * (M * N))()
        _K.get("transpose", _gen_transpose, (None, _P, _I, _I, _P)).fn(
            ctypes.addressof(A), M, N, ctypes.addressof(out))
        return self._unflat(out, (N, M))

    def colsum(self, g, ncols):
        M, N = len(g), ncols
        G = self._buf(self._flat2(g))
        out = (_CD * N)()
        _K.get("colsum", _gen_colsum, (None, _P, _I, _I, _P)).fn(
            ctypes.addressof(G), M, N, ctypes.addressof(out))
        return list(out)

    def scaled_mm(self, a, b, cv):
        M, K, N = len(a), len(a[0]), len(b[0])
        A, B = self._buf(self._flat2(a)), self._buf(self._flat2(b))
        out = (_CD * (M * N))()
        _K.get("scaled_mm", _gen_scaled_mm, (None, _P, _I, _I, _P, _I, _D, _P)).fn(
            ctypes.addressof(A), M, K, ctypes.addressof(B), N, cv, ctypes.addressof(out))
        return self._unflat(out, (M, N))

    def scaled_mm_t(self, a, b, cv):
        M, K, N = len(a), len(a[0]), len(b)
        A, B = self._buf(self._flat2(a)), self._buf(self._flat2(b))
        out = (_CD * (M * N))()
        _K.get("scaled_mm_t", _gen_scaled_mm_t, (None, _P, _I, _I, _P, _I, _D, _P)).fn(
            ctypes.addressof(A), M, K, ctypes.addressof(B), N, cv, ctypes.addressof(out))
        return self._unflat(out, (M, N))

    def scaled_mm_back(self, a, b, g, cv):
        M, K, N = len(a), len(a[0]), len(b[0])
        A, B, G = (self._buf(self._flat2(a)), self._buf(self._flat2(b)),
                   self._buf(self._flat2(g)))
        ga = (_CD * (M * K))()
        gb = (_CD * (K * N))()
        mk = _K.get("scaled_mm_back", _gen_scaled_mm_back,
                    (_D, _P, _I, _I, _P, _I, _P, _D, _P, _P))
        dc = mk.fn(ctypes.addressof(A), M, K, ctypes.addressof(B), N,
                   ctypes.addressof(G), cv, ctypes.addressof(ga), ctypes.addressof(gb))
        return self._unflat(ga, (M, K)), self._unflat(gb, (K, N)), dc

    def scaled_mm_t_back(self, a, b, g, cv):
        M, K, N = len(a), len(a[0]), len(b)
        A = self._buf(self._flat2(a))
        B = self._buf(self._flat2(b))
        G = self._buf(self._flat2(g))
        ga = (_CD * (M * K))()
        gb = (_CD * (N * K))()
        mk = _K.get("scaled_mm_t_back", _gen_scaled_mm_t_back,
                    (_D, _P, _I, _I, _P, _I, _P, _D, _P, _P))
        dc = mk.fn(ctypes.addressof(A), M, K, ctypes.addressof(B), N,
                   ctypes.addressof(G), cv, ctypes.addressof(ga), ctypes.addressof(gb))
        return self._unflat(ga, (M, K)), self._unflat(gb, (N, K)), dc

    def affine2(self, a, b, bias, relu_flag):
        M, K, N = len(a), len(a[0]), len(b[0])
        A, B = self._buf(self._flat2(a)), self._buf(self._flat2(b))
        biasn, BUF = self._bias_arg(bias)
        out = (_CD * (M * N))()
        _K.get("affine2", _gen_affine2, (None, _P, _I, _I, _P, _I, _P, _I, _I, _P)).fn(
            ctypes.addressof(A), M, K, ctypes.addressof(B), N,
            ctypes.addressof(BUF), biasn, 1 if relu_flag else 0, ctypes.addressof(out))
        return self._unflat(out, (M, N))

    def affine2v(self, a, b, bias, relu_flag):
        M, K = len(a), len(a[0])
        A, B = self._buf(self._flat2(a)), self._buf(b)
        biasn, BUF = self._bias_arg(bias)
        out = (_CD * M)()
        _K.get("affine2v", _gen_affine2v, (None, _P, _I, _I, _P, _P, _I, _I, _P)).fn(
            ctypes.addressof(A), M, K, ctypes.addressof(B),
            ctypes.addressof(BUF), biasn, 1 if relu_flag else 0, ctypes.addressof(out))
        return list(out)

    def affine2_back(self, a, b, g, bias, relu_flag):
        M, K, N = len(a), len(a[0]), len(b[0])
        A, B, G = (self._buf(self._flat2(a)), self._buf(self._flat2(b)),
                   self._buf(self._flat2(g)))
        biasn, BUF = self._bias_arg(bias)
        ga = (_CD * (M * K))()
        gb = (_CD * (K * N))()
        gb_bias = (_CD * (N if biasn > 0 else 1))()
        _K.get("affine2_back", _gen_affine2_back,
               (None, _P, _I, _I, _P, _I, _P, _P, _I, _I, _P, _P, _P)).fn(
            ctypes.addressof(A), M, K, ctypes.addressof(B), N, ctypes.addressof(G),
            ctypes.addressof(BUF), biasn, 1 if relu_flag else 0,
            ctypes.addressof(ga), ctypes.addressof(gb), ctypes.addressof(gb_bias))
        bb = list(gb_bias) if biasn > 0 else gb_bias[0]
        return self._unflat(ga, (M, K)), self._unflat(gb, (K, N)), bb

    def affine2v_back(self, a, b, g, bias, relu_flag):
        M, K = len(a), len(a[0])
        A, B, G = self._buf(self._flat2(a)), self._buf(b), self._buf(g)
        biasn, BUF = self._bias_arg(bias)
        ga = (_CD * (M * K))()
        gb = (_CD * K)()
        gb_bias = (_CD * (M if biasn > 1 else 1))()
        _K.get("affine2v_back", _gen_affine2v_back,
               (None, _P, _I, _I, _P, _P, _P, _I, _I, _P, _P, _P)).fn(
            ctypes.addressof(A), M, K, ctypes.addressof(B), ctypes.addressof(G),
            ctypes.addressof(BUF), biasn, 1 if relu_flag else 0,
            ctypes.addressof(ga), ctypes.addressof(gb), ctypes.addressof(gb_bias))
        bb = list(gb_bias) if biasn > 1 else gb_bias[0]
        return self._unflat(ga, (M, K)), list(gb), bb


class MachineBufKernels:
    """Buf 版机器码内核：输入 Buf（ptr 直通机器码），输出新 Buf。
    接口对齐 tl_native._BufKernels，内核执行全部走 tl_emit 机器码。"""

    def mm2(self, a, b):
        M, K = a.shape
        N = b.shape[1]
        out = (_CD * (M * N))()
        _K.get("mm2", gen_mm2, (None, _P, _P, _P, _I, _I, _I)).fn(
            ctypes.addressof(a.arr), ctypes.addressof(b.arr), ctypes.addressof(out), M, K, N)
        return Buf(out, (M, N))

    def mm2v(self, a, b):
        M, K = a.shape
        out = (_CD * M)()
        _K.get("mm2v", _gen_mm2v, (None, _P, _I, _I, _P, _P)).fn(
            ctypes.addressof(a.arr), M, K, ctypes.addressof(b.arr), ctypes.addressof(out))
        return Buf(out, (M,))

    def mm2_back(self, a, b, g):
        M, K = a.shape
        N = b.shape[1]
        ga = (_CD * (M * K))()
        gb = (_CD * (K * N))()
        _K.get("mm2_back", _gen_mm2_back, (None, _P, _I, _I, _P, _I, _P, _P, _P)).fn(
            ctypes.addressof(g.arr), M, N, ctypes.addressof(b.arr), K,
            ctypes.addressof(a.arr), ctypes.addressof(ga), ctypes.addressof(gb))
        return Buf(ga, (M, K)), Buf(gb, (K, N))

    def elem2(self, a, b, op):
        out = (_CD * a.n)()
        kind = {0: "add", 1: "sub", 2: "mul"}.get(op, "add")
        _K.get("elem2_" + kind, lambda k=kind: _gen_single_loop(k),
               (None, _P, _P, _P, _I)).fn(
            ctypes.addressof(a.arr), ctypes.addressof(b.arr), ctypes.addressof(out), a.n)
        return Buf(out, a.shape)

    def relu(self, a):
        out = (_CD * a.n)()
        _K.get("relu", lambda: _gen_single_loop("relu"), (None, _P, _P, _I)).fn(
            ctypes.addressof(a.arr), ctypes.addressof(out), a.n)
        return Buf(out, a.shape)

    def sq(self, a):
        out = (_CD * a.n)()
        _K.get("sq", _gen_sq, (None, _P, _I, _P)).fn(
            ctypes.addressof(a.arr), a.n, ctypes.addressof(out))
        return Buf(out, a.shape)

    def scale(self, a, cv):
        out = (_CD * a.n)()
        _K.get("scale", lambda: _gen_single_loop("scale_div"), (None, _P, _P, _I, _D)).fn(
            ctypes.addressof(a.arr), ctypes.addressof(out), a.n, cv)
        return Buf(out, a.shape)

    def scg(self, g, cv):
        out = (_CD * g.n)()
        _K.get("scg", _gen_scg, (None, _P, _I, _D, _P)).fn(
            ctypes.addressof(g.arr), g.n, cv, ctypes.addressof(out))
        return Buf(out, g.shape)

    def upd(self, v, g, lr):
        out = (_CD * v.n)()
        _K.get("upd", lambda: _gen_single_loop("upd"), (None, _P, _P, _P, _I, _D)).fn(
            ctypes.addressof(v.arr), ctypes.addressof(g.arr), ctypes.addressof(out), v.n, lr)
        return Buf(out, v.shape)

    def relu_mask(self, x, g):
        out = (_CD * x.n)()
        _K.get("relu_mask", lambda: _gen_single_loop("relu_mask"),
               (None, _P, _P, _P, _I)).fn(
            ctypes.addressof(x.arr), ctypes.addressof(g.arr), ctypes.addressof(out), x.n)
        return Buf(out, x.shape)

    def sqg(self, x, g):
        out = (_CD * x.n)()
        _K.get("sqg", lambda: _gen_single_loop("sqg"), (None, _P, _P, _P, _I)).fn(
            ctypes.addressof(x.arr), ctypes.addressof(g.arr), ctypes.addressof(out), x.n)
        return Buf(out, x.shape)

    def rows_softmax(self, a):
        rows, cols = a.shape
        out = (_CD * a.n)()
        _K.get("softmax", _gen_softmax, (None, _P, _I, _I, _P)).fn(
            ctypes.addressof(a.arr), rows, cols, ctypes.addressof(out))
        return Buf(out, a.shape)

    def softmax_grad(self, s, g):
        rows, cols = s.shape
        out = (_CD * s.n)()
        _K.get("softmax_grad", _gen_softmax_grad, (None, _P, _P, _I, _I, _P)).fn(
            ctypes.addressof(s.arr), ctypes.addressof(g.arr), rows, cols, ctypes.addressof(out))
        return Buf(out, s.shape)

    def total(self, a):
        if len(a.shape) == 2:
            rows, cols = a.shape
            base = ctypes.addressof(a.arr)
            row_sums = []
            for r in range(rows):
                row_ptr = ctypes.cast(base + r * cols * 8, ctypes.POINTER(_CD))
                row_sums.append(_K.get("total", _gen_total, (_D, _P, _I)).fn(
                    ctypes.cast(row_ptr, ctypes.c_void_p), cols))
            A = (_CD * rows)(*row_sums)
            return _K.get("total", _gen_total, (_D, _P, _I)).fn(
                ctypes.cast(ctypes.byref(A), ctypes.c_void_p), rows)
        return _K.get("total", _gen_total, (_D, _P, _I)).fn(
            ctypes.addressof(a.arr), a.n)

    def transpose(self, a):
        rows, cols = a.shape
        out = (_CD * a.n)()
        _K.get("transpose", _gen_transpose, (None, _P, _I, _I, _P)).fn(
            ctypes.addressof(a.arr), rows, cols, ctypes.addressof(out))
        return Buf(out, (cols, rows))

    def colsum(self, g, ncols):
        rows, cols = g.shape
        out = (_CD * cols)()
        _K.get("colsum", _gen_colsum, (None, _P, _I, _I, _P)).fn(
            ctypes.addressof(g.arr), rows, cols, ctypes.addressof(out))
        return Buf(out, (cols,))

    def scaled_mm(self, a, b, cv):
        M, K = a.shape
        N = b.shape[1]
        out = (_CD * (M * N))()
        _K.get("scaled_mm", _gen_scaled_mm, (None, _P, _I, _I, _P, _I, _D, _P)).fn(
            ctypes.addressof(a.arr), M, K, ctypes.addressof(b.arr), N, cv, ctypes.addressof(out))
        return Buf(out, (M, N))

    def scaled_mm_t(self, a, b, cv):
        M, K = a.shape
        N = b.shape[0]
        out = (_CD * (M * N))()
        _K.get("scaled_mm_t", _gen_scaled_mm_t, (None, _P, _I, _I, _P, _I, _D, _P)).fn(
            ctypes.addressof(a.arr), M, K, ctypes.addressof(b.arr), N, cv, ctypes.addressof(out))
        return Buf(out, (M, N))

    def scaled_mm_back(self, a, b, g, cv):
        M, K = a.shape
        N = b.shape[1]
        ga = (_CD * (M * K))()
        gb = (_CD * (K * N))()
        mk = _K.get("scaled_mm_back", _gen_scaled_mm_back,
                    (_D, _P, _I, _I, _P, _I, _P, _D, _P, _P))
        dc = mk.fn(ctypes.addressof(a.arr), M, K, ctypes.addressof(b.arr), N,
                   ctypes.addressof(g.arr), cv, ctypes.addressof(ga), ctypes.addressof(gb))
        return Buf(ga, (M, K)), Buf(gb, (K, N)), dc

    def scaled_mm_t_back(self, a, b, g, cv):
        M, K = a.shape
        N = b.shape[0]
        ga = (_CD * (M * K))()
        gb = (_CD * (N * K))()
        mk = _K.get("scaled_mm_t_back", _gen_scaled_mm_t_back,
                    (_D, _P, _I, _I, _P, _I, _P, _D, _P, _P))
        dc = mk.fn(ctypes.addressof(a.arr), M, K, ctypes.addressof(b.arr), N,
                   ctypes.addressof(g.arr), cv, ctypes.addressof(ga), ctypes.addressof(gb))
        return Buf(ga, (M, K)), Buf(gb, (N, K)), dc

    def _bias_args(self, bias):
        # 对齐 NativeKernels._bias_arg：标量或单元素 → biasn=0；len>1 → biasn=len。
        # 避免 biasn>=1 时内核按向量读/写越界（affine2 读 bias[n]、back 写 gb_bias[N]）。
        if isinstance(bias, Buf):
            if bias.n > 1:
                return bias.ptr, bias.n
            arr = (_CD * 1)(bias.arr[0] if bias.n else 0.0)
            return ctypes.cast(arr, ctypes.POINTER(_CD)), 0
        if isinstance(bias, list):
            if len(bias) > 1:
                arr = (_CD * len(bias))(*bias)
                return ctypes.cast(arr, ctypes.POINTER(_CD)), len(bias)
            arr = (_CD * 1)(bias[0] if len(bias) else 0.0)
            return ctypes.cast(arr, ctypes.POINTER(_CD)), 0
        arr = (_CD * 1)(bias)
        return ctypes.cast(arr, ctypes.POINTER(_CD)), 0

    def affine2(self, a, b, bias, relu_flag):
        M, K = a.shape
        N = b.shape[1]
        out = (_CD * (M * N))()
        bias_ptr, bias_len = self._bias_args(bias)
        _K.get("affine2", _gen_affine2, (None, _P, _I, _I, _P, _I, _P, _I, _I, _P)).fn(
            ctypes.addressof(a.arr), M, K, ctypes.addressof(b.arr), N,
            bias_ptr, bias_len, int(relu_flag), ctypes.addressof(out))
        return Buf(out, (M, N))

    def affine2v(self, a, b, bias, relu_flag):
        M, K = a.shape
        out = (_CD * M)()
        bias_ptr, bias_len = self._bias_args(bias)
        _K.get("affine2v", _gen_affine2v, (None, _P, _I, _I, _P, _P, _I, _I, _P)).fn(
            ctypes.addressof(a.arr), M, K, ctypes.addressof(b.arr),
            bias_ptr, bias_len, int(relu_flag), ctypes.addressof(out))
        return Buf(out, (M,))

    def affine2_back(self, a, b, g, bias, relu_flag):
        M, K = a.shape
        N = b.shape[1]
        ga = (_CD * (M * K))()
        gb = (_CD * (K * N))()
        bias_ptr, bias_len = self._bias_args(bias)
        gb_bias = (_CD * max(bias_len, 1))()
        _K.get("affine2_back", _gen_affine2_back,
               (None, _P, _I, _I, _P, _I, _P, _P, _I, _I, _P, _P, _P)).fn(
            ctypes.addressof(a.arr), M, K, ctypes.addressof(b.arr), N,
            ctypes.addressof(g.arr), bias_ptr, bias_len, int(relu_flag),
            ctypes.addressof(ga), ctypes.addressof(gb), ctypes.addressof(gb_bias))
        return Buf(ga, (M, K)), Buf(gb, (K, N)), Buf(gb_bias, (max(bias_len, 1),))

    def affine2v_back(self, a, b, g, bias, relu_flag):
        M, K = a.shape
        ga = (_CD * (M * K))()
        gb = (_CD * K)()
        bias_ptr, bias_len = self._bias_args(bias)
        gb_bias = (_CD * M)()
        _K.get("affine2v_back", _gen_affine2v_back,
               (None, _P, _I, _I, _P, _P, _P, _I, _I, _P, _P, _P)).fn(
            ctypes.addressof(a.arr), M, K, ctypes.addressof(b.arr),
            ctypes.addressof(g.arr), bias_ptr, bias_len, int(relu_flag),
            ctypes.addressof(ga), ctypes.addressof(gb), ctypes.addressof(gb_bias))
        if bias_len <= 1:
            return Buf(ga, (M, K)), Buf(gb, (K,)), gb_bias[0]
        return Buf(ga, (M, K)), Buf(gb, (K,)), Buf(gb_bias, (M,))
