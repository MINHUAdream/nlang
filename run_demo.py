# -*- coding: utf-8 -*-
"""
tl v0.1 演示 + 两项可证伪验证
====================================
验证 1：编译期形状检查能抓错（坏程序在"编译"阶段就被拒绝，而不是运行时崩溃）
验证 2：语言级自动微分的梯度数值正确（与有限差分对比，误差 < 1e-6）
"""
import sys
import os

sys.stdout.reconfigure(encoding="utf-8")  # 保证 Windows 控制台中文正常

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tl
from tl import ShapeError, TLError, backward

HERE = os.path.dirname(os.path.abspath(__file__))


def fmt_flat(v, shape):
    """把嵌套 list 展平成一维列表（用于逐元素比较）。"""
    out = []

    def walk(x):
        if isinstance(x, list):
            for i in x:
                walk(i)
        else:
            out.append(x)
    walk(v)
    return out


def set_param(t, values_flat):
    """把一维数值列表写回 param 张量（按 shape 还原嵌套）。"""
    i = 0

    def build(dim):
        nonlocal i
        if len(dim) == 1:
            r = values_flat[i:i + dim[0]]
            i += dim[0]
            return r
        return [build(dim[1:]) for _ in range(dim[0])]
    t.value = build(t.shape)


# ---------------------------------------------------------------------------
# 运行 demo.tl：lex -> parse -> check -> run
# ---------------------------------------------------------------------------
print("=" * 62)
print("tl v0.1 —— 从 0 写的迷你张量语言原型")
print("=" * 62)
with open(os.path.join(HERE, "demo.tl"), encoding="utf-8") as f:
    code = f.read()

eng = tl.run_program(code)
W1, W2 = eng.vars["W1"], eng.vars["W2"]
b1, b2 = eng.vars["b1"], eng.vars["b2"]
loss = eng.vars["loss"]

print("\n[正向] 程序执行完成。各变量形状：")
for name in ("x", "W1", "b1", "h1", "a1", "W2", "b2", "y", "loss"):
    t = eng.vars[name]
    print(f"  {name:<5} shape={str(t.shape):<8} trainable={t.trainable}")

# ---------------------------------------------------------------------------
# 验证 1：编译期形状检查抓错
# ---------------------------------------------------------------------------
print("\n[验证 1] 编译期形状检查")
bad_code = """
let x = tensor([1.0, 2.0, 3.0])
let W1 = param([2, 3])
let bad = add(W1, x)   # [2,3] + [3] —— 形状不匹配
"""
try:
    tl.compile_program(bad_code)
    print("  ✗ 失败：坏程序竟然通过了编译")
except ShapeError as e:
    print(f"  ✅ 编译期抓错：{e}")
    print("   （错误在'编译'阶段抛出，程序根本没有执行）")
except TLError as e:
    print(f"  ✅ 编译期抓错（语法级）：{e}")

# 坏 matmul 内维
bad_code2 = """
let A = param([2, 3])
let B = param([4, 5])
let bad = matmul(A, B)   # [2,3] x [4,5] 内维 3≠4
"""
try:
    tl.compile_program(bad_code2)
    print("  ✗ 失败：内维不匹配竟然通过了编译")
except ShapeError as e:
    print(f"  ✅ 编译期抓错：{e}")

# ---------------------------------------------------------------------------
# 验证 2：AD 梯度 vs 有限差分
# ---------------------------------------------------------------------------
print("\n[验证 2] 自动微分梯度数值正确性（有限差分对照，eps=1e-5）")

# 关键：把参数初始化为固定非零值（否则全零 + ReLU 会让梯度恒为 0，
# 误差 0 就是空转验证，没有信息量）。固定值保证梯度非零、可复现。
init = {
    "W1": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
    "W2": [0.3, 0.7],
    "b1": [0.1, 0.2],
    "b2": [0.2],
}

# 重新运行一遍并注入非零参数，然后重算 forward（否则中间值仍是全 0 时的旧值，
# 会把梯度掩成 0 —— 空转陷阱）
eng = tl.run_program(code, quiet=True)
for pname, vals in init.items():
    set_param(eng.vars[pname], vals)
eng.recompute()
loss = eng.vars["loss"]
backward(loss)

# 取注入后的参数对象与 AD 梯度
W1, W2, b1, b2 = eng.vars["W1"], eng.vars["W2"], eng.vars["b1"], eng.vars["b2"]
ad_grads = {
    "W1": fmt_flat(W1.grad, W1.shape),
    "W2": fmt_flat(W2.grad, W2.shape),
    "b1": fmt_flat(b1.grad, b1.shape),
    "b2": fmt_flat(b2.grad, b2.shape),
}
# 反空转检查：梯度必须非零，否则验证无意义
all_grads = [g for grads in ad_grads.values() for g in grads]
if all(abs(g) < 1e-12 for g in all_grads):
    print("  ✗ 验证空转：所有梯度为 0，请检查参数初始化")
    sys.exit(1)

EPS = 1e-5
max_err = 0.0
worst = None

for pname, p in (("W1", W1), ("W2", W2), ("b1", b1), ("b2", b2)):
    flat = fmt_flat(p.value, p.shape)
    fd_grads = []
    for i in range(len(flat)):
        # 有限差分：(loss(p+eps) - loss(p-eps)) / 2eps
        def run_with(perturb):
            # 每次都要：注入全部非零参数 → 扰动单个元素 → 重算 forward
            eng2 = tl.run_program(code, quiet=True)
            for nm, vv in init.items():
                set_param(eng2.vars[nm], vv)
            t = eng2.vars[pname]
            vals = list(flat)
            vals[i] = vals[i] + perturb
            set_param(t, vals)
            eng2.recompute()
            return eng2.vars["loss"].value

        f_plus = run_with(EPS)
        f_minus = run_with(-EPS)
        fd = (f_plus - f_minus) / (2 * EPS)
        fd_grads.append(fd)

    ad = ad_grads[pname]
    errs = [abs(a - b) for a, b in zip(ad, fd_grads)]
    m = max(errs)
    if m > max_err:
        max_err = m
        worst = (pname, errs.index(m), ad[errs.index(m)], fd_grads[errs.index(m)])
    print(f"  {pname}: 梯度元素数={len(flat)}  非零梯度={sum(1 for g in ad if abs(g) > 1e-12)}  "
          f"AD 与有限差分最大误差={m:.2e}")

print()
if max_err < 1e-6:
    print(f"  ✅ 全部通过：最大误差 {max_err:.2e} < 1e-6 —— 语言级自动微分的梯度是数值正确的")
else:
    print(f"  ✗ 未通过：最大误差 {max_err:.2e}（worst={worst}）")

print("\n[总结] tl v0.1 原型已验证：")
print("  1. 张量 / 可训练参数是一等公民（demo 中 3→2→1 网络无任何框架代码）")
print("  2. 自动微分是语言原语（backward(loss) 一步得到全部参数梯度）")
print("  3. 形状检查发生在编译期（坏程序直接编译失败，而非运行时报错）")
print("  4. 零第三方依赖（连数值引擎都是自己写的）")
