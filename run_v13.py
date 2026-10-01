# -*- coding: utf-8 -*-
"""tl v0.13 验证：
①kernels.tl 参考 VM == tlb Python 内核（逐位）
②自研机器码（tl_emit）== 参考 VM（逐位，随机数据）
③机器码 mm2 == C 内核 tl_mm2（逐位）+ 性能 vs C（kernels.dll）
④回归 v0.12（子进程）
"""
import io, os, sys, time, random, ctypes, subprocess
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
import tl_kern, tlb, tl_emit

ok_all = True
phase_ok = True
def ok(name, cond, extra=""):
    global ok_all, phase_ok
    print(("  [通过] " if cond else "  [失败] ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        ok_all = False
        phase_ok = False

# 解析 kernels.tl
src = io.open(os.path.join(D, "kernels.tl"), encoding="utf-8").read()
kerns = tl_kern.parse(src)
by_name = {k.name: k for k in kerns}

random.seed(11)
def rnd_mat(r, c): return [random.uniform(-1, 1) for _ in range(r * c)]
def rnd_vec(n): return [random.uniform(-1, 1) for _ in range(n)]

# ---------- ① 参考 VM == tlb ----------
print("[验证 1] kernels.tl 参考 VM == tlb Python 内核")
A = rnd_mat(3, 4); B = rnd_mat(4, 5); X = rnd_vec(12); Y = rnd_vec(12); G = rnd_vec(12)
env = tl_kern.run_kernel(by_name["mm2"], [list(A), list(B), [0.0]*15, 3, 4, 5])
tl_mm = tlb._matmul2([[A[r*4+c] for c in range(4)] for r in range(3)],
                     [[B[r*5+c] for c in range(5)] for r in range(4)])
ref_mm = [v for row in tl_mm for v in row]
ok("mm2", env["out"] == ref_mm)
env = tl_kern.run_kernel(by_name["relu"], [list(X), [0.0]*12, 12])
ok("relu", env["out"] == [x if x > 0 else 0.0 for x in X])
env = tl_kern.run_kernel(by_name["elem2_add"], [list(X), list(Y), [0.0]*12, 12])
ok("elem2_add", env["out"] == [a+b for a, b in zip(X, Y)])
env = tl_kern.run_kernel(by_name["upd"], [list(X), list(G), [0.0]*12, 12, 0.1])
ok("upd", env["out"] == [x - 0.1*g for x, g in zip(X, G)])
env = tl_kern.run_kernel(by_name["relu_mask"], [list(X), list(G), [0.0]*12, 12])
ok("relu_mask", env["out"] == [g if x > 0 else 0.0 for x, g in zip(X, G)])
env = tl_kern.run_kernel(by_name["sqg"], [list(X), list(G), [0.0]*12, 12])
ok("sqg", env["out"] == [2.0*x*g for x, g in zip(X, G)])
stage1_ok = phase_ok

# ---------- ② 机器码 == 参考 VM ----------
phase_ok = True
print("[验证 2] 自研机器码（tl_emit）== kernels.tl 参考 VM")
mks = tl_emit.build_kernels(kerns)
def mk_arr(lst):
    return (ctypes.c_double * len(lst))(*lst)
def out_buf(n):
    return (ctypes.c_double * n)()

def call1(name, args, n):
    """args: 前段 list 指针参数 + 标量；返回输出 list"""
    fn = mks[name].fn
    if name == "relu":
        xa = mk_arr(args[0]); ob = out_buf(n)
        fn(ctypes.addressof(xa), ctypes.addressof(ob), args[1])
        return list(ob)
    if name in ("elem2_add", "elem2_sub", "elem2_mul"):
        aa = mk_arr(args[0]); ba = mk_arr(args[1]); ob = out_buf(n)
        fn(ctypes.addressof(aa), ctypes.addressof(ba), ctypes.addressof(ob), args[2])
        return list(ob)
    if name == "scale":
        xa = mk_arr(args[0]); ob = out_buf(n)
        fn(ctypes.addressof(xa), ctypes.addressof(ob), args[1], args[2])
        return list(ob)
    if name == "upd":
        va = mk_arr(args[0]); ga = mk_arr(args[1]); ob = out_buf(n)
        fn(ctypes.addressof(va), ctypes.addressof(ga), ctypes.addressof(ob), args[2], args[3])
        return list(ob)
    if name in ("relu_mask", "sqg"):
        xa = mk_arr(args[0]); ga = mk_arr(args[1]); ob = out_buf(n)
        fn(ctypes.addressof(xa), ctypes.addressof(ga), ctypes.addressof(ob), args[2])
        return list(ob)
    raise KeyError(name)

for name in ["relu", "elem2_add", "elem2_sub", "elem2_mul", "scale", "upd", "relu_mask", "sqg"]:
    for trial in range(20):
        n = random.randint(1, 64)
        a = rnd_vec(n); b = rnd_vec(n)
        if name == "relu":
            env = tl_kern.run_kernel(by_name[name], [a, [0.0]*n, n])
            got = call1(name, [a, n], n)
        elif name in ("elem2_add", "elem2_sub", "elem2_mul"):
            env = tl_kern.run_kernel(by_name[name], [a, b, [0.0]*n, n])
            got = call1(name, [a, b, n], n)
        elif name == "scale":
            cv = random.uniform(-2, 2)
            env = tl_kern.run_kernel(by_name[name], [a, [0.0]*n, n, cv])
            got = call1(name, [a, n, cv], n)
        elif name == "upd":
            lr = random.uniform(-1, 1)
            env = tl_kern.run_kernel(by_name[name], [a, b, [0.0]*n, n, lr])
            got = call1(name, [a, b, n, lr], n)
        elif name in ("relu_mask", "sqg"):
            env = tl_kern.run_kernel(by_name[name], [a, b, [0.0]*n, n])
            got = call1(name, [a, b, n], n)
        if env["out"] != got:
            ok(f"{name} trial{trial}", False, f"首个差异 {next((i for i,(x,y) in enumerate(zip(env['out'],got)) if x!=y),None)}")
            break
    else:
        ok(name, True, "20 轮随机逐位一致")

# mm2 机器码
ok_mm = True
for trial in range(20):
    M = random.randint(1, 8); K = random.randint(1, 8); N = random.randint(1, 8)
    a = rnd_mat(M, K); b = rnd_mat(K, N)
    env = tl_kern.run_kernel(by_name["mm2"], [a, b, [0.0]*(M*N), M, K, N])
    ap = mk_arr(a); bp = mk_arr(b); ob = out_buf(M*N)
    mks["mm2"].fn(ctypes.addressof(ap), ctypes.addressof(bp), ctypes.addressof(ob), M, K, N)
    got = list(ob)
    if got != env["out"]:
        ok("mm2", False, f"trial{trial} 首个差异 {next((i for i,(x,y) in enumerate(zip(env['out'],got)) if x!=y),None)}")
        ok_mm = False
        break
if ok_mm: ok("mm2", True, "20 轮随机逐位一致")
stage2_ok = phase_ok

# ---------- ③ 机器码 mm2 == C 内核 + 性能 ----------
phase_ok = True
print("[验证 3] 机器码 mm2 vs C 内核（kernels.dll）")
nk = tlb._enable_native()
ok("kernels.dll 加载", nk is not None)

M, K, N = 64, 64, 64
a = rnd_mat(M, K); b = rnd_mat(K, N)
c_ref = nk.mm2([[a[r*K+c] for c in range(K)] for r in range(M)],
               [[b[r*N+c] for c in range(N)] for r in range(K)])
c_flat = [v for row in c_ref for v in row]
aa = mk_arr(a); ba = mk_arr(b); ob = out_buf(M*N)
mks["mm2"].fn(ctypes.addressof(aa), ctypes.addressof(ba), ctypes.addressof(ob), M, K, N)
got = list(ob)
ok("机器码 mm2 == C tl_mm2（逐位）", got == c_flat)

# 性能：机器码 vs C（256×256×10）
S = 256
a = rnd_mat(S, S); b = rnd_mat(S, S)
aa = mk_arr(a); ba = mk_arr(b); ob = out_buf(S*S)
t0 = time.perf_counter()
for _ in range(10):
    mks["mm2"].fn(ctypes.addressof(aa), ctypes.addressof(ba), ctypes.addressof(ob), S, S, S)
t_mach = (time.perf_counter() - t0) * 1000
a2 = [[a[r*S+c] for c in range(S)] for r in range(S)]
b2 = [[b[r*S+c] for c in range(S)] for r in range(S)]
t0 = time.perf_counter()
for _ in range(10):
    nk.mm2(a2, b2)
t_c = (time.perf_counter() - t0) * 1000
ok(f"256×256×10：机器码 {t_mach:.1f}ms vs C {t_c:.1f}ms（机器码/C = {t_mach/t_c:.2f}）", t_mach > 0)
stage3_ok = phase_ok

# ---------- ④ 回归 ----------
print("[验证 4] 回归 v0.12")
r = subprocess.run(
    [sys.executable, "run_v12.py"],
    cwd=D,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
)
ok("run_v12.py exit=0", r.returncode == 0, f"(exit={r.returncode})")

print()
print("=" * 60)
print("tl v0.13 总结：")
print(f"  1. tl 内核参考语义（kernels.tl == tlb）-> {'通过' if stage1_ok else '失败'}")
print(f"  2. 自研机器码（tl_emit）-> {'通过' if stage2_ok else '失败'}")
print(f"  3. 机器码 vs C -> {'通过' if stage3_ok else '失败'}")
print(f"  4. 回归 v0.12 -> {'通过' if r.returncode == 0 else '失败'}")
for k in mks.values():
    k.free()
sys.exit(0 if (ok_all and r.returncode == 0) else 1)
