# -*- coding: utf-8 -*-
"""tl v0.9 验证：全自研后端（tl 字节码 + 自研 VM）。

验证组：
  1. 字节码 forward == 前端解释 forward（transformer_block 全部命名变量逐位）
  2. 字节码训练 == plan.run(naive) 24 epoch loss 逐位一致
  3. 字节码训练 == plan.run(checkpoint) 逐位一致（后端语义 = 前端最优路径）
  4. 字节码增量（update=[W1,b1]）== run_incremental 逐位一致
  5. .tlb 序列化 round-trip：to_text -> from_text -> 训练一致
  6. CLI：tl build / tl train tb.tlb（子进程）
  7. 回归：v0.7 exit=0
"""
import io
import os
import random
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tl
import tlb

BASE = os.path.dirname(os.path.abspath(__file__))
CODE = io.open(os.path.join(BASE, "transformer_block.tl"), encoding="utf-8").read()

print("=" * 62)
print("tl v0.9 —— 全自研后端：tl 字节码 + 自研虚拟机（零 LLVM）")
print("=" * 62)

plan = tl.compile_training(CODE)
prog, _ = tlb.build_program(CODE)
print("  槽数: %d  前向指令: %d  反向指令: %d  update: %s  loss: %d"
      % (len(prog.slots), len(prog.fwd), len(prog.back),
         [prog.slots[u].name for u in prog.updates], prog.loss_id))


def seed_params(eng, params, seed):
    rnd = random.Random(seed)
    for nm in params:
        t = eng.vars[nm]

        def fill(v):
            if isinstance(v, list):
                return [fill(i) for i in v]
            return rnd.uniform(-0.3, 0.3)
        t.value = fill(t.value)


# ---------- 验证 1：forward 逐位一致 ----------
print("\n[验证 1] 字节码 forward == 前端解释 forward（全命名变量逐位）")
eng = tl.Engine()
eng.run(plan.fwd, quiet=True)
seed_params(eng, plan.params, 7)
eng._keep = {k: v for k, v in eng.vars.items()
             if isinstance(v, tl.Tensor) and v._op == "param"}
eng.run(plan.fwd, quiet=True)
eng._keep = None
vm = tlb.BytecodeVM(prog)
vm.run(1, lr=0.0, seed=7)          # 1 epoch 不更新（lr=0）→ 前向一致
ok1 = True
for s in prog.slots:
    if s.kind in ("input", "param"):
        continue
    tv = eng.vars.get(s.name)
    if tv is None:
        continue
    if tv.value != vm.slots[s.id].value:
        ok1 = False
        print("  ✗ %s 不一致: %r vs %r" % (s.name, tv.value, vm.slots[s.id].value))
        break
print("  ✅ 命名中间/损失逐位一致" if ok1 else "  ✗ 不一致")

# ---------- 验证 2：训练 == plan.run(naive) ----------
print("\n[验证 2] 字节码训练 == plan.run(naive) 24 epoch 逐位一致")
losses_ref, _ = plan.run(24, lr=0.2, seed=7, mem_strategy="naive")
vm2 = tlb.BytecodeVM(prog)
losses_bc = vm2.run(24, lr=0.2, seed=7)
ok2 = all(a == b for a, b in zip(losses_bc, losses_ref))
print("  字节码 首 %.12f → 末 %.12f；逐位一致: %s"
      % (losses_bc[0], losses_bc[-1], ok2))

# ---------- 验证 3：训练 == plan.run(checkpoint) ----------
print("\n[验证 3] 字节码训练 == plan.run(checkpoint) 24 epoch 逐位一致")
losses_ck, _ = plan.run(24, lr=0.2, seed=7, mem_strategy="checkpoint")
ok3 = all(a == b for a, b in zip(losses_bc, losses_ck))
print("  与前端检查点路径逐位一致: %s（checkpoint 末 %.12f）" % (ok3, losses_ck[-1]))

# ---------- 验证 4：增量（update 子集）逐位一致 ----------
print("\n[验证 4] 字节码增量（update=[W1,b1]）== run_incremental 逐位一致")
losses_inc_ref, _ = plan.run_incremental(24, lr=0.2, seed=7, update=["W1", "b1"])
vm4 = tlb.BytecodeVM(prog)
losses_bc4 = vm4.run(24, lr=0.2, seed=7, update=["W1", "b1"])
ok4 = all(a == b for a, b in zip(losses_bc4, losses_inc_ref))
print("  字节码 首 %.12f → 末 %.12f；逐位一致: %s"
      % (losses_bc4[0], losses_bc4[-1], ok4))

# ---------- 验证 5：.tlb round-trip ----------
print("\n[验证 5] .tlb 序列化 round-trip（to_text -> from_text 训练一致）")
text = prog.to_text()
prog2 = tlb.BytecodeProgram.from_text(text)
vm5 = tlb.BytecodeVM(prog2)
losses_bc5 = vm5.run(24, lr=0.2, seed=7)
ok5 = all(a == b for a, b in zip(losses_bc5, losses_bc))
print("  .tlb 文本 %d 行，round-trip 训练逐位一致: %s" % (len(text.splitlines()), ok5))

# ---------- 验证 6：CLI ----------
print("\n[验证 6] CLI：tl build / tl train（子进程）")
tlb_path = os.path.join(BASE, "tb.tlb")
r1 = subprocess.run([sys.executable, os.path.join(BASE, "tl.py"),
                     "build", os.path.join(BASE, "transformer_block.tl"),
                     "-o", tlb_path], capture_output=True, text=True)
r2 = subprocess.run([sys.executable, os.path.join(BASE, "tl.py"),
                     "train", tlb_path, "--epochs", "4", "--seed", "7"],
                    capture_output=True, text=True)
ok6 = r1.returncode == 0 and r2.returncode == 0 and "0.068012970" in r2.stdout
print("  build exit=%d, train exit=%d, loss 首值命中: %s"
      % (r1.returncode, r2.returncode, "0.068012970" in r2.stdout))
if r2.returncode != 0:
    print("  stderr:", r2.stderr[-500:])

# ---------- 验证 7：回归 ----------
print("\n[验证 7] 回归：v0.7（含 v0.1-v0.6）")
r3 = subprocess.run([sys.executable, os.path.join(BASE, "run_v07.py")],
                    capture_output=True, text=True)
ok7 = r3.returncode == 0
print("  run_v07.py exit=%d" % r3.returncode)

print("\n[总结] tl v0.9 已验证：")
print("  1. 字节码 forward == 前端解释 逐位一致 -> %s" % ("通过" if ok1 else "失败"))
print("  2. 字节码训练 == plan.run(naive) 逐位一致 -> %s" % ("通过" if ok2 else "失败"))
print("  3. 字节码训练 == plan.run(checkpoint) 逐位一致 -> %s" % ("通过" if ok3 else "失败"))
print("  4. 字节码增量 == run_incremental 逐位一致 -> %s" % ("通过" if ok4 else "失败"))
print("  5. .tlb round-trip 无损 -> %s" % ("通过" if ok5 else "失败"))
print("  6. CLI build/train -> %s" % ("通过" if ok6 else "失败"))
print("  7. 回归 v0.1-v0.7 exit=%d" % r3.returncode)
sys.exit(0 if (ok1 and ok2 and ok3 and ok4 and ok5 and ok6 and ok7) else 1)
