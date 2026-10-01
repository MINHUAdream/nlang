# -*- coding: utf-8 -*-
"""tl v0.11 验证：原生内核后端（kernels.dll via ctypes，Python VM 只留调度）。

验证 1：内核级逐位一致 —— 每个原生内核 vs Python 内核（随机输入逐位相等）
验证 2：训练逐位一致 —— 原生 VM vs Python VM（24 epoch loss 序列逐位 + 中间值）
验证 3：内核 micro-benchmark —— 256×256 matmul：Python vs 原生
验证 4：模型测速 —— big/large encoder block：原生 vs Python 加速比
验证 5：回归 v0.10（含调度器编译）
"""
import io
import os
import random
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tlb
import tl

HERE = os.path.dirname(os.path.abspath(__file__))

print("=" * 62)
print("tl v0.11 —— 原生内核后端：自研 C 内核（kernels.dll），零第三方运行时")
print("=" * 62)

nk = tlb._enable_native()
print("  原生内核加载: %s" % ("kernels.dll" if nk else "失败（回退 Python）"))
if nk is None:
    sys.exit(1)

BASE_PROG = io.open(os.path.join(HERE, "transformer_block.tl"), encoding="utf-8").read()


def rnd_mat(rows, cols, seed):
    r = random.Random(seed)
    return [[r.uniform(-1.0, 1.0) for _ in range(cols)] for _ in range(rows)]


# ---- Python 参考实现（与 tlb 前端语义一致，用于 native 对比） ----
def _scaled_mm_ref(a, b, cv):
    return [[e / cv for e in row] for row in tlb._matmul2(a, b)]


def _scaled_mm_t_ref(a, b, cv):
    mb = [[sum(a[m][k] * b[n][k] for k in range(len(a[0])))
           for n in range(len(b))] for m in range(len(a))]
    return [[e / cv for e in row] for row in mb]


def _scaled_mm_back_ref(a, b, g, cv):
    mvi = tlb._matmul2(a, b)
    bt = tlb._transpose2(b)
    at = tlb._transpose2(a)
    ga = tlb._matmul2([[e / cv for e in row] for row in g], bt)
    gb = tlb._matmul2(at, [[e / cv for e in row] for row in g])
    dc = -sum(g[m][n] * mvi[m][n]
              for m in range(len(g)) for n in range(len(g[0]))) / (cv * cv)
    return [ga, gb, dc]


def _scaled_mm_t_back_ref(a, b, g, cv):
    mvi = tlb._matmul2(a, tlb._transpose2(b))
    ga = [[sum(g[m][n] * b[n][k] for n in range(len(b))) / cv
           for k in range(len(b[0]))] for m in range(len(a))]
    gb = [[sum(g[m][n] * a[m][k] for m in range(len(a))) / cv
           for k in range(len(b[0]))] for n in range(len(b))]
    dc = -sum(g[m][n] * mvi[m][n]
              for m in range(len(g)) for n in range(len(g[0]))) / (cv * cv)
    return [ga, gb, dc]


def _affine2_ref(a, b, bias):
    M, N = len(a), len(b[0])
    z = [[sum(a[m][k] * b[k][n] for k in range(len(b))) for n in range(N)]
         for m in range(M)]
    if len(bias) == N:
        return [[z[m][n] + bias[n] for n in range(N)] for m in range(M)]
    cv = bias[0]
    return [[z[m][n] + cv for n in range(N)] for m in range(M)]


def _affine2v_ref(a, b, bias):
    sa0 = len(a)
    z0 = tlb._matmul2v(a, b)
    if len(bias) == sa0:
        return [z0[m] + bias[m] for m in range(sa0)]
    return [x + bias[0] for x in z0]


def _affine2_back_ref(a, b, g, bias, relu_flag):
    N = len(b[0])
    z = _affine2_ref(a, b, bias)
    g2 = [[(gi if zi > 0 else 0.0) for zi, gi in zip(zz, gg)]
          for zz, gg in zip(z, g)] if relu_flag else g
    bt = tlb._transpose2(b)
    at = tlb._transpose2(a)
    ga = tlb._matmul2(g2, bt)
    gb = tlb._matmul2(at, g2)
    if len(bias) == N:
        gb_bias = tlb._colsum(g2, N)
    else:
        gb_bias = sum(g2[m][n]
                      for m in range(len(g2)) for n in range(len(g2[0])))
    return [ga, gb, gb_bias]


# ---------------------------------------------------------------------------
# 验证 1：内核级逐位一致
# ---------------------------------------------------------------------------
print("\n[验证 1] 内核级逐位一致（原生 == Python，随机输入）")
tlb._NK = None   # 关原生 → Python 内核
ok1 = True
checks = []


def chk(name, native_fn, python_fn, *args):
    global ok1
    try:
        rn = native_fn(*args)
        rp = python_fn(*args)
        eq = rn == rp
        if not eq:
            ok1 = False
            print("  ✗ %s 不一致（差异 %.2e）" % (name, _maxdiff(rn, rp)))
        checks.append((name, eq))
    except Exception as e:
        ok1 = False
        checks.append((name, False))
        print("  ✗ %s 异常: %s" % (name, e))


def _maxdiff(a, b):
    out = 0.0
    stack = [(a, b)]
    while stack:
        x, y = stack.pop()
        if isinstance(x, list):
            for u, v in zip(x, y):
                stack.append((u, v))
        else:
            out = max(out, abs(x - y))
    return out


A2 = rnd_mat(5, 4, 1)
B2 = rnd_mat(4, 6, 2)      # [K,N]：mm2 / scaled_mm / affine2
B2T = rnd_mat(6, 4, 2)     # [N,K]：scaled_mm_t（语义 a@b^T）
B1 = [0.1, -0.2, 0.3, -0.4]
G2 = rnd_mat(5, 4, 3)      # 与 A2 同形（upd/relu_mask/sqg）
G26 = rnd_mat(5, 6, 3)     # [M,N]：colsum / softmax_grad / scaled_mm 反向
S2 = rnd_mat(5, 6, 4)
R2 = rnd_mat(5, 4, 5)      # 与 A2 同形（elem2/relu/sq）
bias_v = [0.1, -0.1, 0.2, -0.2, 0.3, -0.3]

chk("mm2", nk.mm2, tlb._matmul2, A2, B2)
chk("mm2v", nk.mm2v, tlb._matmul2v, A2, B1)
chk("elem2+", lambda a, b: nk.elem2(a, b, 0),
    lambda a, b: tlb._elemwise2(a, b, tlb._add2), A2, R2)
chk("elem2*", lambda a, b: nk.elem2(a, b, 2),
    lambda a, b: tlb._elemwise2(a, b, tlb._mul2), A2, R2)
chk("relu", nk.relu, tlb._relu, R2)
chk("sq", nk.sq, lambda a: tlb._elemwise2(a, a, tlb._mul2), R2)
chk("scale", nk.scale, lambda a, cv: tlb._rec_map(a, lambda x: x / cv), A2, 2.0)
chk("scg", nk.scg, lambda g, cv: tlb._rec_map(g, lambda v: v / cv), G2, 2.0)
chk("upd", nk.upd, lambda v, g, lr: tlb._upd(v, g, lr), A2, G2, 0.2)
chk("relu_mask", nk.relu_mask, tlb._relu_mask, R2, G2)
chk("sqg", nk.sqg, tlb._sqg, R2, G2)
chk("softmax", nk.softmax, tlb._rows_softmax, A2)
chk("total", nk.total, tlb._total, A2)
chk("softmax_grad", nk.softmax_grad, tlb._softmax_grad, S2, G26)
chk("transpose", nk.transpose, tlb._transpose2, A2)
chk("colsum", nk.colsum, lambda g, nc: tlb._colsum(g, nc), G26, 6)
chk("scaled_mm", nk.scaled_mm, _scaled_mm_ref, A2, B2, 2.0)
chk("scaled_mm_t", nk.scaled_mm_t, _scaled_mm_t_ref, A2, B2T, 2.0)
r_n = nk.scaled_mm_back(A2, B2, G26, 2.0)
r_p = _scaled_mm_back_ref(A2, B2, G26, 2.0)
ok_sb = r_n[0] == r_p[0] and r_n[1] == r_p[1] and r_n[2] == r_p[2]
checks.append(("scaled_mm_back", ok_sb))
ok1 = ok1 and ok_sb
r_tb = nk.scaled_mm_t_back(A2, B2T, G26, 2.0)
r_pb = _scaled_mm_t_back_ref(A2, B2T, G26, 2.0)
ok_tb = (r_tb[0] == r_pb[0]) and (r_tb[1] == r_pb[1]) and (r_tb[2] == r_pb[2])
checks.append(("scaled_mm_t_back", ok_tb))
ok1 = ok1 and ok_tb
chk("affine2", lambda a, b, bs: nk.affine2(a, b, bs, False),
    _affine2_ref, A2, B2, bias_v[:6])
chk("affine2v", lambda a, b, bs: nk.affine2v(a, b, bs, False),
    _affine2v_ref, A2, B1, bias_v[:5])
r_ab = nk.affine2_back(A2, B2, G26, bias_v[:6], True)
r_pab = _affine2_back_ref(A2, B2, G26, bias_v[:6], True)
ok_ab = r_ab[0] == r_pab[0] and r_ab[1] == r_pab[1] and r_ab[2] == r_pab[2]
checks.append(("affine2_back", ok_ab))
ok1 = ok1 and ok_ab

tlb._NK = nk
print("  通过 %d/%d 项" % (sum(1 for _, e in checks if e), len(checks)))
if not ok1:
    sys.exit(1)

# ---------------------------------------------------------------------------
# 验证 2：训练逐位一致（原生 VM vs Python VM）
# ---------------------------------------------------------------------------
print("\n[验证 2] 训练逐位一致（原生 VM vs Python VM，24 epoch）")
plan = tl.compile_training(BASE_PROG)
prog, _ = tlb.build_program(BASE_PROG)
tlb._NK = nk
vm_n = tlb.BytecodeVM(prog)
losses_n = vm_n.run(24, lr=0.2, seed=7)
tlb._NK = None
vm_p = tlb.BytecodeVM(prog)
losses_p = vm_p.run(24, lr=0.2, seed=7)
tlb._NK = nk
ok2 = losses_n == losses_p
print("  原生 首 %.12f → 末 %.12f；与 Python VM 逐位一致: %s"
      % (losses_n[0], losses_n[-1], ok2))

# ---------------------------------------------------------------------------
# 验证 3：内核 micro-benchmark（256×256 matmul）
# ---------------------------------------------------------------------------
print("\n[验证 3] 内核 micro-benchmark（256×256 matmul ×10 次）")
A256 = rnd_mat(256, 256, 21)
B256 = rnd_mat(256, 256, 22)
tlb._NK = nk
t0 = time.perf_counter()
for _ in range(10):
    nk.mm2(A256, B256)
t_nat = time.perf_counter() - t0
tlb._NK = None
t0 = time.perf_counter()
for _ in range(10):
    tlb._matmul2(A256, B256)
t_py = time.perf_counter() - t0
tlb._NK = nk
print("  原生: %.1f ms | Python: %.1f ms | 加速比: %.1fx"
      % (t_nat * 1000, t_py * 1000, t_py / t_nat))
ok3 = t_py / t_nat > 20

# ---------------------------------------------------------------------------
# 验证 4：模型测速
# ---------------------------------------------------------------------------
print("\n[验证 4] 模型测速（原生 vs Python VM）")
BIG = io.open(os.path.join(HERE, "transformer_block_big.tl"), encoding="utf-8").read()
LARGE = io.open(os.path.join(HERE, "transformer_block_large.tl"), encoding="utf-8").read()
prog_big, _ = tlb.build_program(BIG)
prog_large, _ = tlb.build_program(LARGE)


def bench_vm(prog_, epochs, native):
    tlb._NK = nk if native else None
    t0 = time.perf_counter()
    tlb.BytecodeVM(prog_).run(epochs, lr=0.2, seed=7)
    dt = time.perf_counter() - t0
    tlb._NK = nk
    return dt


E_BIG, E_LARGE = 400, 50
t_big_py = bench_vm(prog_big, E_BIG, False)
t_big_nt = bench_vm(prog_big, E_BIG, True)
t_lg_py = bench_vm(prog_large, E_LARGE, False)
t_lg_nt = bench_vm(prog_large, E_LARGE, True)
print("  big   [8,16]×d=32  %d epoch：Python %.1f ms | 原生 %.1f ms | %.1fx"
      % (E_BIG, t_big_py * 1000, t_big_nt * 1000, t_big_py / t_big_nt))
print("  large [16,32]×d=64 %d epoch：Python %.1f ms | 原生 %.1f ms | %.1fx"
      % (E_LARGE, t_lg_py * 1000, t_lg_nt * 1000, t_lg_py / t_lg_nt))
# v0.11 已知边界：ctypes 展平/回填（_flat/_buf/_unflat）在小矩阵下吃掉部分收益，
# 模型级加速 1.2–2.0x（内核级 29x）；5x+ 模型级目标留给 v0.12 扁平化数据表示。
ok4 = t_big_py / t_big_nt > 1.0 and t_lg_py / t_lg_nt > 1.0

# 原生模式下 loss 仍逐位（large 模型首末）
vm_lg = tlb.BytecodeVM(prog_large)
l_n = vm_lg.run(E_LARGE, lr=0.2, seed=7)
tlb._NK = None
vm_lg2 = tlb.BytecodeVM(prog_large)
l_p = vm_lg2.run(E_LARGE, lr=0.2, seed=7)
tlb._NK = nk
ok4 = ok4 and l_n == l_p
print("  large 原生 loss 逐位一致: %s（首 %.6f → 末 %.6f）" % (l_n == l_p, l_n[0], l_n[-1]))

# ---------------------------------------------------------------------------
# 验证 5：回归 v0.10
# ---------------------------------------------------------------------------
print("\n[验证 5] 回归 v0.10（含调度器编译，子进程）")
r = subprocess.run([sys.executable, os.path.join(HERE, "run_v10.py")],
                   capture_output=True, text=True)
ok5 = r.returncode == 0
print("  run_v10.py exit=%d" % r.returncode)
if r.returncode != 0:
    print(r.stdout[-800:])
    print(r.stderr[-500:])

print("\n[总结] tl v0.11：")
print("  1. 内核级逐位一致 -> %s" % ("通过" if ok1 else "失败"))
print("  2. 训练逐位一致（原生==Python）-> %s" % ("通过" if ok2 else "失败"))
print("  3. 256x256 matmul 加速 -> %s" % ("通过" if ok3 else "失败"))
print("  4. 模型测速 + loss 逐位 -> %s" % ("通过" if ok4 else "失败"))
print("  5. 回归 v0.10 -> %s" % ("通过" if ok5 else "失败"))
sys.exit(0 if (ok1 and ok2 and ok3 and ok4 and ok5) else 1)
