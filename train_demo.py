# -*- coding: utf-8 -*-
"""
tl v0.1 训练闭环：用语言级自动微分驱动真实梯度下降
==================================================
目标：训练线性模型 pred = matmul(W, x) + b 逼近目标值 y_target。
数据固定、参数随机初始化，50 轮 SGD。loss 应单调下降，最终 W/b 逼近解析解。
"""
import sys
import os

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tl
from tl import backward

HERE = os.path.dirname(os.path.abspath(__file__))

# 用 tl 语言定义模型与损失（MSE 由 mul/sub/sum 组合）
CODE = """
let x = tensor([1.0, 2.0, 3.0])        # 输入 [3]
let W = param([1, 3])                   # 权重 [1,3]
let b = param([1])                      # 偏置 [1]
let pred = add(matmul(W, x), b)         # 预测 [1]
let target = tensor([7.0])              # 目标值
let err = sub(pred, target)             # 残差 [1]
let loss = sum(mul(err, err))           # MSE 标量
print(loss)
"""

TARGET = 7.0


def set_param(t, vals):
    i = 0

    def build(dim):
        nonlocal i
        if len(dim) == 1:
            r = vals[i:i + dim[0]]
            i += dim[0]
            return r
        return [build(dim[1:]) for _ in range(dim[0])]
    t.value = build(t.shape)


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


print("=" * 56)
print("tl v0.1 训练闭环 —— 梯度下降驱动学习")
print("=" * 56)

eng = tl.run_program(CODE, quiet=True)

# 随机非零初始化（固定种子，可复现）
import random
random.seed(42)
W, b = eng.vars["W"], eng.vars["b"]
set_param(W, [random.uniform(-0.5, 0.5) for _ in range(3)])
set_param(b, [random.uniform(-0.5, 0.5)])

LR = 0.003
losses = []
for step in range(100):
    # 关键：先清零参数梯度（param 对象被 recompute 复用，否则梯度跨轮累积）
    for name, t in eng.vars.items():
        if isinstance(t, tl.Tensor) and t.trainable:
            t.grad = tl.zeros_like(t.shape)
    eng.recompute()
    loss = eng.vars["loss"]
    backward(loss)
    # SGD 更新：W -= lr * dW；b -= lr * db
    gW = flat(W.grad)
    set_param(W, [v - LR * g for v, g in zip(flat(W.value), gW)])
    set_param(b, [v - LR * g for v, g in zip(flat(b.value), flat(b.grad))])
    losses.append(loss.value)
    if step % 20 == 0 or step == 99:
        print(f"  step {step:>3}: loss = {loss.value:>10.6f}")

print()
print(f"  初始 loss: {losses[0]:.6f}  →  最终 loss: {losses[-1]:.6f}  "
      f"（下降 {losses[0] / losses[-1]:.0f}x）")
w = flat(W.value)
print(f"  学到的 W: {[round(v, 4) for v in w]}")
print(f"  学到的 b: {round(b.value[0], 4)}")
print(f"  验证 pred = W·x + b = {round(sum(w[i] * (i + 1) for i in range(3)) + b.value[0], 4)}"
      f"（目标 7.0）")

if losses[-1] < 1e-2:
    print("\n  ✅ 训练闭环通过：loss 收敛到 < 1e-2，模型学到了目标映射")
else:
    print("\n  ✗ 未收敛，请检查学习率/数据")
