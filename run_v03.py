# -*- coding: utf-8 -*-
"""
tl v0.3 验证：多头 attention / 完整 Transformer block / 图优化雏形 / 回归
=====================================================================
验证 1：多头 attention（3D batch matmul + 3D softmax）vs 参考实现
验证 2：完整 Transformer encoder block（注入非零参数后）vs 参考实现
验证 3：Transformer block 训练（语言内 update 多参数）—— loss 下降
验证 4：图优化雏形 —— 常量折叠 + 融合检测
验证 5：回归 —— v0.1 / v0.2 脚本仍全部通过
"""
import sys
import os
import math
import subprocess

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tl

HERE = os.path.dirname(os.path.abspath(__file__))

Q3 = [[[0.5, 0.1], [0.2, 0.3], [0.1, 0.4]], [[0.3, 0.2], [0.4, 0.1], [0.2, 0.5]]]
K3 = [[[0.1, 0.2], [0.3, 0.4], [0.2, 0.1]], [[0.4, 0.3], [0.1, 0.2], [0.3, 0.1]]]
V3 = [[[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]], [[0.0, 1.0], [1.0, 0.0], [0.5, 0.5]]]


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
    """把一维数值列表按 t.shape 还原成嵌套结构写回 param。"""
    i = 0

    def build(dim):
        nonlocal i
        if len(dim) == 1:
            r = vals[i:i + dim[0]]
            i += dim[0]
            return r
        return [build(dim[1:]) for _ in range(dim[0])]
    t.value = build(t.shape)


def matmul2_ref(a, b):
    M, K = len(a), len(a[0])
    N = len(b[0])
    return [[sum(a[i][k] * b[k][j] for k in range(K)) for j in range(N)]
            for i in range(M)]


def softmax_rows(x):
    out = []
    for row in x:
        m = max(row)
        ex = [math.exp(v - m) for v in row]
        s = sum(ex)
        out.append([e / s for e in ex])
    return out


print("=" * 62)
print("tl v0.3 —— 多头 attention / Transformer block / 图优化")
print("=" * 62)

# ---------------------------------------------------------------------------
# 验证 1：多头 attention
# ---------------------------------------------------------------------------
with open(os.path.join(HERE, "attention3d.tl"), encoding="utf-8") as f:
    code3d = f.read()

eng = tl.run_program(code3d, quiet=True)
attn3 = eng.vars["attn"].value
ctx3 = eng.vars["ctx"].value

print("\n[验证 1] 多头 attention（H=2, 3D batch matmul + 3D softmax）")
row_sums_all = [sum(r) for h in attn3 for r in h]
print(f"  每行和：{['%.1f' % s for s in row_sums_all]}")
if not all(abs(s - 1.0) < 1e-9 for s in row_sums_all):
    print("  ✗ softmax 行和不为 1")
    sys.exit(1)

# 参考：逐 head 用 2D 公式
def ref_mha(Q, K, V):
    d = math.sqrt(len(Q[0][0]))
    attns, ctxs = [], []
    for h in range(len(Q)):
        q, k, v = Q[h], K[h], V[h]
        qk = [[sum(q[i][j] * k[jj][j] for j in range(len(q[0]))) / d
               for jj in range(len(q))] for i in range(len(q))]
        attn = softmax_rows(qk)
        ctx = matmul2_ref(attn, v)
        attns.append(attn)
        ctxs.append(ctx)
    return attns, ctxs

ref_attn3, ref_ctx3 = ref_mha(Q3, K3, V3)
e1 = max_abs_diff(attn3, ref_attn3)
e2 = max_abs_diff(ctx3, ref_ctx3)
print(f"  attn 最大误差 = {e1:.2e}")
print(f"  ctx  最大误差 = {e2:.2e}")
if e1 < 1e-9 and e2 < 1e-9:
    print("  ✅ 多头 attention 与参考实现一致")
else:
    print("  ✗ 误差超限")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 验证 2：完整 Transformer encoder block（注入非零参数）
# ---------------------------------------------------------------------------
print("\n[验证 2] Transformer encoder block（Q/K/V 投影 + 注意力 + 残差 + FFN + 残差）")

with open(os.path.join(HERE, "transformer_block.tl"), encoding="utf-8") as f:
    code_tb = f.read()

eng2 = tl.run_program(code_tb, quiet=True)
# 注入非零参数（否则全 0 → 空转）
init = {
    "Wq": [0.1 + 0.01 * i for i in range(16)],
    "Wk": [0.2 - 0.01 * i for i in range(16)],
    "Wv": [0.05 + 0.02 * i for i in range(16)],
    "W1": [0.1 * (i % 3 + 1) for i in range(16)],
    "b1": [0.3, -0.2, 0.4, -0.1],
}
for nm, vals in init.items():
    inject(eng2.vars[nm], vals)
eng2.recompute()

out_tb = eng2.vars["out"].value
loss_tb = eng2.vars["loss"].value

# 参考实现（纯 Python，与 tl 同公式；参数与注入值逐元素一致）
X = [[1.0, 0.0, 0.5, 0.2], [0.3, 1.0, 0.1, 0.4], [0.2, 0.5, 1.0, 0.3]]

def row_major(vals):
    return [[vals[i * 4 + j] for j in range(4)] for i in range(4)]

Wq = row_major([0.1 + 0.01 * i for i in range(16)])
Wk = row_major([0.2 - 0.01 * i for i in range(16)])
Wv = row_major([0.05 + 0.02 * i for i in range(16)])
W1 = row_major([0.1 * (i % 3 + 1) for i in range(16)])
b1 = [0.3, -0.2, 0.4, -0.1]
D = math.sqrt(4.0)


def ref_block(X, Wq, Wk, Wv, W1, b1):
    def mm(a, b):
        return [[sum(a[i][k] * b[k][j] for k in range(len(a[0]))) for j in range(len(b[0]))]
                for i in range(len(a))]

    def tr(m):
        return [[m[i][j] for i in range(len(m))] for j in range(len(m[0]))]

    def addm(a, b):
        return [[a[i][j] + b[i][j] for j in range(len(a[0]))] for i in range(len(a))]

    def relu(m):
        return [[max(0.0, v) for v in row] for row in m]

    Q = mm(X, Wq); K = mm(X, Wk); V = mm(X, Wv)
    scores = [[sum(Q[i][j] * K[k][j] for j in range(len(Q[0]))) / D
               for k in range(len(Q))] for i in range(len(Q))]
    attn = softmax_rows(scores)
    ctx = mm(attn, V)
    h = addm(ctx, X)
    f = addm(mm(relu(h), W1), [[b1[j] for j in range(4)] for _ in range(3)])
    out = addm(f, h)
    return out

ref_out = ref_block(X, Wq, Wk, Wv, W1, b1)
# 参考 loss
target = X
flat_out = flat(out_tb)
flat_ref = flat(ref_out)
mse = sum((a - b) ** 2 for a, b in zip(flat_out, flat_ref)) / len(flat_out)
e3 = max_abs_diff(out_tb, ref_out)
print(f"  out 最大误差 = {e3:.2e}")
if e3 < 1e-9:
    print("  ✅ Transformer block 前向与参考实现一致（残差/注意力/FFN 全链路）")
else:
    print("  ✗ 误差超限")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 验证 3：Transformer block 训练（语言内 update 多参数）
# ---------------------------------------------------------------------------
print("\n[验证 3] Transformer block 训练（语言内 update 全部 5 组参数，24 epoch）")

TB_PREFIX = """
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
# 24 epoch，每 epoch 更新全部 5 组参数（含广播 bias b1），中间穿插打印
epoch_body = "\n".join(
    "update(Wq, 0.2)\nupdate(Wk, 0.2)\nupdate(Wv, 0.2)\nupdate(W1, 0.2)\nupdate(b1, 0.2)\nprint(loss)"
    for _ in range(24))
TRAIN_TB = TB_PREFIX + "print(loss)\n" + epoch_body

import io
eng3 = tl.run_program(TRAIN_TB, quiet=True)
# 注入非零随机参数（否则全 0 → loss=0 空转），然后复用同一引擎训练
import random
random.seed(7)
for nm in ("Wq", "Wk", "Wv", "W1"):
    inject(eng3.vars[nm], [random.uniform(-0.3, 0.3) for _ in range(16)])
inject(eng3.vars["b1"], [random.uniform(-0.3, 0.3) for _ in range(4)])

buf = io.StringIO()
old = sys.stdout
sys.stdout = buf
eng3.recompute(quiet=False)  # 复用参数重算 forward，语言内 update 驱动训练并打印每步 loss
sys.stdout = old
out_lines = buf.getvalue().strip().split("\n")
tl_losses = [float(ln.split()[0]) for ln in out_lines if ln.strip()]
print(f"  epoch 0 loss = {tl_losses[0]:.6f}  →  epoch {len(tl_losses)-1} loss = {tl_losses[-1]:.6f}")
print(f"  loss 序列：{['%.3f' % v for v in tl_losses]}")
if tl_losses[-1] < tl_losses[0] and tl_losses[-1] < 2e-2:
    print(f"  ✅ 语言内多参数训练收敛：loss {tl_losses[0]:.4f} → {tl_losses[-1]:.6f}")
else:
    print("  ✗ 未收敛")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 验证 4：图优化雏形
# ---------------------------------------------------------------------------
print("\n[验证 4] 图优化雏形（常量折叠 + 融合检测）")

FOLD_CODE = """
let a = add(tensor([1.0, 2.0]), tensor([3.0, 4.0]))
let m = matmul(tensor([[1.0, 2.0], [3.0, 4.0]]), transpose(tensor([[1.0, 2.0], [3.0, 4.0]])))
let W = param([2, 2])
let X = tensor([[1.0, 2.0], [3.0, 4.0]])
let s = scale(matmul(W, transpose(X)), tensor([2.0]))
let o = add(matmul(W, X), tensor([0.5, -0.5]))
let r = relu(add(matmul(W, X), tensor([0.5, -0.5])))
print(a)
"""
ast, _, fused = tl.compile_program(FOLD_CODE, do_optimize=True)
folded = {}
for st in ast:
    if isinstance(st, tl.LetStmt):
        folded[st.name] = isinstance(st.expr, tl.TensorLit)
print(f"  常量折叠：a → TensorLit? {folded.get('a')}   m → TensorLit? {folded.get('m')}   "
      f"s → TensorLit? {folded.get('s')}（依赖参数，正确不折叠）")
if not folded.get("a"):
    print("  ✗ a 未折叠")
    sys.exit(1)
print(f"  融合报告（{len(fused)} 条，v0.4 起为真融合替换）：")
for line in fused:
    print(f"    · {line}")
if any("scaled_mm_t" in f or "scaled_mm" in f for f in fused):
    print("  ✅ scale(matmul(...)) 被真融合为单算子（图优化从检测升级为执行）")
else:
    print("  ✗ 未融合")
    sys.exit(1)

# 折叠后仍可正常执行
eng4 = tl.run_program(FOLD_CODE, quiet=True)
a_val = eng4.vars["a"].value
print(f"  折叠后执行 a = {a_val}（预期 [4.0, 6.0]）")
if max_abs_diff(a_val, [4.0, 6.0]) < 1e-12:
    print("  ✅ 折叠结果数值正确")
else:
    print("  ✗ 折叠结果错误")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 验证 5：回归
# ---------------------------------------------------------------------------
print("\n[验证 5] 回归：v0.1 / v0.2 脚本")
regs = ["run_demo.py", "train_demo.py", "run_v02.py"]
for r in regs:
    p = subprocess.run([sys.executable, os.path.join(HERE, r)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = p.returncode == 0
    print(f"  {'✅' if ok else '✗'} {r} (exit={p.returncode})")
    if not ok:
        print(p.stdout[-800:])
        print(p.stderr[-800:])
        sys.exit(1)

print("\n[总结] tl v0.3 已验证：")
print("  1. 3D 张量：字面量 / batch matmul / 3D transpose / 沿最后维 softmax")
print("  2. 多头 attention 前向 vs 参考实现一致")
print("  3. 完整 Transformer encoder block（投影+注意力+残差+FFN）vs 参考一致")
print("  4. 语言内多参数训练收敛")
print("  5. 图优化雏形：常量折叠 + 融合检测（杀手锏第一步）")
print("  6. v0.1 / v0.2 全部回归通过")
