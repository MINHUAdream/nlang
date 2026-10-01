/* v0.12 纯 C 训练基准：transformer_block 前向+反向+update，全部用 kernels.c 自研内核。
 * 与 tl Buf VM 同一计算图、同一内核实现 —— 衡量 tl 调度层的相对开销。
 * 用法：zig cc -O2 -ffp-contract=off bench_c.c kernels.c -o bench_c.exe
 *       bench_c.exe big 400 | bench_c.exe large 50
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "kernels.c"

static double frand(void) { return (double)rand() / (double)RAND_MAX; }

/* 嵌套分组 total（与 Python/C tl VM 一致）：每行 Neumaier -> 行和 Neumaier */
static double total_2d(const double* a, int rows, int cols) {
    double* rowsum = (double*)malloc(rows * sizeof(double));
    for (int r = 0; r < rows; r++) rowsum[r] = neumaier(a + r * cols, cols);
    double t = neumaier(rowsum, rows);
    free(rowsum);
    return t;
}

static double run_bench(int M, int K, int N, int epochs, double lr) {
    const int MN = M * N, MK = M * K, KN = K * N, MM = M * M;
    double *X, *T, *Wq, *Wk, *Wv, *W1, *b1;
    double *Q, *Kt, *V, *S, *A, *Ctx, *H, *R, *F, *Out, *E, *E2;
    double *gOut, *gF, *gR, *gH, *gCtx, *gA, *gV, *gS, *gQ, *gKt;
    double *gWq, *gWk, *gWv, *gW1, *gb1;
    double *tmp1, *tmp2, *tmp3;
    int i;

    X  = (double*)malloc(MK * sizeof(double));
    T  = (double*)malloc(MK * sizeof(double));
    Wq = (double*)malloc(KN * sizeof(double));
    Wk = (double*)malloc(KN * sizeof(double));
    Wv = (double*)malloc(KN * sizeof(double));
    W1 = (double*)malloc(KN * sizeof(double));
    b1 = (double*)malloc(N * sizeof(double));
    Q  = (double*)malloc(MK * sizeof(double));
    Kt = (double*)malloc(MK * sizeof(double));
    V  = (double*)malloc(MK * sizeof(double));
    S  = (double*)malloc(MM * sizeof(double));
    A  = (double*)malloc(MM * sizeof(double));
    Ctx = (double*)malloc(MK * sizeof(double));
    H  = (double*)malloc(MK * sizeof(double));
    R  = (double*)malloc(MK * sizeof(double));
    F  = (double*)malloc(MK * sizeof(double));
    Out = (double*)malloc(MK * sizeof(double));
    E  = (double*)malloc(MK * sizeof(double));
    E2 = (double*)malloc(MK * sizeof(double));
    gOut = (double*)malloc(MK * sizeof(double));
    gF   = (double*)malloc(MK * sizeof(double));
    gR   = (double*)malloc(MK * sizeof(double));
    gH   = (double*)malloc(MK * sizeof(double));
    gCtx = (double*)malloc(MK * sizeof(double));
    gA   = (double*)malloc(MM * sizeof(double));
    gV   = (double*)malloc(MK * sizeof(double));
    gS   = (double*)malloc(MM * sizeof(double));
    gQ   = (double*)malloc(MK * sizeof(double));
    gKt  = (double*)malloc(MK * sizeof(double));
    gWq = (double*)malloc(KN * sizeof(double));
    gWk = (double*)malloc(KN * sizeof(double));
    gWv = (double*)malloc(KN * sizeof(double));
    gW1 = (double*)malloc(KN * sizeof(double));
    gb1 = (double*)malloc(N * sizeof(double));
    tmp1 = (double*)malloc(MK * sizeof(double));  /* gX 累加 */
    tmp2 = (double*)malloc(MK * sizeof(double));
    tmp3 = (double*)malloc(KN * sizeof(double));

    for (i = 0; i < MK; i++) { X[i] = frand(); T[i] = frand(); }
    for (i = 0; i < KN; i++) { Wq[i] = frand() * 0.6 - 0.3; Wk[i] = frand() * 0.6 - 0.3;
                               Wv[i] = frand() * 0.6 - 0.3; W1[i] = frand() * 0.6 - 0.3; }
    for (i = 0; i < N; i++) b1[i] = frand() * 0.6 - 0.3;

    double first_loss = 0.0, last_loss = 0.0;
    for (int ep = 0; ep < epochs; ep++) {
        /* ---- 前向 ---- */
        tl_mm2(X, M, K, Wq, N, Q);
        tl_mm2(X, M, K, Wk, N, Kt);
        tl_mm2(X, M, K, Wv, N, V);
        tl_scaled_mm_t(Q, M, K, Kt, M, 2.0, S);
        tl_softmax(S, M, M, A);
        tl_mm2(A, M, M, V, N, Ctx);
        tl_elem2(Ctx, X, MK, 0, H);
        tl_relu(H, MK, R);
        tl_affine2(R, M, K, W1, N, b1, N, 0, F);
        tl_elem2(F, H, MK, 0, Out);
        tl_elem2(Out, T, MK, 1, E);
        tl_sq(E, MK, E2);
        double loss = total_2d(E2, M, K) / (double)(MK);
        if (ep == 0) first_loss = loss;
        last_loss = loss;

        /* ---- 反向 ---- */
        /* mean back: gE[i] = 2*E[i]/MK ; sub back: gOut = gE */
        for (i = 0; i < MK; i++) gOut[i] = 2.0 * E[i] / (double)MK;
        /* out = f + h: gF = gOut, gH 初值 = gOut */
        memcpy(gF, gOut, MK * sizeof(double));
        memcpy(gH, gOut, MK * sizeof(double));
        tl_affine2_back(R, M, K, W1, N, gF, b1, N, 0, gR, gW1, gb1);
        tl_relu_mask(H, gR, MK, tmp2);
        for (i = 0; i < MK; i++) gH[i] += tmp2[i];
        /* h = ctx + X: gCtx = gH（gX 不算，X 不更新） */
        memcpy(gCtx, gH, MK * sizeof(double));
        /* ctx = A @ V: mm2_back(gCtx, M, N, V, Kb=M, A, gA, gV) —— A(8,8) 的共享维 M */
        tl_mm2_back(gCtx, M, N, V, M, A, gA, gV);
        tl_softmax_grad(A, gA, M, M, gS);
        tl_scaled_mm_t_back(Q, M, K, Kt, M, gS, 2.0, gQ, gKt);
        /* Q/K/V = X @ W*：mm2_back(g, M, N, W*, K, X, gX, gW*) —— gX 累加到 tmp1 */
        tl_mm2_back(gQ, M, N, Wq, K, X, tmp1, gWq);
        tl_mm2_back(gKt, M, N, Wk, K, X, tmp2, gWk);
        tl_mm2_back(gV, M, N, Wv, K, X, tmp3, gWv);

        /* ---- 更新 ---- */
        tl_upd(Wq, gWq, KN, lr, Wq);
        tl_upd(Wk, gWk, KN, lr, Wk);
        tl_upd(Wv, gWv, KN, lr, Wv);
        tl_upd(W1, gW1, KN, lr, W1);
        tl_upd(b1, gb1, N, lr, b1);
    }

    printf("  pure C: %d epoch 首 loss %.6f 末 loss %.6f\n", epochs, first_loss, last_loss);
    double ms = 0.0; /* 计时在 main 里做 */
    free(X); free(T); free(Wq); free(Wk); free(Wv); free(W1); free(b1);
    free(Q); free(Kt); free(V); free(S); free(A); free(Ctx); free(H); free(R);
    free(F); free(Out); free(E); free(E2); free(gOut); free(gF); free(gR); free(gH);
    free(gCtx); free(gA); free(gV); free(gS); free(gQ); free(gKt);
    free(gWq); free(gWk); free(gWv); free(gW1); free(gb1);
    free(tmp1); free(tmp2); free(tmp3);
    return ms;
}

int main(int argc, char** argv) {
    const char* which = argc > 1 ? argv[1] : "big";
    int epochs = argc > 2 ? atoi(argv[2]) : 400;
    int M, K, N;
    double lr = 0.2;
    if (strcmp(which, "large") == 0) { M = 16; K = 32; N = 32; epochs = (argc > 2 ? epochs : 50); }
    else { M = 8; K = 16; N = 16; }
    srand(7);
    clock_t t0 = clock();
    run_bench(M, K, N, epochs, lr);
    clock_t t1 = clock();
    double ms = (double)(t1 - t0) * 1000.0 / CLOCKS_PER_SEC;
    printf("  pure C %s %d epoch: %.1f ms\n", which, epochs, ms);
    return 0;
}
