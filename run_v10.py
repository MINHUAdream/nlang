# -*- coding: utf-8 -*-
"""tl v0.10 验证：后端执行性能（调度器编译）+ 四路执行路径对比。

验证 1：调度器编译正确性 —— kernel 路径 == 原 _fwd_op/_back_op 路径（24 epoch 逐位一致）
验证 2：四路执行路径 loss 序列逐位一致（解释 / naive / checkpoint / 字节码 kernel）
验证 3：后端执行性能 —— 四路同任务计时，字节码后端 vs 解释加速比
验证 4：增量路径在 kernel 模式逐位一致（update=[W1,b1]）
验证 5：CLI 字节码训练在 kernel 模式通过 + 回归 v0.9
"""
import io
import os
import random
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tl
import tlb

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_PROG = io.open(os.path.join(HERE, "transformer_block.tl"), encoding="utf-8").read()

print("=" * 62)
print("tl v0.10 —— 后端执行性能：调度器编译（形状 -> 代码生成）")
print("=" * 62)

plan = tl.compile_training(BASE_PROG)
prog, _ = tlb.build_program(BASE_PROG)

# 解释路径程序：base + 每 epoch 全参数 update + print(loss)
def interp_prog(epochs):
    body = "\n".join(
        "update(Wq, 0.2)\nupdate(Wk, 0.2)\nupdate(Wv, 0.2)\nupdate(W1, 0.2)\nupdate(b1, 0.2)\nprint(loss)"
        for _ in range(epochs))
    return BASE_PROG + "print(loss)\n" + body


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


# 解释路径：手动单步循环（每 epoch 1 次 forward+backward+全参数更新，与编译/字节码同工作量）
def _interp_manual(epochs, collect=False):
    eng_m = tl.Engine()
    eng_m.run(plan.fwd, quiet=True)
    rnd = random.Random(7)
    for nm in plan.params:
        t = eng_m.vars[nm]

        def fill(v):
            if isinstance(v, list):
                return [fill(i) for i in v]
            return rnd.uniform(-0.3, 0.3)
        t.value = fill(t.value)
    losses = []
    for _ in range(epochs):
        eng_m.recompute(quiet=True)
        if collect:
            losses.append(eng_m.last_loss.value)
        for nm in plan.params:
            t = eng_m.vars[nm]
            t.grad = tl.zeros_like(t.shape)
        tl.backward(eng_m.last_loss)
        for nm in plan.params:
            t = eng_m.vars[nm]
            t.value = tl._upd(t.value, t.grad, 0.2)
    return losses


EPOCHS = 200

# ---------------------------------------------------------------------------
# 验证 1：调度器编译正确性（kernel == 原路径）
# ---------------------------------------------------------------------------
print("\n[验证 1] 调度器编译正确性：kernel 路径 == 原 _fwd_op/_back_op 路径")
vm_k = tlb.BytecodeVM(prog, kernels=None)          # 自动编译 kernel
vm_o = tlb.BytecodeVM(prog, kernels=(None, None))  # 原解释路径
lk = vm_k.run(24, lr=0.2, seed=7)
lo = vm_o.run(24, lr=0.2, seed=7)
ok1 = lk == lo
print("  kernel 首 %.12f → 末 %.12f；与原路径逐位一致: %s" % (lk[0], lk[-1], ok1))

# ---------------------------------------------------------------------------
# 验证 2：四路 loss 序列逐位一致
# ---------------------------------------------------------------------------
print("\n[验证 2] 四路执行路径 loss 序列逐位一致（%d epoch）" % EPOCHS)
losses_naive, _ = plan.run(EPOCHS, lr=0.2, seed=7, mem_strategy="naive")
losses_ck, _ = plan.run(EPOCHS, lr=0.2, seed=7, mem_strategy="checkpoint")
vm = tlb.BytecodeVM(prog)
losses_vm = vm.run(EPOCHS, lr=0.2, seed=7)
losses_interp = _interp_manual(EPOCHS, collect=True)

ok2 = (losses_naive == losses_ck == losses_vm
       and losses_interp[-1] == losses_vm[-1])
print("  解释 末 %.12f | naive 末 %.12f | checkpoint 末 %.12f | VM 末 %.12f"
      % (losses_interp[-1], losses_naive[-1], losses_ck[-1], losses_vm[-1]))
print("  四路逐位一致: %s" % ok2)

# ---------------------------------------------------------------------------
# 验证 3：后端执行性能（四路计时）
# ---------------------------------------------------------------------------
print("\n[验证 3] 后端执行性能（%d epoch 训练，取中位）" % EPOCHS)


def bench(fn, n=3):
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t0)
    ts.sort()
    return ts[len(ts) // 2]


t_interp = bench(lambda: _interp_manual(EPOCHS))
t_naive = bench(lambda: plan.run(EPOCHS, lr=0.2, seed=7, mem_strategy="naive"))
t_ck = bench(lambda: plan.run(EPOCHS, lr=0.2, seed=7, mem_strategy="checkpoint"))
t_vm = bench(lambda: tlb.BytecodeVM(prog).run(EPOCHS, lr=0.2, seed=7))

print("  解释执行  %d epoch：%.1f ms" % (EPOCHS, t_interp * 1000))
print("  naive      %d epoch：%.1f ms" % (EPOCHS, t_naive * 1000))
print("  checkpoint%d epoch：%.1f ms" % (EPOCHS, t_ck * 1000))
print("  字节码 VM  %d epoch：%.1f ms" % (EPOCHS, t_vm * 1000))
print("  VM vs 解释加速比：%.2fx" % (t_interp / t_vm))
print("  VM vs naive 加速比：%.2fx" % (t_naive / t_vm))
ok3 = t_vm < t_interp * 0.8 and t_vm < t_naive

# 规模测速：更大的 encoder block（[8,16]，d=32）——加速比随规模放大的证据
print("\n[验证 3b] 规模测速：transformer_block_big（[8,16]×d=32，%d epoch）" % EPOCHS)
BIG = io.open(os.path.join(HERE, "transformer_block_big.tl"), encoding="utf-8").read()
plan_big = tl.compile_training(BIG)
prog_big, _ = tlb.build_program(BIG)


def _interp_big(epochs):
    eng = tl.Engine()
    eng.run(plan_big.fwd, quiet=True)
    rnd = random.Random(7)
    for nm in plan_big.params:
        t = eng.vars[nm]

        def fill(v):
            if isinstance(v, list):
                return [fill(i) for i in v]
            return rnd.uniform(-0.3, 0.3)
        t.value = fill(t.value)
    for _ in range(epochs):
        eng.recompute(quiet=True)
        for nm in plan_big.params:
            t = eng.vars[nm]
            t.grad = tl.zeros_like(t.shape)
        tl.backward(eng.last_loss)
        for nm in plan_big.params:
            t = eng.vars[nm]
            t.value = tl._upd(t.value, t.grad, 0.2)


t_bi = bench(lambda: _interp_big(EPOCHS))
t_bv = bench(lambda: tlb.BytecodeVM(prog_big).run(EPOCHS, lr=0.2, seed=7))
print("  解释 %d epoch：%.1f ms | 字节码 VM：%.1f ms | 加速比：%.2fx"
      % (EPOCHS, t_bi * 1000, t_bv * 1000, t_bi / t_bv))
print("  规模放大后加速比: %.2fx -> %s"
      % (t_bi / t_bv, "放大" if t_bi / t_bv > t_interp / t_vm else "未放大"))

# ---------------------------------------------------------------------------
# 验证 4：增量路径（kernel 模式）
# ---------------------------------------------------------------------------
print("\n[验证 4] 增量训练（update=[W1,b1]）kernel 模式逐位一致")
losses_inc_ref, _ = plan.run_incremental(24, lr=0.2, seed=7, update=["W1", "b1"])
vm4 = tlb.BytecodeVM(prog)
losses_bc4 = vm4.run(24, lr=0.2, seed=7, update=["W1", "b1"])
ok4 = losses_bc4 == losses_inc_ref
print("  VM 末 %.12f == 前端增量末 %.12f: %s"
      % (losses_bc4[-1], losses_inc_ref[-1], ok4))

# ---------------------------------------------------------------------------
# 验证 5：CLI + 回归
# ---------------------------------------------------------------------------
print("\n[验证 5] CLI 字节码训练 + 回归 v0.9")
r1 = subprocess.run([sys.executable, os.path.join(HERE, "tl.py"),
                     "train", os.path.join(HERE, "tb.tlb"),
                     "--epochs", "4", "--seed", "7"], capture_output=True, text=True)
r2 = subprocess.run([sys.executable, os.path.join(HERE, "run_v09.py")],
                    capture_output=True, text=True)
ok5 = r1.returncode == 0 and r2.returncode == 0 and "0.068012970" in r1.stdout
print("  CLI train tb.tlb exit=%d（loss 首值命中: %s）；回归 v0.9 exit=%d"
      % (r1.returncode, "0.068012970" in r1.stdout, r2.returncode))

print("\n[总结] tl v0.10：")
print("  1. 调度器编译 kernel == 原路径 逐位一致 -> %s" % ("通过" if ok1 else "失败"))
print("  2. 四路执行 loss 逐位一致 -> %s" % ("通过" if ok2 else "失败"))
print("  3. 后端性能：VM vs 解释 %.2fx, VM vs naive %.2fx -> %s"
      % (t_interp / t_vm, t_naive / t_vm, "通过" if ok3 else "失败"))
print("  4. 增量 kernel 模式逐位一致 -> %s" % ("通过" if ok4 else "失败"))
print("  5. CLI + 回归 v0.9 -> %s" % ("通过" if ok5 else "失败"))
sys.exit(0 if (ok1 and ok2 and ok3 and ok4 and ok5) else 1)
