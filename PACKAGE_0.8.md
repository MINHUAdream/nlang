# n 0.8 Package

状态：`implemented_in_native_slice / measured_goal_cpu_simd / replayable_selection / generalization_open`

本包把 n 的 measured goal 与 CPU SIMD 原生纵切收敛到现有 `tl-lang` 项目。旧 `.tl`
自举材料和兼容回归保留；`.n` 路径的权威链为：

```text
.n -> semantic nIR -> measured selection -> planned nIR -> machine nIR -> n-owned x64 -> RTM Echo/Commit
```

## 已交付

- `CandidateSpec`、`CandidateMeasurement`、`SelectionReceipt` 与 candidate-set digest。
- `goal/synthesize` 的真实 candidate search：`reference_exact`、`cpu_simd_sse2`。
- source/workload/benchmark/hardware digest 绑定；未知成本保持 `None`。
- exact Echo/Commit、零质量损失、已知 p50 才能选择；绑定不一致 fail-closed。
- SIMD 不可用时的 `reference_exact` 执行回退。
- n-owned `n_machine_encoder_x64.py`，与 0.7 add-scalar 机器码摘要兼容。
- `examples/goal_synthesis.n` 可直接测量执行。
- fallback、Echo 失败、candidate mutation 和 digest binding 回归测试。

## 0.8-B 回执持久化与回放

`SelectionReceipt` 可以通过规范 JSON 保存和恢复。恢复时必须提供 receipt digest，
并且 digest 必须与 canonical contents 一致；缺失、篡改或未知 selection policy 会被拒绝。
回放不会重新搜索候选，而是验证完整候选集（每个候选恰好一次）、source/workload/
benchmark/hardware 四类绑定、candidate-set digest 与 machine plan，再进入同一 lowering
链。CLI 支持：

```text
python n_run.py examples/goal_synthesis.n --synthesize add_one_plan \
  --selection-receipt-out selection.json --json
python n_run.py examples/goal_synthesis.n --synthesize add_one_plan \
  --selection-receipt-in selection.json --json
```

这是同一主机、同一 workload 和同一测量协议下的证据回放，不是跨硬件性能保证。

测量回执包含真实 p50/p99，因此同一源码在不同运行中可能产生不同的
`selection_receipt_digest`、planned/machine snapshot digest；这是证据版本变化，不是
代码不稳定。只要选中的候选和契约不变，n-owned machine `code_digest` 与字节码保持
确定性，已有回归测试明确验证这一点。

## 明确未交付

- GPU tile executor、NPU SRAM executor、CXL memory executor。
- 通用 SSA/CFG、完整寄存器分配、目标文件/链接器和自举编译器。
- 跨 workload 的性能优越性、能耗/频率统计和统计置信区间。
- 一般近似数值类型与误差预算传播。

## 复现

```text
python -m compileall -q .
python -m unittest discover -s tests -p "test_n_*.py" -v
python n_run.py examples/goal_synthesis.n --backend n-native --samples 3 --warmup-samples 1 --json
python n_run.py examples/goal_synthesis.n --synthesize add_one_plan --json
```

在非 Windows x86-64 主机上，`n-native` 可能返回 `unavailable`；这不是 SIMD 成功或
失败的性能结论。主机支持时，回执必须包含 source/NIR/phase/plan/code/workload/
hardware/benchmark/result 摘要以及 p50/p99、验证成本、搜索次数、质量损失和回退率。

## 关键文件

| 文件 | 作用 |
| --- | --- |
| `n_goal.py` | 候选规格、规范回执序列化与 fail-closed 选择 |
| `n_measure.py` | 候选测量和 RTM workload receipt |
| `n_compile.py` | measured goal 到 planned/machine nIR 的编译入口 |
| `n_machine_encoder_x64.py` | n-owned x86-64/SSE2 指令编码 |
| `n_codegen_x64.py` | machine nIR 验证后代码生成 |
| `n_plan.py` / `n_lir.py` | 计划绑定与 LIR 只读兼容投影 |
| `examples/goal_synthesis.n` | 完整 measured-goal 示例 |
| `tests/test_n08_goal_simd.py` | 编译、选择和候选突变测试 |
| `tests/test_n08_measure.py` | 绑定、回退和 Echo 失败测试 |

历史 tl/n 设计文档中的性能数字仍按其原始 workload 和复跑状态解释，不由本包重新
背书。新性能结论必须来自同一工作负载、同一硬件和新鲜 receipt。
