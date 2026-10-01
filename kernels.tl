# ============================================================
# kernels.tl —— tl 自研数值内核（用 tl 内核子集书写）
# 内核源码全部由 tl 语言自身表达，经 tl 编译器（tl_kern 解析 +
# tl_emit 自研 x86-64 代码生成）编译为机器码直接执行。
# 零 C / 零 Rust / 零 LLVM —— 内核是 tl 自己的。
# ============================================================

kernel relu(x, out, n) {
    for i in range(n) {
        if x[i] > 0.0 { out[i] = x[i] } else { out[i] = 0.0 }
    }
}

kernel elem2_add(a, b, out, n) {
    for i in range(n) { out[i] = a[i] + b[i] }
}

kernel elem2_sub(a, b, out, n) {
    for i in range(n) { out[i] = a[i] - b[i] }
}

kernel elem2_mul(a, b, out, n) {
    for i in range(n) { out[i] = a[i] * b[i] }
}

kernel scale(x, out, n, cv) {
    for i in range(n) { out[i] = x[i] * cv }
}

kernel upd(v, g, out, n, lr) {
    for i in range(n) { out[i] = v[i] - lr * g[i] }
}

kernel relu_mask(x, g, out, n) {
    for i in range(n) { if x[i] > 0.0 { out[i] = g[i] } else { out[i] = 0.0 } }
}

kernel sqg(x, g, out, n) {
    for i in range(n) { out[i] = 2.0 * x[i] * g[i] }
}

kernel mm2(a, b, out, M, K, N) {
    for i in range(M) {
        for j in range(N) {
            var s = 0.0
            for k in range(K) {
                s = s + a[i*K+k] * b[k*N+j]
            }
            out[i*N+j] = s
        }
    }
}
