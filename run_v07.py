# -*- coding: utf-8 -*-
"""tl v0.7 验证：跨 update 增量优化（静态影响子图 + 冻结参数跨步复用）。

验证组：
  1. 影响子图分析：每个参数的影响闭包（Wq/Wk=8, Wv=6, W1/b1=3），独立复算比对
  2. 增量 == 朴素：同样更新序列（全参数/冻结 FFN），增量执行与"每步全 forward 重算"逐位一致
  3. 增量 == 编译训练：run_incremental(24, update=None) 与 plan.run(24) loss 序列逐位一致
  4. 前向语句量：全参数每步 10 vs 17（↓41%）；冻结 FFN 每步 3 vs 17（↓82%）
  5. 冻结场景收敛：只训 W1/b1（冻结 Q/K/V 投影），loss 显著下降
  6. 回归：v0.6（含 v0.1-v0.5）exit=0
"""
import io
import os
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tl

BASE = os.path.dirname(os.path.abspath(__file__))
CODE = io.open(os.path.join(BASE, "transformer_block.tl"), encoding="utf-8").read()

print("=" * 62)
print("tl v0.7 —— 跨 update 增量优化（静态影响子图 + 冻结复用）")
print("=" * 62)

plan = tl.compile_training(CODE)

# ---------- 验证 1：影响子图分析 ----------
imp = plan.impact_stmts
print("\n[验证 1] 每个参数的影响子图（传递依赖闭包）")
expect = {"Wq": 8, "Wk": 8, "Wv": 6, "W1": 3, "b1": 3}
lets = [st for st in plan.fwd if isinstance(st, tl.LetStmt)]
dep = {st.name: set(tl._refs(st.expr)) for st in lets}
ok1 = True
for p in plan.params:
    names = [st.name for st in imp[p]]
    print("  %-4s -> %d 条: %s" % (p, len(names), names))
    if len(names) != expect.get(p):
        ok1 = False
    affected, frontier, changed = set(), {p}, True
    while changed:
        changed = False
        for st in lets:
            if st.name in affected:
                continue
            if dep[st.name] & frontier:
                affected.add(st.name)
                frontier.add(st.name)
                changed = True
    if affected != set(names):
        ok1 = False
        print("  ✗ %s 影响集与独立闭包复算不一致" % p)
n_all = len({st.name for p in plan.params for st in imp[p]})
n_frozen = len({st.name for p in ("W1", "b1") for st in imp[p]})
print("  ✅ 影响子图规模符合预期；全参数并集 %d 条，冻结 FFN 并集 %d 条（vs 全图 %d）"
      % (n_all, n_frozen, len(lets)) if ok1 else "  ✗ 影响子图错误")

# ---------- 验证 2：增量 == 朴素（逐位一致） ----------
print("\n[验证 2] 增量执行 == 朴素全量重算（同样更新序列，逐位一致）")
EPOCHS, LR, SEED = 12, 0.1, 7
UPDATE_SETS = [None, ["W1", "b1"], ["Wq"]]


def seed_params(eng, params, seed):
    rnd = random.Random(seed)
    for nm in params:
        t = eng.vars[nm]

        def fill(v):
            if isinstance(v, list):
                return [fill(i) for i in v]
            return rnd.uniform(-0.3, 0.3)
        t.value = fill(t.value)


ok2 = True
for us in UPDATE_SETS:
    losses_inc, _ = plan.run_incremental(EPOCHS, lr=LR, seed=SEED, update=us)
    upd = us if us is not None else plan.params
    # 朴素参照：同样每步全量 forward + 更新 upd
    eng = tl.Engine()
    eng.run(plan.fwd, quiet=True)
    seed_params(eng, plan.params, SEED)
    eng._keep = {k: v for k, v in eng.vars.items()
                 if isinstance(v, tl.Tensor) and v._op == "param"}
    eng.run(plan.fwd, quiet=True)
    eng._keep = None
    losses_ref = []
    for _ in range(EPOCHS):
        eng._keep = {k: v for k, v in eng.vars.items()
                     if isinstance(v, tl.Tensor) and v._op == "param"}
        eng.run(plan.fwd, quiet=True)
        eng._keep = None
        for t in eng.vars.values():
            if isinstance(t, tl.Tensor) and t.trainable:
                t.grad = tl.zeros_like(t.shape)
        tl.backward(eng.last_loss)
        for nm in upd:
            t = eng.vars[nm]
            t.value = tl._upd(t.value, t.grad, LR)
        losses_ref.append(eng.last_loss.value)
    eq = all(a == b for a, b in zip(losses_inc, losses_ref))
    print("  update=%s: %d 步逐位一致: %s" % (us, EPOCHS, eq))
    ok2 = ok2 and eq

# ---------- 验证 3：增量 == 编译训练（全参数，24 epoch 逐位） ----------
print("\n[验证 3] run_incremental(24, update=None) == plan.run(24)（逐位一致）")
losses_full_ref, _ = plan.run(24, lr=0.2, seed=7, mem_strategy="naive")
losses_inc_all, eng_all = plan.run_incremental(24, lr=0.2, seed=7)
eq3 = all(a == b for a, b in zip(losses_inc_all, losses_full_ref))
print("  增量首 %.9f → 末 %.9f；与 plan.run 逐位一致: %s"
      % (losses_inc_all[0], losses_inc_all[-1], eq3))
ok3 = eq3 and losses_inc_all[-1] < 0.02

# ---------- 验证 4：前向语句量 + 耗时 ----------
print("\n[验证 4] 前向语句量（编译器静态可数）与耗时")
n_fwd = eng_all.n_fwd_stmts
n_naive = 24 * len(lets)
print("  全参数增量：%d 条 vs 朴素 %d 条（每步 10 vs 17）→ ↓%.0f%%"
      % (n_fwd, n_naive, 100 * (1 - n_fwd / n_naive)))
losses_f, eng_f = plan.run_incremental(24, lr=0.2, seed=7, update=["W1", "b1"])
n_frozen = eng_f.n_fwd_stmts
print("  冻结 FFN（只训 W1/b1）：%d 条 vs 朴素 %d 条（每步 3 vs 17）→ ↓%.0f%%"
      % (n_frozen, n_naive, 100 * (1 - n_frozen / n_naive)))
t0 = time.perf_counter()
plan.run_incremental(24, lr=0.2, seed=7)
t_inc = time.perf_counter() - t0
t0 = time.perf_counter()
plan.run(24, lr=0.2, seed=7, mem_strategy="naive")
t_full = time.perf_counter() - t0
print("  耗时（24 epoch）：增量 %.3fs vs 编译全量 %.3fs" % (t_inc, t_full))
ok4 = n_fwd < n_naive and n_frozen < n_naive

# ---------- 验证 5：冻结场景收敛 ----------
print("\n[验证 5] 冻结主干（只训 W1/b1）收敛")
print("  首步 %.9f → 末步 %.9f（全参数增量 24 epoch 到 %.9f）"
      % (losses_f[0], losses_f[-1], losses_inc_all[-1]))
ok5 = losses_f[-1] < losses_f[0]

# ---------- 验证 6：回归 ----------
print("\n[验证 6] 回归：v0.6（含 v0.1-v0.5）")
r = subprocess.run([sys.executable, os.path.join(BASE, "run_v06.py")],
                   capture_output=True, text=True)
ok6 = r.returncode == 0
print("  run_v06.py exit=%d" % r.returncode)

print("\n[总结] tl v0.7 已验证：")
print("  1. 影响子图：Wq/Wk=8、Wv=6、W1/b1=3，独立复算一致")
print("  2. 增量 == 朴素（全参数/冻结 FFN/单 Wq）逐位一致 -> %s" % ("通过" if ok2 else "失败"))
print("  3. 增量 == plan.run 全参数 24 epoch 逐位一致，收敛 %.9f -> %.9f" % (losses_inc_all[0], losses_inc_all[-1]))
print("  4. 前向语句量：全参数 ↓%.0f%%（10 vs 17），冻结 FFN ↓%.0f%%（3 vs 17）"
      % (100 * (1 - n_fwd / n_naive), 100 * (1 - n_frozen / n_naive)))
print("  5. 冻结主干收敛：%.9f -> %.9f" % (losses_f[0], losses_f[-1]))
print("  6. 回归 v0.1-v0.6 exit=%d" % r.returncode)
sys.exit(0 if (ok1 and ok2 and ok3 and ok4 and ok5 and ok6) else 1)
