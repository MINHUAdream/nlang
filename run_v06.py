# -*- coding: utf-8 -*-
"""
tl v0.6 验证：内存后端 —— 把 v0.5 的内存决策报告变成真实执行
=====================================================================
验证 1：三策略峰值实测（naive / conservative / checkpoint）
验证 2：语义等价 —— 三策略单步 loss 逐位一致（检查点不改变训练语义）
验证 3：训练语义全程等价 —— 三策略 24 epoch loss 序列逐位一致
验证 4：检查点收敛 —— checkpoint 24 epoch 单调下降
验证 5：回归 —— v0.1 / v0.2 / v0.3 / v0.4 / v0.5 全部通过
"""
import sys
import os
import subprocess

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tl

HERE = os.path.dirname(os.path.abspath(__file__))

TRAIN_PROG = """
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


def losses_eq(a, b, tol=1e-12):
    return len(a) == len(b) and all(abs(x - y) < tol for x, y in zip(a, b))


print("=" * 62)
print("tl v0.6 —— 内存后端（决策 → 执行）")
print("=" * 62)

plan = tl.compile_training(TRAIN_PROG)
mem = plan.mem
print(f"  融合报告：{plan.fused}")
print(f"  编译识别参数：{plan.params}")
print(f"  理论 naive 峰值：{mem['naive_bytes']:.0f} B")
print(f"  理论保守峰值：{mem['planned_bytes']:.0f} B")
print(f"  理论检查点峰值：{mem['ckpt_bytes']:.0f} B")
print(f"  检查点候选：{mem['ckpt_candidates']}")

# ---------------------------------------------------------------------------
# 验证 1：三策略峰值实测
# ---------------------------------------------------------------------------
print("\n[验证 1] 三策略峰值实测（真实内存账本，8B/元素）")

peaks = {}
for strat in ("naive", "conservative", "checkpoint"):
    losses, eng = plan.run(1, lr=0.2, seed=7, mem_strategy=strat)
    peaks[strat] = eng.mem_peak
    print(f"  {strat:<14} 峰值 {eng.mem_peak:6.0f} B")

naive, cons, ckpt = peaks["naive"], peaks["conservative"], peaks["checkpoint"]
print(f"  保守 vs naive：↓ {(1 - cons / naive) * 100:.1f}%")
print(f"  检查点 vs naive：↓ {(1 - ckpt / naive) * 100:.1f}%")
if ckpt < cons < naive:
    print("  ✅ 编译器执行的三档策略峰值递减 —— 内存后端真实释放/丢弃激活，不是报告")
else:
    print("  ✗ 峰值未按策略递减")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 验证 2：单步语义等价（12 位一致）
# ---------------------------------------------------------------------------
print("\n[验证 2] 单步语义等价（检查点不改变训练语义）")

l1 = {}
for strat in ("naive", "conservative", "checkpoint"):
    losses, _ = plan.run(1, lr=0.2, seed=7, mem_strategy=strat)
    l1[strat] = losses[0]
    print(f"  {strat:<14} 单步 loss = {losses[0]:.12f}")
if abs(l1["naive"] - l1["conservative"]) < 1e-12 and abs(l1["naive"] - l1["checkpoint"]) < 1e-12:
    print("  ✅ 三种策略单步 loss 逐位一致 —— 释放/重算不影响数值")
else:
    print("  ✗ 单步 loss 不一致")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 验证 3：24 epoch 全程语义等价
# ---------------------------------------------------------------------------
print("\n[验证 3] 24 epoch 全程语义等价（loss 序列逐位一致）")

seqs = {}
for strat in ("naive", "conservative", "checkpoint"):
    losses, _ = plan.run(24, lr=0.2, seed=7, mem_strategy=strat)
    seqs[strat] = losses
    print(f"  {strat:<14} 24 epoch: {losses[0]:.6f} → {losses[-1]:.6f}")
if losses_eq(seqs["naive"], seqs["conservative"]) and losses_eq(seqs["naive"], seqs["checkpoint"]):
    print("  ✅ 三种策略 24 epoch loss 序列逐位一致 —— 检查点 + 重算 = 零语义损失")
else:
    print("  ✗ loss 序列不一致")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 验证 4：检查点收敛
# ---------------------------------------------------------------------------
print("\n[验证 4] 检查点训练收敛")
ck = seqs["checkpoint"]
if ck[-1] < ck[0] and ck[-1] < 2e-2:
    print(f"  ✅ checkpoint 24 epoch 收敛：{ck[0]:.6f} → {ck[-1]:.6f}")
else:
    print("  ✗ 未收敛")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 验证 5：回归
# ---------------------------------------------------------------------------
print("\n[验证 5] 回归：v0.1 / v0.2 / v0.3 / v0.4 / v0.5")
regs = ["run_demo.py", "train_demo.py", "run_v02.py", "run_v03.py", "run_v04.py", "run_v05.py"]
for r in regs:
    p = subprocess.run([sys.executable, os.path.join(HERE, r)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = p.returncode == 0
    print(f"  {'✅' if ok else '✗'} {r} (exit={p.returncode})")
    if not ok:
        print(p.stdout[-800:])
        print(p.stderr[-800:])
        sys.exit(1)

print("\n[总结] tl v0.6 已验证：")
print(f"  1. 内存后端真执行：naive {naive:.0f}B → conservative {cons:.0f}B（↓{(1-cons/naive)*100:.1f}%）"
      f" → checkpoint {ckpt:.0f}B（↓{(1-ckpt/naive)*100:.1f}%）")
print("  2. 单步 loss 逐位一致：释放/重算不改变数值")
print("  3. 24 epoch loss 序列逐位一致：检查点 + 重算 = 零语义损失")
print("  4. 检查点训练收敛")
print("  5. v0.1 / v0.2 / v0.3 / v0.4 / v0.5 全部回归通过")
