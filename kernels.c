/* =====================================================================
 * tl 原生内核 kernels.c —— tl 语言自研数值内核（C 实现，零第三方）
 * v0.11：把 VM 热内核下沉为原生代码（ctypes 加载），Python VM 只留调度。
 *
 * 逐位一致性契约（与 tlb.py 的 Python 内核逐位一致）：
 *  - 朴素累加（s += 循环）：matmul/matmul2v/scaled_mm/affine2v 前向、
 *    matmul 反向（与前端 matmul2 的 s += 循环一致）
 *  - Neumaier 补偿求和：Python 3.12+ 内置 sum() 的浮点算法——用于
 *    scaled_mm_t 内积、affine2 内积、softmax 总和/点积、total/colsum
 *    （这些在 Python 侧用 sum()，必须用同款补偿求和我们才逐位一致）
 *  - 运算顺序：行优先展平（深度优先从左到右，与 Python 嵌套递归一致）
 * ===================================================================== */
#include <math.h>

#ifdef _WIN32
#define TL_EXPORT __declspec(dllexport)
#else
#define TL_EXPORT __attribute__((visibility("default")))
#endif

/* ---------------- Neumaier 补偿求和（复刻 CPython 3.12+ sum()） ------------- */
static double neumaier(const double* x, int n) {
    double s = 0.0, c = 0.0;
    for (int i = 0; i < n; i++) {
        double t = s + x[i];
        if (fabs(s) >= fabs(x[i]))
            c += (s - t) + x[i];
        else
            c += (x[i] - t) + s;
        s = t;
    }
    return s + c;
}

/* ---------------- 朴素 matmul（s += 循环，与前端 matmul2 逐位一致） ------------- */
TL_EXPORT void tl_mm2(const double* a, int M, int K,
                      const double* b, int N, double* out) {
    for (int m = 0; m < M; m++) {
        for (int n = 0; n < N; n++) {
            double s = 0.0;
            for (int k = 0; k < K; k++)
                s += a[m * K + k] * b[k * N + n];
            out[m * N + n] = s;
        }
    }
}

/* a[M,K] x b[K] -> [M]（朴素） */
TL_EXPORT void tl_mm2v(const double* a, int M, int K,
                       const double* b, double* out) {
    for (int m = 0; m < M; m++) {
        double s = 0.0;
        for (int k = 0; k < K; k++)
            s += a[m * K + k] * b[k];
        out[m] = s;
    }
}

/* matmul 反向：ga = g@B^T, gb = A^T@g（朴素，与前端一致） */
TL_EXPORT void tl_mm2_back(const double* g, int M, int N,
                           const double* b, int K,
                           const double* a, double* ga, double* gb) {
    /* ga[M,K] = g[M,N] @ B^T[N,K] */
    for (int m = 0; m < M; m++) {
        for (int k = 0; k < K; k++) {
            double s = 0.0;
            for (int n = 0; n < N; n++)
                s += g[m * N + n] * b[k * N + n];
            ga[m * K + k] = s;
        }
    }
    /* gb[K,N] = A^T[K,M] @ g[M,N] */
    for (int k = 0; k < K; k++) {
        for (int n = 0; n < N; n++) {
            double s = 0.0;
            for (int m = 0; m < M; m++)
                s += a[m * K + k] * g[m * N + n];
            gb[k * N + n] = s;
        }
    }
}

/* ---------------- 逐元素二元：op 0=add 1=sub 2=mul ------------- */
TL_EXPORT void tl_elem2(const double* a, const double* b, int n, int op,
                        double* out) {
    for (int i = 0; i < n; i++) {
        if (op == 0) out[i] = a[i] + b[i];
        else if (op == 1) out[i] = a[i] - b[i];
        else out[i] = a[i] * b[i];
    }
}

/* ---------------- 逐元素一元 ------------- */
TL_EXPORT void tl_relu(const double* a, int n, double* out) {
    for (int i = 0; i < n; i++)
        out[i] = a[i] > 0 ? a[i] : 0.0;
}

TL_EXPORT void tl_sq(const double* a, int n, double* out) {
    for (int i = 0; i < n; i++)
        out[i] = a[i] * a[i];
}

TL_EXPORT void tl_scale(const double* a, int n, double cv, double* out) {
    for (int i = 0; i < n; i++)
        out[i] = a[i] / cv;
}

TL_EXPORT void tl_scg(const double* g, int n, double cv, double* out) {
    for (int i = 0; i < n; i++)
        out[i] = g[i] / cv;
}

TL_EXPORT void tl_upd(const double* v, const double* g, int n, double lr,
                      double* out) {
    for (int i = 0; i < n; i++)
        out[i] = v[i] - lr * g[i];
}

TL_EXPORT void tl_relu_mask(const double* x, const double* g, int n,
                            double* out) {
    for (int i = 0; i < n; i++)
        out[i] = x[i] > 0 ? g[i] : 0.0;
}

TL_EXPORT void tl_sqg(const double* x, const double* g, int n, double* out) {
    for (int i = 0; i < n; i++)
        out[i] = 2.0 * x[i] * g[i];
}

/* ---------------- 自研 exp（tl 数值内核，C/Python 同源）----------------
   x = k*ln2 + r（|r|<=ln2/2），exp(r) 用 16 阶 Taylor（Horner），
   2^k 用 ldexp（无舍入）。不依赖 libm——数值内核全自研。 */
static const double EXP_C[16] = {
    4.7794773323873853e-14, 7.6471637318198164e-13,
    1.1470745597729725e-11, 1.6059043836821613e-10,
    2.08767569878681e-09,   2.505210838544172e-08,
    2.7557319223985888e-07, 2.7557319223985893e-06,
    2.4801587301587302e-05, 0.00019841269841269841,
    0.0013888888888888889,  0.0083333333333333332,
    0.041666666666666664,   0.16666666666666666,
    0.5, 1.0
};
double tl_exp(double x) {
    if (x != x) return x;                      /* nan */
    if (x == INFINITY) return INFINITY;
    if (x == -INFINITY) return 0.0;
    double kf = floor(x * 1.4426950408889634 + 0.5);
    long k = (long)kf;
    if (k > 1023) return INFINITY;
    double r = x - (double)k * 0.6931471805599453;
    double p = EXP_C[0];
    for (int i = 1; i < 16; i++) p = p * r + EXP_C[i];
    p = p * r + 1.0;
    return ldexp(p, (int)k);
}
TL_EXPORT double tl_exp_test(double x) { return tl_exp(x); }

/* ---------------- 行 softmax：max -> 自研 exp -> Neumaier sum -> div ------------- */
TL_EXPORT void tl_softmax(const double* a, int rows, int cols, double* out) {
    for (int r = 0; r < rows; r++) {
        const double* row = a + r * cols;
        double m = row[0];
        for (int j = 1; j < cols; j++)
            if (row[j] > m) m = row[j];
        double ex[4096];
        for (int j = 0; j < cols; j++)
            ex[j] = tl_exp(row[j] - m);
        double s = neumaier(ex, cols);
        for (int j = 0; j < cols; j++)
            out[r * cols + j] = ex[j] / s;
    }
}

/* ---------------- 全量求和（Neumaier） ------------- */
TL_EXPORT double tl_total(const double* a, int n) {
    return neumaier(a, n);
}

/* ---------------- softmax 反向：dot=Neumaier(s*g), out=si*(gi-dot) ------------- */
TL_EXPORT void tl_softmax_grad(const double* s, const double* g,
                               int rows, int cols, double* out) {
    for (int r = 0; r < rows; r++) {
        double prod[4096];
        for (int j = 0; j < cols; j++)
            prod[j] = s[r * cols + j] * g[r * cols + j];
        double dot = neumaier(prod, cols);
        for (int j = 0; j < cols; j++)
            out[r * cols + j] = s[r * cols + j] * (g[r * cols + j] - dot);
    }
}

/* ---------------- 转置 ------------- */
TL_EXPORT void tl_transpose(const double* a, int M, int N, double* out) {
    for (int j = 0; j < N; j++)
        for (int i = 0; i < M; i++)
            out[j * M + i] = a[i * N + j];
}

/* ---------------- 列和（Neumaier）：out[n] = sum_m g[m][n] ------------- */
TL_EXPORT void tl_colsum(const double* g, int M, int N, double* out) {
    for (int n = 0; n < N; n++) {
        double col[8192];
        for (int m = 0; m < M; m++)
            col[m] = g[m * N + n];
        out[n] = neumaier(col, M);
    }
}

/* ---------------- scaled_mm：朴素 matmul + /cv（与前端一致） ------------- */
TL_EXPORT void tl_scaled_mm(const double* a, int M, int K,
                            const double* b, int N, double cv, double* out) {
    for (int m = 0; m < M; m++) {
        for (int n = 0; n < N; n++) {
            double s = 0.0;
            for (int k = 0; k < K; k++)
                s += a[m * K + k] * b[k * N + n];
            out[m * N + n] = s / cv;
        }
    }
}

/* scaled_mm_t：Neumaier 内积 sum_k a[m][k]*b[n][k] + /cv（与 sum() 逐位一致） */
TL_EXPORT void tl_scaled_mm_t(const double* a, int M, int K,
                              const double* b, int N, double cv, double* out) {
    for (int m = 0; m < M; m++) {
        for (int n = 0; n < N; n++) {
            double prod[8192];
            for (int k = 0; k < K; k++)
                prod[k] = a[m * K + k] * b[n * K + k];
            out[m * N + n] = neumaier(prod, K) / cv;
        }
    }
}

/* scaled_mm 反向（朴素 mm 路径 + /cv）；返回 dc */
TL_EXPORT double tl_scaled_mm_back(const double* a, int M, int K,
                                   const double* b, int N, const double* g,
                                   double cv, double* ga, double* gb) {
    /* ga[M,K] = (g/cv) @ B^T */
    for (int m = 0; m < M; m++) {
        for (int k = 0; k < K; k++) {
            double s = 0.0;
            for (int n = 0; n < N; n++)
                s += (g[m * N + n] / cv) * b[k * N + n];
            ga[m * K + k] = s;
        }
    }
    /* gb[K,N] = A^T @ (g/cv) */
    for (int k = 0; k < K; k++) {
        for (int n = 0; n < N; n++) {
            double s = 0.0;
            for (int m = 0; m < M; m++)
                s += a[m * K + k] * (g[m * N + n] / cv);
            gb[k * N + n] = s;
        }
    }
    /* dc = -sum(g[m][n] * (a@b)[m][n]) / (cv*cv) —— sum() 是 Neumaier */
    double prod_all[8192];
    int idx = 0;
    for (int m = 0; m < M; m++)
        for (int n = 0; n < N; n++) {
            double p = 0.0;
            for (int k = 0; k < K; k++)
                p += a[m * K + k] * b[k * N + n];
            prod_all[idx++] = g[m * N + n] * p;
        }
    return -neumaier(prod_all, idx) / (cv * cv);
}

/* scaled_mm_t 反向（Neumaier 内积路径）；返回 dc */
TL_EXPORT double tl_scaled_mm_t_back(const double* a, int M, int K,
                                     const double* b, int N, const double* g,
                                     double cv, double* ga, double* gb) {
    /* ga[M,K] = sum_n g[m][n]*b[n][k] / cv（Neumaier） */
    for (int m = 0; m < M; m++) {
        for (int k = 0; k < K; k++) {
            double prod[8192];
            for (int n = 0; n < N; n++)
                prod[n] = g[m * N + n] * b[n * K + k];
            ga[m * K + k] = neumaier(prod, N) / cv;
        }
    }
    /* gb[N,K] = sum_m g[m][n]*a[m][k] / cv（Neumaier） */
    for (int n = 0; n < N; n++) {
        for (int k = 0; k < K; k++) {
            double prod[8192];
            for (int m = 0; m < M; m++)
                prod[m] = g[m * N + n] * a[m * K + k];
            gb[n * K + k] = neumaier(prod, M) / cv;
        }
    }
    /* dc = -sum(g[m][n] * (a@b^T)[m][n]) / (cv*cv)（Neumaier） */
    double s = 0.0, c = 0.0;
    for (int m = 0; m < M; m++) {
        for (int n = 0; n < N; n++) {
            double p = 0.0;
            for (int k = 0; k < K; k++)
                p += a[m * K + k] * b[n * K + k];
            double t = s + (g[m * N + n] * p);
            if (fabs(s) >= fabs(g[m * N + n] * p))
                c += (s - t) + g[m * N + n] * p;
            else
                c += (g[m * N + n] * p - t) + s;
            s = t;
        }
    }
    return -(s + c) / (cv * cv);
}

/* ---------------- affine/bias_relu 前向 2D：Neumaier 内积 + bias + relu -------------
   biasn: 0 = 标量（bias[0]），>0 = 向量长 biasn */
TL_EXPORT void tl_affine2(const double* a, int M, int K,
                          const double* b, int N, const double* bias,
                          int biasn, int relu_flag, double* out) {
    for (int m = 0; m < M; m++) {
        for (int n = 0; n < N; n++) {
            double prod[8192];
            for (int k = 0; k < K; k++)
                prod[k] = a[m * K + k] * b[k * N + n];
            double z = neumaier(prod, K);
            z += (biasn > 0) ? bias[n] : bias[0];
            out[m * N + n] = relu_flag ? (z > 0 ? z : 0.0) : z;
        }
    }
}

/* affine/bias_relu 前向 2D×1D：朴素 mm2v + bias（与前端 _affine_fwd 一致） */
TL_EXPORT void tl_affine2v(const double* a, int M, int K,
                           const double* b, const double* bias,
                           int biasn, int relu_flag, double* out) {
    double z[4096];
    for (int m = 0; m < M; m++) {
        double s = 0.0;
        for (int k = 0; k < K; k++)
            s += a[m * K + k] * b[k];
        z[m] = s + ((biasn > 1) ? bias[m] : bias[0]);
        out[m] = relu_flag ? (z[m] > 0 ? z[m] : 0.0) : z[m];
    }
}

/* affine/bias_relu 反向 2D：z 重算（Neumaier）、g2（relu mask）、
   ga/gb（Neumaier）、gb_bias（列和）；返回 gb_bias（若 biasn>0 则 out 向量） */
TL_EXPORT void tl_affine2_back(const double* a, int M, int K,
                               const double* b, int N, const double* g,
                               const double* bias, int biasn, int relu_flag,
                               double* ga, double* gb, double* gb_bias) {
    double z[8192], g2[8192];
    for (int m = 0; m < M; m++) {
        for (int n = 0; n < N; n++) {
            double prod[8192];
            for (int k = 0; k < K; k++)
                prod[k] = a[m * K + k] * b[k * N + n];
            double zz = neumaier(prod, K);
            zz += (biasn > 0) ? bias[n] : bias[0];
            z[m * N + n] = zz;
        }
    }
    for (int i = 0; i < M * N; i++)
        g2[i] = (relu_flag && !(z[i] > 0)) ? 0.0 : g[i];
    /* ga[M,K] = g2 @ B^T —— 前端 _matmul2（朴素 s+= 循环） */
    for (int m = 0; m < M; m++) {
        for (int k = 0; k < K; k++) {
            double s = 0.0;
            for (int n = 0; n < N; n++)
                s += g2[m * N + n] * b[k * N + n];
            ga[m * K + k] = s;
        }
    }
    /* gb[K,N] = A^T @ g2 —— 前端 _matmul2（朴素） */
    for (int k = 0; k < K; k++) {
        for (int n = 0; n < N; n++) {
            double s = 0.0;
            for (int m = 0; m < M; m++)
                s += a[m * K + k] * g2[m * N + n];
            gb[k * N + n] = s;
        }
    }
    /* gb_bias：标量（biasn==0）= Neumaier(g2)；向量 = 列和（Neumaier） */
    if (biasn > 0) {
        for (int n = 0; n < N; n++) {
            double col[8192];
            for (int m = 0; m < M; m++)
                col[m] = g2[m * N + n];
            gb_bias[n] = neumaier(col, M);
        }
    } else {
        gb_bias[0] = neumaier(g2, M * N);
    }
}

/* affine/bias_relu 反向 2D×1D（与前端 _affine_back 一致） */
TL_EXPORT void tl_affine2v_back(const double* a, int M, int K,
                                const double* b, const double* g,
                                const double* bias, int biasn, int relu_flag,
                                double* ga, double* gb, double* gb_bias) {
    double z[4096], g2[4096];
    for (int m = 0; m < M; m++) {
        double s = 0.0;
        for (int k = 0; k < K; k++)
            s += a[m * K + k] * b[k];
        z[m] = s + ((biasn > 1) ? bias[m] : bias[0]);
    }
    for (int m = 0; m < M; m++)
        g2[m] = (relu_flag && !(z[m] > 0)) ? 0.0 : g[m];
    for (int m = 0; m < M; m++) {
        for (int k = 0; k < K; k++)
            ga[m * K + k] = g2[m] * b[k];
    }
    /* gb[k] = sum_m a[m][k]*g2[m] —— 前端 sum()（Neumaier） */
    for (int k = 0; k < K; k++) {
        double prod[8192];
        for (int m = 0; m < M; m++)
            prod[m] = a[m * K + k] * g2[m];
        gb[k] = neumaier(prod, M);
    }
    if (biasn > 1) {
        for (int m = 0; m < M; m++)
            gb_bias[m] = g2[m];
    } else {
        double s = 0.0;
        for (int m = 0; m < M; m++)
            s += g2[m];
        gb_bias[0] = s;
    }
}
