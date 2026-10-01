# -*- coding: utf-8 -*-
"""tl v0.12 验证：
①Buf 内核 vs NativeKernels 逐位（23 项）
②训练逐位：Buf 模式 vs list 模式（small 24ep + large 50ep 全序列）
③性能对比：tl(Buf VM) vs 纯 C（同图同内核，报告调度开销）
④回归 v0.11（子进程）
"""
import os, subprocess, sys, time, io

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import tlb

nk = tlb._enable_native()
bk = tlb._BK
assert nk is not None, "kernels.dll 加载失败"

ok_all = True
def ok(name, cond, extra=""):
    global ok_all
    print(("  [通过] " if cond else "  [失败] ") + name + (f"  {extra}" if extra else ""))
    if not cond: ok_all = False

# ---------- ① Buf 内核 vs NativeKernels 逐位 ----------
import random
random.seed(123)
def rnd_mat(r, c): return [[random.uniform(-1, 1) for _ in range(c)] for _ in range(r)]
def rnd_vec(n): return [random.uniform(-1, 1) for _ in range(n)]
A = rnd_mat(3, 4); B = rnd_mat(4, 6); Bv = rnd_vec(4); G = rnd_mat(3, 6); g3 = rnd_vec(3)
cv = 0.7; bias = rnd_vec(6); bv = rnd_vec(4)
BT = [[B[r][c] for r in range(4)] for c in range(6)]
S = [[0.1, 0.2, 0.3, 0.4], [0.4, 0.3, 0.2, 0.1]]

def to_buf(v): return tlb._Buf.from_list(v)
def same(a, b):
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b

def chk_buf(name, ref_f, buf_f, *args):
    r = ref_f(*args)
    rb = buf_f(*[to_buf(a) for a in args])
    if isinstance(rb, tlb._Buf):
        return same(r, rb.to_list())
    if isinstance(rb, tuple):
        return all(same(x, y.to_list()) if isinstance(y, tlb._Buf) else x == y for x, y in zip(r, rb))
    return r == rb

tests = [
    ("mm2", lambda: nk.mm2(A, B), lambda: bk.mm2(to_buf(A), to_buf(B))),
    ("mm2v", lambda: nk.mm2v(A, Bv), lambda: bk.mm2v(to_buf(A), to_buf(Bv))),
    ("mm2_back", lambda: nk.mm2_back(A, B, G), lambda: bk.mm2_back(to_buf(A), to_buf(B), to_buf(G))),
    ("elem2_add", lambda: nk.elem2(A, A, 0), lambda: bk.elem2(to_buf(A), to_buf(A), 0)),
    ("elem2_sub", lambda: nk.elem2(A, A, 1), lambda: bk.elem2(to_buf(A), to_buf(A), 1)),
    ("elem2_mul", lambda: nk.elem2(A, A, 2), lambda: bk.elem2(to_buf(A), to_buf(A), 2)),
    ("relu", lambda: nk.relu(A), lambda: bk.relu(to_buf(A))),
    ("sq", lambda: nk.sq(A), lambda: bk.sq(to_buf(A))),
    ("scale", lambda: nk.scale(A, cv), lambda: bk.scale(to_buf(A), cv)),
    ("scg", lambda: nk.scg(G, cv), lambda: bk.scg(to_buf(G), cv)),
    ("upd", lambda: nk.upd(A, G, 0.1), lambda: bk.upd(to_buf(A), to_buf(G), 0.1)),
    ("relu_mask", lambda: nk.relu_mask(A, G), lambda: bk.relu_mask(to_buf(A), to_buf(G))),
    ("sqg", lambda: nk.sqg(A, G), lambda: bk.sqg(to_buf(A), to_buf(G))),
    ("rows_softmax", lambda: nk.softmax(S), lambda: bk.rows_softmax(to_buf(S))),
    ("softmax_grad", lambda: nk.softmax_grad(S, S), lambda: bk.softmax_grad(to_buf(S), to_buf(S))),
    ("total", lambda: nk.total(S), lambda: bk.total(to_buf(S))),
    ("total_1d", lambda: nk.total(A[0]), lambda: bk.total(to_buf(A[0]))),
    ("transpose", lambda: nk.transpose(A), lambda: bk.transpose(to_buf(A))),
    ("colsum", lambda: nk.colsum(G, 6), lambda: bk.colsum(to_buf(G), 6)),
    ("scaled_mm", lambda: nk.scaled_mm(A, B, cv), lambda: bk.scaled_mm(to_buf(A), to_buf(B), cv)),
    ("scaled_mm_t", lambda: nk.scaled_mm_t(A, BT, cv), lambda: bk.scaled_mm_t(to_buf(A), to_buf(BT), cv)),
    ("scaled_mm_back", lambda: nk.scaled_mm_back(A, B, G, cv), lambda: bk.scaled_mm_back(to_buf(A), to_buf(B), to_buf(G), cv)),
    ("scaled_mm_t_back", lambda: nk.scaled_mm_t_back(A, BT, G, cv), lambda: bk.scaled_mm_t_back(to_buf(A), to_buf(BT), to_buf(G), cv)),
    ("affine2", lambda: nk.affine2(A, B, bias, 0), lambda: bk.affine2(to_buf(A), to_buf(B), to_buf(bias), 0)),
    ("affine2_relu", lambda: nk.affine2(A, B, bias, 1), lambda: bk.affine2(to_buf(A), to_buf(B), to_buf(bias), 1)),
    ("affine2v", lambda: nk.affine2v(A, Bv, bv, 0), lambda: bk.affine2v(to_buf(A), to_buf(Bv), to_buf(bv), 0)),
    ("affine2v_relu", lambda: nk.affine2v(A, Bv, bv, 1), lambda: bk.affine2v(to_buf(A), to_buf(Bv), to_buf(bv), 1)),
    ("affine2_back", lambda: nk.affine2_back(A, B, G, bias, 0), lambda: bk.affine2_back(to_buf(A), to_buf(B), to_buf(G), to_buf(bias), 0)),
    ("affine2v_back", lambda: nk.affine2v_back(A, Bv, g3, bv, 0), lambda: bk.affine2v_back(to_buf(A), to_buf(Bv), to_buf(g3), to_buf(bv), 0)),
]
print("[验证 1] Buf 内核逐位一致（BufKernels == NativeKernels）")
n_pass = 0
for name, rf, bf in tests:
    okk = chk_buf(name, rf, bf)
    ok(f"{name}", okk)
    if okk: n_pass += 1
print(f"  Buf 内核 {n_pass}/{len(tests)} 逐位一致")

# ---------- ② 训练逐位：Buf vs list ----------
print("[验证 2] 训练逐位一致（Buf 模式 == list 模式）")
def train_losses(path, epochs, seed=7, lr=0.2):
    code = io.open(path, encoding="utf-8").read()
    prog, _ = tlb.build_program(code)
    tlb._BUF = True
    l1 = tlb.BytecodeVM(prog).run(seed=seed, lr=lr, epochs=epochs)
    tlb._BUF = False
    l2 = tlb.BytecodeVM(prog).run(seed=seed, lr=lr, epochs=epochs)
    return l1, l2

l1, l2 = train_losses("transformer_block.tl", 24)
same_small = l1 == l2
ok(f"small [3,4] 24 epoch Buf==list（首 {l1[0]:.15f} 末 {l1[-1]:.15f}）", same_small)
l1, l2 = train_losses("transformer_block_large.tl", 50)
same_large = l1 == l2
ok(f"large [16,32] 50 epoch Buf==list（首 {l1[0]:.6f} 末 {l1[-1]:.6f}）", same_large)

# ---------- ③ 性能：tl(Buf VM) vs 纯 C ----------
print("[验证 3] 性能对比：tl(Buf VM) vs 纯 C（同图同内核）")
def run_tl_ms(path, epochs, seed=7, lr=0.2):
    code = io.open(path, encoding="utf-8").read()
    prog, _ = tlb.build_program(code)
    tlb._BUF = True
    vm = tlb.BytecodeVM(prog)
    t0 = time.perf_counter()
    losses = vm.run(seed=seed, lr=lr, epochs=epochs)
    return (time.perf_counter() - t0) * 1000.0, losses

def run_c_ms(which, epochs):
    exe = os.path.join(D, "bench_c.exe")
    if not os.path.exists(exe):
        return None, []
    r = subprocess.run(
        [exe, which, str(epochs)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    lines = r.stdout.strip().splitlines()
    for line in lines:
        if "pure C" in line and "ms" in line:
            ms = float(line.split("ms")[0].strip().split()[-1])
            return ms, lines
    return None, lines

# big
t_tl_big, _ = run_tl_ms("transformer_block_big.tl", 400)
r_c = run_c_ms("big", 400)
t_c_big = r_c[0] if r_c[0] is not None else 0
ratio_big = t_tl_big / t_c_big if t_c_big else float("nan")
ok(f"big 400ep：tl {t_tl_big:.1f} ms vs 纯C {t_c_big:.1f} ms → 调度开销 {ratio_big:.1f}x", t_c_big > 0)

# large
t_tl_large, _ = run_tl_ms("transformer_block_large.tl", 50)
r_c = run_c_ms("large", 50)
t_c_large = r_c[0] if r_c[0] is not None else 0
ratio_large = t_tl_large / t_c_large if t_c_large else float("nan")
ok(f"large 50ep：tl {t_tl_large:.1f} ms vs 纯C {t_c_large:.1f} ms → 调度开销 {ratio_large:.1f}x", t_c_large > 0)

print(f"[验证 4] 回归 v0.11（子进程）")
r = subprocess.run(
    [sys.executable, "run_v11.py"],
    cwd=D,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
)
ok("run_v11.py exit=0", r.returncode == 0, f"(exit={r.returncode})")

print()
print("=" * 60)
print("tl v0.12 总结：")
print(f"  1. Buf 内核逐位一致 -> {'通过' if n_pass == len(tests) else '失败'}")
print(f"  2. 训练逐位（Buf==list）-> {'通过' if same_small and same_large else '失败'}")
print(f"  3. 性能（tl vs 纯C）-> {'通过' if t_c_big > 0 and t_c_large > 0 else '失败'}")
print(f"      big   400ep: tl {t_tl_big:.1f} ms vs C {t_c_big:.1f} ms ({ratio_big:.1f}x 调度开销)")
print(f"      large  50ep: tl {t_tl_large:.1f} ms vs C {t_c_large:.1f} ms ({ratio_large:.1f}x 调度开销)")
print(f"  4. 回归 v0.11 -> {'通过' if r.returncode == 0 else '失败'}")
sys.exit(0 if (n_pass == len(tests) and same_small and same_large and t_c_big > 0 and t_c_large > 0 and r.returncode == 0) else 1)
