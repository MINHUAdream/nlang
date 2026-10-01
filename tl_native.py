# -*- coding: utf-8 -*-
"""tl v0.11 —— 原生内核后端：ctypes 加载自研 kernels.dll，Python VM 只留调度。

NativeKernels 的方法与 tlb.py 的 Python 内核一一对应（同名同语义），
逐位一致契约：C 内核复刻 Python 的累加方式（朴素 s+= vs Neumaier sum()）。
上层（VM kernel 闭包 / _fwd_op / _back_op）通过 tlb 的 native 优先包装自动加速。
"""
import ctypes

_CD = ctypes.c_double


class NativeKernels:
    def __init__(self, dll_path):
        self.dll = ctypes.CDLL(dll_path)
        d = self.dll
        # ---- 签名声明 ----
        d.tl_mm2.argtypes = [ctypes.POINTER(_CD), ctypes.c_int, ctypes.c_int,
                             ctypes.POINTER(_CD), ctypes.c_int, ctypes.POINTER(_CD)]
        d.tl_mm2v.argtypes = [ctypes.POINTER(_CD), ctypes.c_int, ctypes.c_int, ctypes.POINTER(_CD), ctypes.POINTER(_CD)]
        d.tl_mm2_back.argtypes = [ctypes.POINTER(_CD), ctypes.c_int, ctypes.c_int,
                                  ctypes.POINTER(_CD), ctypes.c_int, ctypes.POINTER(_CD), ctypes.POINTER(_CD), ctypes.POINTER(_CD)]
        d.tl_elem2.argtypes = [ctypes.POINTER(_CD), ctypes.POINTER(_CD), ctypes.c_int, ctypes.c_int, ctypes.POINTER(_CD)]
        d.tl_relu.argtypes = [ctypes.POINTER(_CD), ctypes.c_int, ctypes.POINTER(_CD)]
        d.tl_sq.argtypes = [ctypes.POINTER(_CD), ctypes.c_int, ctypes.POINTER(_CD)]
        d.tl_scale.argtypes = [ctypes.POINTER(_CD), ctypes.c_int, _CD, ctypes.POINTER(_CD)]
        d.tl_scg.argtypes = [ctypes.POINTER(_CD), ctypes.c_int, _CD, ctypes.POINTER(_CD)]
        d.tl_upd.argtypes = [ctypes.POINTER(_CD), ctypes.POINTER(_CD), ctypes.c_int, _CD, ctypes.POINTER(_CD)]
        d.tl_relu_mask.argtypes = [ctypes.POINTER(_CD), ctypes.POINTER(_CD), ctypes.c_int, ctypes.POINTER(_CD)]
        d.tl_sqg.argtypes = [ctypes.POINTER(_CD), ctypes.POINTER(_CD), ctypes.c_int, ctypes.POINTER(_CD)]
        d.tl_softmax.argtypes = [ctypes.POINTER(_CD), ctypes.c_int, ctypes.c_int, ctypes.POINTER(_CD)]
        d.tl_total.restype = _CD
        d.tl_total.argtypes = [ctypes.POINTER(_CD), ctypes.c_int]
        d.tl_exp_test.restype = _CD
        d.tl_exp_test.argtypes = [_CD]
        d.tl_softmax_grad.argtypes = [ctypes.POINTER(_CD), ctypes.POINTER(_CD), ctypes.c_int, ctypes.c_int, ctypes.POINTER(_CD)]
        d.tl_transpose.argtypes = [ctypes.POINTER(_CD), ctypes.c_int, ctypes.c_int, ctypes.POINTER(_CD)]
        d.tl_colsum.argtypes = [ctypes.POINTER(_CD), ctypes.c_int, ctypes.c_int, ctypes.POINTER(_CD)]
        d.tl_scaled_mm.argtypes = [ctypes.POINTER(_CD), ctypes.c_int, ctypes.c_int,
                                  ctypes.POINTER(_CD), ctypes.c_int, _CD, ctypes.POINTER(_CD)]
        d.tl_scaled_mm_t.argtypes = [ctypes.POINTER(_CD), ctypes.c_int, ctypes.c_int,
                                     ctypes.POINTER(_CD), ctypes.c_int, _CD, ctypes.POINTER(_CD)]
        d.tl_scaled_mm_back.restype = _CD
        d.tl_scaled_mm_back.argtypes = [ctypes.POINTER(_CD), ctypes.c_int, ctypes.c_int,
                                        ctypes.POINTER(_CD), ctypes.c_int, ctypes.POINTER(_CD), _CD,
                                        ctypes.POINTER(_CD), ctypes.POINTER(_CD)]
        d.tl_scaled_mm_t_back.restype = _CD
        d.tl_scaled_mm_t_back.argtypes = [ctypes.POINTER(_CD), ctypes.c_int, ctypes.c_int,
                                          ctypes.POINTER(_CD), ctypes.c_int, ctypes.POINTER(_CD), _CD,
                                          ctypes.POINTER(_CD), ctypes.POINTER(_CD)]
        d.tl_affine2.argtypes = [ctypes.POINTER(_CD), ctypes.c_int, ctypes.c_int,
                                 ctypes.POINTER(_CD), ctypes.c_int, ctypes.POINTER(_CD), ctypes.c_int,
                                 ctypes.c_int, ctypes.POINTER(_CD)]
        d.tl_affine2v.argtypes = [ctypes.POINTER(_CD), ctypes.c_int, ctypes.c_int,
                                  ctypes.POINTER(_CD), ctypes.POINTER(_CD), ctypes.c_int, ctypes.c_int, ctypes.POINTER(_CD)]
        d.tl_affine2_back.argtypes = [ctypes.POINTER(_CD), ctypes.c_int, ctypes.c_int,
                                      ctypes.POINTER(_CD), ctypes.c_int, ctypes.POINTER(_CD), ctypes.POINTER(_CD),
                                      ctypes.c_int, ctypes.c_int, ctypes.POINTER(_CD), ctypes.POINTER(_CD), ctypes.POINTER(_CD)]
        d.tl_affine2v_back.argtypes = [ctypes.POINTER(_CD), ctypes.c_int, ctypes.c_int,
                                       ctypes.POINTER(_CD), ctypes.POINTER(_CD), ctypes.POINTER(_CD), ctypes.c_int,
                                       ctypes.c_int, ctypes.POINTER(_CD), ctypes.POINTER(_CD), ctypes.POINTER(_CD)]

    # ---------------- 数据转换 ----------------
    @staticmethod
    def _flat2(a):
        """2D 嵌套 list -> 展平列表。"""
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
        """任意维嵌套 -> 行优先展平（深度优先从左到右，与 Python 递归一致）。"""
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
        """按形状回填嵌套 list。"""
        if len(shape) == 0:
            return vals[0]
        if len(shape) == 1:
            return list(vals)
        n = shape[0]
        step = 1
        for d in shape[1:]:
            step *= d
        return [NativeKernels._unflat(vals[i * step:(i + 1) * step], shape[1:])
                for i in range(n)]

    # ---------------- 内核方法（与 tlb 模块函数同名同语义） ----------------
    def mm2(self, a, b):
        M, K = len(a), len(a[0])
        N = len(b[0])
        A, B = self._buf(self._flat2(a)), self._buf(self._flat2(b))
        out = (_CD * (M * N))()
        self.dll.tl_mm2(A, M, K, B, N, out)
        return self._unflat(out, (M, N))

    def mm2v(self, a, b):
        M, K = len(a), len(a[0])
        A, B = self._buf(self._flat2(a)), self._buf(b)
        out = (_CD * M)()
        self.dll.tl_mm2v(A, M, K, B, out)
        return list(out)

    def mm2_back(self, a, b, g):
        M, K, N = len(a), len(a[0]), len(b[0])
        A, B, G = (self._buf(self._flat2(a)), self._buf(self._flat2(b)),
                   self._buf(self._flat2(g)))
        ga = (_CD * (M * K))()
        gb = (_CD * (K * N))()
        self.dll.tl_mm2_back(G, M, N, B, K, A, ga, gb)
        return self._unflat(ga, (M, K)), self._unflat(gb, (K, N))

    def elem2(self, a, b, op):
        n = len(self._flat(a))
        A, B = self._buf(self._flat(a)), self._buf(self._flat(b))
        out = (_CD * n)()
        self.dll.tl_elem2(A, B, n, op, out)
        return self._unflat(out, _shape(a))

    def relu(self, a):
        n = len(self._flat(a))
        A = self._buf(self._flat(a))
        out = (_CD * n)()
        self.dll.tl_relu(A, n, out)
        return self._unflat(out, _shape(a))

    def sq(self, a):
        n = len(self._flat(a))
        A = self._buf(self._flat(a))
        out = (_CD * n)()
        self.dll.tl_sq(A, n, out)
        return self._unflat(out, _shape(a))

    def scale(self, a, cv):
        n = len(self._flat(a))
        A = self._buf(self._flat(a))
        out = (_CD * n)()
        self.dll.tl_scale(A, n, cv, out)
        return self._unflat(out, _shape(a))

    def scg(self, g, cv):
        n = len(self._flat(g))
        G = self._buf(self._flat(g))
        out = (_CD * n)()
        self.dll.tl_scg(G, n, cv, out)
        return self._unflat(out, _shape(g))

    def upd(self, v, g, lr):
        n = len(self._flat(v))
        V, G = self._buf(self._flat(v)), self._buf(self._flat(g))
        out = (_CD * n)()
        self.dll.tl_upd(V, G, n, lr, out)
        return self._unflat(out, _shape(v))

    def relu_mask(self, x, g):
        n = len(self._flat(x))
        X, G = self._buf(self._flat(x)), self._buf(self._flat(g))
        out = (_CD * n)()
        self.dll.tl_relu_mask(X, G, n, out)
        return self._unflat(out, _shape(x))

    def sqg(self, x, g):
        n = len(self._flat(x))
        X, G = self._buf(self._flat(x)), self._buf(self._flat(g))
        out = (_CD * n)()
        self.dll.tl_sqg(X, G, n, out)
        return self._unflat(out, _shape(x))

    def softmax(self, a):
        """2D 行 softmax（3D 由 tlb 递归调本方法）。"""
        rows, cols = len(a), len(a[0])
        A = self._buf(self._flat2(a))
        out = (_CD * (rows * cols))()
        self.dll.tl_softmax(A, rows, cols, out)
        return self._unflat(out, (rows, cols))

    def exp_test(self, x):
        """自研 exp（C 侧）——与 tlb._tl_exp 逐位一致的验证入口。"""
        return self.dll.tl_exp_test(x)

    def total(self, a):
        """嵌套分组求和：与 Python `sum(_total(i) for i in v)` 一致——
        先每行 Neumaier，再对行和 Neumaier（Neumaier 不结合，分组必须一致）。"""
        if isinstance(a[0], list):
            row_sums = [self.total(row) for row in a]
            A = self._buf(row_sums)
            return self.dll.tl_total(A, len(row_sums))
        A = self._buf(a)
        return self.dll.tl_total(A, len(a))

    def softmax_grad(self, s, g):
        rows, cols = len(s), len(s[0])
        S, G = self._buf(self._flat2(s)), self._buf(self._flat2(g))
        out = (_CD * (rows * cols))()
        self.dll.tl_softmax_grad(S, G, rows, cols, out)
        return self._unflat(out, (rows, cols))

    def transpose(self, a):
        M, N = len(a), len(a[0])
        A = self._buf(self._flat2(a))
        out = (_CD * (M * N))()
        self.dll.tl_transpose(A, M, N, out)
        return self._unflat(out, (N, M))

    def colsum(self, g, ncols):
        M, N = len(g), ncols
        G = self._buf(self._flat2(g))
        out = (_CD * N)()
        self.dll.tl_colsum(G, M, N, out)
        return list(out)

    def scaled_mm(self, a, b, cv):
        M, K, N = len(a), len(a[0]), len(b[0])
        A, B = self._buf(self._flat2(a)), self._buf(self._flat2(b))
        out = (_CD * (M * N))()
        self.dll.tl_scaled_mm(A, M, K, B, N, cv, out)
        return self._unflat(out, (M, N))

    def scaled_mm_t(self, a, b, cv):
        M, K, N = len(a), len(a[0]), len(b)
        A, B = self._buf(self._flat2(a)), self._buf(self._flat2(b))
        out = (_CD * (M * N))()
        self.dll.tl_scaled_mm_t(A, M, K, B, N, cv, out)
        return self._unflat(out, (M, N))

    def scaled_mm_back(self, a, b, g, cv):
        M, K, N = len(a), len(a[0]), len(b[0])
        A, B, G = (self._buf(self._flat2(a)), self._buf(self._flat2(b)),
                   self._buf(self._flat2(g)))
        ga = (_CD * (M * K))()
        gb = (_CD * (K * N))()
        dc = self.dll.tl_scaled_mm_back(A, M, K, B, N, G, cv, ga, gb)
        return self._unflat(ga, (M, K)), self._unflat(gb, (K, N)), dc

    def scaled_mm_t_back(self, a, b, g, cv):
        M, K, N = len(a), len(a[0]), len(b)
        A = self._buf(self._flat2(a))
        B = self._buf(self._flat2(b))
        G = self._buf(self._flat2(g))
        ga = (_CD * (M * K))()
        gb = (_CD * (N * K))()
        dc = self.dll.tl_scaled_mm_t_back(A, M, K, B, N, G, cv, ga, gb)
        return self._unflat(ga, (M, K)), self._unflat(gb, (N, K)), dc

    def _bias_arg(self, bias):
        """返回 (biasn, buf)：非 list 或 len==1 -> 标量（biasn=0）；len>1 -> 向量。"""
        if isinstance(bias, list):
            if len(bias) > 1:
                return len(bias), self._buf(bias)
            return 0, self._buf([bias[0] if len(bias) else 0.0])
        return 0, self._buf([bias])

    def affine2(self, a, b, bias, relu_flag):
        M, K, N = len(a), len(a[0]), len(b[0])
        A, B = self._buf(self._flat2(a)), self._buf(self._flat2(b))
        biasn, BUF = self._bias_arg(bias)
        out = (_CD * (M * N))()
        self.dll.tl_affine2(A, M, K, B, N, BUF, biasn, 1 if relu_flag else 0, out)
        return self._unflat(out, (M, N))

    def affine2v(self, a, b, bias, relu_flag):
        M, K = len(a), len(a[0])
        A, B = self._buf(self._flat2(a)), self._buf(b)
        biasn, BUF = self._bias_arg(bias)
        out = (_CD * M)()
        self.dll.tl_affine2v(A, M, K, B, BUF, biasn, 1 if relu_flag else 0, out)
        return list(out)

    def affine2_back(self, a, b, g, bias, relu_flag):
        M, K, N = len(a), len(a[0]), len(b[0])
        A, B, G = (self._buf(self._flat2(a)), self._buf(self._flat2(b)),
                   self._buf(self._flat2(g)))
        biasn, BUF = self._bias_arg(bias)
        ga = (_CD * (M * K))()
        gb = (_CD * (K * N))()
        gb_bias = (_CD * (N if biasn > 0 else 1))()
        self.dll.tl_affine2_back(A, M, K, B, N, G, BUF, biasn,
                                 1 if relu_flag else 0, ga, gb, gb_bias)
        bb = list(gb_bias) if biasn > 0 else gb_bias[0]
        return self._unflat(ga, (M, K)), self._unflat(gb, (K, N)), bb

    def affine2v_back(self, a, b, g, bias, relu_flag):
        M, K = len(a), len(a[0])
        A, B, G = self._buf(self._flat2(a)), self._buf(b), self._buf(g)
        biasn, BUF = self._bias_arg(bias)
        ga = (_CD * (M * K))()
        gb = (_CD * K)()
        gb_bias = (_CD * (M if biasn > 1 else 1))()
        self.dll.tl_affine2v_back(A, M, K, B, G, BUF, biasn,
                                  1 if relu_flag else 0, ga, gb, gb_bias)
        bb = list(gb_bias) if biasn > 1 else gb_bias[0]
        return self._unflat(ga, (M, K)), list(gb), bb


def _shape(v):
    s = []
    while isinstance(v, list):
        s.append(len(v))
        v = v[0] if v else []
    return tuple(s)


def load(dll_path):
    try:
        return NativeKernels(dll_path)
    except Exception:
        return None


# ======================================================================
# v0.12 —— Buf 扁平化表示：槽值直接存连续 double buffer（零拷贝热路径）
# ======================================================================
class Buf:
    """扁平张量：ctypes 双精度数组 + shape（行优先）。ptr 预 cast，热路径直通 C。"""
    __slots__ = ("arr", "ptr", "shape", "n")

    def __init__(self, arr, shape):
        self.arr = arr
        self.ptr = ctypes.cast(arr, ctypes.POINTER(_CD))
        self.shape = tuple(shape)
        n = 1
        for d in self.shape:
            n *= d
        self.n = n

    def to_list(self):
        return NativeKernels._unflat(self.arr, self.shape)

    def scalar(self):
        """shape==(1,) 或 () 时取标量。"""
        return self.arr[0] if self.n == 1 else None

    @classmethod
    def from_list(cls, v, shape=None):
        if shape is None:
            shape = NativeKernels._shape(v)
        flat = NativeKernels._flat(v)
        return cls((_CD * len(flat))(*flat), shape)


class _BufKernels:
    """Buf 版内核：输入 Buf（flat 指针直通 C），输出新 Buf。"""

    def __init__(self, nk):
        self.nk = nk
        self.d = nk.dll

    def mm2(self, a, b):
        M, K = a.shape
        N = b.shape[1]
        out = (_CD * (M * N))()
        self.d.tl_mm2(a.ptr, M, K, b.ptr, N, out)
        return Buf(out, (M, N))

    def mm2v(self, a, b):
        M, K = a.shape
        out = (_CD * M)()
        self.d.tl_mm2v(a.ptr, M, K, b.ptr, out)
        return Buf(out, (M,))

    def mm2_back(self, a, b, g):
        M, K = a.shape
        N = b.shape[1]
        ga = (_CD * (M * K))()
        gb = (_CD * (K * N))()
        self.d.tl_mm2_back(g.ptr, M, N, b.ptr, K, a.ptr, ga, gb)
        return Buf(ga, (M, K)), Buf(gb, (K, N))

    def elem2(self, a, b, op):
        out = (_CD * a.n)()
        self.d.tl_elem2(a.ptr, b.ptr, a.n, op, out)
        return Buf(out, a.shape)

    def relu(self, a):
        out = (_CD * a.n)()
        self.d.tl_relu(a.ptr, a.n, out)
        return Buf(out, a.shape)

    def sq(self, a):
        out = (_CD * a.n)()
        self.d.tl_sq(a.ptr, a.n, out)
        return Buf(out, a.shape)

    def scale(self, a, cv):
        out = (_CD * a.n)()
        self.d.tl_scale(a.ptr, a.n, cv, out)
        return Buf(out, a.shape)

    def scg(self, g, cv):
        out = (_CD * g.n)()
        self.d.tl_scg(g.ptr, g.n, cv, out)
        return Buf(out, g.shape)

    def upd(self, v, g, lr):
        out = (_CD * v.n)()
        self.d.tl_upd(v.ptr, g.ptr, v.n, lr, out)
        return Buf(out, v.shape)

    def relu_mask(self, x, g):
        out = (_CD * x.n)()
        self.d.tl_relu_mask(x.ptr, g.ptr, x.n, out)
        return Buf(out, x.shape)

    def sqg(self, x, g):
        out = (_CD * x.n)()
        self.d.tl_sqg(x.ptr, g.ptr, x.n, out)
        return Buf(out, x.shape)

    def rows_softmax(self, a):
        rows, cols = a.shape
        out = (_CD * a.n)()
        self.d.tl_softmax(a.ptr, rows, cols, out)
        return Buf(out, a.shape)

    def softmax_grad(self, s, g):
        rows, cols = s.shape
        out = (_CD * s.n)()
        self.d.tl_softmax_grad(s.ptr, g.ptr, rows, cols, out)
        return Buf(out, s.shape)

    def total(self, a):
        """嵌套分组 total：与 Python 递归 sum 一致（每行 Neumaier → 行和 Neumaier）。"""
        if len(a.shape) == 2:
            rows, cols = a.shape
            base = ctypes.addressof(a.arr)
            row_sums = []
            for r in range(rows):
                row_ptr = ctypes.cast(base + r * cols * 8, ctypes.POINTER(_CD))
                row_sums.append(self.d.tl_total(row_ptr, cols))
            A = (_CD * rows)(*row_sums)
            return self.d.tl_total(A, rows)
        return self.d.tl_total(a.ptr, a.n)

    def transpose(self, a):
        rows, cols = a.shape
        out = (_CD * a.n)()
        self.d.tl_transpose(a.ptr, rows, cols, out)
        return Buf(out, (cols, rows))

    def colsum(self, g, ncols):
        rows, cols = g.shape
        out = (_CD * cols)()
        self.d.tl_colsum(g.ptr, rows, cols, out)
        return Buf(out, (cols,))

    def scaled_mm(self, a, b, cv):
        M, K = a.shape
        N = b.shape[1]
        out = (_CD * (M * N))()
        self.d.tl_scaled_mm(a.ptr, M, K, b.ptr, N, cv, out)
        return Buf(out, (M, N))

    def scaled_mm_t(self, a, b, cv):
        M, K = a.shape
        N = b.shape[0]
        out = (_CD * (M * N))()
        self.d.tl_scaled_mm_t(a.ptr, M, K, b.ptr, N, cv, out)
        return Buf(out, (M, N))

    def scaled_mm_back(self, a, b, g, cv):
        M, K = a.shape
        N = b.shape[1]
        ga = (_CD * (M * K))()
        gb = (_CD * (K * N))()
        dc = self.d.tl_scaled_mm_back(a.ptr, M, K, b.ptr, N, g.ptr, cv, ga, gb)
        return Buf(ga, (M, K)), Buf(gb, (K, N)), dc

    def scaled_mm_t_back(self, a, b, g, cv):
        M, K = a.shape
        N = b.shape[0]
        ga = (_CD * (M * K))()
        gb = (_CD * (N * K))()
        dc = self.d.tl_scaled_mm_t_back(a.ptr, M, K, b.ptr, N, g.ptr, cv, ga, gb)
        return Buf(ga, (M, K)), Buf(gb, (N, K)), dc

    @staticmethod
    def _bias_len(bias):
        if isinstance(bias, Buf):
            return bias.n
        if isinstance(bias, list):
            return len(bias)
        return 1

    def affine2(self, a, b, bias, relu_flag):
        M, K = a.shape
        N = b.shape[1]
        out = (_CD * (M * N))()
        bias_len = self._bias_len(bias)
        if isinstance(bias, Buf):
            bias_ptr = bias.ptr
        elif isinstance(bias, list):
            bias_arr = (_CD * len(bias))(*bias)
            bias_ptr = ctypes.cast(bias_arr, ctypes.POINTER(_CD))
        else:
            bias_arr = (_CD * 1)(bias)
            bias_ptr = ctypes.cast(bias_arr, ctypes.POINTER(_CD))
        self.d.tl_affine2(a.ptr, M, K, b.ptr, N, bias_ptr,
                          0 if bias_len <= 1 else bias_len,
                          int(relu_flag), out)
        return Buf(out, (M, N))

    def affine2v(self, a, b, bias, relu_flag):
        M, K = a.shape
        out = (_CD * M)()
        if isinstance(bias, Buf):
            bias_ptr = bias.ptr
            bias_len = bias.n
        elif isinstance(bias, list):
            bias_arr = (_CD * len(bias))(*bias)
            bias_ptr = ctypes.cast(bias_arr, ctypes.POINTER(_CD))
            bias_len = len(bias)
        else:
            bias_arr = (_CD * 1)(bias)
            bias_ptr = ctypes.cast(bias_arr, ctypes.POINTER(_CD))
            bias_len = 1
        if bias_len <= 1:
            bias_len = 0
        self.d.tl_affine2v(a.ptr, M, K, b.ptr, bias_ptr, bias_len,
                           int(relu_flag), out)
        return Buf(out, (M,))

    def affine2_back(self, a, b, g, bias, relu_flag):
        M, K = a.shape
        N = b.shape[1]
        ga = (_CD * (M * K))()
        gb = (_CD * (K * N))()
        if isinstance(bias, Buf):
            bias_ptr = bias.ptr
            bias_len = bias.n
        elif isinstance(bias, list):
            bias_arr = (_CD * len(bias))(*bias)
            bias_ptr = ctypes.cast(bias_arr, ctypes.POINTER(_CD))
            bias_len = len(bias)
        else:
            bias_arr = (_CD * 1)(bias)
            bias_ptr = ctypes.cast(bias_arr, ctypes.POINTER(_CD))
            bias_len = 1
        gb_bias = (_CD * max(bias_len, 1))()
        self.d.tl_affine2_back(a.ptr, M, K, b.ptr, N, g.ptr, bias_ptr,
                               0 if bias_len <= 1 else bias_len,
                               int(relu_flag), ga, gb, gb_bias)
        return Buf(ga, (M, K)), Buf(gb, (K, N)), Buf(gb_bias, (bias_len,))

    def affine2v_back(self, a, b, g, bias, relu_flag):
        M, K = a.shape
        ga = (_CD * (M * K))()
        gb = (_CD * K)()
        if isinstance(bias, Buf):
            bias_ptr = bias.ptr
            bias_len = bias.n
        elif isinstance(bias, list) and len(bias) > 1:
            bias_arr = (_CD * len(bias))(*bias)
            bias_ptr = ctypes.cast(bias_arr, ctypes.POINTER(_CD))
            bias_len = len(bias)
        else:
            bias_arr = (_CD * 1)(bias if not isinstance(bias, list) else bias[0])
            bias_ptr = ctypes.cast(bias_arr, ctypes.POINTER(_CD))
            bias_len = 1
        gb_bias = (_CD * M)()
        self.d.tl_affine2v_back(a.ptr, M, K, b.ptr, g.ptr, bias_ptr,
                                0 if bias_len <= 1 else bias_len,
                                int(relu_flag), ga, gb, gb_bias)
        if bias_len <= 1:
            return Buf(ga, (M, K)), Buf(gb, (K,)), gb_bias[0]
        return Buf(ga, (M, K)), Buf(gb, (K,)), Buf(gb_bias, (M,))
