# -*- coding: utf-8 -*-
"""
tl v0.2 验证：attention 前向数值正确 + softmax 性质 + 语言内训练（update 语句）
=====================================================================
验证 1：softmax 输出每行和为 1（概率分布性质）
验证 2：attention 前向 vs 纯 Python 参考实现，误差 < 1e-9
验证 3：语言内 update(W, lr) 训练闭环——loss 单调下降且收敛
"""
import sys
import os
import math

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tl

HERE = os.path.dirname(os.path.abspath(__file__))

Q = [[0.5, 0.1, 0.2, 0.3], [0.1, 0.4, 0.6, 0.1], [0.3, 0.2, 0.1, 0.5]]
K = [[0.2, 0.3, 0.4, 0.1], [0.5, 0.1, 0.2, 0.3], [0.1, 0.6, 0.3, 0.2]]
V = [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]


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


# ---------------------------------------------------------------------------
# 验证 1 + 2：attention 前向
# ---------------------------------------------------------------------------
print("=" * 62)
print("tl v0.2 —— attention / softmax / 语言内训练")
print("=" * 62)

with open(os.path.join(HERE, "attention.tl"), encoding="utf-8") as f:
    code = f.read()

eng = tl.run_program(code, quiet=True)
attn = eng.vars["attn"].value
ctx = eng.vars["ctx"].value

print("\n[验证 1] softmax 性质")
row_sums = [sum(r) for r in attn]
print(f"  attn 每行和：{row_sums}")
if all(abs(s - 1.0) < 1e-9 for s in row_sums):
    print("  ✅ 每行和为 1，是合法的概率分布")
else:
    print("  ✗ 行和不为 1")
    sys.exit(1)

print("\n[验证 2] attention 前向 vs Python 参考实现")
# 参考实现
def ref_attention(Q, K, V):
    d = math.sqrt(len(Q[0]))
    S = len(Q)
    qk = [[sum(Q[i][j] * K[k][j] for j in range(len(Q[0]))) / d
           for k in range(S)] for i in range(S)]
    attn = []
    for row in qk:
        m = max(row)
        ex = [math.exp(v - m) for v in row]
        s = sum(ex)
        attn.append([e / s for e in ex])
    ctx = [[sum(attn[i][k] * V[k][j] for k in range(S)) for j in range(len(V[0]))]
           for i in range(S)]
    return attn, ctx

ref_attn, ref_ctx = ref_attention(Q, K, V)
e1 = max_abs_diff(attn, ref_attn)
e2 = max_abs_diff(ctx, ref_ctx)
print(f"  attn 最大误差 = {e1:.2e}")
print(f"  ctx  最大误差 = {e2:.2e}")
if e1 < 1e-9 and e2 < 1e-9:
    print("  ✅ 与参考实现一致（< 1e-9）—— tl 的 attention 前向数值正确")
else:
    print("  ✗ 误差超限")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 验证 3：语言内训练（update 语句，无需宿主 Python 驱动）
# ---------------------------------------------------------------------------
print("\n[验证 3] 语言内训练：update(W, lr) 语法（20 个 update = 20 epoch）")

TRAIN_CODE = """
let x = tensor([1.0, 2.0, 3.0])
let W = param([1, 3])
let b = param([1])
let target = tensor([7.0])
let pred = add(matmul(W, x), b)
let err = sub(pred, target)
let loss = mean(square(err))
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
update(W, 0.02)
print(loss)
"""

# 语言内 print 在 update 之间输出每步 loss；捕获 stdout 逐行读取
import io
buf = io.StringIO()
old = sys.stdout
sys.stdout = buf
tl.run_program(TRAIN_CODE)
sys.stdout = old
out_lines = buf.getvalue().strip().split("\n")
losses = []
for ln in out_lines:
    # 形如 "  123.456789  （形状 ()）"
    losses.append(float(ln.split()[0]))

print(f"  epoch 0 loss = {losses[0]:.6f}")
print(f"  epoch 9 loss = {losses[9]:.6f}")
print(f"  epoch 19 loss = {losses[-1]:.6f}")
print(f"  loss 序列（每 5 epoch）：{['%.4f' % losses[i] for i in range(0, 20, 5)]}")

mono = all(losses[i] >= losses[i + 1] - 1e-9 for i in range(len(losses) - 1))
if losses[-1] < losses[0] * 0.01 and losses[-1] < 1e-2 and mono:
    ratio = losses[0] / max(losses[-1], 1e-12)
    print(f"  ✅ 语言内训练收敛：loss {losses[0]:.4f} → {losses[-1]:.8f}（下降 "
          f"{ratio:.0f}x），且单调下降")
else:
    print(f"  ✗ 未收敛（最终={losses[-1]:.4f}, 单调={mono}）")
    sys.exit(1)

print("\n[总结] tl v0.2 新增能力已验证：")
print("  1. 算子：transpose / scale / softmax / mean / square —— attention 前向全用 tl 语言表达")
print("  2. softmax 输出是合法概率分布（每行和=1）")
print("  3. attention 前向与参考实现误差 < 1e-9")
print("  4. update(W, lr) 训练语法进语言 —— 训练不再需要宿主 Python 驱动")
