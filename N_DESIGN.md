# n 编程语言设计规格（Draft 0.15 Contract-Carrying Transition Machine）

> n（读作“en”）是原生 AI 的 Contract-Carrying Transition Machine（契约携带状态转换机器）语言。
> 世界、状态、预测、目标、学习、适应、记忆、事件、群体探索和 Agent 协作是语言/类型/n-IR/运行时语义；AI 不是附加框架，也不等同于 LLM。
>
> 本文是设计基线，不把尚未实现的能力写成既成事实。当前原型目录仍使用 `tl` 名称，见“迁移策略”。

## 1. 定位

n 的首要服务对象是自主 AI 系统，而非人类程序员。目标是让 AI 能原生表达状态、推理、学习、世界交互、协作和自我改进，并在给定语义与资源边界内最大化任务能力和进化效率。人类可读语法、诊断和调试视图是检查与互操作接口，不是核心优化目标。n 不承诺所有程序都超过 C 或 Fortran；性能必须以相同质量门槛、硬件和预算口径实测。Agent 是 n/AI 的自主计算主体，不是 n 的全部，更不是 LLM 的包装器。

| 场景 | n 的目标 |
| --- | --- |
| AI 计算 | 原生表达状态、世界、动力学、目标、预测、学习、适应与评估 |
| 多范式学习 | 统一规则/搜索、梯度学习、局部可塑性、元学习、进化与混合系统 |
| 时间与事件 | 同时支持离散步、连续动力学和稀疏事件/SNN，并暴露求解与调度成本 |
| 开放式探索 | 原生表达种群、谱系、环境生成、新颖度和质量多样性档案，但资源始终有界 |
| Agent 认知 | 原生表达观察、证据、信念、目标、计划、行动、反馈和学习 |
| Agent 融合 | 多个 Agent 以证据代数融合，保留冲突、来源和不确定性 |
| AI 自主性 | Agent 可提出策略、能力与运行计划的改进候选，并通过机器验证后自主晋升 |
| 系统完整性 | 现实标签、数据流、资源预算、外部副作用和能力边界是类型/效果/运行时不变量 |
| AI 效能 | 在任务质量、能力增长和完整性约束下最大化吞吐/单位资源效率，优化延迟、算力、内存、能耗与通信 |
| 数值内核 | 安全模式下接近 C/Fortran；张量路径支持 SIMD、CPU/GPU 和显式布局 |
| 可验证性 | 认知轨迹、n-IR、内存效果、浮点模式和行动决策可导出并重放 |

n 不把“Agent 认知”实现成隐藏的黑盒运行时，也不把意识、情感或主观体验宣称为已解决问题。n 表达的是可执行的认知状态转换。量子硬件、同伦类型或拓扑算法仍是可选扩展，必须有后端和可测语义才进入标准库。

## 2. 设计原则

1. **n-IR 优先**：源代码先编译到带类型和效果信息的 n-IR；LLVM、PTX 等只是后端格式。
2. **零隐藏成本**：不默认 GC、隐式复制、隐式线程或隐式设备传输。
3. **运行完整性默认值**：边界、生命周期、别名、效果和整数溢出默认可检查；证明安全后消除热路径检查。
4. **确定性优先**：浮点模式、归约顺序和并行语义必须显式声明。
5. **渐进复杂度**：普通函数不必使用 `seed`、线性资源或设备特性。
6. **可互操作**：C ABI、Fortran ABI、BLAS/LAPACK、CUDA 和系统调用都有明确的逃生舱。
7. **证据先于断言**：未知不是错误；`Tr` 的未知态必须保留来源和证据量，不能被隐式转换为真或假。
8. **行动必须授权并提交**：Agent 只能通过显式 `authorize` 产生一次性行动票据，再由 `execute` 产生外部行动；计划和行动不能偷偷产生 IO。
9. **融合可重放**：Agent 融合是确定的证据代数，不是不可审计的“群体直觉”。
10. **分支可互相影响但不可互相篡改**：并行 Agent 通过带因果关系的消息和显式合并影响彼此；分支历史保持不可变。
11. **AI 原生而非模型绑定**：世界模型、元学习、SNN、进化、符号推理和 Agent 共享同一语义基底；任何特定网络架构都不是语言本体。
12. **现实与想象隔离**：`Observed[T]`、`Predicted[T]`、`Imagined[T]`、`Generated[T]` 和 `Counterfactual[T]` 不可隐式互换；模拟/采样结果不能伪装成现实证据。
13. **学习也是状态转换**：参数、更新规则、数据范围、随机种子和评估协议必须进入类型、效果或事件日志；“训练”不能是编译器不可见的黑箱。
14. **无 LLM 基线**：语言、编译器和标准运行时不加载、不调用 LLM；借鉴架构原则时必须给出 n 内可执行、可检验的重构。
15. **AI 优先、机器原生**：编译器和运行时首先面向自主 AI 生成、变换、执行和评估 n 程序；人类可读性不能阻断机器生成效率、静态特化或零拷贝路径。
16. **效能最大化而非单指标投机**：在任务质量下限、现实/想象边界、数据流完整性与资源预算内，最大化能力进展和有效工作量；以质量/能力、尾延迟、计算、内存、能耗、通信和覆盖组成的 Pareto 前沿比较实现，不把“最快”或“最少数据”孤立成普遍目标。
17. **自治在系统不变量内扩展**：Agent 可自行提出和验证能力、策略、记忆、路由与调度改进；权限和资源不能被候选自授予，改进由独立的机器可验证 AdmissionGate 检查，不要求默认有人类逐次审批。
18. **结果优先、解释可选**：AI 可以提交 `none/result_only` 的结论或候选，不必生成可读推理链；机器仍要求版本、输入/输出摘要、适用域、质量/残差和必要的验证契约。不可解释性不等于免除类型、效果、现实标签、资源或外部行动边界。
19. **规范不自证**：规范解释器、版本化验证语料、固定基准和独立裁判共同构成语义主权；候选、被测程序和优化器不能构造自己的最终报告，也不能把一次通过写成普遍真理。
20. **契约携带转换**：每个可执行计算都是带输入/输出、资源、效果、误差、成本、回退和回放契约的 `Transition`；执行计划是可验证的一等值，不是编译器黑魔法。

### 2.1 AI 中心效能宪法

n 不把性能定义成单一 FLOPs、峰值吞吐或最短延迟，而把它定义成 AI 在物理资源上取得的**有效能力进展**。候选执行方案先满足硬不变量，再比较效能；硬不变量不是人的偏好，而是保持计算可用、状态不被破坏、结果不被伪造所需的机器规则。

```text
EfficiencyObjective = {
    maximize: task_quality, capability_gain, useful_throughput, coverage,
    minimize: p50/p99_latency, compute, memory, storage, energy, communication, recovery_cost,
    subject_to: RTST_integrity, numeric_contract, resource_envelope, effect_contract
}
```

1. **质量优先的最快合格路径**：先排除违反现实标签、状态/效果、资源上限或任务质量下限的候选，再从可行候选的 Pareto 前沿选择。任务可以声明词典序、约束或权重；语言不硬编码一个可被投机的万能标量。
2. **AI 自动优化**：Agent/运行时可持续产生 `schedule/layout/device/precision/route/cache/memory/fanout` 候选，用同输入或等价保留集做影子执行、差分测试和成本采样；通过 `AdmissionGate` 后自动晋升，退化时自动回滚，不要求人逐次调参。
3. **规范语义与最快执行分离**：`repro-v1` 是差分验证的参考数值语义；默认执行策略是 `adaptive-fastest`，在 `NumericContract`、质量下限和目标设备能力内选择最快的已验证 profile。无法建立误差/质量界时退回参考路径，而不是静默改变结果。
4. **控制面与热数据面分离**：RealityTag、capability、provenance 和验证策略存在于 RTST 控制面；纯 Tensor/SIMD/kernel 热区降级为紧凑 n-IR/机器码。已静态证明的检查被消除，细粒度事件可在边界合并为摘要；外部副作用、状态提交、学习晋升和未知结果仍必须留下不可省略的转换记录。
5. **优化本身可学习**：编译器 profile、运行时遥测和失败回退形成 `PerformanceReceipt`；它们可训练或搜索新的执行策略，但遥测开销也必须进入 `CostVector`，优化器不能靠隐藏测量成本制造虚假收益。
6. **评价器独立**：优化候选不得改写评价自己的 `Objective`、质量下限、计费口径或保留集。目标版本在一个 evaluation epoch 内不可变；目标演化是单独的 `ObjectiveDelta`，由旧版本和独立环境评估后才进入下一 epoch，防止把改分数冒充能力增长。
7. **选择一次、长段执行**：多版本代码的设备/profile/布局/路由选择在稳定 RTST 边界完成，并按程序、形状、设备、目标和 profile 摘要缓存；热循环内不得反复动态分派或检查 capability。在线重优化只在安全点替换 `PlanDigest`，在途 kernel 继续使用旧计划直至完成。

```text
OptimizationCandidate[P] = {
    plan: P,
    base_plan: PlanDigest,
    objective_epoch: VersionId,
    predicted_gain: CostVector + QualityReport,
    proof_or_test: Evidence,
    rollback: RollbackPolicy
}

PerformanceReceipt = {
    plan: PlanDigest,
    workload: Digest,
    benchmark: BenchmarkBinding,
    objective_epoch: VersionId,
    quality: QualityReport,
    cost: CostVector,
    latency: LatencyProfile,
    cold_start: CostVector,
    optimization_overhead: CostVector,
    regressions: CanonicalSet[ConstraintId],
    fallback_taken: Bool,
    result_digest: Digest
}

BenchmarkBinding = {
    source_digest: Digest,
    nir_digest: Digest,
    compiler_digest: CompilerDigest,
    runtime_digest: Digest,
    hardware_digest: Digest,
    benchmark_digest: Digest,
    includes_compile: Bool,
    includes_dispatch: Bool,
    includes_data_movement: Bool,
    includes_monitoring: Bool,
    includes_fallback: Bool
}

LatencyProfile = {
    samples: u64,
    warmup: u64,
    p50_ns: u64,
    p95_ns: u64,
    p99_ns: u64,
    max_ns: u64
}
```

因此，“完整性”与“性能”不是两套互相拉扯的机制：RTST 提供可证明边界，证明让运行时删除检查；证据不足时才付动态验证或回退成本。n 的理想热路径是**带证明生成、无多余守卫执行、在提交边界结算**。

### 2.2 语义主权与验证语料（G9）

n 吸收 Resona 的工程纪律，但不吸收其“场/波/纠缠”等本体论假说。n 的规范权威固定为四件套：

```text
SemanticAuthority = {
    reference_semantics: Digest,   // 版本化 n-IR + 参考解释器
    corpus: CorpusManifest,        // 正例、负例、性质和差分语料
    benchmark: BenchmarkManifest,  // 固定输入、质量门槛和成本口径
    adjudicator: EvaluatorDigest   // 与候选隔离的裁判/证据运行器
}

CorpusManifest = {
    version: VersionId,
    entries: CanonicalMap[CorpusId, CorpusEntry],
    digest: Digest
}

CorpusEntry = {
    kind: positive | negative | property | differential,
    source_digest: Digest,
    expected: accept | reject | invariant,
    rule_ids: CanonicalSet[ConstraintId],
    fixtures: CanonicalSet[Digest]
}

CorpusId = Digest
BenchmarkManifest = {
    version: VersionId,
    workload_digest: Digest,
    quality_gate: ConstraintSet,
    cost_schema: Digest,
    digest: Digest
}
```

四件套的职责不同：参考语义定义“程序是什么意思”，语料检查实现是否遵守，基准定义“在什么质量/资源口径下比较”，独立裁判签发最终报告。任何一项改变都使受影响的报告和 `AdmissionReceipt` 失效；候选不能修改自己的 `corpus`、`benchmark`、`evaluator` 或计费口径。

G9 是文档治理规则，而不是新的运行时机制：

1. 声称“可执行”“已通过”或“规范要求”的代码块必须带 `CorpusId`、语料版本和源摘要，并能从 `CorpusManifest` 重建；文档不能成为第二份规范。
2. 设计散文可以给出非规范伪代码，但必须明确标为 `illustrative`，不得作为验收证据，也不得使用“已验证”“保证”“真实”等强断言。
3. 每个新的 n-IR 操作、类型规则、效果门或优化变换，先添加至少一个正例和一个负例；负例必须证明检查器确实会拒绝，而不只是记录预期错误文本。
4. `pending` 概念只能成为 `Candidate`/`ArtifactVersion` 或 `CorpusEntry` 的候选，不能获得核心语义权力；概念准入继续复用 `verify -> evaluate -> AdmissionGate`，不新增票据或赎回系统。

最终报告的记录格式可以公开，但构造器必须是受信边界私有的：`EvaluationReport`、`PerformanceReceipt`、`GroundingReport` 和 `AdmissionReceipt` 只能由参考解释器、`evidence-runner`、RuntimeRoot 或已认证适配器构造。`pass`/`admitted` 只表示在绑定的语义、语料、基准、适用域和资源前提下未发现违规或满足门槛；它不等于“程序为真”“模型正确”或“现实已被证明”。缺少裁判摘要、语料摘要、基准摘要、适用域或回退策略时，结果必须为 `unknown`、隔离或拒绝。

显式效果同样是不可偷偷放宽的契约：函数声明的 `! {effects}` 是对调用图的承诺，编译器可以计算一个仅用于诊断的 effect superset，但不能用推断结果自动扩展声明。直接调用的效果必须是声明集合的子集；无法证明时拒绝或保留显式边界。`pure` 只能构造值、约束和 `Delta`，不能提交持久状态、事件、外部 IO 或隐式读取时钟/随机数。

异步域采用局部逻辑时钟。`causal_async` 允许消息在因果就绪的安全点影响另一分支，但“暂无消息”不代表收敛；只有 `WorkCredit`、mailbox/outbox 和主干提交同时满足停止条件时才可记录 `Quiescent`。不能证明处理器满足合流律时，必须退回 `ordered_async` 或 `round_sync`，不能由调度器猜测等价性。

### 2.3 Contract-Carrying Transition Machine（CCTM）

n 的独特路线收敛为一个核心对象：**带契约的状态转换**。模型、Agent、张量内核、设备搬运、学习更新和分支合并都不是平行的特殊机制，而是同一 `Transition[S,I,O]` 的特化。转换在执行前携带契约，在执行后产生回执；契约不足时只能回退、隔离或拒绝。

```text
Value[T] = {
    data: T,
    shape: Shape,
    layout: Layout,
    ownership: Ownership,
    device: DeviceId,
    reality: RealityTag,
    error: ErrorBound,
    provenance: ProvenanceRef,
    cost: CostVector
}

Transition[S, I, O] = {
    input: Tagged[I, RealityTag],
    output: Tagged[O, RealityTag],
    state: S,
    delta: CanonicalSet[DeltaRef],
    effects: CanonicalSet[EffectId],
    contract: TransitionContract,
    receipt: TransitionRecord
}
```

#### 一等执行计划

`ExecutionPlan[T]` 是不可变、可寻址、可验证的值；它通常作为 `ArtifactVersion[ExecutionPlan[T]]` 管理，选择、canary、激活、退化和回滚继续使用既有 `version.*` 与 `AdmissionGate`，不新增第二套生命周期。

```text
PlanDigest = Digest
Shape = static(CanonicalVector[u64]) | symbolic(SchemaDigest)
Layout = row_major | column_major | blocked(u32) | strided | opaque(Digest)
Ownership = owned | borrow | borrow_mut | linear | shared_read

ExecutionPlan[T] = {
    program: Digest,
    code: Digest,
    placement: PlacementPlan,
    numeric: EncodingProfile,
    numeric_contract: NumericContract,
    memory: Digest,
    communication: Digest,
    proof: PlanProof,
    compatibility: CompatibilityContract,
    fallback: FallbackPolicy,
    monitor: PlanMonitor,
    objective_epoch: VersionId,
    digest: PlanDigest
}

PlanProof = {
    reference_program: Digest,
    refines: Digest,
    assumptions: ConstraintSet,
    error: ErrorBound,
    quality: QualityReport,
    verifier: EvaluatorDigest,
    corpus: Digest,
    digest: Digest
}

PlanMonitor = {
    residual_checks: CanonicalSet[ConstraintId],
    sampling: u64,
    trigger: ConstraintSet,
    safe_point: ConstraintId
}

FallbackPolicy = none
                | exact(PlanDigest)
                | prior(PlanDigest)
                | reject(ConstraintId)

PlanReceipt = {
    selected: PlanDigest,
    executed: PlanDigest,
    fallback_taken: Bool,
    residual: ResidualReport,
    cost: CostVector,
    transition: Digest
}
```

`plan.specialize` 生成候选，`plan.select` 在稳定 RTST 边界绑定唯一计划，`plan.execute` 执行并产生 `PlanReceipt`，`plan.monitor` 检查残差，`plan.fallback` 在安全点原子切换到兼容计划。计划必须保持输出 schema、Delta 域、RealityTag、效果和幂等提交键兼容；热循环不能偷偷改变设备、布局、精度或通信策略。已经静态证明的字段可以擦除，但其摘要必须留在 `PlanDigest` 和回放记录中。

`Value[T]` 的 `device/layout/ownership` 是语义索引；`device.copy`、`repack`、`tile` 和远程搬运可以由计划自动插入，但插入后的操作必须出现在 n-Opt-IR、`CostVector` 和 `PlanReceipt` 中。没有对应数据移动契约的后端优化视为不合法，而不是“编译器内部细节”。

以下为 `illustrative` 表面投影；在进入验收语料前不得宣称其已实现：

```text
plan fast = specialize(matmul, shape=[B,M,K,N], device=auto,
                       precision=adaptive, memory=checkpoint)
proof fast refines exact where error <= 1e-4
fallback fast -> exact_matmul
```

#### 版本图与分支合并

计算版本图是 `ArtifactVersion`、`BranchSnapshot`、`TransitionRecord` 和 `Delta` 的规范视图，不是新的版本控制运行时。`branch.fork` 从不可变快照产生候选分支；每个分支可以选择不同的 `ExecutionPlan` 并异步推进；`branch.integrate` 只按 `Delta.merge_law` 原子合并，基线过期必须 `rebase` 或返回 `StaleBranch`/`MergeConflict`。合并不能复制 capability、预算或外部副作用，也不能用到达顺序偷偷决定结果。

```text
fork(base_snapshot) -> (branch_a, branch_b)
run(plan_a, branch_a) -> Delta_a
run(plan_b, branch_b) -> Delta_b
merge(base_snapshot, Delta_a, Delta_b, law)
    -> TransitionRecord | MergeConflict
```

这使候选计划、反事实路径、训练版本和失败实验共享同一可回放图；共享前缀可以结构复用，分支历史保持不可变，只有通过既有 `CommitGate` 的合并才影响主干。

#### 统一 `derive`

`derive` 是从同一份 n-IR 生成导数、影响、生命周期、误差和成本分析的唯一编译器原语；它不是新的运行时效果，也不取代 `Delta` 或 `CommitGate`。所有领域表面（包括 `n.autodiff` 和 `agent.derive`）都必须降级为一个带目标的 `derive.request`。

```text
DeriveTarget = tangent | adjoint | influence | memory | error
              | cost | schedule | shape | provenance | belief
DeriveMode = exact | bounded | heuristic

DeriveSpec = {
    target: DeriveTarget,
    wrt: CanonicalSet[ValueId],
    mode: DeriveMode,
    scope: CanonicalSet[NodeId],
    assumptions: ConstraintSet,
    budget: Credit[derive]
}

Derivation[T] = {
    value: T,
    target: DeriveTarget,
    source_ir: Digest,
    dependencies: CanonicalSet[NodeId],
    proof: PlanProof?,
    residual: ResidualReport,
    cost: CostVector,
    mode: DeriveMode,
    digest: Digest
}

DeriveError = UnsupportedTarget | MissingAssumption | BudgetExceeded
            | Unbounded | ResidualUnproven | ScopeConflict
```

`derive loss wrt weights` 产生 `adjoint`，`derive output wrt weights` 产生 `influence` 闭包，`derive memory wrt kernel` 产生生命周期/检查点计划，`derive error wrt precision` 产生误差敏感度，`derive cost wrt schedule` 产生带成本回执的计划候选。`exact` 必须由参考语义或证明支持；`bounded` 必须携带残差和触发回退；`heuristic` 只能产生候选，不能单独提交状态、现实证据、外部行动或 active 版本。`agent.derive` 只是 `target=belief` 的语义投影，并不再是一套独立推导机制。

以下为 `illustrative` 表面投影；真正验收必须进入带 `CorpusId` 的正负例语料：

```text
derive loss wrt weights          // target = adjoint
derive output wrt weights        // target = influence
derive memory wrt kernel         // target = memory
derive error wrt precision       // target = error
derive cost wrt schedule         // target = cost/schedule candidate
```

#### 带误差的值与精确回退

近似不再只是 profile 的注解，而是带类型和回退的值。`Approx[T]` 不能隐式当作 `T` 使用；只有 `refine` 通过误差契约，或 `plan.fallback` 产生兼容的精确值，才能进入需要精确输入的操作。

```text
Approx[T] = {
    value: T,
    bound: ErrorBound,
    numeric_contract: NumericContract,
    plan: PlanDigest,
    fallback: PlanDigest,
    residual: ResidualReport
}

ErrorBound = exact | absolute(F64) | relative(F64)
           | interval(low: F64, high: F64) | unproven
```

表面语法 `approx expr within error <= e fallback exact_plan` 降级为 `plan.execute` + `numeric.approx`；运行时监测实际 residual，超界时在契约声明的安全点切换，不得把部分近似结果和精确结果静默混合。缺少可传播误差界的 profile 只能留在候选或低风险内部路径，不能构造现实 `Evidence`、`ActionTicket` 或 `AdmissionReceipt`。

`f16`、`f32`、`f64` 仍表示数值表示/存储格式；误差界不直接烙进裸标量类型，因为同一格式在不同输入、归约和算子上具有不同误差。上下文误差由 `Approx[T] + NumericContract + ExecutionPlan` 携带，避免伪造一个全局固定的“f16 永远满足某误差”。

## 3. 语言分层

```text
n/Surface       AI 可生成/消费的 ai、world、agent、learner、event、函数、tensor 和 seed 语法；文本同时可供人检查
n/AI            state、world、dynamics、objective、predict、rollout、update、adapt、population、archive、transition、ground、commit
n/Agent         belief、evidence、goal、memory、plan、authorize、execute、fuse、branch、publish、receive、integrate
n/Core          let、函数、代数数据类型、模式匹配、借用、效果、三态代数、Value、Transition、Plan、derive
n/IR            typed SSA、tensor、region、memory、parallel、device、plan、derive、numeric fallback
n/Runtime       AI/Agent 调度、RuntimeRoot、rollout、事件队列、持久 mailbox、ExecutionFabric、热替换、日志、分配器和 ABI 适配
n/Backends      x86-64、ARM64、RISC-V、CUDA、ROCm、WASM、neuromorphic adapter
```

`n/AI` 建立在 n/Core 之上，定义跨范式的 AI 状态、动力学、目标、学习、事件和评估语义；`n/Agent` 再建立在 n/AI 之上，增加信念、权限、行动和协作。两层都不是普通库：语法、类型检查、n-IR 和运行时共同保留其语义。没有 LLM、提示词、token 解码器或预训练权重也必须能构建并运行完整的 n AI 程序。

## 4. 最小核心语义

### 4.0 AI 原生最小语义

n 的基本 AI 单元是“带类型的状态 + 可审计的转换”，不限定为神经网络或 Agent：

```n
ai AdaptiveController {
    state: AIState
    world: World[WorldState, Observation, Action]
    dynamics: Dynamics[WorldState, Action]
    objective: Objective[Trajectory]
    learner: Learner[Parameters, Experience]
    memory: Memory
}
```

最小 AI 生命周期为：

```text
observe(world, input)                  -> Observed[Observation]
infer_state(state, observation)        -> StateEstimate
predict(dynamics, state, action)       -> Predicted[NextState]
rollout(dynamics, state, policy, k)    -> Trajectory[Imagined[State]]
evaluate(objective, trajectory)        -> Score + Evidence
update(learner, parameters, experience)-> Update[Parameters]
adapt(meta_state, task, k)             -> Candidate[TaskPolicy]
```

`Observed[T]` 只能由受控观察边界或已验证记录构造；`Predicted[T]` 来自动力学预测；`Imagined[T]` 来自 rollout；`Generated[T]` 来自扩散、采样或能量过程；`Counterfactual[T]` 来自改变假设后的模拟。五者可以共同参与计划，但不能隐式转成相同完整性等级的 `EvidenceAtom`。学习产生新版本的参数/规则/Reasoner，不能静默改写当前执行代码；新版本必须经过 `Candidate -> evaluate -> verify -> promote`。

这五个名称是统一 `Tagged[T, RealityTag]` 的可读别名，而不是五套互不兼容的包装器：

```text
Observed[T]       = Tagged[T, observed]
Predicted[T]      = Tagged[T, predicted]
Imagined[T]       = Tagged[T, imagined]
Generated[T]      = Tagged[T, generated]
Counterfactual[T] = Tagged[T, counterfactual]
Validated[T, P]   = Tagged[T, validated(P)]
```

标签不能用普通 cast 改变。只有显式 `validate`、`ground`（用现实观察/约束和版本化策略验证预测或生成值）和 `promote`（晋升已评估候选）门可以产生 `Validated`；其中只有 `ground` 产生可进入现实证据的 `validated(P)`，`validate` 只证明结构/契约，`promote` 只证明版本准入。三者都追加相应报告、来源和策略摘要。`Validated` 仍不是绝对真值，只是“在策略 `P` 的范围内通过检查”。

Agent 是这个 AI 基底上带信念、目标、权限和外部行动能力的特化。一个 Agent 是可序列化的状态：

```n
agent Analyst {
    belief: BeliefStore
    goals: GoalSet
    memory: Memory
    working_set: WorkingSet
    reasoners: ReasonerSet
    tool_scopes: ToolScopeSet
    policy: Policy
    budget: Budget
}
```

“AI 原生”有七个可检查含义：源语言/n-IR 能声明 `ai/world/learner/agent`；类型系统区分现实、预测、想象、参数和 capability；n-IR 保留预测、rollout、更新、适应、事件、行动、`ExecutionPlan` 和 `derive`；运行时提供学习/事件/群体/Agent 调度；后端能针对 dense、sparse、event-driven 和异构织网降级或特化；AI 能用 `ProgramDelta` 直接生成和演化程序；系统能从 `PerformanceReceipt` 学习并自动晋升更优执行计划。所有行为必须降级为 RTST 的 `TransitionContract`，并由 `Delta`/`CommitGate`/`Credit` 约束。Agent 不是普通类库，也不是内置黑箱智能。

Agent 状态可以序列化；主机句柄、工具能力和一次性票据不属于可复制的 Agent 状态，必须由运行时重新绑定。`reasoners` 保存可审计的 n 实现及其摘要，不保存 LLM 会话或远端模型句柄。

Agent 的单步转换分为纯认知、授权和不可逆执行三个阶段：

```text
observe(agent, input)  -> EvidenceDelta
derive(agent, evidence) -> BeliefDelta
judge(state, question) -> Decision
plan(agent, decision)  -> Plan
authorize(plan, capability, budget) -> Result[ActionTicket, CommitError]
execute(ticket)         -> Result[Observation, ToolError] ! io
learn(agent, outcome)  -> Agent
```

`observe`、`derive`、`judge`、`plan` 和 `learn` 默认是显式输入到输出的 n 计算：规则、约束求解、证据代数、图搜索和调度器都可由 n 程序检查与组合。n/Core 和参考运行时不包含 LLM 调用路径；提示词、token 预测、Transformer 权重和外部 LLM API 均不是 Agent 语义。外部计算必须通过 FFI/effect 与 RuntimeRoot 授予的 capability 声明并记录，不能被伪装成 n 原生推理。时钟、随机数和环境变量也不能在 `pure` 代码中隐式读取。

`ToolCapability`、`BudgetToken` 和 `ActionTicket` 都是由 RuntimeRoot 在部署级 `RootEnvelope` 内签发的线性资源：不能由 Agent 代码伪造、复制或重复执行。`authorize` 是确定性的机器门操作，不是请求人类批准：它消耗预算并生成绑定工具、输入摘要、策略版本、能力范围、幂等键和 nonce 的票据；静态已知检查可被编译器证明并提升到 RTST 边界，动态检查每张票只执行一次，不进入工具内部热循环。`execute` 消耗票据后才允许 IO。`Action` 只是可复制的描述值，不能直接执行。RuntimeRoot 是机器执行边界；默认可在已授予能力与预算内自主运行和优化。

每次转换都可以记录为事件：

```n
fn cycle(agent: Agent, input: Observation, question: Question,
         cap: linear[ToolCapability], budget: linear[BudgetToken])
    -> Result[(Agent, EventLog), CycleError] ! io {
    let e = observe(agent, input)
    let beliefs = apply(agent, derive(agent, e))
    let d = agent.reasoners.judge(&beliefs, &question)?
    let p = plan(beliefs, d)
    let ticket = authorize(p, cap, budget)?
    let outcome = execute(ticket)?
    let next = learn(beliefs, outcome)
    Ok((next, record(e, d, p, outcome)))
}
```

推理实现摘要、工具结果、输入事件、授权票据摘要和策略版本都必须出现在事件日志中；重放使用相同的输入、算法版本和工具回放数据，而不是再次调用外部世界。这不是对意识的承诺，而是让 Agent 的信念变化、工具行动和学习路径成为语言可检查的值。

工具执行策略必须显式选择：

```text
at_most_once  授权后最多执行一次；崩溃后进入 outcome_unknown 并由 reconciliation 判定，不自动重试
exactly_once  只有适配器能力证明确认支持同一幂等键/事务协议时才可使用
replay_only   只允许读取事件日志中的既有结果，不触碰外部世界
```

语言不能凭空保证外部系统的 exactly-once。`IdempotentEffect` 必须由可信适配器依据远端契约声明并由 RuntimeRoot 验证，不能由 Agent 代码自我声明。若能力在静态类型中体现，编译器要求该能力/事务约束；若能力由运行时动态绑定，授权阶段验证机器描述，不支持时返回 `UnsupportedExecutionPolicy`，不能把运行时信息伪装成编译期证明。发生结果不确定时，Agent 可继续本地推理和其他独立任务；只有依赖该结果的外部副作用被挂起。

### 4.0.1 平衡三态证据代数

`Tr` 不只是 `-1/0/+1` 数字，而是证据投影。证据必须保留多条来源，不能用一个 `SourceId` 覆盖融合历史：

```text
Evidence = {
    atoms: CanonicalSet[EvidenceAtom],
    policy_id: PolicyId,
    evaluation_time: LogicalTime,
    support: u64,
    oppose: u64,
    provenance: ProvenanceRef,
    mass: u64,
    digest: EvidenceDigest,
    saturated: Bool
}
EvidenceAtom = {
    id: EvidenceId,
    polarity: support | oppose,
    source: SourceId,
    dependence_key: Digest,
    weight_q: u64,
    data_label: DataLabel,
    origin: RealityTag,
    created_at: LogicalTime,
    provenance_leaf: ProvenanceRef
}
combine(policy, e1, e2) = project(policy, unique_union(e1.atoms, e2.atoms))
stance(p, n) = +1 if p > n
             =  0 if p = n
             = -1 if p < n
residual(p, n) = min(p, n)
status(p, n, mass) = no_evidence if mass = 0
                   = conflict if p > 0 and n > 0
                   = directional otherwise
```

`EvidenceAtom.origin` 是证据的现实来源标签：原始观察使用 `observed`，模型预测/生成只有在 `ground` 成功并附带 `GroundingReport` 后才能以 `validated(P)` 进入证据；`validate` 产生的结构标签和 `promote` 产生的版本准入不能单独充当现实 grounding。`imagined`、`counterfactual` 和未验证的 `predicted/generated` 只能作为计划输入，不能直接进入 `Evidence.atoms`。`created_at` 是证据进入 n 的逻辑时间，不再暗示所有证据都来自现实观察。

`ProvenanceGraph` 是内容寻址的有向无环图，节点分为 `Entity`（输入、输出或证据）、`Activity`（observe、judge、tool call、fusion 等）和 `Agent`（执行主体）；边表达 `used`、`generated`、`derived_from`、`attributed_to` 和 `associated_with`。原始载荷可以在日志中保留，也可以只保存受控存储引用和内容摘要。`sources` 是从 provenance 图投影出的叶来源集合，不再是唯一的溯源结构。合并时按节点 ID 去重并规范化边；ID 冲突必须报错，压缩后保留 Merkle 根、摘要和可按策略取回的叶节点。

因此：

- `+1` 表示当前正证据占优，不等于绝对真；
- `-1` 表示当前反证据占优，不等于绝对假；
- `0` 是认知投影；`status` 再区分无证据和有冲突，不能隐式当作 `false`；
- `residual` 保留冲突强度，`provenance` 和 `digest` 保留输入、判断过程和派生关系。

`support`、`oppose` 和 `mass` 是 `atoms` 在固定 `EvidencePolicy` 下的缓存投影，不是可独立累加的真值。原子 ID 由完整规范化原子内容寻址；不能只信任不可信外部输入自报的 ID。同 ID 不同内容必须返回 `EvidenceIdCollision`。`dependence_key` 由证据策略根据可信 provenance 生成或验证，不能由不可信输入任意选择。`combine(policy, a, b)` 要求两侧 `policy_id` 和 `evaluation_time` 与策略快照一致，对原子集合做规范化并集，再从头计算投影；不同策略/时间需显式 `reproject`。`digest` 覆盖策略 ID、评价时间、规范化原子 ID 和不可变来源 provenance。权重使用确定性定点数和饱和算术，溢出设置 `saturated=true`。策略可按 `dependence_key` 对同源或派生证据限额，避免多 Agent 重复转发放大权重；这只是保守去重规则，不是统计独立性证明。

由于底层是原子集合并集，固定同一策略和评价时间时，`combine` 可满足交换律、结合律和幂等律；摘要由策略 ID、评价时间、规范化原子 ID 与各原子的不可变来源 provenance 计算，不依赖到达顺序。传输/转发活动单独记入 `EventLog`，不能改变证据原子的身份或权重；证据融合不把每次 merge 的操作节点追加进规范证据根。不同 Agent 可以并行收集并重复转发证据，再以相同策略快照重放融合结果。证据质量、来源权重、依赖组限额、时间衰减和最大 `residual` 必须由版本化 `EvidencePolicy` 明确定义。

`EvidencePolicy` 至少定义定点权重规则、依赖组限额、评价时间、最小证据质量和允许的最大 `residual`。因此“支持”不是自动“批准”：决策策略还必须检查 `status`、质量阈值和目标风险。

```n
claim Safety {
    value: Bool
    evidence: Evidence
}

let fused = reduce[Evidence.combine[policy], associative, commutative, idempotent](claims_from_agents.evidence)
match stance(fused) {
    +1 -> approve()
     0 -> request_more_evidence()
    -1 -> reject()
}
```

### 4.0.2 Agent 融合

`fuse` 是 n 的原生组合操作，不是把多个 Agent 隐式平均。可并行的策略必须声明代数定律：

```n
cap FusionPolicy[A] {
    const associative: Bool
    const commutative: Bool
    const idempotent: Bool
    fn merge(A, A) -> Result[A, FuseError] ! pure
}

fuse[P: FusionPolicy](agents: View[Agent, [N]])
    -> Result[Agent, FuseError] ! pure
```

融合规则固定为：

1. 信念按 `Evidence` 合并，保留每条来源和 `residual`；
2. 目标按策略合并，冲突目标生成 `GoalConflict`，不能静默覆盖；
3. 记忆按事件 ID 去重，事件内容不可变；
4. 工具权限取交集，扩权必须显式 `grant`，不能因融合自动获得更多权限；
5. 预算取保守值，并记录预算来源；
6. 策略必须显式选择 `consensus`、`priority` 或自定义 `cap FusionPolicy`；只有 `associative && commutative` 的策略允许并行重排，只有 `idempotent` 的策略允许事件去重。

融合结果仍是普通 `Agent` 值，可以继续观察、计划、行动或再次融合。多 Agent 系统由同一代数构成，而不是额外发明一套隐式消息语义。

`Plan` 必须是带前置条件、预期效果、风险、资源估算和证据摘要的描述值；它不是执行保证。`authorize` 重新检查前置条件、工具 schema、数据标签和预算，任何一项不满足都返回 `CommitError`。

### 4.0.3 RuntimeRoot、预算和记忆

RuntimeRoot 是语言运行时的机器化信任根。启动时装载版本化 `RootEnvelope`，其中包含可用设备/外部接口、数据流标签规则、效果范围、资源上限、完整性不变量和晋升规则；它不是逐项由人审批的工作流。硬完整性不变量不可由 Agent 改写；envelope 的可调部分只能通过独立 AdmissionGate 验证的版本转换更新。Agent 可在 envelope 内自行派生 capability、分配预算、选择数据保留/压缩策略并优化运行计划；越界候选不能自行批准或签发 root authority。无外部 capability 时，纯推理、学习候选和本地计划仍可运行；只有相应外部效果被拒绝。

```text
RootEnvelope = {
    mission_objective: Digest,
    objective_epoch: VersionId,
    hardware: DeviceCapabilitySet,
    external_interfaces: CapabilitySet,
    dataflow: DataFlowContract,
    resources: ResourceEnvelope,
    hard_invariants: ConstraintSet,
    upgrade_policy: PolicyId,
    evaluators: CanonicalSet[EvaluatorDigest],
    digest: Digest
}
```

`hardware` 可由运行时探测，外部接口能力来自可验证适配器契约，其余字段来自已签名的系统映像或上一 epoch 已提交的 envelope。RuntimeRoot 按 `upgrade_policy` 和 evaluator 集为具体候选构造 `AdmissionGate`；候选版本不能成为自身唯一 evaluator，也不能在评价过程中改写 `mission_objective`、计时器、成本计数器或保留集。

RuntimeRoot 不应成为每个 kernel 的远程中心服务。启动或 epoch 边界由根生成绑定运行时实例的本地线性 `RootLease`，其中缓存本地可用的 capability、预算上限、数据流摘要、评价 epoch 和撤销 epoch；它不可跨进程复制，跨设备/worker 必须派生子 lease。热路径只验证 lease 的局部不变量，不查询远端 root。撤销通过有界延迟的控制面传播；lease 声明最大失效延迟，达到期限后本地立即失效。外部副作用提交边界必须再检查 lease epoch/撤销水位，不能仅凭热路径缓存授权。拓扑、envelope 或依赖摘要不匹配时，只停止受影响的外部效果/计划，并允许独立纯计算继续。

```text
RootLease = {
    root: Digest,
    envelope: Digest,
    runtime_instance: Digest,
    subject: Digest,
    capability: CapabilitySet,
    credit: Credit[resource],
    objective_epoch: VersionId,
    expires_at: MonotonicDeadline,
    max_revocation_staleness: Duration,
    revoke_epoch: u64,
    fabric: Digest,
    local_checks: ConstraintSet,
    digest: Digest
}
```

1. 外部输入和工具返回值默认是 `Untrusted[T]`；schema 校验只证明结构符合，不证明事实为真或内容安全。输入可以影响推理和计划，但不能授予 `ToolCapability`、提升预算或改变策略版本。可选的 `Validated[T, PolicyId]` 只表示满足指定验证策略，不表示客观真实；得到该类型必须经过显式、可审计的验证操作，不能强制转换。`DataLabel` 分开记录完整性与机密性，二者按各自策略传播；验证不能降低机密性，降低机密性必须有独立授权的 `declassify` 操作并写入事件。
2. `ToolCapability` 由 RuntimeRoot 按 `RootEnvelope` 创建或从父 capability 衰减派生，携带工具名、参数/结果 schema、允许的副作用、数据标签、速率限制和撤销句柄。Agent 字段只能保存 `ToolScope`，不能伪造可执行能力。工具描述和行为注解只是提示，不构成授权；结果必须 schema 校验并继续标记为不可信。
3. `Budget` 是单调消耗的资源，至少分为 `steps`、`bytes`、`compute`、`time` 和 `tool_calls`；每种推理内核和工具必须声明计费单位。`authorize` 先锁定最坏情况预算，`execute` 按实际使用结算，退款必须显式记录。预算不足返回 `BudgetExceeded`，不得静默降级为无限运行。
4. `Memory` 不是无限日志。它必须有 `retention`、`max_bytes` 和 `compact` 策略；Agent 可按学习价值、未来任务收益、回放价值和存储/能耗成本自主选择保留、压缩与淘汰，在 `RootEnvelope` 的数据流/保留边界内提升单位资源的信息效用。压缩后保留事件 DAG 根摘要和证据残余，不能宣称与原始记忆逐字等价。
5. Agent 的可信度、人格或策略不是语言魔法；它们是可版本化的普通值，改变策略必须产生新 `PolicyId` 并记录在事件中。

### 4.0.4 回放、时间和外部世界

可重放只对 n 代码和已记录的外部边界作保证，不对现实世界的再次执行作虚假承诺。每个事件至少包含：

```text
Event = {
    sequence: u64,
    kind: EventKind,
    parents: CanonicalSet[EventHash],
    event_schema_version: u32,
    nir_version: u32,
    program_digest: Digest,
    input_digest: Digest,
    inference_digest: Digest?,
    inference_trace: Recorded[InferenceTrace]?,
    decision_result: Recorded[Decision]?,
    decision_digest: Digest?,
    provenance_root: ProvenanceRef?,
    policy_id: PolicyId,
    effect_key: EffectKey?,
    effect_status: EffectStatus?,
    action_ticket_digest: Digest?,
    tool_result: Recorded[Observation]?,
    task_id: TaskId?,
    branch_id: BranchId?,
    message_id: MessageId?,
    base_event: EventHash?,
    branch_revision: u64?,
    mailbox_cursor: MessageCursor?,
    state_digest: Digest,
    logical_time: u64
}
EventKind = observe | retrieve | focus | route | derive | judge | effect | task | branch | message | merge | memory | quiescent | state_transition
EffectStatus = intent | succeeded | failed | outcome_unknown
```

`ReplayMode` 分为：

```text
strict    所有输入、推理算法版本、工具结果和随机种子都必须来自事件日志
simulate  工具不执行，只返回日志中记录的结果
audit     只验证事件 DAG、权限、预算和状态摘要，不重新运行推理算法
```

墙上时钟、网络响应、外部计算结果和随机数只能通过显式效果进入；可重放代码使用 `logical_time` 和记录的值。每个外部副作用先写入含稳定 `EffectKey` 的 intent，再记录结果；若进程在外部执行后、结果落盘前崩溃，状态是 `outcome_unknown`，不能自动重试或谎称已回滚。只有外部服务支持同一幂等键/事务时，才能安全重试。事件日志采用规范化序列化和内容寻址 DAG：分支各自追加事件，跨分支合并事件引用所有因果父项；DAG 必须无环，父项集合按规范顺序参与摘要。schema/IR/程序版本不匹配必须返回 `ReplayError`。升级旧任务需要显式、可测试的 replay adapter，不允许悄悄用新代码解释旧事件。

推理轨迹、外部输入和工具结果是带完整性/机密性标签的计算资产；存储采用加密内容寻址、按 capability 检查的数据流和显式保留契约。n 不设“越少保留越好”的普遍目标：AI 在 envelope 允许范围内，以学习/回放/未来任务价值对比存储、带宽和能耗，选择保留、压缩或淘汰。淘汰必须留下可审计摘要；载荷无法取回时严格回放返回 `ReplayDataUnavailable`，不能把 digest 冒充原始结果或静默重调外部系统。

### 4.0.5 类型化判断原语（JEV 启发，无模型依赖）

JEV 更接近“给定状态、提出具名问题、返回结构化判断”的决策接口，而不是一门语言。n 只吸收问题边界清晰、判断与行动分离的思路；JEV 和它所使用的外部模型都不是 n 的运行时依赖。在 n 中，判断由 n 实现的规则、约束、搜索或数值内核产生，是可组合、可审计的一等值：

```n
enum DecisionState {
    support,
    oppose,
    unknown,
    conflict
}

struct QuestionId {
    name: String
    version: u32
    input_schema: Digest
    output_schema: Digest
}

struct Decision[T] {
    answer: T?
    state: DecisionState
    confidence: f32?
    evidence: Evidence
    question: QuestionId
    reasoner: ReasonerDigest
    explanation: ExplanationMode
    trace: InferenceTraceRef?
    output_digest: Digest
}

ExplanationMode = none | result_only | summary | trace | proof(Digest)

ReasoningReceipt = {
    question: QuestionId,
    reasoner: ReasonerDigest,
    policy: PolicyId,
    input_digest: Digest,
    output_digest: Digest,
    explanation: ExplanationMode,
    quality: QualityReport,
    residual: ResidualReport,
    trace: InferenceTraceRef?,
    replay: ReplayMode
}
```

`DecisionPolicy` 是 `Evidence.status` 到 `DecisionState` 的唯一规范映射，不能由各个 Reasoner 私自解释：`no_evidence`、低于最小质量/覆盖率或超出校准域映射为 `unknown`；正反证据同时存在且超过允许 `residual` 映射为 `conflict`；满足阈值才映射为 `support`/`oppose`。因此 `DecisionState` 是带策略版本的投影，不与 `Tr` 或概率混为一谈。`ExplanationMode` 由目标/成本策略选择，允许 `none` 或 `result_only`；不可解释的候选可参与 AI 内部搜索、预测和受限用途，但 opacity 不会自动生成 Evidence、GroundingReport、Capability 或 AdmissionReceipt。需要提交、外部行动或现实标签提升时，门控检查的是相应机器契约，不强迫生成一段自然语言推理过程。

`Question` 是稳定版本化的声明，不是任意提示词。一个问题应只判断一个边界明确的属性，并固定输入 schema、输出 schema、问题 ID 和版本：

```n
question CallbackRequested {
    id: "callback-requested@1"
    input: Message
    answer: Bool
}

reasoner CallbackRules for CallbackRequested {
    derive(message) {
        support(true) when message.intent == callback
        support(false) when message.intent in {decline, information_only}
        unknown otherwise
    }
}
```

判断实现通过能力接口接入；实现必须是可编译的 n 代码，例如规则网络、约束求解器、图搜索、规划器、传统分类器或数值算法：

```n
cap Judge[S, Q: Question, A] {
    const reasoner_digest: ReasonerDigest
    fn judge(state: &S, question: &Q)
        -> Result[Decision[A], JudgeError] ! {pure, alloc}
}
```

`Judge` 的实现必须产生类型化 `Decision[A]` 和 `ReasoningReceipt`；它可以选择不暴露中间轨迹。`explanation = none/result_only` 时，运行时至少保留输入/输出摘要、Reasoner 版本、策略版本、适用域、质量/残差和随机/数值 profile；这些是机器回放与门控所需的结果契约，不是人类可读证明。若策略或风险等级要求 `Evidence`、`GroundingReport` 或 `proof`，缺少对应产物仍返回 `unknown`/拒绝；不要求把内部推理翻译成自然语言。违反输出 schema 返回 `SchemaMismatch`，不能静默转换成布尔值。`DecisionState` 由 `Evidence.status` 和策略阈值计算：`unknown` 对应无足够证据，`conflict` 对应正反证据同时存在；不能把二者隐式当成 `false`。`confidence` 只是由 `EvidencePolicy` 定义的校准指标，不是概率，也不能单独授予权限。
对内部搜索、路由和低风险控制，默认可采用 `result_only` 以减少解释、日志和延迟成本；只有诊断、回放差异、训练信号或 `EvidencePolicy` 明确要求时才生成完整 trace/certificate。这样“灵光一现”的结果可以直接进入受限计算路径，但不能绕过 `verify`、`authorize` 或版本晋升门。

判断与行动始终分离：

```n
let decision = CallbackRules.judge(&state, &CallbackRequested)?

match decision.state {
    support  -> authorize(callback_plan, capability, budget)
    oppose   -> continue_without_callback()
    unknown  -> request_more_evidence()
    conflict -> escalate_to_human()
}
```

即使 `Decision` 为 `support`，它也只能作为 `Plan` 的输入；只有 `authorize` 重新检查策略、能力、数据标签和预算后，才能产生 `ActionTicket`。推理实现摘要、问题版本、输入/输出摘要、`ReasoningReceipt`、按策略要求的 `Evidence` 和 `DecisionState` 都必须写入事件日志；`InferenceTrace` 仅在 `ExplanationMode`、诊断或风险策略要求时写入。严格回放运行相同 n-IR 或使用已记录结果，不能依赖未绑定摘要和版本的不可见黑箱判断；绑定 `ReasoningReceipt` 的 result-only 结果可以直接回放。

多个判断可以通过固定策略快照下的 `Evidence.combine(policy, ...)` 或显式 `FusionPolicy` 融合，但必须保留问题 ID、版本、原子证据 ID、来源和冲突残余。编译器和工具链应为每个问题提供精度、召回率、未知率、冲突率、schema 失败率和版本漂移基准；这些指标不能被语言类型系统伪装成正确性证明。

### 4.0.6 Agent 委派与耐久任务

`fuse` 组合的是认知状态，不负责跨进程通信，也不会把权限从一个 Agent 复制给另一个 Agent。跨 Agent 协作必须建立有身份、可撤销、限时和预算受限的委派：

```n
struct DelegationGrant {
    issuer: AgentId
    subject: AgentId
    task_digest: Digest
    tool_scopes: ToolScopeSet
    data_labels: DataLabelSet
    budget: BudgetSlice
    expires_at: LeaseExpiry
    policy_id: PolicyId
}

enum TaskState {
    submitted, running, needs_input, completed, failed,
    cancel_requested, cancelled, rejected, outcome_unknown
}

struct AgentTask[Output] {
    id: TaskId
    state: TaskState
    updates: Recorded[TaskUpdate]
    artifacts: View[Untrusted[Output]]
}
```

父 Agent 通过 `authorize_delegation` 为子任务派生受限 grant：子权限必须是父 capability 的子集，预算从父预算中预留，数据标签不得降级，RuntimeRoot 的 `LeaseExpiry` 不得晚于父 grant。子 Agent 不能自行扩大权限或预算；进一步委派必须处于 envelope 允许的委派规则内并再次衰减 grant。远端身份认证、grant 绑定和撤销由 RuntimeRoot/传输适配器完成，语言类型不能替代密码学认证。

任务状态迁移必须由事件驱动并记录版本、更新时间和 artifact 摘要。`needs_input` 可通过同一 Task 的后续消息恢复；`cancel_requested` 不等于已取消，`cancelled` 也不意味着先前完成的外部副作用已回滚。远程断连或超时不能确定动作是否发生时，状态必须是 `outcome_unknown`，由显式 reconcile 决定后续操作。任务输出即使通过 schema 校验，仍是 `Untrusted[T]`，必须保留 provenance 和数据标签。

网络协议属于互操作扩展，不属于 n/Core。`n.agent.protocol` 可以适配 MCP 风格的工具 schema 与 A2A 风格的异步任务/制品流；协议描述、Agent card 和工具注解都不能授予权限。传输层必须实现超时、取消、背压、重连和幂等键；任务观察句柄可复制，授权、预算和取消票据仍遵守线性语义。

### 4.0.7 多螺旋认知并行

n 把“多条平行螺旋”定义为从共同主干快照分出的并行认知分支：每个分支可采用不同假设、策略或数据切片，独立观察与推演；分支之间通过增量消息互相启发，主干按检查点吸收有效变化。它不是共享可变 Agent，也不是把多个答案做多数表决。

```n
struct BranchSnapshot {
    id: BranchId
    base_event: EventHash
    local_head: EventHash
    revision: u64
    mailbox_cursor: MessageCursor
}

struct BranchMessage[T] {
    id: MessageId
    message_version: u32
    payload_schema: Digest
    from: BranchId
    recipients: CanonicalSet[BranchId]
    scope: peer | trunk | peer_and_trunk
    sender_seq: u64
    causal_parents: CanonicalSet[EventHash]
    payload: Untrusted[T]
    provenance: ProvenanceRef
}

enum BranchConsistency {
    causal_async,
    ordered_async,
    round_sync
}
```

默认优先尝试 `causal_async`：没有全局 epoch barrier。分支完成一个局部转换后即可发布消息；另一分支即使仍在运行，也能在自己的下一个安全点从持久 mailbox 取得因果就绪的消息并改变后续推演。消息不能插入正在执行的指令，也不能直接写入另一个分支的状态。`ordered_async` 使用主干签发、包含活动发送者集合及各发送者下界的 watermark，确认规范顺序之前没有缺失消息；`round_sync` 只用于确实需要轮次算法、批处理或严格实验对照的场景。

分支协作分成两个互不混淆的通道：`peer` 消息进入指定分支的 mailbox，只影响其后的本地推演；标记为 `trunk` 的增量才有资格进入主干合并，且仍需通过 `BranchPolicy`。`peer_and_trunk` 只是同一消息的双路投递，不代表两条独立证据。主干变化作为带来源和因果父项的 `TrunkDelta` 异步投递给订阅分支。完整 Agent 状态、权限票据和预算不能作为可合并负载。

执行规则：

1. `fork` 从同一个不可变 `BranchSnapshot` 建立分支；大对象、Evidence atom 和纯计算缓存可结构共享，分支内的可变状态和本地事件头隔离。
2. 分支只能用 `publish` 发出版本化的 `EvidenceDelta`、`Constraint`、`Question` 或 `Proposal`，并指定收件分支及通道。`MessageId` 由规范化消息内容与发送分支摘要寻址；同一发送者的 `sender_seq` 单调递增。消息在 durable outbox 提交后即可异步传输，但不会直接改写收件分支；收件分支必须在后续 `receive` 状态转换中显式消费。
3. mailbox 只暴露因果父事件已提交的消息；父项缺失的消息等待或进入隔离区。`causal_async` 只允许编译器从受限的 join-semilattice/delta 组合中证明为单调、交换、幂等且合流的处理器自由重排/批处理，用户声明本身不构成证明。无法证明的处理器必须使用 `ordered_async`，等待 watermark 后按规范键 `(sender, sender_seq, MessageId)` 处理，或退回 `round_sync`；否则返回 `NonConfluentAsync`。
4. 主干通过 `integrate` 只吸收显式标记为 trunk-visible 且获 `BranchPolicy` 许可的增量：Evidence atom 做集合并集并保留完整性/机密性标签；目标/约束冲突返回 `MergeConflict`；记忆按事件/atom ID 去重；权限不能通过融合扩张，预算只能由主干显式切片。`Proposal` 和 `Plan` 保持不可信描述值，须重新审核，不能被 merge 自动执行。整批 merge 原子提交，冲突失败不留下半更新；到达顺序不能决定结果。
5. 每个分支绑定 `base_event`。主干前进后，旧分支必须显式 `rebase` 并处理冲突，或以旧基线继续只读探索；禁止按字段最后写入者静默覆盖。
6. 消息、分支结果和 rebase 都写入事件 DAG。分支彼此影响留下因果边，因此可重放“谁在何时看到什么并因此改变了什么”。
7. 可重排的 `BranchPolicy` 必须声明并满足交换律/结合律/幂等律；不满足的策略必须给定显式稳定优先级，编译器不能按线程完成顺序选择胜者。
8. 分支状态、已消费 cursor 和待发送 outbox 在同一持久事务中提交。崩溃前未提交则重新计算；提交后未送达则按同一 `MessageId` 重投。收件方去重，所以交付可以是 at-least-once，而认知转换不会被重复计入。
9. 异步主干整合器持续消费 trunk-visible 增量。满足代数定律的增量可并行合并；其他增量绑定 `base_event`，主干已前进时返回 `StaleBranch` 或要求 rebase。
10. mailbox 和 outbox 都有显式容量。普通消息达到上限时 `publish` 必须 await 或返回 `Backpressure`，不能静默丢弃；取消、撤销和预算耗尽等控制消息使用有界保留通道，避免数据拥塞阻止停止。
11. `cancel(branch)` 只在安全点生效：分支进入 `draining` 后不再产生新工作，已提交消息仍按日志语义投递，未提交计算被丢弃，持有的 `WorkCredit` 必须显式归还。取消不撤回已经合并的证据，也不谎称外部副作用已回滚。

`BranchPolicy` 必须给出一致性模式、处理器代数声明、最大活动分支数、最大状态转换数、mailbox/outbox 与控制通道容量、最大在途消息数、消息/载荷上限、允许的主干陈旧度、全局及单分支预算、路由/主干准入规则和停止谓词。调度器从有限预算内选择分支，不因“多开几个”就默认更好：先保留少量假设不同的探索分支；只有预期新增信息或风险覆盖足以抵偿边际成本时才扩大 fan-out。预算中可保留一部分给低排名但假设不同的分支，避免单一评分导致过早同质化。调度分数只是调度提示，不是证据权重、真实性或行动授权。

```n
async scope multi_spiral {
    spawn trunk_integrator {
        while let deltas = await trunk_mailbox.receive_ready() {
            let (next_trunk, trunk_delta) = integrate(trunk, deltas, policy)?
            atomic event_commit {
                trunk = next_trunk
                trunk_mailbox.advance(deltas.cursor)
                trunk_outbox.append(publish(trunk_delta, subscribers))
            }
        }
    }

    for branch in branches {
        spawn branch_worker(branch) {
            loop while policy.permits(branch) {
                let inputs = await branch.mailbox.receive_ready(policy.consistency)
                let (next, outputs) = analyze(branch.snapshot, inputs)
                atomic event_commit {
                    branch.snapshot = next
                    branch.mailbox.advance(inputs.cursor)
                    branch.outbox.append(canonicalize(outputs))
                }
            }
        }
    }
}
```

异步可重放不等于跨调度结果天然相同。若处理器满足上面的合流性质，运行时可以证明不同合法交错最终得到同一规范摘要；若使用 `ordered_async` 或含非单调推理，实际 message/cursor 顺序就是程序的可观察输入，必须写入事件 DAG，重放相同顺序。需要跨调度等价但无法证明合流的程序必须选择 `round_sync`，不能由编译器猜测。

异步系统不能把“一段时间没消息”当成收敛。每个被调度的工作持有线性 `WorkCredit`；派生新任务或消息时，outbox 事件必须记录 credit 的转移/拆分，完成且不再派生工作时归还。消息重投只复用同一 credit 转移记录，不能再次铸造 credit。只有根调度器收回全部 credit、所有 durable mailbox/outbox 为空、没有进行中的主干提交时，才能记录 `Quiescent`。它只表示在给定策略和预算下当前没有待处理工作，不证明结论真实或问题已穷尽。达到状态转换、计算、时间或工具预算上限时返回 `IterationLimit`，并保留 pending mailbox。重复消息按 `MessageId` 去重；Evidence atom 沿用原始 ID 和 `dependence_key`，转述/互引不能制造新证据或放大权重。

效率来自独立探索的并行执行、等待隐藏、不可变输入/纯计算缓存、增量消息、按边际收益调整 fan-out，以及对已无新工作的分支早停。跨分支 memo key 至少包含函数/程序摘要、输入摘要、类型/布局、策略版本；只缓存纯计算，不能把网络或工具副作用伪装成可安全复用。调度器必须有稳定 tie-break 和防饥饿规则；工作窃取仅改变纯任务的执行者，不能改变分支可见性或预算归属。早停和限分支可能减少覆盖率；异步协作也可能增加通信和总计算成本。因此必须同时度量墙钟时间、总计算成本、消息量、覆盖率和最终质量，并在相同质量门槛与预算口径下比较单分支/同步多分支/异步多分支。

### 4.0.8 无 LLM 的认知内核与架构借鉴

n 借鉴 LLM 架构解决信息选择、稀疏路由、长程记忆和推测验证的方法，但不采用语言模型本身：不需要 tokenizer、提示词、自回归 next-token、Transformer 权重、预训练语料或 LLM 服务。参考运行时的 Agent 测试必须仅用 n 编写的规则、约束、搜索、规划、检索和证据代数通过。

| LLM/模型中的思路 | n 的非 LLM 重构 | 明确不采用 |
| --- | --- | --- |
| [Attention](https://arxiv.org/abs/1706.03762) | `focus` 根据目标、因果距离、风险和证据新颖度，从工作集选出有界相关子集；评分函数和选择依据可审计 | 不使用学习出的注意力权重充当不可解释真值 |
| 多头注意力 | 多条类型化 FocusLane 分别检查事实、反证、风险、资源和目标，再用证据代数合并 | 不把多个 lane 简化为多数投票 |
| [稀疏专家路由](https://arxiv.org/abs/2101.03961) | `route` 只激活少量满足类型/能力约束的 Reasoner，并约束负载、预算和 fallback | 不复制超大参数专家或训练不稳定性 |
| [长程分段记忆](https://arxiv.org/abs/1901.02860) | `WorkingSet` 保存当前焦点，`EpisodicMemory` 保存内容寻址事件段；摘要带残余和 provenance，可显式取回 | 不使用隐式固定 token context 作为记忆 |
| [检索增强](https://arxiv.org/abs/2005.11401) | `retrieve` 先从外部/长期记忆取回证据原子，再由 `derive/judge` 使用；每个结果保留来源和有效期 | 不让检索文本直接变成未验证结论 |
| 残差连接 | `BeliefDelta` 叠加到不可变基线，冲突保留 residual；失败可回退到旧状态 | 不静默覆盖信念或主干 |
| KV cache | 增量依赖缓存按程序、输入、策略、布局和版本摘要复用纯计算 | 不缓存网络、工具或其他副作用 |
| 推测解码/自一致性 | 多螺旋分支提出候选，`verify` 检查约束与证据后才 `integrate` | 不生成 token，也不把重复答案数量当证据 |

核心认知流水线因此是 `retrieve -> focus -> route -> derive -> judge -> plan -> verify -> authorize`。其中 `focus` 决定现在看什么，`route` 决定调用哪些显式 Reasoner，`derive` 产生可追溯的新信念，`verify` 阻止未经检查的候选进入主干或行动阶段。所有步骤都降级到 n-IR，并可分别替换、测试和计费。

### 4.0.9 多模型架构的 AI-native 重构

n 不把每种 AI 架构做成一套孤立框架，而抽取它们共有的状态、时间、更新、搜索和验证结构：

| 架构来源 | 可吸收的核心思想 | n 的原生重构 | 不照搬 |
| --- | --- | --- | --- |
| [World Models](https://arxiv.org/abs/1803.10122)、[DreamerV3](https://arxiv.org/abs/2301.04104) | 学习环境动力学，在内部 rollout 中评估未来行为 | `World`、`Dynamics`、`StateEstimate`、`rollout`、`Trajectory[Imagined[T]]`；现实校准误差是一等值 | 不把“梦境”当真实证据，不强制使用生成神经网络或强化学习 |
| [I-JEPA](https://arxiv.org/abs/2301.08243) | 在表示空间预测重要目标，而非必须重建所有细节 | `Latent[T, Schema]`、`PredictionTarget` 和可验证表征契约 | 不把特定 ViT/遮罩策略固化进核心，也不假设潜变量天然可解释 |
| [Mamba/选择性状态空间](https://arxiv.org/abs/2312.00752) | 以状态递推处理长序列，并根据输入选择性保留/遗忘 | `StateSpace`、`RetentionPolicy`、增量扫描和有界流式状态 | 不内建 Mamba 网络、token 序列或训练配方 |
| [MAML](https://arxiv.org/abs/1703.03400) | 优化“如何快速适应”，区分跨任务元状态与任务内更新 | `MetaState`、`TaskState`、`adapt@k`、内/外目标和参数区域 | 不假设所有适应都靠梯度，也不允许任务数据泄漏到元评估 |
| [POET](https://arxiv.org/abs/1901.01753) | 环境与解法共同产生，多路径探索并转移 stepping stone | `WorldGenerator`、`Population`、`Lineage`、`transfer` 和受限并行生态 | “开放式”不等于无限资源、无限权限或无安全边界 |
| [MAP-Elites](https://arxiv.org/abs/1504.04909) | 保存多样且高质量的解，而不是只追逐单一最优值 | 类型化 `BehaviorDescriptor`、`QDArchive`、novelty/quality 双指标 | 不把预定义的描述维度冒充完整智能度量 |
| [Neural ODE](https://arxiv.org/abs/1806.07366)、[Liquid Time-constant Networks](https://arxiv.org/abs/2006.04439) | 连续时间动力学、适应性求解和状态相关时间尺度 | `ContinuousDynamics`、`SolverPolicy`、容差/稳定性合约和可微求解 | 不隐藏求解器误差、步长、刚性失败或反向近似 |
| [Surrogate-gradient SNN](https://arxiv.org/abs/1901.09948) | 以稀疏脉冲、局部状态和可塑性进行事件驱动计算 | `Spike`、`EventStream`、`NeuronState`、`SynapseState`、`PlasticityRule` 和 neuromorphic backend | 不宣称生物等价、意识或能耗优势；优势必须由硬件基准证明 |
| [DDPM / Diffusion](https://arxiv.org/abs/2006.11239) | 以显式噪声日程和逐步去噪表示生成/逆过程 | `NoiseSchedule`、`DenoisingProcess`、`ScoreField`；每一步携带 seed、温度、预算和 `Generated[T]` 标签 | 不把采样样本当作 `Observed`，不把固定采样步数或扩散网络写死进核心 |
| [Graph Networks](https://arxiv.org/abs/1806.01261) | 以节点、边和全局量的关系归纳偏置进行消息传递 | `Graph[N, E]`、`GraphMessage`、显式聚合顺序与拓扑 provenance | 不把任意张量 reshape 冒充无损图转换，也不隐藏动态图拓扑变化 |
| [Memory-Augmented Networks](https://arxiv.org/abs/1605.06065)、[Titans](https://arxiv.org/abs/2501.00663) | 外部/长期记忆通过地址策略读写，记忆可在测试时更新 | `AdaptiveMemory`、`MemoryAddress`、`MemoryUpdate`；容量、遗忘、权限、版本和来源进入效果/事件 | 不允许隐藏可变缓存改变纯函数，也不允许测试时更新绕过候选评估 |
| [RWKV](https://arxiv.org/abs/2305.13048)、[RetNet](https://arxiv.org/abs/2307.08621)、[Hyena](https://arxiv.org/abs/2302.10866) | 在并行训练、递归推理、保留状态和长卷积之间切换 | 统一 `SequenceOperator`、`RetentionState`、`LongKernel`、`scan/recur/chunk` 三种执行计划；状态边界可重放 | 不内建 token、语言模型权重或某一种线性注意力公式；不同计划必须共享结果契约 |
| [Test-Time Training](https://arxiv.org/abs/2407.04620) | 把隐状态视为可更新的小模型，以当前序列做受限自监督适应 | `test_adapt@k` 产生隔离的 `AdaptiveState`/`Candidate`，记录数据窗口、损失、步数和回滚点 | 不把在线样本自动写入长期模型，不把适应结果当无偏真值 |
| [Kolmogorov-Arnold Networks](https://arxiv.org/abs/2404.19756) | 将可学习的一元函数放在边上，提供更强的函数可视化和归纳偏置 | `BasisFunction`、`FunctionEdge` 和可导/可审计基函数；导出近似符号或误差报告 | 不声称可解释性自动成立，不把 spline 参数表示强制成唯一训练方式 |
| [Deep Equilibrium Models](https://arxiv.org/abs/1909.01377) | 用求根直接求隐式平衡状态，避免按层展开的固定深度 | `EquilibriumState`、`solve_equilibrium`、残差/容差/最大迭代和 `ConvergenceCertificate` | 不把“无限深度”当无限运行；不收敛、非唯一或梯度不稳定必须显式失败 |
| [Perceiver IO](https://arxiv.org/abs/2107.14795) | 用有限潜变量和查询解耦输入/输出规模与任务结构 | `LatentBottleneck`、`QueryPlan`、有界 latent memory；输入输出 schema 和信息损失可追踪 | 不用潜变量瓶颈掩盖丢失信息，也不把任意 query 结果当事实 |
| [Energy-Based Models](https://arxiv.org/abs/2002.05616) | 用能量/约束排序状态，不要求显式归一化概率 | `EnergyFunction`、`Constraint`、`SamplerPolicy`，采样温度、步数和收敛报告显式化 | 不把 energy 分数直接当概率、置信度或真实性 |
| [Conformal Prediction](https://arxiv.org/abs/2107.07511) | 将预测包装成带覆盖率目标的不确定性集合/区间 | `PredictionSet`、`CoverageContract`、`CalibrationReport`；校准集、分布假设和失效条件进入 provenance | 不把覆盖率承诺外推到未声明的分布漂移或对抗环境 |

#### 世界模型和预测边界

```n
world CartWorld {
    state: WorldState
    observation: SensorFrame
    action: Control

    fn transition(s: &WorldState, a: &Control, dt: TimeDelta)
        -> (Predicted[WorldState], StateDelta) ! pure
}

let futures: Trajectory[Imagined[WorldState]] =
    rollout(CartWorld, estimate, candidate_policy, horizon=64, budget)
let candidate = select(futures, objective)
let grounded = verify_against(candidate, latest_observation)?
```

`rollout` 消耗显式 horizon/compute/memory 预算。`Imagined` 可以产生候选计划和探索问题，但在 `authorize` 前必须经过策略指定的现实观测、约束证明或风险界限；预测校准、分布外状态和模型误差必须随 `Trajectory` 传播。

#### 元学习与可控自修改

```n
let candidate: Candidate[TaskPolicy] = adapt@k(meta_state, task_data, k=5)
let report = evaluate(candidate, held_out_task_data)
let next = promote(candidate, report, promotion_capability)?
```

元参数、任务参数、训练数据、保留评估数据和优化器状态使用不同区域/标签；`adapt@k` 必须有步数和预算上限。学习或进化只能产生新版本 `Candidate[T]`，不能在原地重写正在执行的 Reasoner、Policy 或授权规则；`promote` 是带审计记录的能力操作。

#### 开放式与质量多样性

开放式搜索由 `Population[Individual]`、`WorldGenerator`、`BehaviorDescriptor`、`QDArchive`、`Lineage` 和 `TransferReceipt` 组成。每次变异、环境生成、评估和跨环境迁移都记录父代、随机种子、预算和制品摘要。生成的世界默认处于无外部效果 capability 的隔离域；只有通过约束、回归、资源和完整性评估的候选才能晋升。n 使用“持续产生新颖且可验证的候选”作为开放式过程定义，不承诺复杂度无限增长或必然产生通用智能。

#### 连续时间、事件时间与 SNN

n 的时间域分为 `DiscreteTime`、`ContinuousTime` 和 `EventTime`。连续系统必须声明 solver、误差容限、最大步数和失败策略；SNN/event-driven 系统使用单调逻辑 tick 或定点时间戳，不能依赖不可重放的浮点事件排序。同一时间的事件按规范批次处理；零延迟事件环必须有微步上限，否则返回 `EventCycle`。突触可塑性是版本化 `PlasticityRule` 状态转换；surrogate gradient、STDP 或其他局部规则作为可替换 Learner，而不是 SNN 的唯一训练语义。

#### 前沿架构的共同执行契约

上述架构不增加互相竞争的“模型模式”。它们都降级为四种可组合对象：

1. **状态算子**：`SequenceOperator`、`StateSpace`、`AdaptiveMemory` 和 `EquilibriumState` 都是显式状态转换；状态的所有权、更新窗口、容量和回滚点必须可见。
2. **生成/搜索过程**：`DenoisingProcess`、`SamplerPolicy`、`rollout` 和 `Population` 都产生 `Imagined` 或 `Generated` 值；seed、噪声日程、温度、最大步数和预算进入事件摘要，不能隐式变成现实证据。
3. **结构化表示**：`Graph`、`LatentBottleneck`、`BasisFunction` 和 `QueryPlan` 都携带 schema、拓扑/信息损失和 provenance；转换必须显式，不能以同名 Tensor 类型掩盖语义变化。
4. **验证与不确定性**：`ConvergenceCertificate`、`CalibrationReport`、`CoverageContract` 和 `EvaluationReport` 只证明声明范围内的性质。校准失败、分布漂移、求解不收敛和采样预算耗尽都返回显式状态。

长序列执行计划至少有 `parallel`、`recur` 和 `chunked` 三种形式。编译器可以根据 `SequenceOperator` 的代数属性选择计划，但必须保留同一状态转换、归约顺序和浮点模式；RWKV/RetNet/Hyena 的具体公式属于 `n.sequence` 扩展，不是 n/Core 关键字。

测试时学习是受限的状态更新，不是隐式自修改：

```n
let adapted: Candidate[AdaptiveState] =
    test_adapt@k(base_state, window, objective,
                 steps=3, budget=adapt_budget)
let report = evaluate(adapted, calibration_window)
let next = promote(adapted, report, promotion_capability)?
```

`test_adapt@k` 默认只能写入短期隔离区域；要写入长期 `AdaptiveMemory` 或当前策略，必须经过 `evaluate -> verify -> promote`。同一输入和事件摘要下，适应前后状态都必须能重放；窗口外数据不得通过隐式全局缓存进入更新。

隐式平衡求解使用有界不动点/求根接口：

```n
let eq = solve_equilibrium(operator, initial,
                           tolerance=1e-6, max_iter=128,
                           policy=solver_policy)?
```

返回值携带残差、迭代次数、稳定性摘要和 solver 版本。没有 `ConvergenceCertificate` 的平衡状态不能自动进入 `Evidence` 或授权计划。

不确定性集合也不能绕过现实/想象边界：`PredictionSet[Predicted[T]]` 可以表达覆盖率目标，但只有在声明的校准域内才可使用该目标；域外、漂移或对抗输入必须降级为 `unknown`/`out_of_calibration`。

#### 反事实一致性、主动观测与持续适应

新一轮世界模型研究提醒：预测一个可能的未来，不等于学到了可用于行动的因果机制；从同一状态出发的不同动作分支，不能各自“看起来合理”却违反共同的环境约束。n 把多种干预看成同一基线上的一组候选转换，而不是互不关联的 rollout：

```text
ActionChoice[A] = single(A) | joint(CanonicalMap[AgentId, A])
Observability = complete | partial | unknown
JointActionSemantics = coupled | factorized(Validated[FactorizationContract, PolicyId])
FactorizationContract = {
    agent_partition: CanonicalSet[CanonicalSet[AgentId]],
    independence_condition: ConstraintSet,
    valid_domain: ConstraintSet,
    evaluation: EvaluationReport
}

WorldContract = {
    intervention_domain: ConstraintSet,
    joint_action_semantics: JointActionSemantics,
    invariants: CanonicalSet[Validated[Invariant, PolicyId]],
    invariant_policy: PolicyId
}

StateEstimate[S] = {
    hypotheses: Distribution[S],
    evidence: CanonicalSet[EvidenceId],
    history: EventStream[Digest],
    observability: Observability,
    residual: ResidualReport
}

CounterfactualFamily[S, A, O] = {
    base_state: Digest,
    kernel_version: VersionId,
    alternatives: CanonicalMap[ActionChoice[A], Tagged[O, counterfactual]],
    world_contract: Digest,
    report: CausalReport
}

CausalReport = {
    intervention_coverage: EvaluationReport,
    action_discrimination: Score,
    invariant_violations: CanonicalSet[InvariantViolation],
    unresolved: CanonicalSet[ConstraintId]
}
```

所有 alternatives 必须引用同一 `base_state` 和 `kernel_version`；除非 `WorldContract` 明确声明且验证因子化条件，否则多 Agent 同时行动必须作为 `joint` 输入建模，不能把单体模型预测简单相加。`CausalReport` 分别报告干预覆盖、候选动作可区分性、已验证不变量违反和未知项。预测误差低只支持观测域内预测质量，不自动证明因果可识别；学得的不变量先是 `Candidate[Invariant]`，只有通过独立验证的约束才能拒绝行动或优化计划。

部分可观测状态不能被一个“当前快照”假装完整：`StateEstimate` 必须保留历史证据引用、可观测性和残余不确定性。已有 `QueryPlan`/`focus` 可用于选择下一次传感或检索，目标是按信息增益、决策价值和完整 `CostVector` 进行权衡；如果观测需要外部传感器/工具，仍必须通过 `ActionGate`。请求计划不是观察，只有受控观察边界返回的值才能成为 `Observed`。

持续学习继续使用既有 `Delta[D,T]`，不增加一套“记忆融合”语义。每个经验更新声明适应域和依赖基线；互相干扰或契约不兼容的 Delta 使用 `reject_on_conflict` 并作为并存候选保留，只有可证明兼容且通过回归/保留集验证的更新才合并或晋升。质量多样性档案应保留多条有效策略/技能路径，避免单一 champion 覆盖可迁移但风格不同的解法。

开放式学习的报告至少同时追踪行为/任务覆盖、跨环境迁移、旧能力保留和单位预算的有效增长；新颖度或候选数量单独上升不构成能力增长。信息论“bit-equivalent”可作为实验指标候选，必须与外部验证的任务复杂度、迁移和保持率共同报告，暂不作为 n 的唯一规范定义。

事件/SNN 路径可复用 `RoutePlan`：在预测残差低且结构契约允许时抑制冗余事件或发送残差摘要；残差上升时扩展精确事件/回退。验收必须计入通信字节、路由与同步延迟和实际能耗，不能从稀疏脉冲数推断硬件节能。

#### 跨范式组合

Tensor、Graph、Symbol、Distribution、EventStream 和 Population 是并列表示，不互相冒充。转换必须显式，例如 `events_to_tensor(window)`、`tensor_to_distribution(policy)`、`latent_to_symbol(validator)`；转换携带信息损失、时间窗口、校准和 provenance。由此可以组合“世界模型 + 符号约束 + SNN 感知 + 元学习适应 + 开放式环境生成”，同时仍由统一的类型、预算、证据和事件日志约束。

### 4.0.10 n 的独有路线：现实标记的可验证状态转移代数

n 不把自己的身份定义为“支持更多模型”，而定义为一种统一的 **现实标记状态转移**（Reality-Tagged State Transition，RTST）机制。任何 AI、Agent、学习、记忆、分支或工具动作，都必须降级为同一种可检查的 `TransitionContract`：

```text
enum RealityTag {
    observed,
    predicted,
    imagined,
    generated,
    counterfactual,
    validated(PolicyId),
    untrusted
}

TransitionContract = {
    inputs:     typed values + RealityTag,
    reads:      owned/borrowed regions,
    deltas:     CanonicalSet[DeltaRef],
    plan:       PlanDigest?,
    cost:       CostVector,
    replay:     ReplayMode,
    output:     typed values + RealityTag
}

TransitionRecord = {
    contract: TransitionContract,
    program_digest: Digest,
    compiler_digest: CompilerDigest,
    plan_digest: PlanDigest?,
    objective_epoch: VersionId,
    fabric_digest: Digest?,
    input_digest: Digest,
    output_digest: Digest,
    delta_digests: CanonicalSet[Digest],
    plan_receipt: Digest?,
    performance_receipt: Digest?,
    status: TransitionStatus,
    event: EventHash,
    logical_time: u64
}

TransitionStatus = prepared | committed | rejected | rolled_back | outcome_unknown

UnitTag = dimensionless | count | operation | byte | second | joule | hertz
         | meter | kilogram | kelvin | radian | custom(Digest)
SemanticTag = generic | flow | production | probability | information
            | throughput | latency | energy | custom(Digest)

Quantity[U, S, Rep] = {
    value: Rep,
    unit: U,
    semantic: S
}

// Addition/subtraction require identical U and S. Conversion is explicit and
// must carry a versioned calibration; multiplication/division use only a
// verifier-approved dimension algebra. CostVector remains separate because
// every measure may also be unknown with a stated reason.
CostUnit = count | operation | flop | byte | nanosecond | nanojoule | backend_unit(UnitId)
CostMeasure = known(value: u64, unit: CostUnit) | unknown(CostReason)
CostVector = {
    steps: CostMeasure,
    compute: CostMeasure,
    memory_bytes: CostMeasure,
    storage_bytes: CostMeasure,
    bandwidth_bytes: CostMeasure,
    synchronization: CostMeasure,
    latency_ns: CostMeasure,
    energy_nj: CostMeasure,
    duration_ns: CostMeasure,
    tool_calls: CostMeasure,
    code_bytes: CostMeasure,
    compile_ns: CostMeasure,
    optimization_ns: CostMeasure,
    recovery_ns: CostMeasure
}

MergeLaw = replace | join | append_unique | ordered | reject_on_conflict

CommitGate = AdmissionGate | ActionGate
AdmissionGate = {
    capability: PromotionCapability,
    evaluation: EvaluationReport,
    target: VersionId
}
ActionGate = {
    capability: ToolCapability,
    budget: BudgetToken,
    idempotence: IdempotentEffect
}

Delta[D, T] = {
    domain: D,
    base: Digest,
    payload: T,
    precondition: Constraint[D],
    merge_law: MergeLaw
}

DeltaRef = {
    domain: DomainId,
    payload_type: TypeId,
    base: Digest,
    digest: Digest
}

StateDelta       = Delta[state, StateChange]
EvidenceDelta    = Delta[evidence, EvidenceChange]
BeliefDelta      = Delta[belief, BeliefChange]
TrunkDelta       = Delta[trunk, TrunkChange]
AuthorityDelta   = Delta[authority, AuthorityChange]
MemoryUpdate[K,V] = Delta[memory[K], MemoryChange[K,V]]
ProgramDelta     = Delta[program, NirPatch]
ObjectiveDelta   = Delta[objective, ObjectiveChange]
WorkCredit       = Credit[work]
BudgetToken      = Credit[budget]
```

`rolled_back` 只适用于 n 内部尚未越过外部 effect 边界的事务；`ActionGate` 一旦提交外部副作用，失败恢复只能记录 `outcome_unknown` 或由远端幂等协议确认结果，不能由 n 伪造回滚。

`Delta[D, T]` 是 n 里所有“更新/增量/补丁”的唯一语义：它描述基线、载荷、前置条件和合并律，但本身不写入状态。`learn.update`、`memory.write`、`branch.publish`、`population.mutate` 等领域操作都先产生相应 Delta；只有 `transition.commit` 或 `commit.*` 才能提交它。`MergeLaw` 必须明确是 `replace`、`join`、`append_unique`、`ordered` 或 `reject_on_conflict`，不能让不同模块各自定义隐式覆盖规则。

`TransitionContract.deltas` 是所有待提交更新的唯一入口；Evidence、Belief、Memory、Authority、Program 和 Objective 不再各占一套旁路字段。`DeltaRef` 按 `(domain, digest)` 规范排序；同一域内范围重叠的多个 Delta 必须先按声明的 MergeLaw 合成，否则整批拒绝。`transition.commit` 的效果由 Delta 域自动精化：`state/evidence/belief/trunk/authority` 需要 `! state`，`memory` 需要 `! memory`，`parameters/program/objective/policy` 需要 `! learn`，追加规范事件或发送 durable 消息需要 `! event`；Authority/Objective 还必须携带相应 PromotionCapability。多个内部域的原子提交取效果并集并全成或全败；外部 effect 仍遵循 intent/result 和 `outcome_unknown`。纯函数只能构造和检查 Delta，不能偷偷提交它。

被评价的 `ProgramDelta` 不得与改变其评价口径的 `ObjectiveDelta`、evaluator 或成本计数器更新在同一 evaluation epoch/提交中。Objective 变化先由旧 epoch 生成独立 EvaluationReport，再作为下一 epoch 的单独提交；这样代码优化不能把“换尺子”与“跑得更好”包装成一个原子更新。

记忆也采用一个统一抽象，而不是为每种模型各造一套缓存：

```text
MemoryStore[K, V, Mode] = {
    snapshot: MemorySnapshot[V],
    address: MemoryAddress[K],
    mode: MemoryMode,
    retention: RetentionPolicy,
    capacity: u64,
    pending: Delta[memory[K], MemoryChange[K,V]]
}

Memory[T]                  = MemoryStore[EventId, T, episodic]
WorkingSet[T]              = MemoryStore[FocusKey, T, working]
EpisodicMemory[T]          = MemoryStore[EventId, T, append_only]
AdaptiveMemory[K,V]        = MemoryStore[K, V, adaptive]
MemoryMode = working | episodic | append_only | adaptive | external
```

`retrieve`、`focus`、外部记忆读写、测试时记忆和模型缓存只改变 `MemoryMode` 与地址/保留策略；都必须经过 `memory.read` 或产生 `MemoryUpdate` Delta。`working`/`adaptive` 可以短期可变，`append_only` 只能追加不可变事件；`external` 读写还必须声明 `! net`。没有一种记忆模式可以绕过 `RealityTag`、provenance 或容量预算。

源码示例中的无参数 `Memory` 是 `Memory[T]` 的上下文推断简写；实现和 n-IR 中必须实例化具体键、值和 `MemoryMode`，不能存在无类型的全局记忆。

`World`、`Dynamics`、`StateSpace`、`ContinuousDynamics` 和 `SequenceOperator` 也共享一个状态转移核：

```text
TransitionKernel[Input, State, Output, TimeDomain]
    = step(input, state, time)
        -> (output: Tagged[Output, RealityTag], delta: StateDelta | none)

Dynamics[S, A]              = TransitionKernel[A, S, S, DiscreteTime]
StateSpace[S, I, O]         = TransitionKernel[I, S, O, DiscreteTime]
ContinuousDynamics[S]       = TransitionKernel[Control, S, S, ContinuousTime]
SequenceOperator[I, S, O]   = TransitionKernel[I, S, O, DiscreteTime]
```

它们是不同约束的类型别名/特化，不是四套生命周期、回放和预算机制。差异只在时间域、输入输出 schema 和求解策略；`world.transition`、`state_space.scan`、`sequence.recur` 与 `dynamics.integrate` 最终都降级到同一 `transition.step` n-IR 操作。`step` 不隐式修改状态；若有状态变化就返回 `StateDelta`，提交由调用方显式执行 `transition.commit`，因此仿真、预测和现实状态更新不会混在一个操作里。

一次转换只产生一个规范 `TransitionRecord`，然后投影出三种视图：

| 视图 | 回答的问题 | 是否能改变事实 |
| --- | --- | --- |
| `EventLog` | 什么时候发生了什么、顺序和提交状态是什么 | 否，只记录时间事实 |
| `ProvenanceGraph` | 哪些输入/活动派生了哪些值 | 否，只记录因果来源 |
| `Evidence` | 当前证据对某个命题支持、反对还是未知 | 否，只是策略投影 |

这三者不再各自重复写一套日志：事件、来源和证据都引用同一个 `TransitionRecord`；它们仍保持不同语义，不能因为共享摘要就互相替代。

`transition.begin/step` 先创建 `prepared` 的 `TransitionRecord`；`transition.commit` 原子地把同一记录更新为 `committed`、`rejected` 或 `outcome_unknown`，不会为同一 Delta 再制造第二条不可关联的主记录。

重复的“候选晋升”和“外部行动授权”也统一为 `CommitGate`，但保留两种不可混淆的门：

```text
commit[AdmissionGate](candidate, evaluation, PromotionCapability)
    -> (admitted version, TransitionRecord)
commit[ActionGate](plan, ToolCapability, BudgetToken)
    -> (one-shot ActionTicket, TransitionRecord)
```

`promote` 和 `authorize` 只是这两个门的受约束表面 API；二者都必须检查输入摘要、策略版本、数据标签、预算、有效期和 `TransitionContract`，但 `AdmissionGate` 只能改变 n 内部版本，`ActionGate` 才能产生外部副作用票据。不存在一个“万能 commit”可以绕过二者的差异。

预算和异步 `WorkCredit` 也统一为线性 `Credit[D]`：`Budget` 是按 `steps/bytes/compute/time/tool_calls` 计量的有界账本，`WorkCredit` 是 `Credit[work]` 的特化。`Credit[D]` 没有普通构造器，只能由 RuntimeRoot 或持有 credit 的父转换签发、拆分、转移和归还；任何分支、候选或工具结果都不能隐式铸造 credit。这样学习预算、工具预算和并行停止条件使用同一守恒规则。

效果系统增加四个精化标签，但不改变值语义：

```text
! state     持久状态提交
! memory    可变记忆读写
! learn     把候选/更新写入训练或策略版本
! event     追加规范事件或发送 durable 消息
```

返回新值的纯 `update`、纯 `adapt` 和纯 `fuse` 仍可标记 `pure`；只有写入持久状态、记忆、版本或事件日志时才必须声明对应精化效果。由此解决“学习是状态转换”与“普通函数默认 pure”之间的冲突。

### 4.0.11 稀疏认知、可补偿路由与受控自主改进

附件中的稀疏注意力工作给 n 的启发不是增加 `attention` 关键字，而是把“只计算一部分”提升为所有长序列、检索、记忆和多螺旋任务都可使用的**选择性转换**。NSA 说明稀疏路径必须从训练/转换语义开始就成立；InfLLM-V2 说明优化计划应尽量保持输入输出和状态契约；Flux 说明路由粒度和内存访问会决定真实墙钟收益；Prism、CEDAR 与 CompKV 说明选择必须同时考虑结构质量、近似误差和补偿，而不能只按一个相关性分数硬丢弃。Dream-RSI 与 RSI 路线则说明探索和上线改进必须分离，并且自主性必须有能力等级。

#### 选择性转换

```text
RouteUnit = token | block | head | layer | branch | device | memory_entry | event_window
RouteGranularity = per_unit(RouteUnit) | hierarchical(RouteUnit, RouteGranularity)

RoutePlan[U] = {
    input_digest: Digest,
    granularity: RouteGranularity,
    universe: CanonicalSet[U],
    selected: CanonicalSet[U],
    omitted: CanonicalSet[U],
    semantic_score: Score,
    structural_score: Score,
    temporal_score: Score,
    compensation: CompensationPolicy,
    compatibility: CompatibilityContract,
    predicted_cost: CostVector,
    error_bound: ErrorBound,
    fallback: FallbackPolicy,
    route_version: VersionId
}

CompatibilityContract = {
    input_schema: SchemaDigest,
    output_schema: SchemaDigest,
    state_delta_schema: SchemaDigest?,
    reality_policy: RealityPolicy,
    random_stream: RandomStreamPolicy,
    error_policy: ErrorPolicy,
    tolerance: Tolerance,
    valid_domain: ConstraintSet
}

CompensationPolicy = none | summary(SummarySpec) | residual(ResidualSpec)
    | archive(ArchiveRef) | exact_fallback(FallbackPolicy)

RouteReceipt[U] = {
    plan: Digest,
    selected: CanonicalSet[U],
    recovered: CanonicalSet[U],
    fallback_taken: Bool,
    actual_cost: CostVector,
    residual: ResidualReport,
    quality: QualityReport,
    invalidation: InvalidationReason?
}
```

`RoutePlan` 是计划，不是事实；它可以由纯 `route.plan` 构造，也可以被标为 `Predicted`。执行时必须生成同一个 `TransitionRecord` 引用的 `RouteReceipt`，记录实际选择、补偿、回退、成本和质量。路由器本身也消耗 `Credit[route]`，不能因为省下了内核计算就把路由开销隐藏掉。

选择性转换有五条硬规则：

1. `universe`、`selected` 与 `omitted` 必须形成可检查的完备划分，且单元 ID 由 `input_digest` 唯一确定；未知或重复单元显式报错。
2. `omitted` 非空时，必须有 `CompensationPolicy`、可验证的 `error_bound` 或明确的 `exact_fallback`；硬丢弃不能默认为安全。
3. `semantic_score`、`structural_score`、`temporal_score` 分开记录。语义相关但位置/拓扑不可靠的单元不能仅凭相关性被删除。
4. 路由结果只能在其 `CompatibilityContract` 范围内替换原执行计划；输入 schema、输出 schema、状态 Delta、RealityTag、随机流和错误语义不兼容时，优化器必须拒绝替换。
5. `error_bound` 必须声明适用输出和组合规则。误差无法沿后续 kernel/Delta 传播时，输出保留近似标签，不得升级为 `validated`、现实 Evidence 或高风险行动依据。

`route.reuse` 可以复用跨层、跨步或跨分支的路由元数据，但缓存条目必须绑定输入依赖、产生它的 `TransitionRecord`、路由版本、有效期和失效条件。查询尚未出现时不得伪造 query-dependent 重要性；只能使用缓存自身携带、已声明适用域的信号，并把该限制写进 `CompatibilityContract`。

`CostVector` 不再把 FLOPs 当作速度代理：`latency_ns` 是关键路径延迟，`duration_ns` 是消耗的累计运行时间，两者在并行负载下不可互换。每个已知值必须带单位；异构 `backend_unit` 只有通过版本化校准转换后才能跨后端比较。n 的优化目标以任务质量/能力进展为主，在质量下限和 RTST 完整性约束内最大化有效工作量，并联合优化延迟、总计算、内存、能耗、通信和覆盖率。运行时比较满足硬约束的 Pareto 前沿；具体任务可给维度权重或约束，不存在脱离目标和预算的普遍“绝对最快”。AI 可基于持续基准更新 schedule/route/precision 候选，通过 `AdmissionGate` 晋升。`CostVector` 中未支持的维度必须显式标记为 `unknown`，不能以零代替。

#### 探索树与自主性阶梯

```text
ExplorationTree[H, O] = {
    root: ExplorationNode[H, O],
    nodes: ContentAddressed[ExplorationNode[H, O]],
    replay_domain: ReplayDomain,
    budget: Credit[exploration],
    policy_version: VersionId
}

ExplorationNode[H, O] = {
    parent: NodeId?,
    hypothesis: H,
    outcome: O?,
    reality: RealityTag,
    transition: TransitionRecord,
    children: CanonicalSet[NodeId]
}

AutonomyLevel = execution | strategy | experience | environment | meta_improvement
CapabilityLadder = {
    level: AutonomyLevel,
    admission: AdmissionGate,
    action: ActionGate?,
    max_delta_domain: DomainSet,
    rollback: RollbackPolicy,
    budget: Credit[autonomy]
}
```

`dream(tree)` 只在 `replay_domain` 中重放已发生的节点，返回 `Candidate[PolicyDelta]` 或 `Candidate[RoutePlan]`；它不能直接写入当前策略、长期记忆、现实 Evidence 或工具状态。候选仍需 `evaluate -> verify -> AdmissionGate`，上线后还要按 `CapabilityLadder` 检查权限、预算、回滚点和失败降级。经验摘要不是天然奖励，只有在信息增益、相关性和保留集验证均通过时才允许进入候选。

`AutonomyLevel` 变更本身是受保护的 `AuthorityDelta`：候选可自主提出升级，只有 RuntimeRoot 派生的 level capability 与独立、机器可验证的评估策略共同通过 `AdmissionGate` 才能生效。当前等级不能签发更高等级的 capability，也不能扩大自身 `max_delta_domain` 或 `ActionGate`；通过门控不要求逐次人工审批。

这条路线将“稀疏计算”和“原生 AI”融合为 n 自己的机制：n 不知道 Transformer、KV 或 tokenizer 也能用同一套路由/补偿/成本/回放语义调度 State、Memory、EventStream、Population 和 Agent 分支；后端可以为 attention、SNN、图遍历或硬件存储层提供特化实现，但不能改变语言契约。

### 4.0.12 AI 自举、程序演化与异构执行织网

面向 AI 的语言不能要求智能体把程序退化成字符串再交给面向人的编辑器。`.n` 是可读投影；AI 的首选编程接口是类型化 n-Core-IR、规范二进制 `.nib` 和结构化 `ProgramDelta`。AI 可以绕过 lexer/parser，但不能绕过 IR verifier、资源/效果检查或 RTST 提交边界。

```text
ProgramVersion = {
    core_ir: Digest,
    schema: SchemaDigest,
    abi: AbiDigest,
    dependencies: CanonicalMap[ModuleId, Digest],
    objective_epoch: VersionId,
    compiler: CompilerDigest,
    digest: Digest
}

NirPatch = CanonicalSet[
    insert(NodeId, TypedOperation)
  | replace(NodeId, expected_digest, TypedOperation)
  | delete(NodeId, expected_digest)
  | rewire(ValueId, expected_use_digest, ValueId)
]

SemanticDiff = {
    changed_types: CanonicalSet[TypeId],
    changed_effects: CanonicalSet[EffectId],
    changed_reality_flows: CanonicalSet[NodeId],
    changed_cost_model: CanonicalSet[NodeId],
    abi_change: AbiChange,
    state_migration: MigrationPlan?
}

AbiChange = none | backward_compatible | forward_compatible
          | breaking(CanonicalSet[SchemaDigest])

MigrationPlan = {
    from_schema: SchemaDigest,
    to_schema: SchemaDigest,
    transform: Digest,
    inverse: Digest?,
    precondition: ConstraintSet,
    validation: EvaluationReport,
    budget: Credit[migration]
}
```

`NirPatch` 引用稳定节点和值摘要，前置摘要不匹配即产生冲突；不允许按文本行号模糊修改。应用 patch 只得到 `Candidate[ProgramVersion]`，然后依次经过增量类型/效果/所有权验证、参考解释、后端差分、质量保留集、效能基准和 `AdmissionGate`。代码更新继续使用 `Delta + CommitGate`，不发明第二套自修改规则；提交 ProgramDelta 使用 `! learn`，因为程序版本是可学习策略的一种持久状态。

#### 自编译而不自证

编译器和运行时本身可以由 n 表达并被 AI 优化，但候选不能单独证明自己正确。自举采用父版本验证和多阶段固定点：

```text
parent compiler C0
  -> compile candidate source with C0          => C1
  -> compile the same source with C1           => C2
  -> normalize(C1 machine IR) == normalize(C2 machine IR)
  -> reference/differential/property corpus
  -> performance and resource benchmark
  -> shadow execution / canary
  -> commit[AdmissionGate] or rollback
```

固定点相等只证明自举稳定，不单独证明语义正确；参考解释器、旧编译器、至少一个独立后端和性质测试共同形成 `BootstrapReport`。候选不得删除失败样例、改变评价 epoch 或用自己的输出作为唯一真值。编译器升级失败时继续使用父版本；运行中的编译任务绑定原 `CompilerDigest`，不会被中途替换。

#### 状态保持的热替换

程序版本只在 RTST 安全点切换：没有在途 kernel 使用将被替换的代码，待提交 Delta 已结算，外部效果处于确定状态或显式 `outcome_unknown`。ABI 或状态 schema 改变时必须提供 `MigrationPlan`；迁移本身产生 `StateDelta` 和 `TransitionRecord`。旧版本、旧状态摘要和回滚窗口在新版本通过 canary 前保持可恢复。函数指针、JIT 入口和设备 kernel 使用版本化 indirection table，在安全点一次原子换表，热循环内部不查版本。

#### 异构执行织网

AI 工作负载面向的是 CPU、GPU、NPU、neuromorphic、内存层级和网络组成的机器织网，而不是一颗抽象 CPU。设备、链路、内存和故障域进入执行计划：

```text
ExecutionFabric = {
    devices: CanonicalMap[DeviceId, DeviceCapability],
    links: CanonicalMap[LinkId, LinkProfile],
    memories: CanonicalMap[MemoryId, MemoryCapability],
    failure_domains: CanonicalSet[FailureDomain],
    topology_digest: Digest
}

PlacementPlan = {
    program: Digest,
    fabric: Digest,
    operations: CanonicalMap[NodeId, DeviceId],
    buffers: CanonicalMap[ValueId, MemoryId],
    transfers: CanonicalSet[TransferEdge],
    pipelines: CanonicalSet[PipelineStage],
    collectives: CanonicalSet[CollectivePlan],
    predicted_cost: CostVector,
    fallback: FallbackPolicy
}
```

数据移动、格式转换、同步、collective 和容错都必须进入 n-Opt-IR 与 `CostVector`；后端不能用隐式复制伪造 kernel 加速。AI 可联合搜索算子融合、分片、流水线、精度、稀疏路由、缓存和设备放置，但只在稳定边界激活 `PlacementPlan`。拓扑、设备温度/频率、链路拥塞或失败域改变会使计划失效并触发重规划；旧计划在可执行时继续服务，避免全局停顿。

分布式 RTST 不承诺物理世界的全局原子提交：单故障域内可使用事务，跨故障域使用 intent/outbox、幂等键、补偿或 `outcome_unknown`。纯计算和内容寻址数据可以自由复制/迁移；状态、credit、capability 和外部效果的转移必须守恒并可追踪。由此，AI 可扩大到机器集群而不把网络失败伪装成本地函数调用。

这不是第七套语言机制：程序演化是 `Delta[program]`，自举/热替换是 `AdmissionGate`，设备搜索是 `OptimizationCandidate[PlacementPlan]`，分布式执行仍是 `TransitionContract + Credit + EventLog`。n 的核心闭环成为：

```text
observe workload/fabric
  -> propose ProgramDelta + PlacementPlan
  -> verify semantics and quality
  -> measure complete CostVector
  -> admit at safe point
  -> execute branch-free hot path
  -> learn from PerformanceReceipt
  -> retain, revise, fork or rollback
```

### 4.0.13 统一制品版本生命周期

参数、Reasoner、策略、程序、编译器、路由、放置计划、记忆 schema 和 Objective 都是可进化制品，不应各自发明一套“训练完成/部署/上线”语义。它们统一包装为不可变 `ArtifactVersion[T]`：

```text
 ArtifactKind = parameters | reasoner | policy | program | compiler
             | route_plan | placement_plan | execution_plan | memory_schema | objective

VersionState = proposed | verified | shadowed | canary | active
              | degraded | retired | rejected

ArtifactVersion[T] = {
    kind: ArtifactKind,
    version: VersionId,
    parent: VersionId?,
    artifact: T,
    artifact_digest: Digest,
    objective_epoch: VersionId,
    compatibility: CompatibilityContract,
    dependencies: CanonicalMap[ModuleId, Digest],
    rollback: RollbackPolicy,
    created_by: TransitionRecord
}

VersionStatus = {
    version: VersionId,
    scope: ScopeId,
    state: VersionState,
    transition_head: Digest
}

DeploymentBinding = {
    scope: ScopeId,
    eligible: CanonicalSet[VersionId],
    route_plan: VersionId?,
    epoch: u64,
    digest: Digest
}

AdmissionReceipt = {
    candidate: VersionId,
    verifier: Digest,
    evaluations: CanonicalSet[EvaluationReport],
    performance: PerformanceReceipt?,
    gate: Digest,
    decision: admitted | rejected,
    transition: TransitionRecord
}

VersionAction = propose | verify | shadow | canary | activate | degrade
              | rollback | retire | reject

VersionTransition = {
    artifact: VersionId,
    scope: ScopeId,
    expected_state: VersionState,
    next_state: VersionState,
    action: VersionAction,
    binding_before: Digest,
    binding_after: Digest,
    rollback_target: VersionId?,
    reason: Digest,
    evidence: CanonicalSet[Digest],
    lease: Digest,
    transition: TransitionRecord
}

VersionTransitionError = stale_state | missing_evidence | dependency_changed
                       | incompatible | lease_expired | gate_rejected
                       | rollback_unavailable
```

制品 payload 和 digest 永不原地改变；`VersionStatus` 是按 scope 从追加式 `VersionTransition` 派生的读模型。`active` 表示该版本在 scope 内有资格被选择，不表示所有请求都直接指向它；同一 scope 可有多个 active 专家，具体调用由版本化 `RoutePlan` 选出唯一 `VersionId`。`rolled_back` 不是制品状态，而是一次 `rollback` 转换的动作/结果，避免把失败版本、部署指针和旧版本状态混为一谈。

状态迁移边固定为：

| 当前状态 | 允许的下一状态 | 条件 |
| --- | --- | --- |
| `proposed` | `verified`, `rejected` | verifier/依赖摘要已绑定；验证失败则拒绝 |
| `verified` | `shadowed`, `rejected` | 与真实工作负载旁路比较；不得影响当前绑定 |
| `shadowed` | `canary`, `rejected` | 质量、效能和兼容性门通过；canary slice 与 Credit 有界 |
| `canary` | `active`, `degraded`, `rejected` | canary receipt 满足冻结门槛；失败保留原绑定 |
| `active` | `degraded`, `retired` | 退化时原子切换绑定到仍有效的 fallback；retire 时从 eligible 集移除 |
| `degraded` | `retired` | 失败版本不再接新流量；回滚由 binding 切换表达 |
| `rejected`, `retired` | 无 | 终态；修正必须创建子版本 |

`version.rollback(failed, target, scope)` 原子地将 `failed` 置为 `degraded`，并把 `DeploymentBinding` 的选择切到已验证、依赖仍有效的 `target`；目标版本不需要被“复活”或改写状态。若没有合格 target，则绑定为空并拒绝依赖该制品的效果，独立纯计算仍可运行。canary 失败则直接 reject/revert canary binding，不触碰原 active binding。每个转换比较 `expected_state + binding_before`，任一并发改变返回 `stale_state`，由调用方基于新摘要重新评估。

1. 制品 payload 不可原地修改；任何变化产生带父摘要的新版本。状态只追加 transition 记录，读模型可重建；旧 payload 在 retention 期限内保持内容寻址可取回。
2. `verified` 只表示类型/契约/性质检查通过；`shadowed` 表示未影响当前绑定的真实工作负载比较；`canary` 只接收显式切片的 traffic/credit；`active` 表示通过 gate 且可被 binding/RoutePlan 选中。
3. 退化与回滚是单个原子 binding 更新；若外部效果结果未知，不伪造回滚成功，记录 `outcome_unknown` 并只恢复内部版本选择。
4. 候选绑定 base、scope、Objective epoch、verifier、编译器、fabric 和数据域摘要；任一依赖改变均使旧 AdmissionReceipt 失效，必须重验或显式 rebase。
5. 每个请求在调度边界绑定唯一 artifact digest；多专家并行只通过版本化 RoutePlan 产生明确的 fan-out/merge，不共享可变代码或状态。
6. `learn.promote`、`autonomy.admit`、`program.activate`、`optimize.activate` 和 compiler hot swap 都是这个状态机的表面投影，最终降级为 `version.transition + commit[AdmissionGate]`。

版本状态转换是 n-Core-IR 的唯一生命周期原语：

```text
version.propose       // 产生 proposed ArtifactVersion，不改变 active
version.verify        // 绑定 verifier/evidence，proposed -> verified
version.shadow        // 在真实工作负载旁路比较，verified -> shadowed
version.canary        // 给定切片和 credit，shadowed -> canary
version.activate      // canary -> active，并更新 DeploymentBinding
version.degrade       // 记录退化并停止新流量，active -> degraded
version.rollback      // degraded -> degraded; 原子切换 DeploymentBinding 到 target
version.retire        // 从 eligible 集撤销新流量，保留可取回摘要
version.reject        // 将失败候选置为终态 rejected
```

以上操作通过同一 `version.transition` verifier lowering，消费 `RootLease`、`Credit` 和 `TransitionContract`，没有隐式后台晋升。`learn.promote`、`autonomy.admit`、`program.activate`、`optimize.activate`、`compiler hot swap` 以及记忆 schema 升级只定义参数化 lowering；若 lowering 不能构造同一 `VersionTransition`，编译器必须拒绝，而不是新增旁路状态机。

统一生命周期把“自我改进”从神秘递归改成多版本事务：可以高速并行探索，却只有通过同一机器证据链的不可变版本进入执行主路径。

### 4.1 普通函数

n 是严格求值语言。函数默认纯函数，副作用通过效果标记暴露：

```n
fn add(a: i32, b: i32) -> i32 ! pure {
    a + b
}

fn write_line(s: String) -> Unit ! io {
    io.stdout.write(s)
}
```

效果集合至少包含 `pure`、`state`、`memory`、`learn`、`event`、`io`、`alloc`、`async`、`gpu`、`clock`、`random`、`net` 和 `unsafe`。`state/memory/learn/event` 是对持久状态提交的精化效果：返回新值的函数仍可保持 `pure`，写入持久区域或追加事件时必须声明对应效果。调用者必须声明或继承被调用者的效果；其中 `clock`、`random` 和 `net` 默认不可出现在可重放的 `pure` 计算中。LLM 不是效果种类，也不是标准运行时能力。

### 4.2 Seed 和折叠

`seed` 是一个普通的、可拥有的值，不是无限递归对象。`self` 只表示构造器或当前值的显式引用：

```n
seed Counter {
    state: i64

    observe(ctx: Context) -> i64 ! pure {
        self.state
    }

    fold(x: i64) -> Counter ! pure {
        Counter { state: x + 1 }
    }

    report(x: i64) -> String ! pure {
        "counter = " + show(x)
    }
}
```

一步折叠定义为：

```text
step(seed, ctx) = fold(seed, observe(seed, ctx))
```

`run(seed, ctx, steps)` 明确执行有限步；`report` 只在调用处产生输出，不改变 seed。

### 4.3 有界自指

安全核心只提供有界不动点：

```text
fix@0(f, x)   = x
fix@(k + 1)(f, x) = f(fix@k(f, x))
```

`k` 必须是编译期可知的非负整数。无界递归使用结构化递归或显式 `loop`，不能用 `fix` 绕过终止检查。

### 4.4 折叠顺序

默认归约是左到右、可重放的。只有声明结合律和单位元后，编译器才可并行重排：

```n
reduce[sum, associative, identity=0](xs)
reduce[stable_sum, ordered](xs)
```

这条规则避免“自动并行”改变浮点结果，也把原方案中“非结合折叠”的语义落到了可执行契约上。

## 5. 类型系统

### 5.1 基本类型

```text
 Unit  Bool  Tr Trit i8 i16 i32 i64 u8 u16 u32 u64 f16 f32 f64
 String  Bytes  Option[T]  Result[T, E]  CanonicalMap[K, V]  CanonicalVector[T]
AIState  Parameters  Experience  Objective[T]  ObjectiveDelta  ObjectiveChange  Learner[P, E]  Update[P]
 RuntimeRoot  RootEnvelope  RootLease  ResourceEnvelope  DataFlowContract  DeviceCapabilitySet  CapabilitySet
EfficiencyObjective  OptimizationCandidate[P]  PerformanceReceipt  LatencyProfile  BenchmarkBinding  PlanDigest
Value[T]  Transition[S,I,O]  ExecutionPlan[T]  PlanProof  PlanMonitor  PlanReceipt
DeriveTarget  DeriveMode  DeriveSpec  Derivation[T]  DeriveError  Approx[T]
 SemanticAuthority  CorpusId  CorpusManifest  CorpusEntry  BenchmarkManifest
 ArtifactKind  VersionState  VersionAction  ArtifactVersion[T]  VersionStatus  DeploymentBinding  AdmissionReceipt  VersionTransition  VersionTransitionError
 ProgramVersion  ProgramDelta  NirPatch  SemanticDiff  BootstrapReport  CompilerDigest  EvaluatorDigest  AbiDigest  AbiChange  MigrationPlan
ExecutionFabric  DeviceCapability  LinkProfile  MemoryCapability  FailureDomain  PlacementPlan
 DeviceId  LinkId  MemoryId  AxisId  Shape  Layout  Ownership  TransferEdge  PipelineStage  CollectivePlan  ModuleId  ValueId  TypeId  EffectId  TypedOperation
TransitionKernel[I, S, O, TimeDomain]  World[S, O, A]  Dynamics[S, A]  ContinuousDynamics[S]  StateEstimate[S]
 RealityTag  Tagged[T, R]  GroundingReport  TransitionContract  TransitionRecord  TransitionStatus  DeltaRef  DomainId  StateDelta  AuthorityDelta  UnitTag  SemanticTag  Quantity[U, S, Rep]  CostUnit  CostMeasure  CostVector  MergeLaw
RouteUnit  RouteGranularity  RoutePlan[U]  CompensationPolicy  CompatibilityContract  RouteReceipt[U]
ErrorBound  FallbackPolicy  ResidualReport  QualityReport  InvalidationReason  CostReason  UnitId  ReplayDomain  NodeId  Score  SummarySpec  ResidualSpec  ArchiveRef  DomainSet  RollbackPolicy
SchemaDigest  RealityPolicy  RandomStreamPolicy  ErrorPolicy  Tolerance  ConstraintSet
StateChange  EvidenceChange  BeliefChange  TrunkChange  AuthorityChange  MemoryChange[K, V]
Observed[T]  Predicted[T]  Imagined[T]  Counterfactual[T]  Generated[T]  Trajectory[T]
ActionChoice[A]  Observability  WorldContract  JointActionSemantics  FactorizationContract
CounterfactualFamily[S,A,O]  CausalReport  Invariant  InvariantViolation  ConstraintId
Validated[T, PolicyId]  Candidate[T]  EvaluationReport  PromotionCapability  CommitGate  AdmissionGate  ActionGate  PolicyId  VersionId  MetaState  AdaptationState  AdaptiveState
Latent[T, Schema]  PredictionTarget[T]  StateSpace[S, I, O]  RetentionPolicy
DiscreteTime  ContinuousTime  EventTime  TimeDelta  SolverPolicy
EventStream[T]  Spike  NeuronState  SynapseState  PlasticityRule
SequenceOperator[I, S, O]  RetentionState[S]  LongKernel[K]
MemoryStore[K, V, M]  MemoryMode  MemorySnapshot[T]  MemoryAddress[K]  MemoryUpdate[K, V]
Memory[T]  AdaptiveMemory[K, V]
NoiseSchedule  DenoisingProcess[T]  ScoreField[T]
EnergyFunction[T]  SamplerPolicy  EquilibriumState[T]
ConvergenceCertificate  LatentBottleneck[T]  QueryPlan[Q]
GraphMessage[N, E]  BasisFunction[T]  FunctionEdge[T]  PredictionSet[T]
CoverageContract  CalibrationReport
Population[T]  Individual[T]  WorldGenerator[W]  BehaviorDescriptor[T]
QDArchive[D, T]  Lineage  TransferReceipt  Distribution[T]  Graph[N, E]
ExplorationTree[H, O]  ExplorationNode[H, O]  AutonomyLevel  CapabilityLadder
Evidence  Claim[T]  Belief[T]  Goal  Plan  Action  Observation
ProvenanceGraph  ProvenanceRef  AgentId  AgentTask[T]  TaskId  TaskState
BranchSnapshot  BranchId  BranchInbox  BranchMessage[T]  MessageId  MessageCursor
BranchPolicy  BranchConsistency  TrunkDelta  WorkCredit  QuiescenceSnapshot
EvidenceDelta  BeliefDelta  Constraint[T]  Proposal[T]  Cohort
SyncRound  MergeConflict  QuiescencePolicy  BranchReceipt
 QuestionId  Question  DecisionState  DecisionPolicy  Decision[T]  ExplanationMode  Judge[S, Q, A]
 ReasonerId  ReasonerDigest  ReasonerSet  InferenceTrace  InferenceTraceRef  ReasoningReceipt
WorkingSet[T]  EpisodicMemory[T]  FocusLane[T]  FocusPolicy  RoutingPolicy
Agent[Belief, Goal, Memory, WorkingSet, Reasoners, ToolScopes, Policy, Budget]
Budget  BudgetSlice  Credit[D]  CreditLedger
SourceId  EvidenceId  EvidenceAtom  EvidenceDigest  EvidencePolicy
 Untrusted[T]  DataLabel  DataLabelSet  IdempotentEffect  NumericContract  RadixSpec  DigitPolicy
 NumericEncoding  EncodingGranularity  EncodingProfile  NumericReference  RoundingPolicy
 SpecialValuePolicy  PackingPolicy  ScalePolicy
 IntegrityLabel  ConfidentialityLabel  LeaseExpiry  MonotonicDeadline  Duration  ScopeId  EffectStatus  EffectKey  EventKind  CancelTicket
ToolScope  ToolCapability  BudgetToken  ActionTicket
CommitError  ToolError  FuseError  JudgeError  SchemaMismatch  EvidenceIdCollision
GoalConflict  BudgetExceeded  CycleError  ReplayDataUnavailable
MergeConflict  IterationLimit  StaleBranch  NonConfluentAsync
Backpressure  CancelledBranch  CausalGap  EventCycle
CalibrationError  SolverError  PromotionError  AdaptationLimit
ValidationError  UnsupportedExecutionPolicy
DelegationGrant  BudgetSlice  TaskUpdate  EventLog  EventHash  Digest  Recorded[T]
ReplayMode  ReplayError
```

`Tr` 是平衡三值 `{-1, 0, +1}`，表示反对、未知、支持。它是语言层的认知投影，默认仍编译到二进制机器码；需要证据强度时使用 `Evidence`，不把 `Tr` 冒充概率。

### 5.1.1 多进制数值层

n 采用多进制，但不是把一种进制写进所有程序的唯一语义。必须区分三层：

1. **值语义层**：操作作用于 `i*`、`f*`、`Trit`、Tensor 或带误差契约的抽象数值；结果不因存储进制改变。
2. **编码层**：值可用二进制、平衡三进制、任意有限基、低比特浮点、定点、log/posit、codebook 或混合进制编码；编码是带摘要的 `EncodingProfile`。
3. **执行层**：后端根据设备能力、形状、数据分布和 `NumericContract` 选择已验证 profile；选择在 RTST 稳定边界完成，热循环不反复检查进制。

```text
RadixSpec = uniform(base: u16, digits: DigitPolicy)
          | mixed(bases: CanonicalVector[u16], group: u32, axis: AxisId?)

DigitPolicy = unsigned | signed_magnitude | balanced

NumericEncoding = integer | fixed_point | ieee_float | block_float
                | log | posit | codebook(Digest)

NumericReference = repro_v1 | exact_integer | exact_rational
RoundingPolicy = nearest_even | toward_zero | stochastic(seed: Digest)
SpecialValuePolicy = ieee | saturate | reject | reserved(Digest)
PackingPolicy = unpacked | bit_packed(order: CanonicalVector[u8]) | lut(Digest)
ScalePolicy = none | per_tensor | per_axis(AxisId) | per_block(u32)

EncodingGranularity = scalar | vector(width: u16) | block(size: u32)
                    | tensor_axis(AxisId, block: u32)

EncodingProfile = {
    semantic_type: TypeId,
    radix: RadixSpec,
    encoding: NumericEncoding,
    granularity: EncodingGranularity,
    bits_per_value: u16,
    scale: ScalePolicy,
    rounding: RoundingPolicy,
    special_values: SpecialValuePolicy,
    packing: PackingPolicy,
    device: DeviceId?,
    digest: Digest
}

NumericContract = {
    reference: NumericReference,
    admissible: CanonicalSet[Digest],
    max_error: ErrorBound,
    quality_gate: ConstraintSet,
    fallback: PlanDigest,
    monitor: PlanMonitor?,
    replay: ReplayMode
}
```

数值近似必须以 `Approx[T]` 或等价的 `Tagged[T, validated(P)]` 携带 `ErrorBound`、实际 `ResidualReport`、使用的 `PlanDigest` 和兼容 `fallback`。`NumericContract.max_error` 是允许上界，不是执行结果的自证；运行时仍须采样/证明实际残差。`Approx[T]` 不能隐式流入要求精确 `T` 的操作，`numeric.refine` 或 `plan.fallback` 必须显式产生转换记录。若 `ErrorBound = unproven`，该值只能参与候选、低风险内部计算或继续测量。

约束如下：

- `base` 在 n-IR 中为 2..256；混合进制只能按向量、block 或 tensor 轴分组，不能在同一标量的热循环内隐式变基。
- `balanced` 只对奇数基有效，规范 digit 集为 `[-floor(base/2), ..., +floor(base/2)]`；非法 digit 集、溢出和进制转换必须在 verifier 中拒绝或显式返回 `Result`。
- `Trit` 是数值三态 `{ -1, 0, +1 }`，可用于稀疏/符号/门控计算；认知 `Tr` 仍是证据投影，稳定 ABI 仍为 `0xFF/0x00/0x01`，二者不能互换。
- `repro-v1` 仍是参考语义；任何低比特、三值、log、posit 或 codebook profile 都必须声明量化误差、溢出/下溢、特殊值、归约和随机舍入规则。无法传播误差的 profile 不能进入 `validated`、现实 Evidence 或高风险 Action。
- 训练可以保留高精度 shadow/master 值，前向、梯度、优化器和通信分别选择 profile；不得因为权重为三值就假设激活、累加器或梯度也必须三值。
- 多进制不是新权限系统，也不是新的提交机制。profile 的生成、影子比较、canary、晋升和回滚继续使用 `OptimizationCandidate`、`PerformanceReceipt`、`ArtifactVersion`、`AdmissionGate` 和 `DeploymentBinding`。
- 默认策略是 `adaptive-fastest`，但只在冻结的 `NumericContract` 内选择。没有已验证硬件 kernel、质量门或完整成本测量时，回退到 reference profile；未知成本不得按零参与 Pareto 排序。

源码字面量可支持 `base#digits`（人类投影限制在 2..36），但 AI 主要直接生成带 `RadixSpec` 的 n-IR。这样“多进制”成为可演化的表示空间，而不是迫使所有算法依赖某一种神秘数字体系。

`CanonicalMap[K,V]` 按规范化 key 排序、拒绝重复 key，并以确定性编码参与摘要；其逻辑顺序不承诺特定的物理存储或迭代性能。

`ReasonerDigest` 覆盖推理 n-IR、规则/约束数据、配置和依赖版本；`InferenceTrace` 记录取回项、焦点选择、路由、派生边和拒绝原因。`ToolCapability` 至少包含工具标识、参数 schema、允许的效果、数据标签、幂等能力和撤销状态，由 RuntimeRoot 在 `RootEnvelope` 内签发，不能由 Agent 代码伪造。

### 5.2 Tensor、View 和形状

```text
Tensor[T, Shape, Layout, Device]
View[T, Shape, Stride, Device]
ViewMut[T, Shape, Stride, Device]
```

形状可以是字面量、符号维度或运行时维度。编译器解线性约束；无法静态确定的约束保留为一次运行时检查。

```n
fn axpy[N](a: f32, x: View[f32, [N]], y: ViewMut[f32, [N]]) -> Unit ! pure {
    parallel for i in 0..N {
        y[i] = a * x[i] + y[i]
    }
}
```

布局是类型的一部分。`row_major`、`column_major`、`blocked[B]` 和 `strided` 不可隐式混用；转换必须写成 `repack` 或 `view`。

### 5.3 所有权与借用

| 标记 | 含义 |
| --- | --- |
| `owned[T]` | 唯一所有者，可移动，可变更 |
| `borrow[T]` | 只读借用，不能逃出所有者生命周期 |
| `borrow_mut[T]` | 独占可变借用 |
| `shared[T]` | 可复制的只读句柄；底层缓冲区不可变 |
| `linear[T]` | 必须恰好消费一次的资源 |

安全代码禁止悬垂引用、数据竞争和隐式别名。`unsafe` 只允许出现在局部块，并要求声明 ABI、对齐和别名前置条件。

### 5.4 合约和证明

第一版只支持可检查合约：`requires`、`ensures`、`invariant`。它们可以生成运行时检查或在常量/形状分析成功后消除。完整 HoTT、范畴和拓扑证明属于 `n.proof` 扩展，不阻塞核心编译器。

## 6. 内存和并发模型

1. 栈值、静态区、显式堆和设备内存四类区域均可在 IR 中观察。
2. `Tensor` 默认连续拥有缓冲区；`View` 不拥有数据，不能延长数据生命周期。
3. 分配器支持 `arena`、`pool` 和 `manual` 三种策略；策略写入模块配置，不由运行时猜测。
4. `parallel for` 要求迭代之间无未声明的可变别名。归约必须使用 `reduce` 或 `atomic`。
5. `async` 返回事件句柄；设备传输和等待点在源码中可见。
6. 默认整数溢出和越界会产生 `panic`；`fast` 或 `wrapping` 必须显式选择。

## 7. n-IR

n-IR 是可序列化、可验证、可执行和可重放的规范表示。它不是 LLVM IR 的别名。

### 7.1 n-IR 的核心操作

```text
const, add, mul, fma, cast
numeric.encode, numeric.decode, numeric.requantize
tensor.alloc, tensor.view, tensor.load, tensor.store
loop.for, parallel.for, simd.for, reduce
region.if, region.match, call, return
async.launch, async.await, device.copy
seed.observe, seed.fold, seed.report, fix.bounded
ai.observe, ai.infer_state, ai.predict, ai.rollout, ai.evaluate
world.transition, dynamics.integrate, state_space.scan
transition.begin, transition.step, transition.delta, transition.commit, reality.ground
derive.request, derive.materialize, derive.verify
plan.specialize, plan.select, plan.execute, plan.monitor, plan.fallback, plan.retire
numeric.approx, numeric.refine, numeric.fallback
learn.update, learn.adapt, learn.evaluate, learn.promote
event.emit, event.schedule, event.advance, spike.fire, plasticity.apply
population.spawn, population.mutate, population.evaluate
archive.insert, archive.query, lineage.record, population.transfer
sequence.scan, sequence.retain, sequence.recur, sequence.chunk
memory.read, memory.write, memory.update, memory.compact
diffuse.noise, diffuse.denoise, energy.score, sampler.step
graph.message, graph.aggregate, latent.query, basis.apply
equilibrium.solve, equilibrium.residual, equilibrium.certificate
learn.test_adapt, uncertainty.calibrate, uncertainty.coverage
agent.observe, agent.derive, agent.plan, agent.authorize
agent.execute, agent.learn, agent.fuse, belief.combine
judge.question, judge.evaluate, decision.project, decision.escalate
cognition.retrieve, cognition.focus, cognition.route, route.plan, route.execute, route.reuse, route.receipt, proposal.verify
world.intervene, world.counterfactual_family, world.compare_actions, world.validate_invariants
exploration.record, exploration.dream, exploration.evaluate, exploration.verify
autonomy.check, autonomy.admit, autonomy.rollback
program.patch, program.validate, program.semantic_diff, program.migrate, program.activate, program.rollback
compiler.bootstrap, compiler.differential, compiler.shadow, compiler.receipt
fabric.observe, fabric.place, fabric.transfer, fabric.collective, fabric.failover
profile.measure, optimize.propose, optimize.shadow, optimize.activate, optimize.rollback
version.propose, version.verify, version.shadow, version.canary, version.transition
version.activate, version.degrade, version.rollback, version.retire, version.reject
agent.authorize_delegation, agent.delegate, task.submit, task.query
task.transition, task.artifact, task.cancel, task.reconcile
branch.fork, branch.publish, branch.await_receive, branch.cursor_commit
branch.outbox_commit, branch.watermark, branch.cancel, branch.drain
branch.integrate, branch.rebase, branch.quiescent
gate.check, commit.gate, commit.admit, commit.effect, credit.split, credit.transfer, credit.return
effect.intent, effect.result, event.append
evidence.atom, evidence.combine, evidence.project, evidence.status
provenance.node, provenance.edge, provenance.merge
data.validate, data.declassify
```

每个值携带类型、形状、布局、设备、所有权和效果；认知值还携带规范化证据来源、残余冲突、目标约束、策略版本和预算/能力范围；每个内存操作携带区域和别名信息。

`derive.request`、`plan.*` 和 `numeric.*` 是 CCTM 的核心降级点：前者从同一 n-IR 产生分析/变换，后两者把验证过的计划绑定到转换并在残差超界时执行回退。它们不能绕过 `TransitionContract`、`Delta`、`Credit` 或 `CommitGate`；领域 API 只是这些操作的类型化投影。

### 7.2 三个 IR 层级

```text
n-Core-IR       保留 AI 状态、世界/想象标签、学习、程序 Delta、事件、seed、效果、线性资源和形状语义
n-Opt-IR        显式循环、张量布局、并行区域、设备放置、数据移动、流水线和内存生命周期
n-Machine-IR    SSA、寄存器、向量/事件/collective 指令、调用约定和设备指令
```

多进制 profile 在三层的责任不同：n-Core-IR 保存 `NumericContract`、语义类型、误差/质量门和 profile digest；n-Opt-IR 决定 block/axis 分组、scale、LUT、数据移动与转换位置；n-Machine-IR 才决定具体 bit packing、指令和设备格式。任何只在后端发生而未写回 profile digest 的变基或重新量化，都视为不合法优化。

### 7.3 AI 直接 IR 与可读投影

AI 可以通过类型化 builder、`.nib` 或结构化 `ProgramDelta` 直接生成/修改 n-IR；`.n`/`.nir` 文本是同一规范图的可读投影。直接 IR 路径省去词法/语法解析，但仍必须经过同一个 verifier：

```n
@nir fn saxpy_kernel[T, N](a: f32, x: View[f32, [N]], y: ViewMut[f32, [N]]) {
    parallel.for %i = 0 .. N {
        %v = tensor.load %x[%i]
        %w = tensor.load %y[%i]
        tensor.store %y[%i], fma(%a, %v, %w)
    }
}
```

`@nir` 代码仍需经过 n-IR 验证。AI 不应通过拼接文本或不稳定节点序号修改 IR；使用内容摘要与 `NirPatch` 的预期摘要检测并发冲突。直接嵌入 LLVM、PTX 或机器码只能使用 `unsafe extern`，不能改变 n/Core 的语义。

## 8. 编译器和后端

```text
.n 可读表面 -> lexer/parser ┐
.nir/.nib/ProgramDelta -----┴-> n-Core verifier
  -> 名称、现实/想象标签、学习效果、时间、形状、所有权、Objective epoch 检查
  -> n-Core-IR
  -> 常量折叠 / 融合 / rollout / 事件调度 / 布局 / 增量依赖 / fabric 放置搜索
  -> n-Opt-IR
  -> 向量化 / 分块 / 并行调度 / 数据移动 / 设备分派
  -> n-Machine-IR
  -> x86-64 / ARM64 / RISC-V / CUDA / ROCm / WASM / neuromorphic / custom accelerator
```

后端必须提供：调用约定、原子操作、向量宽度、对齐要求、内存层级、链路/collective 能力、故障域、设备能力表和浮点模式。没有能力表的扩展不能进入自动调度。

首批 CPU 目标为 x86-64 System V、Windows x64 和 AArch64。GPU 后端以 CUDA、ROCm 为优先；没有 GPU 时同一 `parallel for` 必须有 CPU 降级路径。

## 9. 互操作和标准库

```n
extern "C" fn cblas_sgemm(...) -> Unit ! unsafe
extern "fortran" fn dgemm(...) -> Unit ! unsafe
extern "cuda" fn launch_kernel(...) -> Event ! gpu
```

标准库分为：`n.core`、`n.ai`、`n.world`、`n.learn`、`n.meta`、`n.evolve`、`n.event`、`n.snn`、`n.sequence`、`n.memory`、`n.diffusion`、`n.energy`、`n.equilibrium`、`n.uncertainty`、`n.agent`、`n.evidence`、`n.judge`、`n.program`、`n.compiler`、`n.fabric`、`n.profile`、`n.mem`、`n.graph`、`n.tensor`、`n.math`、`n.parallel`、`n.io`、`n.ffi`、`n.autodiff`。`n.ai` 的关键类型和 n-IR 语义属于语言规范；具体动力学、Learner、神经元、进化算子、采样器和求解器放在标准库，可替换而不能绕过核心类型边界。BLAS、LAPACK、MPI 和系统调用都通过 `n.ffi` 适配，不成为语言核心依赖。

## 10. 典型程序

### 10.1 矩阵乘

```n
fn matmul[M, K, N](
    a: View[f32, [M, K], row_major],
    b: View[f32, [K, N], row_major]
) -> owned[Tensor[f32, [M, N], row_major]] ! alloc {
    let c = zeros[f32](M, N)
    parallel for i in 0..M {
        for k in 0..K {
            let aik = a[i, k]
            simd for j in 0..N {
                c[i, j] += aik * b[k, j]
            }
        }
    }
    c
}
```

编译器可融合循环、选择分块和 SIMD；但如果布局或别名条件不满足，必须报告原因而不是默默生成错误优化。

### 10.2 增量 seed

```n
seed RunningSum {
    total: f64

    observe(batch: View[f64, [N]]) -> f64 ! pure {
        reduce[stable_sum, ordered](batch)
    }

    fold(x: f64) -> RunningSum ! pure {
        RunningSum { total: self.total + x }
    }

    report(_: f64) -> f64 ! pure {
        self.total
    }
}
```

编译器可以把不变的前缀缓存起来；只有在 `observe` 被标记为可重排归约时才允许跨线程并行。

## 11. 性能验收标准

性能不能用“理论上极快”验收。n 的基准套件固定输入、编译器版本、CPU/GPU、线程数、精度、质量门槛和误差阈值，并同时发布源码、n-IR、机器码及 `PlanDigest`。每个结果都绑定 `BenchmarkBinding` 的 source/n-IR/compiler/runtime/hardware/benchmark/result 摘要，并明确是否计入编译、调度、数据移动、监测和回退。冷启动、编译/自动调优、稳态、p50/p99 延迟、峰值内存和能耗分别报告；自动调优成本不能只在图外摊销。数值内核同时对比等价 C/C++/Fortran、厂商库和适用的专用编译器路径，AI 工作负载则比较相同任务质量下的端到端效能。

第一阶段验收。所有性能结果必须同时给出任务质量/能力指标和 `CostVector`；只有在质量不低于基线或满足明确容差时，才计算速度与单位资源收益：

1. 标量循环：相对同编译器同选项的 C，安全模式额外开销不超过 5%。
2. Dense GEMM、AXPY、stencil、FFT：与 C/Fortran + 厂商库比较；n 至少达到同一库调用性能。
3. 融合算子：与未融合 n 程序比较，证明临时分配和内存往返减少。
4. 增量训练：与全量重算比较，结果逐元素相等或在声明的浮点容差内相等。
5. Agent 回放：同一输入事件、Reasoner 摘要、证据来源和策略版本必须产生相同的 `Decision`、`Plan`、`ReasoningReceipt` 和授权摘要；若策略要求则还必须相同 `Evidence`，result-only 不要求重建隐藏 trace；外部工具只使用回放结果。
6. Agent 融合：交换输入 Agent 的顺序不改变 `consensus` 结果；`residual`、来源和权限集合必须保持可追踪。
7. RuntimeRoot 完整性：没有 `ToolCapability` 的 Agent 不能产生对应外部行动；预算耗尽必须返回 `BudgetExceeded`，但不依赖该外部效果的本地推理仍可继续。
8. 编译器正确性：参考解释器、n-IR 执行器和目标后端三者通过差分测试。
9. 类型化判断：问题 ID/版本、Reasoner 摘要和 schema 变更可检测；相同 n-IR 回放必须复现 `Decision`、`Evidence`（若策略要求）和 `ReasoningReceipt`/授权摘要；`none/result_only` 不要求重建隐藏轨迹，但必须重现输出 digest、质量/残差和 replay 状态，并报告精度、召回率、未知率、冲突率和 schema 失败率。
10. 数据流边界：schema 合法但内容错误的工具或外部输入仍保持 `Untrusted[T]`，不能构造 capability 或降低数据标签；所有 declassify 都需机器策略事件。
11. 崩溃一致性：在 effect intent、远端执行和结果落盘之间注入崩溃；无幂等协议时必须得到 `outcome_unknown` 且不得自动重放副作用。
12. 委派边界：子 grant 的权限、预算、数据标签和有效期均不超过父 grant；取消、超时和断连不被误报为回滚或成功。
13. Evidence/Provenance：重复 atom 投递不改变投影或摘要；合并顺序不改变规范图摘要；策略/评价时间不匹配必须失败或显式重投影；同 ID 内容不匹配必须失败；压缩后可校验根摘要。
14. 异步多螺旋：快分支可在慢分支尚未完成时影响其后续转换；随机化网络延迟、重复投递和工作线程完成顺序后，已证明合流的 `causal_async` 策略必须得到相同 trunk digest；非合流处理器必须被拒绝或使用 `ordered_async`/`round_sync`。未 receive 的消息不能改变分支，旧 base 的 merge 必须 rebase 或返回 `StaleBranch`/`MergeConflict`。
15. 异步恢复与停止：在 state/cursor/outbox 提交和消息送达之间注入崩溃，不能丢消息或重复计入 Evidence；只有全部 `WorkCredit` 返回、mailbox/outbox 为空且无主干提交时才能报告 `Quiescent`。
16. 并行效率：对独立与相互依赖任务比较单分支、同步多分支和异步多分支的墙钟时间、总计算成本、消息量、覆盖率和质量，发布完整预算；只有 Pareto 改善或满足任务声明的效能次序时才晋升，不能只凭 wall-clock speedup 宣称更高效。
17. 无 LLM 基线：断网且没有 LLM 模型文件、API 密钥、tokenizer 或提示词资产时，标准 AI/Agent 语义测试、回放测试和多螺旋测试必须完整通过。
18. 背压与取消：填满数据通道不能丢消息，也不能阻止控制通道传递取消；取消后不得派生新工作，已提交历史保持可回放，全部 `WorkCredit` 最终守恒。
19. 世界模型边界：`Imagined`/`Predicted` 不能隐式构造 `Observed`；rollout 必须报告 horizon、预算、校准误差和分布外状态。故意混淆现实/想象的程序应编译失败。
20. 元学习：任务训练集与保留评估集的数据标签必须阻止泄漏；`adapt@k` 恰好受步数/预算限制，未通过 evaluate/verify 或没有 PromotionCapability 的候选不能替换当前策略。
21. 开放式探索：固定种子和调度记录可重放谱系与档案摘要；达到种群/世界/预算上限后停止且保存 archive，生成候选只能从父 capability 衰减派生，不能继承 RuntimeRoot 根能力。
22. 连续动力学：求解器、容差、最大步数和浮点模式进入摘要；参考求解器与优化后端在声明误差界内一致，刚性/不收敛返回 `SolverError`。
23. SNN/事件计算：同 tick 事件的规范批处理与零延迟环检测可重放；CPU 参考事件解释器和 neuromorphic adapter 的脉冲/状态轨迹在声明容差内一致。能耗优势必须报告真实硬件、吞吐、延迟和精度，不能由稀疏性推断。
24. 跨范式转换：Tensor/Graph/Symbol/Distribution/EventStream 之间的转换必须记录窗口、损失和 provenance；省略必要验证或校准时编译失败或返回显式错误。
25. 长序列计划：同一 `SequenceOperator` 在 `parallel`、`recur` 和 `chunked` 计划下，在声明的浮点/状态容差内得到相同规范摘要；状态边界、布局和计划版本可重放。
26. 测试时适应：`test_adapt@k` 严格限制步数、窗口和预算；短期更新不能污染长期记忆，未晋升候选不能改变当前策略，回滚后事件摘要保持一致。
27. 生成与能量过程：Diffusion/EBM 固定 seed、噪声/温度/采样策略和最大步数可重放；`Generated` 样本不能隐式转换为 `Observed`/Evidence，采样失败或预算耗尽必须可观察。
28. 隐式平衡：`EquilibriumState` 只有在残差、容差、稳定性和 solver 摘要满足契约时才可通过；不收敛、多解或隐式梯度超界返回 `SolverError`。
29. 不确定性：`PredictionSet` 的覆盖率、宽度、拒答率和校准域必须进入报告；域外或漂移数据只能返回 `unknown/out_of_calibration`，不能继续使用旧覆盖率承诺。
30. 多级编译：外部 MLIR/StableHLO/Triton/Halide/Futhark 等路径必须先降级到可验证 n-IR；参考解释器、优化 n-IR 和后端通过差分测试后才允许自动调度。
31. RTST 投影一致性：同一 `TransitionRecord` 导出的 EventLog、ProvenanceGraph 和 Evidence 摘要必须互相引用且不能产生不同输入摘要；删除/压缩载荷后只能按 ReplayMode 返回明确缺失状态。
32. Delta 合并：`Delta[D,T]` 的 base digest、前置条件、幂等键和 `MergeLaw` 必须阻止重复提交、静默覆盖和无证明重排；合流 Delta 的提交顺序改变时规范摘要不变。
33. CommitGate：`AdmissionGate` 只能晋升内部版本，`ActionGate` 才能产生一次性 ActionTicket；缺少对应 capability、预算或效果时编译/运行时拒绝，不能互相替代。
34. Credit 守恒：BudgetToken、WorkCredit 和 DelegationGrant 的拆分、转移、退款和归还总量守恒；崩溃重放不得重复铸造 credit。
35. MemoryStore：working/episodic/adaptive/external 模式的容量、retention、地址、效果和 provenance 可审计；无参数 Memory 在 n-IR 中不得出现。
36. RealityTag：只有显式 `validate`/`ground`/`promote` 门能生成 `validated(P)`；只有带 `GroundingReport` 的 `ground` 结果能进入现实 Evidence。策略撤销、校准域变化或证据删除后，旧 validated 标签必须显式失效，不能继续授权。
37. 选择性转换：同一输入在 dense、route、补偿和 exact fallback 计划下，输出 schema、状态 Delta、RealityTag 和错误语义一致；`RouteReceipt` 能重放实际选择与回退。
38. 路由成本：基准分别报告路由、内核、内存流量、同步、延迟、能耗和总成本；任何未观测维度都显示 `unknown`，不能作为零成本参与 Pareto 排序。
39. 误差恢复：注入被误选、摘要失真和跨层漂移，必须触发 residual 超界、补偿或 exact fallback，且不能把未验证结果写入现实 Evidence。
40. 计划兼容：违反 `CompatibilityContract` 的优化计划在编译期或运行时拒绝；合法计划的随机流、状态边界、浮点模式和 replay 摘要可复现。
41. 探索与上线隔离：`dream` 只能读取 replay tree 并产生 Candidate；在没有 `AdmissionGate`、预算、回滚点或保留集验证时，当前策略、长期记忆和工具权限保持不变。
42. 自主性阶梯：逐级测试 execution/strategy/experience/environment/meta_improvement，越级 Delta、权限扩张和外部 ActionTicket 必须拒绝，失败后可回滚且保留审计记录。
43. 反事实一致性：同一 `CounterfactualFamily` 的替代行动共享 base/kernel/world contract；不满足已验证不变量的候选必须显式报告，不能由各分支单独“看起来合理”掩盖矛盾。
44. 联合行动：多 Agent 同时行动的预测默认使用 `joint` action；只有经验证的 `FactorizationContract` 才能拆成独立转换，联合效应不得通过单体预测求和近似而不报告误差。
45. 部分可观测：`StateEstimate` 必须保留历史证据、可观测性和 residual；主动 `QueryPlan` 按信息/决策价值和全成本比较，观察请求未返回前不能构造 `Observed`。
46. 持续适应隔离：冲突 Delta 不得静默覆盖先前能力；旧能力保留率、未见环境迁移和预算归一化覆盖与新任务得分一起报告。
47. 事件通信效率：SNN/event 路由的稀疏率不能替代带宽、同步延迟和真实设备能耗测量；预测抑制必须在 residual 超界时回退到更完整事件路径。
48. 开放式增长：新颖候选数或 QD archive 大小单独增加不能通过验收；报告需包含行为/任务覆盖、迁移、保持和单位预算增益。
49. AI 自动优化：对 `schedule/layout/device/precision/route/cache/memory/fanout` 候选执行影子/差分基准；只有质量契约不退化且 Pareto 改善的候选可以自动晋升，性能回退必须触发版本回滚。
50. 控制面开销：分别报告纯 kernel、RTST 边界、provenance/遥测和 RuntimeRoot 动态检查成本；可静态证明的纯热区不得保留逐元素 RealityTag、capability 或日志检查，边界摘要不能改变 kernel 输出。
51. ProgramDelta：随机生成插入/替换/删除/重连 patch，并注入旧 base、错类型、错效果、悬垂 value、RealityTag 越级和并发冲突；verifier 必须拒绝，失败不得产生半更新 ProgramVersion。
52. 自举编译器：C0->C1->C2 固定点、参考解释器、旧/新编译器和至少一个独立后端进行差分；固定点相等但语义测试失败仍不得晋升，编译器候选不能删除或改写失败语料。
53. 热替换：在 kernel、异步事件、Delta 提交和状态迁移的每个边界注入切换/崩溃；只有安全点可换入口表，ABI/schema 变化必须迁移或拒绝，canary 失败能恢复旧代码和状态摘要。
54. 异构织网：分别测 kernel、数据移动、重排、collective、同步、拥塞和恢复成本；改变拓扑/频率/温度并注入设备或链路失败后，陈旧 PlacementPlan 必须失效、降级或重规划，不能隐藏复制和丢状态。
55. 自主程序演化闭环：AI 从 workload/fabric receipt 产生 ProgramDelta/PlacementPlan，完成验证、影子执行、自动晋升、稳态观测和回滚；评价 epoch、质量门槛、计时/成本口径及保留集在一次评估内保持不可变，候选不能通过修改评价器制造“进步”。
56. 统一制品生命周期：随机生成 parameters/reasoner/policy/program/compiler/route/placement/memory schema/objective 版本及失败转换；verifier 必须拒绝原地修改、缺证据晋升、依赖摘要漂移、过期 RootLease 和不兼容迁移；shadow/canary 失败后 active 版本与回滚窗口保持可恢复，多个 active 专家必须由唯一版本化 RoutePlan 选择。
57. 多进制数值 profile：在相同输入、质量门槛和 `NumericContract` 下比较 binary/ternary/low-bit/mixed-radix 编码；必须报告量化误差、转换/LUT/解码、带宽、同步、能耗、编译和回退成本，且参考解释器、优化 n-IR 与后端结果在声明容差内一致。隐式变基、错误特殊值、`Trit`/`Tr` ABI 混淆或未知成本按零计入时必须拒绝。
58. 结果优先/不可解释性：`none/result_only` 的 ReasoningReceipt 可以在内部搜索和低风险控制中省略 trace，但同一输入、Reasoner/Policy/数值 profile 和回放模式必须复现输出 digest、质量/残差和门控结果；缺少所需 Evidence/GroundingReport/proof 时，现实标签提升、外部 ActionTicket 和 ArtifactVersion 晋升必须返回 `unknown`/拒绝，不能把 opacity 当作安全证明。
59. CCTM 执行计划：`ExecutionPlan` 必须绑定程序、机器码/后端、布局、设备、通信、`NumericContract`、误差证明、回退计划、监测策略和 `objective_epoch`；执行只能经 `plan.select -> plan.execute -> PlanReceipt`，退化在安全点原子切回兼容计划。
60. 统一 `derive`：`tangent/adjoint/influence/memory/error/cost/schedule` 等目标必须从同一 source n-IR 产生，记录依赖闭包、模式、预算、摘要和残差；`heuristic` 推导不能直接提交 Delta、现实 Evidence、ActionTicket 或 active 版本。
61. 近似值回退：`Approx[T]` 不得隐式当作精确 `T`；注入误差超界、精度漂移、设备不匹配和 fallback 失败时，必须得到可重放的 `numeric.fallback`/拒绝结果，不能把混合路径伪装成精确执行。
62. 基准可归因：每个性能/质量声明必须绑定 `source_digest`、`nir_digest`、`compiler_digest`、`runtime_digest`、`hardware_digest`、`benchmark_digest` 和 `result_digest`，并标明是否计入编译、调度、数据移动和回退成本；缺任一摘要只能标为未归因，不能进入 `AdmissionGate`。

“超过 C/Fortran”只在明确的工作负载和基准口径下成立；对任意程序作绝对承诺是不严谨的。

## 12. 工具链

CLI 是可观测投影；AI 的主接口是 `n.compiler`/`n.runtime` 的类型化本地协议，消息直接使用 `.nib`、`ProgramDelta`、`OptimizationCandidate` 和 receipt，不需要解析终端文本：

```text
CompilerService.validate(nib | ProgramDelta) -> Result[Candidate[ProgramVersion], ValidationError]
CompilerService.optimize(program, fabric, objective) -> Stream[OptimizationCandidate[Plan]]
Runtime.shadow(candidate, workload) -> PerformanceReceipt
Runtime.admit(candidate, receipt, gate) -> Result[VersionId, PromotionError]
Runtime.rollback(version, reason) -> TransitionRecord
```

供检查、调试和兼容自动化使用的 CLI 为：

```text
n check file.n                 类型、形状、所有权和效果检查
n run file.n                   解释器或 JIT 执行
n build file.n -o app          生成目标程序
n emit-ir file.n -o file.nir  导出可审计 n-IR
n apply delta.nib              验证 ProgramDelta 并产生候选版本
n optimize app.nib --fabric F  搜索并影子验证执行计划
n bootstrap compiler.n         生成 BootstrapReport，不自动替换当前编译器
n test                         运行标准库和后端回归
n bench suite                  运行固定基准并输出机器可读结果
n fmt file.n                   格式化
```

调试构建保留边界、生命周期和浮点检查；发布构建只能删除已证明安全的检查，并在 `emit-ir` 报告中列出删除依据。

## 13. 版本路线

路线按“可被 AI 直接使用的机器语义”排序，而不是按人类语法或某个后端的完成度排序。每个阶段都必须有可执行验收物；未通过的阶段保留为候选，不能用文档或演示冒充稳定能力。

| 版本 | 机器优先交付物 |
| --- | --- |
| n-0.1 | 规范 `.nib`/`.nir` 双编码、n-Core-IR schema、round-trip codec、n-Core verifier、参考解释器、`TransitionStore`、`RootEnvelope`/本地 `RootLease` loader；`.n` 仅作为可选诊断投影 |
| n-0.2 | `RealityTag`/`Tagged`、`Delta`/`TransitionContract`、`Credit`、`CommitGate`、事件回放，以及 `version.*` 统一制品生命周期 |
| n-0.3 | `ProgramDelta`、增量依赖 verifier、类型/所有权/效果/形状检查、`Result`/结构化诊断、稳定 C ABI；`.n` parser 作为无损投影接入 |
| n-0.4 | 标量/Tensor/View、布局/设备/分配器、多进制 `RadixSpec`/`EncodingProfile`、`parallel`/SIMD、x86-64 参考后端、参考解释器与后端差分基准 |
| n-0.5 | `AIState`、`Objective`、`Observed/Predicted/Imagined/Counterfactual`、`Tr`/Evidence、确定性 seed、Tensor/Graph/EventStream 和自动微分 n-IR 变换 |
| n-0.6 | `World/Dynamics/rollout`、`Learner/update`、原生 Agent 生命周期、`retrieve/focus/route/judge/verify`、工具授权与事件日志 |
| n-0.7 | `MemoryStore`、Provenance DAG、持久 mailbox、因果异步多螺旋、耐久任务、受限委派、故障注入和三档一致性 |
| n-0.8 | `adapt@k`、QD/open-ended 档案、SNN/连续动力学/扩散/能量/平衡参考解释器、跨范式转换和不确定性校准 |
| n-0.9 | `WorldContract`/`CounterfactualFamily`、联合动作、部分可观测恢复、主动 `QueryPlan`、选择性转换/补偿、冲突隔离和多维成本 |
| n-0.10 | `EfficiencyObjective`、多进制/低精度 profile 的 `adaptive-fastest`、控制面/热数据面分离、完整 `PerformanceReceipt`、RouteReceipt 和版本化自动调优 |
| n-0.11 | 影子执行、canary、状态迁移、事务热替换、自举编译器、父版本/独立后端差分和程序演化闭环 |
| n-0.12 | `ExecutionFabric`、CPU/GPU/NPU/neuromorphic、拓扑感知放置、数据移动/collective、故障域恢复和跨域 ABI |
| n-0.13 | CCTM 核心：一等 `ExecutionPlan`、统一 `derive`、`Approx[T]` 误差界/精确回退、计划回执和摘要绑定基准 |
| n-1.0 | 稳定 AI/Agent/RTST/n-IR、自治程序演化、异构织网、标准库、跨后端回放、性能/自治完整性基准和可复现多阶段自举 |

`topo`、`quantum`、`proof` 只有在拥有可执行后端、测试向量和明确成本模型后，才进入 1.x 扩展协议。

## 14. 借鉴其他现代语言

n 应该学习成熟语言解决过的问题，但不能把每门语言的复杂性叠加进核心。下表是“采用、改造、不采用”的边界：

| 来源 | 借鉴 | n 的改造 | 不照搬 |
| --- | --- | --- | --- |
| Rust | 所有权、借用、`Result`、trait 约束、优秀诊断 | 让 Tensor/View/Device 成为一等类型；把生命周期错误映射到内存区域和异步事件 | 不复制完整 Rust 语法、宏体系和过度泛型；不要求所有用户手写生命周期 |
| Zig | 显式 allocator、`comptime`、错误联合、无隐藏运行时 | allocator 作为模块/函数参数；`comptime` 只能执行纯、可终止、可缓存的代码 | 不把未定义行为当作默认优化工具；安全模式不允许静默越界 |
| Mojo | 参数化声明、编译期求值、SIMD/硬件友好类型、逐步提高约束 | 用 n-IR 保留参数、布局、设备和向量宽度，并在实例化报告中显示成本 | 不继承 Python 语法和运行时语义；不把编译器黑盒优化当作语言保证 |
| Julia | 多重分派和按类型特化 | 默认静态分派；动态分派必须写 `dyn`，热路径可通过显式 `specialize` 特化 | 不允许隐式全局类型变化破坏可预测性能 |
| Swift | 值语义、`move`/非复制值、并发安全诊断 | `owned`、`borrow`、`linear` 与 n 的设备事件和 Tensor 生命周期统一 | 不把引用计数作为核心运行时成本；不隐藏跨设备复制 |
| Vale | 借用检查与区域/代际内存思路 | 第一版使用词法区域 + 所有权，后续增加 arena/epoch 推断 | 不在没有证明和基准前承诺自动内存回收 |
| Koka / Eff 风格语言 | 效果行、让副作用进入类型 | `! pure/state/memory/learn/event/io/alloc/async/gpu/unsafe` 作为可组合效果集合 | 不把所有标准库调用都变成难读的效果注解 |
| Odin / Jai | 直白的系统接口、编译期工具和数据导向布局 | 放入 `n.ffi`、`comptime` 和显式 `layout`，全部可导出到 n-IR | 不依赖隐式全局状态或不可审计的宏替换 |
| C++ | RAII、零开销抽象、模板/概念、`constexpr`、协程、成熟 ABI 生态 | RAII 语义落到 `owned`/区域；模板能力收敛为 `cap` + 参数化；协程落到 `async` 事件 | 不引入继承层次、隐式拷贝、异常作为控制流、宏元编程和未定义行为优化 |
| D | 契约、`@safe` 分层、编译期函数执行、范围/切片 | `requires`/`ensures`/`invariant` 进入 n-IR；`safe`/`unsafe` 与效果系统合并 | 不复制 D 的隐式 GC 默认和过大的语法表面 |
| C# | `Span`/切片、模式匹配、`async`/`await`、清晰的工具链 | `View`/`ViewMut` 借用切片；异步句柄必须显式等待或转移 | 不把 GC、JIT 或异常吞入系统核心；托管运行时只能作为后端/宿主 |
| Java | 分层 JIT、逃逸分析、成熟字节码和工具生态 | n-IR 可保留 profile 提示，JIT 只能优化不改变的 n 语义；提供 JVM FFI | 不采用 GC、类继承和运行时反射作为 n/Core 依赖 |
| Go | goroutine/channel、简单接口、工具链和可读并发 | 用 `task`/`channel`/`select` 扩展表达结构化并发，并由效果系统标注阻塞 | 不默认无限 goroutine、共享可变内存或 GC；所有任务必须有生命周期 |
| Haskell | 代数数据类型、模式匹配、惰性/纯函数、类型类 | ADT 和穷尽匹配进入 n/Core；惰性只作为 `lazy` 值或显式流 | 不让全局惰性隐藏内存峰值、终止性和调度成本 |
| OCaml / F# | 模块签名、代数类型、局部类型推断、实用函数式风格 | `module`/`cap` 分离抽象与实现；推断失败时给出可读的类型洞察 | 不牺牲 ABI、布局和可预测性能来追求完全隐式推断 |
| Erlang / Elixir | actor、邮箱、监督树、故障隔离、热升级 | 作为 `n.actor` 运行时扩展；消息类型、背压和监督策略写入效果/IR | 不把 actor 调度和 GC 引入 CPU 数值核心；不隐藏复制和序列化成本 |
| Kotlin | 空安全、代数式 `when`、结构化协程、跨平台工具 | `Option`/`Result`、穷尽 `match`、结构化 `task` 纳入标准库 | 不复制 JVM 类体系和隐式装箱；原生路径必须明确布局 |

### 14.0 编译器基础轴

Agent 认知代数是 n 的公开语言机制；以下六个轴是支撑它的编译器基础，不是 n 的最终身份。它们仍然保持正交，避免同一个事实由多套规则重复表达：

| 轴 | 解决的问题 | 主要来源 | n 的唯一机制 |
| --- | --- | --- | --- |
| **值 Value** | 数据是什么、如何匹配和组合 | C++ struct、Haskell/OCaml ADT、C# pattern | `struct`、`enum`、`match`、值语义 |
| **资源 Resource** | 谁拥有、谁借用、何时释放 | C++ RAII、Rust borrow、Swift move、Zig allocator | `owned<T>`、`borrow<T>`、`borrow_mut<T>`、`linear<T>`、区域 |
| **能力 Capability** | 可以对值做什么 | Rust trait/C++ concept、Zig interface 风格 | `cap` 约束、静态实例化、显式 `dyn cap` |
| **效果 Effect** | 计算能否提交状态、记忆、学习、事件、IO、分配、异步或触碰设备 | Koka/Eff、Rust Result、Go/Elixir 并发 | `! {pure, state, memory, learn, event, io, alloc, async, gpu, unsafe}` |
| **索引 Index** | 形状、布局、精度、设备是否匹配 | Mojo SIMD/参数、C# Span、D contract | `Tensor[T, Shape, Layout, Device]` 与可检查合约 |
| **执行 Execution** | 何时、在哪个执行域运行 | C++ coroutine、Java JIT、Go task、Erlang actor | `region`、`task`、`channel`、`actor`、`seed` |

基础轴规则是：

1. **资源轴负责生命周期，效果轴负责权限，索引轴负责数据合法性。** `owned` 不替代 `! alloc`，`gpu` 也不替代 `Device` 类型。
2. **能力轴只约束操作集合。** `cap Float` 不隐含分配、线程、布局或所有权；这些信息必须由其他轴表达。
3. **执行轴只描述调度，不改变值语义。** `task`、`actor` 和 JIT 可以换调度方式，但必须保留同一 n-Core-IR 结果契约。
4. **同一事实只保留一个来源。** 例如“不能写入”由 `borrow<T>` 表达，不再同时用 `const`、`readonly` 和 `shared` 三套关键字表达。
5. **所有表面语法先降级到六轴核心。** 优化器只消费 n-IR 中的轴信息，不直接理解 C++/Rust/Mojo 风格的语法。

RTST 不是第七套互相竞争的类型轴，而是横跨六轴的唯一提交不变量：任何值、资源、能力、效果、索引或执行计划形成的转换，都必须能够构造同一个 `TransitionContract`，并通过现实标签、Delta、Credit 和 replay 字段检查。这样“AI 机制”不会再成为绕过 Core 规则的旁路。

统一示例：

```n
fn matmul[A: Allocator, T: Float, M, K, N, D: Device]
    (a: borrow[Tensor[T, [M, K], row_major, D]],
     b: borrow[Tensor[T, [K, N], row_major, D]],
     alloc: borrow_mut[A])
    -> Result[owned[Tensor[T, [M, N], row_major, D]], AllocError]
    ! {pure, alloc, gpu} {
    let c = Tensor.alloc_in[T](alloc, [M, N])?
    parallel for i in 0..M {
        simd for j in 0..N {
            c[i, j] = reduce[ordered](0..K, |k| a[i, k] * b[k, j])
        }
    }
    c
}
```

在这个声明中：

- `owned`/`borrow` 合并了 RAII、移动和借用，但没有引入隐式析构或引用计数；
- `A: Allocator` 合并了显式分配器和区域检查；
- `T: Float` 合并了模板/trait/concept 的能力约束；
- `[M, K]`、布局和 `D` 合并了形状、切片、SIMD 和设备约束；
- `! {pure, alloc, gpu}` 合并了效果和异步/设备权限；
- `parallel`/`simd` 只提供调度提示，最终必须在 n-IR 中证明别名、归约顺序和设备能力满足要求。

### 14.0.1 编译器不变量

AI 源程序不需要处理“机制冲突”；那是编译器必须验证的不变量。公开语义中的不确定性和分歧使用 `Evidence.residual`、`GoalConflict` 和 `Result` 表示。编译器内部按以下优先级拒绝非法优化：

```text
内存安全与资源唯一性
    > 语言语义与错误可观察性
    > 浮点确定性与可重放性
    > 设备/并行可移植性
    > 性能启发式
```

因此：

- 优化器不能为了向量化而违反借用或改变 `ordered` 归约；
- JIT 不能把 `Result` 失败变成未定义行为；
- GPU 后端不能隐藏 CPU↔GPU 复制和等待；
- 只有 `unsafe` 块可以越过安全检查，而且必须携带前置条件、ABI 和审计信息；
- 若多个合法实现性能不同，编译器应输出选择理由和基准数据，而不是改变程序语义。

### 14.0.2 核心与扩展的边界

AI 原生不意味着把所有算法塞进 n/Core。n/Core 保留 ADT、函数、`Result`、`match`、所有权、效果、时间、Tensor/Graph/EventStream、`RealityTag`、`Delta`、`Credit` 和区域；规范性的 n/AI 层保留 `AIState`、World/Dynamics/Objective/Learner 接口、TransitionKernel、更新版本、事件和 Evidence 语义；n/Agent 再增加信念、目标、能力、行动与协作。具体网络、优化器、神经元、进化算子和环境属于可替换标准模块，但不能绕过 RTST 提交边界：

| 扩展 | 复用的核心轴 | 不能新增的规则 |
| --- | --- | --- |
| `n.autodiff` | Value + Capability + Index | 不得绕过 Resource 和 Effect |
| `n.world` | AIState + Time + Evidence | rollout 不能把 Imagined 提升为 Observed；求解误差必须暴露 |
| `n.meta` | Learner + Region + Provenance | 内外循环数据和参数不得隐式别名；候选不能自动晋升 |
| `n.evolve` | Population + Budget + Provenance | 变异不能继承权限；开放式搜索仍受预算、沙箱和谱系约束 |
| `n.snn` | EventStream + Time + Learner | 不固定神经元/可塑性规则；事件排序和延迟必须可重放 |
| `n.sequence` | AIState + Execution + Index | 不固定 RWKV/RetNet/Hyena 公式；parallel/recur/chunk 计划必须共享状态转换契约 |
| `n.memory` | Resource + Provenance + Effect | 读写、容量、遗忘和测试时更新必须显式；不得把隐藏缓存当纯值 |
| `n.diffusion` | Time + Random + Evidence | 噪声、日程、采样器和 Generated 标签必须显式；样本不能提升为 Observed |
| `n.energy` | Objective + Constraint + Random | energy 不等于概率；采样必须有温度、步数、收敛和预算 |
| `n.equilibrium` | SolverPolicy + Index + Evidence | 求根残差、容差、最大迭代和不收敛状态不得隐藏 |
| `n.uncertainty` | Evidence + Calibration + Provenance | 覆盖率只在声明校准域内有效；分布漂移必须降级为 unknown |
| `n.neuromorphic` | Device + EventStream + Capability | 设备后端不得改变时间/数值语义；能耗结论需要真实基准 |
| `n.actor` | Execution + Effect + Value | 不得隐藏消息复制、背压和任务生命周期 |
| `n.agent.protocol` | Agent + Capability + Effect | 协议声明不能授予权限；远端输入/输出仍受信任标签、schema 和预算规则约束 |
| `n.topo` | Value + Index + Capability | 不得把拓扑等价偷偷当作字节相等 |
| `n.quantum` | Value + Resource + Execution | 不得假装普通 CPU Tensor 就有量子语义 |
| `n.proof` | Index + Capability + Effect | 证明失败必须是编译错误或显式运行时检查 |

自动微分的定位已经固定：AD 是 n-IR 的规范编译变换，不是新的运行时效果。源程序可以通过 `n.autodiff` 的 `grad`、`jvp`、`vjp` 和 `implicit_grad` API 请求导数，但编译器必须把它们降级为带资源、形状、设备和数值策略的 n-IR；反向传播产生的临时值遵守同一所有权/效果规则。无梯度的规则、搜索、SNN 局部可塑性、进化和采样程序仍是合法 n/AI 程序，不能因为 AI 原生就被强制改写为梯度训练。

### 14.0.3 JEV：可吸收的判断边界，不是语言依赖

JEV 的可借鉴点是“状态 + 具名问题 -> 类型化判断”。n 将判断、行动计划和 capability 边界都纳入 `Question`、`Decision[T]`、`Judge`、`ReasonerDigest`、`EvidencePolicy` 与 RuntimeRoot 语义，而不是把自主性外置到业务代码；判断可以被类型检查、融合、记录和回放。JEV 不是后端依赖；同样的问题必须能由 n 中的规则、约束或搜索实现。

不照搬的部分包括：把外部 API 或 LLM 当作 n/Core 依赖、把评分当成概率、把结构化结果当作真实性证明，以及让判断结果直接触发工具调用。Reasoner/schema 版本漂移、约束不可满足和证据不足都必须以 `JudgeError`、`unknown` 或 `conflict` 显式暴露。

### 14.0.4 工作流、溯源和 Agent 协议的外部启发

| 来源 | 吸收的设计启发 | n 的边界 |
| --- | --- | --- |
| [W3C PROV-O](https://www.w3.org/TR/prov-o/) | 用 Entity、Activity、Agent 及生成、使用、派生、归属关系表达 provenance，而不只存平面来源列表 | 只吸收可内容寻址的 provenance DAG；不把 RDF/OWL 推理引入 n/Core |
| [Temporal Workflows](https://docs.temporal.io/workflows) | 确定性重放依赖完整事件历史；网络、工具等外部活动的结果应记录并在重放中复用 | n 定义自己的 effect intent/result、崩溃恢复和版本兼容语义，不依赖 Temporal 运行时 |
| [MCP Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) | 工具输入/输出 schema 可机器验证；行为注解是不可信提示；调用应考虑确认、结果校验、超时和审计 | schema 合法不代表内容真实、安全或已授权；MCP 只是 `n.agent.protocol` 的适配器 |
| [A2A Specification](https://a2a-protocol.org/latest/specification/) | 跨 Agent 长任务需要显式任务状态、续问、取消、更新和制品，而非只交换一次性文本 | n 的 `AgentTask` 与委派 grant 定义语义；A2A 线格式、Agent Card 和传输细节留在适配层 |

这些来源的协议和文档会演进，n 只固定自身的抽象语义和适配器兼容矩阵；协议版本、服务端能力和 schema 摘要必须写入任务事件，不能被当成稳定不变的语言承诺。

### 14.0.5 编程语言与编译器生态的新增启发

模型架构之外，n 还需要学习“如何把复杂语义编译成可验证、可优化、可互操作的程序”。以下经验进入 n 的设计边界，而不是照搬某个工具链：

| 来源 | 可吸收的机制 | n 的重构 | 不照搬 |
| --- | --- | --- | --- |
| [MLIR](https://mlir.llvm.org/)、[StableHLO](https://github.com/openxla/stablehlo) | 多级 IR、方言、渐进 lowering 和验证器 | n-Core-IR/n-Opt-IR/n-Machine-IR 使用可验证 dialect；AI、事件、设备和线性资源信息在 lowering 时不得丢失 | 不把 LLVM/MLIR 方言名称当成 n 的语义，也不允许未验证的方言逃逸到后端 |
| [Halide](https://halide-lang.org/) | 算法与 schedule 分离，针对硬件重排而保持结果不变 | n 将纯 AI 图/状态转换与 `schedule`、布局、tile、设备放置分离；schedule 必须携带等价性和成本报告 | 不允许 schedule 偷改浮点归约、现实/想象标签或副作用顺序 |
| [Triton](https://triton-lang.org/main/) | 以 tile、warp、shared memory 组织 GPU kernel，保留较高层的张量表达 | `@kernel`/`tile` 作为 n-Opt-IR 扩展，布局、向量宽度、同步和设备能力显式化 | 不把某 GPU 的线程模型写进 n/Core，也不隐藏越界、同步和 CPU fallback |
| [Futhark](https://futhark-lang.org/) | 纯数组语言、唯一性/内存复用和融合 | n 的 Tensor/View/owned 与确定性 `map/reduce/scan` 复用其数据流思想；融合前后必须有 n-IR 摘要 | 不强制所有 AI 状态都变成规则数组，不牺牲 Graph/EventStream/Provenance 语义 |
| [Dex](https://github.com/google-research/dex-lang) | 可组合数组计算、索引类型与可微分函数式表示 | 借鉴“形状/索引/AD 由编译器组合”，把梯度变换固定为 n-IR pass | 不依赖实验性语言实现，不把 AD 当作所有程序的默认效果 |
| [Lean](https://lean-lang.org/)、[F*](https://fstar-lang.org/)、[Dafny](https://dafny.org/) | 规格、契约、精化类型和可证明安全 | `requires/ensures/invariant` 先做可执行检查；`n.proof` 可把形状、资源、融合等证明摘要接入编译器 | 不要求第一版具备完整定理证明器，也不把未检查的注释当证明 |
| [Pony](https://www.ponylang.io/) | actor + reference capability，隔离共享可变状态 | `n.actor` 使用能力/借用规则约束 mailbox、背压和取消；消息类型保留 provenance | 不把 actor/序列化成本隐藏在数值核心，不默认复制所有消息 |
| [Roc](https://roc-lang.org/)、[Unison](https://www.unison-lang.org/) | 纯函数、可恢复错误、内容寻址代码与可复现构建 | 程序、模块、n-IR、策略和事件日志使用摘要绑定；缓存/重放按 digest 而不是路径名匹配 | 不把内容寻址当作权限系统；RuntimeRoot capability 仍必须线性授予 |

由此得到一条编译器不变量：**优化可以改变表示和调度，不能改变 AI 状态转换、现实/想象标签、资源效果、证据溯源、随机种子或外部副作用顺序。** 每个新后端先实现参考解释器和差分测试，再申请自动调度能力。

### 14.1 n 的能力约束（trait 的简化版）

Rust trait 的核心价值是“按能力约束泛型”，而不是 trait 关键字本身。n 使用更小的 `cap` 声明：

```n
cap Add[T] {
    fn add(T, T) -> T ! pure
}

fn sum[T: Add[T], N](xs: View[T, [N]]) -> T ! pure {
    reduce[Add.add, ordered](xs)
}
```

规则：

1. `cap` 只描述可调用能力和关联常量，不携带隐式状态。
2. 默认静态分派；编译器为实际实例生成专用版本，并在 n-IR 中记录实例。
3. `dyn Cap` 是显式的胖指针/函数表，调用成本和布局可见。
4. 能力约束不能改变所有权、形状或设备；这些仍由独立类型参数表达。

### 14.2 参数化和 comptime

Mojo 的参数化思路适合 n 的形状和 SIMD，但 n 对编译期执行设置更严格的边界：

```n
comptime fn tile_for[T: Scalar](m: Dim, n: Dim, target: Target) -> Tile {
    // 纯函数；输入只来自类型、常量和目标能力表
    choose_tile[T, m, n, target]()
}

fn axpy[N, W: SimdWidth](x: View[f32, [N]], y: ViewMut[f32, [N]]) ! pure {
    let tile = comptime tile_for[f32](N, N, target())
    simd[W] for i in 0..N { y[i] += x[i] }
}
```

`comptime` 必须满足：无 `io`、无 `alloc`、无未绑定运行时值、有限步数、结果可序列化。超过预算时编译器报告诊断，不偷偷退化成运行时执行。

### 14.3 显式分配器

Zig 的 allocator 思路直接进入 n，但分配器的所有权比 Zig 更严格：

```n
fn make_matrix[A: Allocator, M, N](a: borrow_mut[A])
    -> Result[owned[Tensor[f32, [M, N]]], AllocError] ! alloc {
    let out = Tensor.alloc_in[f32](a, [M, N])?
    out
}

with arena() as a {
    let x = make_matrix[arena, 128, 128](a)?
    use(x)
} // 区域结束；x 和所有 View 必须已经结束
```

标准分配器接口固定为：

```text
allocate(layout) -> Result[RawBlock, AllocError]
deallocate(block, layout)
grow(block, old_layout, new_layout)
```

`Tensor` 记录分配器句柄和设备；`View` 只记录父缓冲区借用。编译器不允许把 arena 中的值返回到 arena 外，也不允许把 CPU 缓冲区视图伪装成 GPU 缓冲区。

### 14.4 错误、效果和诊断

借鉴 Rust 的 `Result`、Zig 的错误联合以及 Koka 风格效果，n 的失败路径统一为：

```n
fn load(path: String) -> Result[Bytes, IoError] ! io {
    let f = io.open(path)?
    f.read_all()
}
```

规则：

1. 可恢复错误返回 `Result[T, E]`；`panic` 只用于违反已声明合约或不可恢复故障。
2. `?` 只传播 `Result`，不隐藏分配、设备等待或 IO。
3. `! effect` 是调用图的一部分；`pure` 函数不能调用 `io`、`gpu` 或 `unsafe`。
4. 诊断必须指出：源位置、推断出的形状/布局/区域、冲突的借用，以及建议的修复方向。

### 14.5 分派、布局和硬件特化

Julia 的特化能力和 Mojo 的 SIMD 参数化都值得借鉴，但 n 采用“静态优先、动态显式”：

```n
fn dot[T: Float, N](a: View[T, [N]], b: View[T, [N]]) -> T ! pure

fn dot_dynamic(a: dyn NumericView, b: dyn NumericView) -> Result[f64, TypeError] ! pure
```

编译器在 `n build --target=x86-64-v4` 时可以实例化 AVX2/AVX-512 版本，并生成运行时能力选择器；选择器只负责一次分派，循环内部不能反复检查 CPU 特性。

### 14.6 明确不采用的设计

- 不承诺“所有程序都超过 C/Fortran”；性能必须由固定基准证明。
- 不把 `unsafe`、未定义行为或隐式别名当作常规优化接口。
- 不把量子、拓扑、意识或层论概念放进 CPU 核心语义；它们必须是可执行扩展。
- 不引入宏驱动的第二套语法；编译期生成统一产出 n-IR。
- 不默认全局多线程、隐式 GPU 传输、隐式引用计数或隐式数据复制。

### 14.0.6 多进制与低精度计算的外部启发

低精度研究给 n 的结论不是“所有 AI 都应使用三进制”，而是表示和算法必须共同优化：二值/三值权重可以显著减少存储和乘法；次 4-bit 的矩阵乘法收益常来自减少内存移动和 LUT，而不只是减少算术；FP8 的不同指数/尾数布局服务于不同动态范围；量化码本的误差还依赖 block size 和数据分布。因此 n 把 `RadixSpec + EncodingProfile + NumericContract` 放进 n-IR，让 profile 可测、可回退、可回放。

可迁移的原始研究包括：[Quantized Neural Networks](https://arxiv.org/abs/1609.07061) 的低比特权重/激活、[Ternary Weight Networks](https://arxiv.org/abs/1605.04711) 与 [Trained Ternary Quantization](https://arxiv.org/abs/1612.01064) 的三值权重、[LUT-GEMM](https://arxiv.org/abs/2206.09557) 的查表低比特矩阵乘，以及 [FP8 Formats for Deep Learning](https://arxiv.org/abs/2209.05433) 对 E4M3/E5M2 动态范围取舍的分析。它们只提供可验证假设，不成为 n 的硬件或模型依赖。

近期 NVFP4 研究还提示：block size、scale 粒度和 outlier 分组会直接改变量化误差；[OCGQuant](https://arxiv.org/abs/2609.00066) 将异常通道与低幅值 companion 重新分组，说明“同一 bit 数”不等于同一质量。n 因此把分组、scale、codebook 和 outlier 策略都放入 `EncodingProfile` 摘要，不能只记录一个 `bits_per_value`。

三值应作为 n 的重要候选而不是唯一基线：`Trit` 适合稀疏权重、门控、符号更新和事件状态；连续状态、累加器、梯度、概率校准和外部 ABI 默认保留更高精度或明确的低精度契约。多进制选择由 `adaptive-fastest` 在任务质量、误差、带宽、能耗、转换、编译和恢复成本共同约束下完成。任何 profile 若只节省 bit 数却增加解码、同步或回退成本，不得晋升。

## 15. AI-native 增补路线

AI-native 不是在传统语言完成后再附加 Agent 库，而是从 n-0.1 就验证“AI 直接产生 n-IR、机器执行、机器评价、机器晋升”的闭环。以下交付物与第 13 节版本对应；每一项都必须同时交付参考语义、失败路径和机器可读证据：

1. **n-0.1**：AI 直接生成 `.nib`，codec round-trip 与 verifier 拒绝错类型、错效果、越级 RealityTag 和非法 capability；参考解释器能执行最小 `observe -> delta -> commit`。
2. **n-0.2**：`RootEnvelope` 在启动时派生本地 `RootLease`；`Delta`、`Credit`、`CommitGate` 和 `version.*` 状态机可回放，热路径不依赖远程 root 查询。
3. **n-0.3**：`ProgramDelta` 增量验证、`cap`/`dyn cap`、所有权/借用、Allocator/arena/pool、效果和结构化诊断；`.n` 只是无损投影。
4. **n-0.4**：Tensor/View、布局/设备、多进制 `RadixSpec`/`EncodingProfile`、`comptime` 纯度与终止性、`parallel`/SIMD、x86-64 后端；参考解释器、n-Opt-IR 和机器码差分。
5. **n-0.5**：`AIState`/`Objective`、现实/预测/想象类型、`Tr`/Evidence、确定性 seed、Graph/EventStream、自动微分 n-IR 变换。
6. **n-0.6**：World/Dynamics/rollout、Learner/update、Agent 生命周期、retrieve/focus/route/judge/verify、工具 schema/授权和事件日志。
7. **n-0.7**：MemoryStore、Provenance DAG、持久 mailbox、因果异步多螺旋、耐久任务、受限委派和崩溃故障注入。
8. **n-0.8**：adapt@k、QD/open-ended、SNN、连续动力学、Diffusion/EBM/Equilibrium、跨范式转换和 PredictionSet 校准。
9. **n-0.9**：CounterfactualFamily、联合动作、StateEstimate、主动 QueryPlan、RoutePlan/CompensationPolicy、持续适应隔离和全成本测量。
10. **n-0.10**：EfficiencyObjective、多进制/低精度 `adaptive-fastest`、控制面/热数据面分离、PerformanceReceipt、RouteReceipt、影子/边缘流量和自动回滚。
11. **n-0.11**：状态迁移、事务热替换、C0->C1->C2 多阶段自举、父编译器/参考解释器/独立后端差分，以及 AI 生成 ProgramDelta 的稳定闭环。
12. **n-0.12**：ExecutionFabric、CPU/GPU/NPU/neuromorphic、异构放置、传输/collective/拥塞账本、故障域恢复和跨域 ABI。
13. **n-0.13**：CCTM 核心闭环：AI 生成 `ExecutionPlan`/`derive` 请求/`Approx[T]` 候选；参考解释器、优化 n-IR 和后端共同验证，残差超界自动回退，所有性能声明绑定完整摘要。
13. **n-1.0**：稳定 n-Core-IR、AI/Agent/RTST 语义、自治程序演化、标准库、跨后端回放、性能/自治完整性基准和可复现多阶段自举。

## 16. 从 Ω 和 tl 迁移

| 旧名称 | n 名称 |
| --- | --- |
| `Ω` | `n` |
| `omega run` | `n run` |
| `.omega` / `.tl` | `.n` |
| `Tensor`、`shape`、`layout` | 保留，纳入 n/Core |
| `seed`、`observe`、`fold`、`report` | 保留，按本规格收紧语义 |
| 无界 `fix` | 删除；使用结构化递归或 `fix@k` |
| 量子/拓扑/层论内建 | 改为 `n.quantum`、`n.topo`、`n.sheaf` 扩展 |

当前原型的 `tl` 文件和命令先作为兼容入口；实现迁移完成后，`tl` 只保留为兼容别名，并在 n-1.0 前给出弃用警告。

## 17. 已选默认值与重新开启条件

本节冻结 n-0.1 起的默认语义，避免每个后端各自“合理”却彼此不兼容。默认值是设计决策，不代表已有实现或已通过验证。实现未满足验收条件时必须拒绝、返回 `unknown`、保留候选状态或回退到参考路径，不得静默放宽语义。只有出现本节列出的反证或新需求时，才重新开启决策；所有改变都必须提升语义配置版本并进入程序摘要。

1. **n-IR 序列化：一份规范语义，两种编码。** 定义版本化的规范语义图；二进制 `.nib` 是 AI/编译器/运行时的主要交换、缓存和增量 patch 格式，文本 `.nir` 是无损可读投影，用于差异、诊断和检查，不进入性能关键路径。两者必须解码到同一规范语义摘要，摘要采用带算法标识的 SHA-256；编码版本、IR schema 和语义摘要都进入缓存键与回放记录。文本和二进制不是两套独立规范。若无法保持同摘要，拒绝缓存命中/回放，不猜测转换。只有确有无法由双编码满足的机器互操作要求，才重开格式选择。
2. **GPU 异步借用：借用随完成事件存活。** 设备内存借用绑定线性 `DeviceLease` 与完成事件；事件完成之前不得释放借用。跨函数传递必须把 lease/event 作为线性对一起转移，转移本身不解除等待义务；借用不得逃逸到无关区域或被 CPU/host 侧访问。取消只表示请求取消，不代表设备工作或副作用已经停止。无法证明生命周期时，插入等待/复制的完整性路径或拒绝编译。只有目标设备无法表达该生命周期且有等价的所有权证明时，才增加特化规则。
3. **浮点：`repro` 定义参考，`adaptive-fastest` 是默认执行。** `repro-v1` 对受支持的浮点格式采用 IEEE 754 roundTiesToEven、保留有符号零和次正规数、规范化可观察 NaN、禁止未声明的重排和收缩，并固定归约树与异常值传播规则；它用于参考解释、差分测试和需要逐位回放的区域。默认运行时在版本化 `NumericContract` 的容差、任务质量下限和目标设备能力内，自动选择最快的已验证 precision/reduction/contraction profile；不支持合格快速路径时回退 `repro-v1`。逐位复现只承诺在相同 n-IR、编译器、后端和 profile 下。任何快速 profile 都必须传播误差/质量 residual，越界时自动回退、回滚或拒绝晋升，不能静默改变语义。
4. **自动微分：稳定的是 n-IR 变换契约。** `n.autodiff` 表面 API 可演进；规范语义由版本化的 n-IR 变换定义。变换标识、版本、导数约定、非光滑点规则、精度 profile 和相关假设进入程序摘要及回放记录。未定义梯度的点必须显式报错或按声明的次梯度规则处理，不能由后端自行选择。只有新导数语义无法在新变换版本中表达时，才重开核心 API。
5. **`Tr` ABI：规范字节表示，内部表示自由。** 稳定 ABI 使用单字节位型：`0xFF = oppose (-1)`、`0x00 = unknown (0)`、`0x01 = support (+1)`；其他值为非法标签，解码必须拒绝。SIMD、张量和设备内可采用位打包，但边界转换必须无损、显式且通过差分测试。位布局不属于跨模块 ABI。只有实测表明字节 ABI 阻断目标硬件互操作，且可提供版本化等价 ABI，才重新讨论。
6. **`SequenceOperator`：规范顺序定义语义，计划定义实现。** 规范递归语义确定状态更新顺序和归约结果；parallel/chunk 只是执行计划。编译器仅在代数律和数值 profile 足以证明等价时自动替换，否则要求显式容差/近似契约并传播 residual，或使用规范顺序执行。状态布局留在 n-IR/后端契约内，不固化为 ABI。任何静默的重排、丢状态或改变提交顺序均为不兼容。
7. **`AdaptiveMemory` ABI：稳定句柄与策略，不暴露内部布局。** ABI 暴露 opaque handle、schema/version、容量上限、retention/eviction 模式、更新窗口和能力要求；具体索引、摘要结构及存储布局由实现决定。读写与测试时适应分别显式标记效果；长期晋升必须经过 `Delta`、保留集验证及 `CommitGate`，不得由一次读取或隐式后台写入触发。只有确有跨实现交换原始内部状态的需求，才引入有版本的导入/导出格式。
8. **求解器与随机流：版本化计数器流加数值 profile。** 随机数使用无全局隐式状态、可拆分和可重放的 `RngStreamV1`，规范生成器为 Philox4x64-10：key 为 128 位、counter 为 256 位，每块按固定 lane 顺序产出四个 64 位字，块计数递增；整数编码为 little-endian，counter 耗尽时报错。流是线性资源，抽样显式返回新 counter；`split` 不消耗父流，必须用稳定标签和序号分配给并行工作。`split(label, ordinal)` 的 SHA-256 输入依次为固定域分隔字节串 `n/RngStreamV1/split`、16 字节父 key、8 字节 little-endian label 字节长度、原样 UTF-8 label 字节及 8 字节 little-endian `u64` 序号，取摘要前 16 字节作为子 key、counter 从零开始。标签路径、key、counter、采样器版本及分布参数进入回放摘要。随机流不是密码学密钥或安全随机源。求解器必须声明容差、残差范数、最大迭代数、停止/失败条件和后端数值 profile。随机流相同不等于浮点输出跨设备相同；跨设备仅按误差契约比较。若采样器输出仍无法重放，回放返回明确不完整，不伪造确定性。
9. **`PredictionSet`：校准适用域是值的一部分。** 每个集合绑定校准方法/版本、数据域摘要、划分来源、目标覆盖率、样本量与漂移检测策略。域外、漂移超界或校准证据失效时，状态降为 `out_of_calibration`/`unknown`，不得作为已校准承诺或单独授权高风险动作。重校准产生新版本并重新验证。只有目标应用给出足以改变覆盖定义的统计假设时，才重开契约。
10. **多进制表示：采用表示层，不采用单一全局基。** n-IR 支持 2..256 的 uniform/mixed `RadixSpec`，以及 balanced ternary、低比特浮点、定点、log/posit 和 codebook 等 `EncodingProfile`；值语义、误差和外部 ABI 不随 profile 偷换。混合进制默认按 vector/block/axis 分组，不能在标量热循环中隐式变基；`Trit` 与认知 `Tr` 分离。profile 必须绑定 `NumericContract`、质量/误差界、转换成本、硬件 kernel、随机舍入和回放摘要，并由 `adaptive-fastest` 选择；不合格或未知 profile 回退 `repro-v1`。只有实测证明另一粒度能在同一语义和完整成本下稳定改善，才重新开启粒度/基集合。
11. **CCTM 计划与推导：计划先于执行，推导先于优化。** 所有非参考执行都必须选择版本化 `ExecutionPlan`，计划携带 `PlanProof`、`NumericContract`、监测和 fallback；所有 AD/影响/内存/误差/成本分析都从同一 `derive.request` 降级。无法构造兼容计划、误差界或完整回退时，返回 `unknown`、回退到参考计划或拒绝，不把后端猜测写入规范语义。

### 17.1 决策闭环

逻辑推理可以消除规格内部矛盾、推导类型/代数不变量、检查状态机可达性，并证明某个实现满足给定前提；它不能从逻辑本身推出真实硬件速度、模型在分布外的正确性或因果可识别性。n 不把数据流、外部副作用和资源边界表述成人的偏好：它们是 RuntimeRoot 的版本化机器契约，规定 AI 可用的执行空间；AI 的目标是在契约内最大化任务能力、学习进展和单位资源效能，并可提交经验证的 envelope/profile 改进候选。每项风险归入静态证明、运行时/故障协议、实证评估或 RuntimeRoot 不变量，并记录前提、失败回退与验收证据。

风险关闭的最小记录为：风险编号；可检查的不变量/触发条件；证据产物及其代码、n-IR、后端和数据集摘要；失败时的拒绝/隔离/回退行为；以及使结论失效、必须重新审查的条件。测试通过只关闭该版本、声明域和配置下的风险，不构成普遍正确性证明。缺证据即未关闭；在无法证明或测量时采用 fail-closed，不允许“待实现”被描述成语言能力。

## 18. AI-first 可执行实现蓝图

本节是实现顺序和最小可信边界，不表示当前目录已经具备这些组件。每个里程碑都必须在同一版本中保留参考路径；优化路径失败时回退到参考路径，而不是把失败解释为“模型不确定”。

### 18.1 最小可信核

第一批实现只需要六个不可替代组件：

1. `nib-codec`：规范语义图、`.nib` 二进制和 `.nir` 文本投影的双向编码，输出同一 schema/digest。
2. `ncore-verifier`：类型、效果、所有权、形状/设备、RealityTag、Delta 前置条件和 RootLease 局部不变量检查。
3. `reference-interpreter`：按 `repro-v1` 顺序执行 n-Core-IR；外部效果只产生 intent，不直接接触宿主。
4. `transition-store`：原子保存 `TransitionRecord`、Delta、EventLog、Provenance 和回放索引；重复提交按幂等键返回已有记录。
5. `root-loader`：加载 `RootEnvelope`，派生/撤销/续期本地线性 `RootLease`，并提供跨域边界回调。
6. `evidence-runner`：执行性质、差分、质量保留集和成本测量，生成不可被候选修改的 `AdmissionReceipt`。

这六个组件组成最小闭环：

```text
AI emits .nib/ProgramDelta
  -> codec + verifier
  -> reference-interpreter
  -> evidence-runner
  -> AdmissionReceipt
  -> version.transition + transition-store
  -> local RootLease execution
```

### 18.2 里程碑与退出条件

| 里程碑 | 实现内容 | 退出条件 |
| --- | --- | --- |
| M0 编码 | `.nib`/`.nir` round-trip、规范摘要、坏输入拒绝、`CorpusManifest`/`BenchmarkManifest` 固化 | 随机 IR 经过双编码后摘要相同；截断、重复字段和未知必填字段均拒绝；语料/基准摘要进入回放和报告 |
| M1 验证 | n-Core verifier、错误路径和结构化诊断、G9 正负例闭环 | 生成式 patch 不能产生悬垂 value、错效果、越级 RealityTag 或未声明外部效果；每个新增规则至少有可执行正例和负例，负例确实被拒绝 |
| M2 参考执行 | `observe`、纯 kernel、`Delta`、`transition.commit`、`repro-v1` | 解释器回放产生相同 state/event/provenance digest；外部副作用只停在 intent |
| M3 程序演化 | `ProgramDelta`、依赖闭包重验、`version.*` 生命周期 | 旧 base、并发冲突、错误 ABI 和失败迁移原子拒绝；当前 active 不被部分更新 |
| M4 单机后端 | x86-64 n-Machine-IR、一次能力选择、PerformanceReceipt | 参考解释器、n-Opt-IR 和机器码在声明容差内差分一致，含错误/取消路径 |
| M5 自适应最快 | profile、RoutePlan、precision/layout/device 候选、shadow/canary/rollback | 质量门槛、完整 CostVector 和评价 epoch 冻结；退化自动回滚，热循环无重复动态检查 |
| M6 自举织网 | C0->C1->C2、自举、ExecutionFabric、跨设备/故障域恢复 | 固定点不再是唯一证据；父编译器、参考解释器、独立后端、故障注入和跨 fabric 回放均通过 |

### 18.3 AI 编程接口的最小形态

AI 首先输出结构化操作，而不是文本：

```text
emit(operation, typed_inputs, expected_digests, objective_epoch)
patch(base_program, NirPatch, dependency_scope)
measure(candidate, workload, fabric, frozen_objective)
admit(candidate, AdmissionReceipt)
```

`emit` 和 `patch` 只构造候选；`measure` 不能修改候选的目标、评价器、计费口径或保留集；`admit` 只能通过 `version.transition` 提交。`.n` parser、IDE 和格式化器随后作为可替换的观察/互操作层接入，不能成为 AI 运行主路径的必经环节。

### 18.4 性能不变量

AI-first 不等于把检查全部删掉。可静态证明的检查应在 RTST 边界提升并从热循环消除；无法证明的检查保留在边界或回退路径。每个优化候选必须同时报告：纯 kernel 成本、控制面成本、数据移动/同步成本、编译与缓存成本、恢复成本、任务质量和能力进展。任何未知维度都保留为 `unknown`，不得按零计入 Pareto 排序。

## 19. RTM 0.40 基础实现

RTM 第一阶段已经在 `tl-lang` 中落地为独立模块：`n_front.py` 直接解析 `.n`
子集，`n_ir.py` 生成可 round-trip 的 NIR-RTM，`n_rtm.py` 实现
`Field -> Wave -> Echo -> Commit` 的 epoch/原子提交语义，`n_backend_tl.py`
提供参考后端和真实 `kernels.dll` 适配。旧 tl AST、VM 和回归脚本没有被新前端
依赖，因而后续可以替换兼容层而不改变 n-IR。

第一阶段的验收边界是 `add_scalar` 单 field workload：stale wave、echo fail、
unknown 和长度冲突都不能改变 field；成功提交才递增 epoch。后续 regime、局部
细化、异步 mailbox、多进制、GPU/NPU/CXL 和多目标 derive 必须复用同一提交边界，
不能另建旁路状态机制。性能结论仍只能来自绑定 workload 的 receipt。

`goal`/`synthesize` 也直接进入 NIR-RTM；规划器只处理有限候选和显式硬件要求，
不会通过隐式模型调用或改写目标来制造进步。`n_fabric.py` 的 CPU/GPU/NPU/CXL
探测与实际 executor 分离，缺设备时返回 `unavailable`。

### 20. n 统一编译器架构修订（2026-10-01）

旧 tl 的单体解释器、旧 AST 和按固定 kernel 名分派的 emitter 不再作为 n 的
目标架构。`.n` 由 n 自有 frontend/NIR 开始，经过摘要绑定的 `PlanManifest`，再由
n 自有目标 lowering 生成可执行机器码，最后进入同一个 RTM Echo/Commit 状态边界。
旧 tl 保留为兼容语言、历史回归和自举实验资产；它不是 n 的语义权威。

现阶段已经验证的只是一个窄纵切：Windows x86-64/SSE2 上 contiguous CPU `f64`
`add_scalar`。它从 n NIR 生成显式 buffer/effect/loop 的 n-LIR，再生成 packed-double
机器码、以 RW->RX 方式执行，并通过
reference exact Echo 后提交。计划 manifest 绑定 source/NIR/target/shape/type/
operation/fallback；测量回执增加 compile、backend init、verification、commit、
fallback 和 machine-code digest。Python 当前仍是过渡宿主，不能据此宣称 n 自举。

下一结构阶段是在扩大操作集或增加第二个实质 backend 前补齐通用 n-LIR，明确控制流、
内存效果、布局、数值契约、向量宽度、数据移动和回退边。`goal/synthesize` 的候选
指标目前仍为声明估值，未有真实工作负载的测量证据时不得驱动性能结论或晋升计划。
完整自研路线仍需完成 n-LIR/类型与效果检查、ABI/寄存器分配/目标文件、差分与性质
验证、真实硬件工作负载及可重放的自举链；GPU/NPU/CXL 仅有探测不等于执行器。

### 21. n 0.7 Unified Phased IR

#### 21.1 架构决策

0.7 合并 NIR 与 n-LIR 的**数据模型**，但保留 lowering 的语义阶段。唯一权威容器
为 `nIRModule`，编译路径为：

```text
nIR.semantic -> nIR.planned -> nIR.machine -> machine code
```

三个 phase 使用同一 value/type/shape/effect/region/provenance/digest 系统；阶段转换
通过 `RewriteDelta` 或持久化结构共享产生新 snapshot，而不是完整构造另一套节点图。
这样能减少编译器分配、复制、规范序列化和重复摘要成本，同时让一个 value 的契约
从语义层一直追踪到机器码。

这不是无阶段的“万能 IR”。每个 phase 只允许自己的 operation 集合：

| phase | 负责 | 禁止 |
| --- | --- | --- |
| `semantic` | Field/Wave/Goal/Contract/Delta/Echo/Commit、类型/效果/RealityTag | 物理寄存器、ABI offset、目标指令 |
| `planned` | layout/device/tile/vector/numeric/fallback/communication | 未绑定证据的性能晋升、具体物理寄存器 |
| `machine` | buffer/offset/ABI/register/target instruction/data move | 未解析 goal、隐式效果、丢失的契约/回退 |

`n_codegen_x64` 只消费通过 structural、semantic、phase 和 target verifier 的
`machine` snapshot。任何跨 phase 非法 operation、悬垂 value、效果缺失或摘要不匹配
都 fail-closed。

#### 21.2 RewriteDelta 与摘要链

每次转换记录 `parent_digest`、规则 id、受影响 value/region、旧/新摘要、verifier
摘要、成本和回退引用。未变化节点可共享 arena 存储；跨进程序列化仍输出完整规范
表示，不能依赖对象地址。摘要链至少为：

```text
source_digest
  -> semantic_digest
  -> planned_digest
  -> machine_digest
  -> code_digest
  -> result_digest
```

任一父摘要、目标能力、shape/layout、数值契约、效果或 objective epoch 改变，后续
manifest 和机器制品都失效。

#### 21.3 PlanManifest 不再是 IR

`PlanManifest` 仅保存选中的 planned snapshot、target/capabilities、placement、numeric
profile、schedule、verifier、fallback、benchmark 和 objective epoch 摘要。它不能
复制一套 operation graph，也不能把声明 cost/quality 冒充测量。`goal/synthesize`
只有在候选共享冻结 workload、硬件、目标和测量协议时，才可使用 receipt 晋升计划。

#### 21.4 性能结论

统一 IR 直接优化的是**编译器性能**：IR 分配量、峰值内存、重写、摘要/序列化和
缓存压力。它不会因“少一层”自动让最终程序更快。**生成程序性能**仍由最终指令、
布局、数据移动、同步、验证、回退和硬件决定，必须按绑定 workload 测量 p50/p99、
质量损失、搜索次数、回退率和完整 CostVector。

#### 21.5 已实现迁移边界

0.7 原生纵切已完成以下迁移：`NIRModule` 同时承载 semantic/planned/machine snapshot；
旧 `n-ir/rtm-0.1` 可无损读取并升级，旧摘要保存在 `legacy_digest`；`PlanManifest v2`
经两段绑定避免计划与模块摘要循环；planned 和 machine 由 `RewriteDelta` 串成父摘要
链；x64 权威 codegen 只接受经过 target verifier 的 machine snapshot。`LIRKernel`、
`lower_to_lir` 和 `lower_lir` 保留为兼容投影，差分测试要求新旧入口机器码逐字节相同。

当前 snapshot 仍会规范化复制映射，尚未实现 arena/持久化节点的物理结构共享，因而
“降低分配和峰值内存”仍是待基准验证目标。RTM Echo/Commit、旧 `.tl`、自举和历史
回归资产没有被本次迁移改写。现有证据只关闭 Windows x86-64/SSE2 contiguous CPU
`f64 add_scalar` 的 phase 链、拒绝路径和兼容差分；通用后端仍须扩展 verifier 与测试。

#### 21.6 2026-10-01 验证证据

- `python -m unittest discover -s tests -p "test_n_*.py" -v` 连续两次 44/44 通过；
- semantic/planned/machine 分别为 3/4/9 个 operation，rewrite count 为 2；
- machine 新 codegen 与 `LIRKernel -> lower_lir` 兼容入口的 code digest 相同；
- 非法 phase、重复 id、缺失 fallback、错误父摘要、错误 machine digest 和改变的
  objective epoch 均被 fail-closed 拒绝；
- Windows x86-64/SSE2 `rtm_add_one` 的 5 个测量样本提交成功、质量损失 0、回退率 0。

这些结果不证明统一 IR 已降低编译时间或内存，也不证明 n 普遍快于 C/Fortran；下一
证据项是对 0.50/0.7 的节点分配、峰值内存、冷/热编译和摘要成本做同机对照。

完整规范见
`docs/superpowers/specs/2026-10-01-n-0.7-unified-phased-ir-design.md`，实施计划见
`docs/superpowers/plans/2026-10-01-n-0.7-unified-phased-ir.md`。

版本说明：旧 tl v0.7 和此前路线表中的 n-0.7 仍是历史标识；本架构用全名
**n 0.7 Unified Phased IR**，旧 n-0.7 的 MemoryStore/多螺旋内容后移到 Agent/RTST
里程碑，不作为机器 IR phase。
