# -*- coding: utf-8 -*-
"""
tl v0.4 验证：融合算子真执行（编译器革命第一块真砖）
=====================================================================
验证 1：4 个融合算子 vs 纯 Python 参考（forward 数值）
验证 2：全网络融合等价性 —— Transformer block 融合前后 loss/out/全部参数梯度一致
验证 3：图规模缩减量化 —— 融合消除了多少中间算子
验证 4：融合版训练仍收敛（含 bias 广播梯度走融合路径）
验证 5：回归 —— v0.1 / v0.2 / v0.3 全部通过
"""
import sys
import os
import copy
import subprocess

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tl

HERE = os.path.dirname(os.path.abspath(__file__))


def flat(v):
    out = []

    def walk(x):
        if isinstance(x, list):
            for i in x:
                walk(i)
        else:
            out.append(x)
    walk(v)
    return out


def max_abs_diff(a, b):
    return max(abs(x - y) for x, y in zip(flat(a), flat(b)))


def inject(t, vals):
    i = 0

    def build(dim):
        nonlocal i
        if len(dim) == 1:
            r = vals[i:i + dim[0]]
            i += dim[0]
            return r
        return [build(dim[1:]) for _ in range(dim[0])]
    t.value = build(t.shape)


def count_calls(expr):
    if isinstance(expr, tl.Call):
        return 1 + sum(count_calls(a) for a in expr.args)
    return 0


def stmt_calls(st):
    if isinstance(st, tl.LetStmt):
        return count_calls(st.expr)
    if isinstance(st, tl.PrintStmt):
        return count_calls(st.expr)
    return 0


print("=" * 62)
print("tl v0.4 —— 融合算子真执行（编译器革命第一块真砖）")
print("=" * 62)

# ---------------------------------------------------------------------------
# 验证 1：融合算子 forward vs 纯 Python 参考
# ---------------------------------------------------------------------------
print("\n[验证 1] 4 个融合算子 vs 参考实现（forward）")

FUSED_CODE = """
let A = tensor([[0.5, 0.1, 0.2, 0.3], [0.4, 0.2, 0.1, 0.5], [0.3, 0.6, 0.2, 0.1]])
let B = tensor([[0.2, 0.4, 0.1], [0.3, 0.1, 0.5], [0.6, 0.2, 0.3], [0.1, 0.5, 0.2]])
let c = tensor([2.0])
let s = scaled_mm(A, B, c)
let K = tensor([[0.2, 0.4, 0.1, 0.3], [0.3, 0.1, 0.5, 0.2], [0.6, 0.2, 0.3, 0.1]])
let st = scaled_mm_t(A, K, c)
let b = tensor([0.5, -0.5, 0.1])
let af = affine(A, B, b)
let br = bias_relu(A, B, b)
"""
eng = tl.run_program(FUSED_CODE, quiet=True)
s_val = eng.vars["s"].value
st_val = eng.vars["st"].value
af_val = eng.vars["af"].value
br_val = eng.vars["br"].value

A = [[0.5, 0.1, 0.2, 0.3], [0.4, 0.2, 0.1, 0.5], [0.3, 0.6, 0.2, 0.1]]
B = [[0.2, 0.4, 0.1], [0.3, 0.1, 0.5], [0.6, 0.2, 0.3], [0.1, 0.5, 0.2]]
K = [[0.2, 0.4, 0.1, 0.3], [0.3, 0.1, 0.5, 0.2], [0.6, 0.2, 0.3, 0.1]]
b = [0.5, -0.5, 0.1]
c = 2.0


def mm(a, bb):
    return [[sum(a[i][k] * bb[k][j] for k in range(len(a[0])))
             for j in range(len(bb[0]))] for i in range(len(a))]


ref_s = [[e / c for e in row] for row in mm(A, B)]
ref_st = [[sum(A[i][k] * K[j][k] for k in range(len(A[0]))) / c
           for j in range(len(K))] for i in range(len(A))]
ref_af = [[mm(A, B)[i][j] + b[j] for j in range(len(B[0]))] for i in range(len(A))]
ref_br = [[max(0.0, v) for v in row] for row in ref_af]

checks = [
    ("scaled_mm(A,B,c)   = (A@B)/c", s_val, ref_s),
    ("scaled_mm_t(A,K,c) = (A@Kᵀ)/c", st_val, ref_st),
    ("affine(A,B,b)      = A@B + b", af_val, ref_af),
    ("bias_relu(A,B,b)   = relu(A@B+b)", br_val, ref_br),
]
ok = True
for label, got, ref in checks:
    e = max_abs_diff(got, ref)
    mark = "✅" if e < 1e-12 else "✗"
    if e >= 1e-12:
        ok = False
    print(f"  {mark} {label}：误差 {e:.2e}")
if not ok:
    sys.exit(1)

# ---------------------------------------------------------------------------
# 验证 2：全网络融合等价性（Transformer block：forward + 梯度）
# ---------------------------------------------------------------------------
print("\n[验证 2] Transformer block 融合前后等价（loss / out / 全部参数梯度）")

with open(os.path.join(HERE, "transformer_block.tl"), encoding="utf-8") as f:
    code_tb = f.read()

ast_plain, _, _ = tl.compile_program(code_tb)
ast_fused, _, fused = tl.compile_program(code_tb, do_optimize=True)
print(f"  融合报告（{len(fused)} 条）：")
for line in fused:
    print(f"    · {line}")

init = {
    "Wq": [0.1 + 0.01 * i for i in range(16)],
    "Wk": [0.2 - 0.01 * i for i in range(16)],
    "Wv": [0.05 + 0.02 * i for i in range(16)],
    "W1": [0.1 * (i % 3 + 1) for i in range(16)],
    "b1": [0.3, -0.2, 0.4, -0.1],
}


def run_with_grads(ast):
    e = tl.Engine()
    e.run(ast, quiet=True)
    for nm, vals in init.items():
        inject(e.vars[nm], vals)
    e.recompute(quiet=True)
    tl.backward(e.last_loss)
    return e, {nm: copy.deepcopy(e.vars[nm].grad) for nm in init}


eng1, g1 = run_with_grads(ast_plain)
eng2, g2 = run_with_grads(ast_fused)

e_loss = abs(eng1.last_loss.value - eng2.last_loss.value)
e_out = max_abs_diff(eng1.vars["out"].value, eng2.vars["out"].value)
print(f"  loss 误差 = {e_loss:.2e}   out 误差 = {e_out:.2e}")
max_g = 0.0
for nm in init:
    d = max_abs_diff(g1[nm], g2[nm])
    max_g = max(max_g, d)
print(f"  全部参数梯度最大误差 = {max_g:.2e}")
if e_loss < 1e-12 and e_out < 1e-12 and max_g < 1e-12:
    print("  ✅ 融合前后 loss / out / 梯度逐元素一致 —— 融合是等价变换，不改变语义")
else:
    print("  ✗ 融合等价性破坏")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 验证 3：图规模缩减量化
# ---------------------------------------------------------------------------
print("\n[验证 3] 图规模缩减（中间算子消除）")
n_plain = sum(stmt_calls(st) for st in ast_plain)
n_fused = sum(stmt_calls(st) for st in ast_fused)
print(f"  算子调用总数：未融合 {n_plain} → 融合后 {n_fused}（消除 {n_plain - n_fused} 个中间算子）")
if n_fused < n_plain:
    print("  ✅ 图规模确实缩减 —— 中间张量（scores 的 scale、FFN 的 add）不再单独创建")
else:
    print("  ✗ 图规模未缩减")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 验证 4：融合版训练仍收敛（b1 广播梯度走融合 affine 路径）
# ---------------------------------------------------------------------------
print("\n[验证 4] 融合版 Transformer 训练（24 epoch）")

TRAIN_TB = """
let X = tensor([[1.0, 0.0, 0.5, 0.2], [0.3, 1.0, 0.1, 0.4], [0.2, 0.5, 1.0, 0.3]])
let Wq = param([4, 4])
let Wk = param([4, 4])
let Wv = param([4, 4])
let Q = matmul(X, Wq)
let K = matmul(X, Wk)
let V = matmul(X, Wv)
let d = tensor([2.0])
let scores = scale(matmul(Q, transpose(K)), d)
let attn = softmax(scores)
let ctx = matmul(attn, V)
let h = add(ctx, X)
let W1 = param([4, 4])
let b1 = param([4])
let f = add(matmul(relu(h), W1), b1)
let out = add(f, h)
let target = tensor([[1.0, 0.0, 0.5, 0.2], [0.3, 1.0, 0.1, 0.4], [0.2, 0.5, 1.0, 0.3]])
let loss = mean(square(sub(out, target)))
"""
epoch_body = "\n".join(
    "update(Wq, 0.2)\nupdate(Wk, 0.2)\nupdate(Wv, 0.2)\nupdate(W1, 0.2)\nupdate(b1, 0.2)\nprint(loss)"
    for _ in range(24))
TRAIN_TB = TRAIN_TB + "print(loss)\n" + epoch_body

ast_tr, _, fused_tr = tl.compile_program(TRAIN_TB, do_optimize=True)
print(f"  融合报告：{fused_tr}")

import io
import random
eng3 = tl.Engine()
eng3.run(ast_tr, quiet=True)
random.seed(7)
for nm in ("Wq", "Wk", "Wv", "W1"):
    inject(eng3.vars[nm], [random.uniform(-0.3, 0.3) for _ in range(16)])
inject(eng3.vars["b1"], [random.uniform(-0.3, 0.3) for _ in range(4)])

buf = io.StringIO()
old = sys.stdout
sys.stdout = buf
eng3.recompute(quiet=False)
sys.stdout = old
out_lines = buf.getvalue().strip().split("\n")
tl_losses = [float(ln.split()[0]) for ln in out_lines if ln.strip()]
print(f"  epoch 0 loss = {tl_losses[0]:.6f}  →  epoch {len(tl_losses)-1} loss = {tl_losses[-1]:.6f}")
print(f"  loss 序列：{['%.3f' % v for v in tl_losses]}")
if tl_losses[-1] < tl_losses[0] and tl_losses[-1] < 2e-2:
    print("  ✅ 融合版训练收敛 —— 融合算子的反向路径（含广播 bias 梯度）数值正确")
else:
    print("  ✗ 融合版训练未收敛")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 验证 5：回归
# ---------------------------------------------------------------------------
print("\n[验证 5] 回归：v0.1 / v0.2 / v0.3")
regs = ["run_demo.py", "train_demo.py", "run_v02.py", "run_v03.py"]
for r in regs:
    p = subprocess.run([sys.executable, os.path.join(HERE, r)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = p.returncode == 0
    print(f"  {'✅' if ok else '✗'} {r} (exit={p.returncode})")
    if not ok:
        print(p.stdout[-800:])
        print(p.stderr[-800:])
        sys.exit(1)

print("\n[总结] tl v0.4 已验证：")
print("  1. 4 个融合算子（scaled_mm_t/scaled_mm/affine/bias_relu）forward 与参考一致")
print("  2. 融合是等价变换：Transformer block 融合前后 loss/out/梯度逐元素一致")
print("  3. 图规模真实缩减：中间算子被编译器消除")
print("  4. 融合版训练收敛：编译器革命的优化路径不破坏语义")
print("  5. v0.1 / v0.2 / v0.3 全部回归通过")
