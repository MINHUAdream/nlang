# n 设计审查报告（Draft 0.15 Contract-Carrying Transition Machine）

审查对象：[N_DESIGN.md](N_DESIGN.md)

## 结论

设计已经从 Agent-native 扩展并重新定位为不依赖 LLM 的 AI-native n：n/AI 原生表达世界、状态、现实/想象、动力学、目标、学习、适应、时间、事件、种群和评估；n/Agent 是其上带信念、权限、行动和异步协作的特化。世界模型、元学习、开放式路线、连续动力学、SNN、选择性转换和反事实行动规划共享同一类型/n-IR 基底，而非形成彼此隔离的框架。当前仍是设计规格，不能等同于已实现、已验证的 AI 运行时。

本轮继续扩展了架构研究范围：新增 Diffusion、Graph Networks、Memory-Augmented/Titans、RWKV/RetNet/Hyena、Test-Time Training、KAN、Deep Equilibrium、Perceiver IO、Energy-Based Models 和 Conformal Prediction；并补充 MLIR/StableHLO、Halide、Triton、Futhark、Dex、Lean/F*/Dafny、Pony、Roc/Unison 的语言与编译器启发。它们均被重构为 n 的状态、时间、索引、资源、效果、预算、溯源和验证契约，没有被直接变成一组互相冲突的核心模型 API。

自动微分的定位也已收敛：`n.autodiff` 提供表面 API，AD 是 n-IR 的规范编译变换，不是独立效果；规则、搜索、SNN 局部可塑性、进化和采样可以不使用梯度。

本轮进一步合并重复机制，确定 n 的独有路线为 RTST（Reality-Tagged State Transition）：现实标签、Delta、TransitionContract、CommitGate、线性 Credit、选择性转换、反事实转换族和三种可重放视图（EventLog/Provenance/Evidence）共同组成 n 的核心，而不是继续增加模型专用 API。World/Dynamics/StateSpace/SequenceOperator 统一为 `TransitionKernel` 特化；所有更新/增量/补丁统一为 `Delta[D,T]`。

本轮把九项悬而未决的跨平台语义定为 n-0.1 起的默认值：规范 n-IR 双编码、事件绑定的 GPU lease、`repro-v1` 参考语义与 `adaptive-fastest` 默认执行、n-IR 自动微分契约、字节稳定 `Tr` ABI、顺序参考语义、opaque `AdaptiveMemory` ABI、可拆分计数器随机流和带适用域的 `PredictionSet`。它们关闭的是设计选择，不是实现风险；具体验收和重开条件见 [N_DESIGN.md](N_DESIGN.md) 第 17 节。

决策原则是“能证明的写成不变量，不能证明的写成带边界的实验，AI 在机器契约内自主优化”。n 面向自主 AI 而非人类编程体验优先；AI 效能按任务质量/能力进展、延迟、计算、内存、能耗、通信和覆盖联合度量。数据流、资源和外部副作用不是宿主偏好，而是 RuntimeRoot 的版本化执行不变量；AI 可在 envelope 内自行选择策略并提出升级候选，不得自授根权限。不新增风险引擎：沿用 RTST 的契约、效果、证据与提交门，把风险连到检测、回退、证据产物和重开条件。逻辑不能代替性能实测、分布外检验或因果识别。

Draft 0.14 在此基础上把机器 IR 和统一制品生命周期前移：n-0.1 先交付 `.nib/.nir`、n-Core verifier、参考解释器、TransitionStore 和 RootLease loader；`.n` 是无损投影而非 AI 的必经入口。`ArtifactVersion` 与 `version.*` 状态机统一参数、策略、程序、编译器、路由、放置和记忆 schema 的 shadow/canary/active 生命周期，rollback 作为 DeploymentBinding 的原子切换，避免每个子系统再发明上线机制。此前 Draft 0.12 的 `repro-v1` 参考、`adaptive-fastest`、RTST 控制面/热数据面分离仍然保留；优化候选可以自动生成、影子验证、晋升和回滚，但不能改写评价自己的 Objective、计费口径或保留集。

本轮对照《Resona 0.4.2 / R19 收尾设计文档》完成自检。可迁移的是工程纪律，不是“场/波/纠缠”本体论：n 吸收了语义主权四件套、G9 语料单源、负例优先、私有报告构造器、pending 概念延迟准入、显式效果契约和局部时钟边界，并全部降级到既有 `n-IR + Delta + AdmissionGate + EventLog`。报告中的 `pass`/`admitted` 现在明确只表示绑定语义、语料、基准、适用域和资源前提下未发现违规或满足门槛，不表示真实世界真理。

本轮进一步收敛 n 的独特优势为 **Contract-Carrying Transition Machine（CCTM）**：模型、Agent、张量内核、设备搬运、学习更新和分支合并都统一为带契约的 `Transition`。新增的三项核心不是旁路机制：`ExecutionPlan` 是 `ArtifactVersion` 的一等计划值，`derive` 是从同一 n-IR 生成梯度/影响/内存/误差/成本分析的唯一编译器原语，`Approx[T]` 是携带误差界、监测和精确回退的数值值。它们最终仍降级为 `TransitionContract + Delta + Credit + CommitGate`。

计划的 `PlanProof`、`FallbackPolicy`、`PlanMonitor` 和 `PlanReceipt` 使自动优化从后端黑魔法变成可回放语义；`BenchmarkBinding` 强制绑定源码、n-IR、编译器、运行时、硬件、基准和结果摘要。缺少摘要、误差界、兼容回退或独立裁判时，候选只能回退、隔离或拒绝。

CCTM 自检结论：

| 检查项 | 结果 | 保留的边界 |
| --- | --- | --- |
| 执行计划是否真正一等化 | 通过设计闭合：`ExecutionPlan` 是 `ArtifactVersion` payload，计划选择/执行/监测/回退均有 n-IR 操作 | 尚需实现 plan codec、计划证明检查和安全点切换测试 |
| `derive` 是否与 AD/影响/内存/成本分析重复 | 已合并：领域 API 统一降级为带 `DeriveTarget` 的 `derive.request` | 只有 `exact`/`bounded` 且有证据的推导才能驱动提交；启发式只能生成候选 |
| 近似是否可能伪装精确 | 已封闭：`Approx[T]` 不可隐式转为 `T`，必须带残差和兼容 fallback | 仍需验证跨设备、混合精度、随机舍入和 fallback 崩溃恢复 |
| 分支/合并是否新增旁路机制 | 未新增：复用 `BranchSnapshot + Delta + CommitGate + EventLog` | 仍需压力测试 fan-out、merge conflict、credit 守恒和共享前缀缓存 |
| 基准是否可归因 | 已封闭：`BenchmarkBinding` 绑定七类摘要并记录编译/调度/移动/回退口径 | 当前 tl 原型历史性能记录仍不能替代新绑定格式的实测 receipt |

自检还发现一个此前未被统一表达的类型债务：`CostUnit` 不能阻止同单位但不同语义的量相加。Draft 0.14 增加 `UnitTag`、`SemanticTag` 和 `Quantity[U,S,Rep]`；加减要求单位与语义标签同时相同，转换必须携带版本化校准，乘除只能使用验证器认可的量纲代数。它是类型层约束，不是新的运行时或权限机制。

附件自身的反例也纳入边界检查：

| 附件主张 | 自检结果 | n 的处理 |
| --- | --- | --- |
| 因果必须是 DAG，但示例存在 `thought -> memory -> thought` 反馈 | 语义冲突；反馈可作为时间展开图，但不能仍声称原图无环 | n 用事件 DAG 记录因果历史；反馈必须有逻辑时间、步数/credit 上限和 `EventCycle` 检查 |
| `Obs` 免费 | 容易漏计传感器、网络、存储和日志成本 | n 允许透明观察不增加权限，但完整 `CostVector` 仍计量采集、传输、保存和重放成本 |
| 效果声明“不推断” | 若只查直接调用，间接调用/高阶值可能漏报 | n 保留显式声明作为契约，同时要求调用图闭包检查；推导结果只用于诊断，不得放宽声明 |
| 线性只覆盖 `Coupled/NESS` | 复合类型和部分消费规则仍未封闭 | n 将其列为 verifier 风险；未证明的复合线性操作拒绝或降级到非线性值，不宣称已安全 |
| `PASS` 是审计通过 | 容易被读成“真理已证” | n 的 `EvaluationReport`/`AdmissionReceipt` 绑定范围、前提、裁判和回退；`pass` 不产生真实性标签 |
| 概念票据 pending/redeemed | 可作为治理记录，但若另建运行时票据会与版本/准入重复 | n 将其投影为 `Candidate`/`ArtifactVersion`/`CorpusEntry`，不新增票据机制 |

实现状态也做了独立复跑核验：规范 Markdown 的围栏计数平衡，新增治理/量纲定义各自唯一；但当前 `python -X utf8 run_v13.py` 未通过，因为旧回归链在 `run_v12 -> run_v11` 处失败，`run_v11` 报告 large 模型逐位一致失败并继续暴露更早版本回归失败。普通 Windows 默认编码还会使 `run_v12.py` 的子进程读取触发 `UnicodeDecodeError`。这不由本轮文档改动引起，却意味着 README 中历史的“全部 exit=0”只能作为历史记录，不能作为当前实现证明；在修复回归链前，n 的实现状态应标为 `open`/`reopened`，而不是 `verified_in_scope`。

AI-first 还延伸到语言自身：AI 可直接生成规范 n-IR，并用带基线摘要的 `ProgramDelta` 修改程序、编译器与运行时；候选经父版本验证、多阶段自举、差分语料、影子执行和安全点热替换后才成为当前版本。CPU/GPU/NPU/neuromorphic/内存/网络被统一为 `ExecutionFabric`，放置、传输、collective、拥塞和故障恢复都进入 IR 与成本账本。上述能力全部复用 Delta、CommitGate、Credit 和 RTST，不另建不可审计的“自我修改后门”。

此前 Draft 0.13 进一步把“可进化”统一成 `ArtifactVersion[T]` 和 `version.*` n-IR 原语：参数、Reasoner、策略、程序、编译器、路由、放置、记忆 schema 和 Objective 共用 proposed -> verified -> shadowed -> canary -> active -> degraded/retired 生命周期；rollback 是原子切换 DeploymentBinding 的转换，而不是第三种制品状态。RuntimeRoot 在边界派生本地 `RootLease`，热数据面不远程查询 root；租约失效、依赖摘要漂移或证据不足时，候选只能拒绝/隔离/回退。这样机器自治的快路径、版本演化和安全边界都落在同一 TransitionContract，而不是为“上线”“训练完成”“热替换”各自增加机制。

本轮加入多进制数值层：`RadixSpec`、`EncodingProfile` 和 `NumericContract` 将二进制、平衡三进制、低比特浮点、定点、LUT/codebook 与 mixed-radix 统一为可验证表示候选，而不是新增一套数值语义。依据低比特/三值网络和 LUT/FP8 研究，n 把内存移动、解码、误差、累加器、转换与能耗纳入完整 `CostVector`；`Trit` 与认知 `Tr` ABI 分离，profile 失败回退 `repro-v1`。

对近期 NVFP4 工作的补充核验表明，block size、scale 粒度和 outlier 分组是语义/性能共同的变量；n 不允许把 `bits_per_value` 当作足够的 profile 身份，而要求把分组和 scale 策略绑定进摘要。这里引用的是研究论文提出的可测试假设，不是对所有硬件的性能承诺。

本轮还把“灵光式结论”写成 `ExplanationMode`/`ReasoningReceipt`：trace 不再是所有推理的硬性输出，AI 可在内部搜索和低风险控制中直接返回 `result_only`；提交现实状态、外部行动或新版本时仍按风险策略要求机器证据，而不是要求自然语言解释。这样放宽的是可解释性成本，不是完整性门槛。

## 附件核验与可迁移启发

对附件和本轮扩展检索中的代表论文，已通过官方 arXiv API 核对标题、版本和摘要；TD-MPC2、脉冲预测抑制等还核对了记录中的会议/期刊备注。很多 2026 条目仍是预印本，原文元数据不等于同行评审或独立复现。下面只提炼可测试的设计假设，不把论文模型、性能数字或“最佳”结论写成 n 的承诺。

| 原文 | 可迁移到 n 的问题 | n 的重构 |
| --- | --- | --- |
| [NSA 2502.11089](https://arxiv.org/abs/2502.11089) | 稀疏路径从训练/转换语义开始成立，而不是事后剪枝 | 选择性 `TransitionKernel`，计划与状态契约一起编译 |
| [InfLLM-V2 2509.24663](https://arxiv.org/abs/2509.24663) | 长短输入切换要减少结构扰动并保持兼容 | `CompatibilityContract`，不兼容计划拒绝替换 |
| [Prism 2602.08426](https://arxiv.org/abs/2602.08426) | 粗粒度摘要可能损失局部/高频结构 | `semantic/structural/temporal` 三类质量分数 |
| [Flux Attention 2604.07394](https://arxiv.org/abs/2604.07394) | 路由粒度和内存访问决定墙钟收益 | `RouteGranularity` + 多维 `CostVector` |
| [Dream-RSI 2609.14858](https://arxiv.org/abs/2609.14858) | 用历史树离线评估探索策略，探索与执行分离 | `ExplorationTree` + `dream` 只产生 Candidate |
| [The Last AI Built by Humans 2609.11873](https://arxiv.org/abs/2609.11873) | 自主改进存在能力阶梯，不应一次开放递归自改 | `CapabilityLadder` + 分级 `CommitGate` |
| [CEDAR 2609.07237](https://arxiv.org/abs/2609.07237) / [CompKV 2609.26300](https://arxiv.org/abs/2609.26300) | 选择必须和残差/补偿联合设计，固定预算会浪费或丢信息 | `CompensationPolicy` + `ErrorBound` + fallback |
| [RouteRelay 2609.07306](https://arxiv.org/abs/2609.07306) / [Pareto Atlas 2609.17863](https://arxiv.org/abs/2609.17863) | 路由元数据可复用，但必须检测漂移；优化应看 Pareto 前沿 | 路由缓存失效契约 + 质量/延迟/成本联合验收 |
| [DreamerV3 2301.04104](https://arxiv.org/abs/2301.04104) / [TD-MPC2 2310.16828](https://arxiv.org/abs/2310.16828) | 想象 rollout 可以服务策略评估；隐式潜空间模型也可用于局部规划 | 保持 `Imagined` 隔离；规划报告 horizon、误差、成本和真实回测，不限定生成器或 RL 算法 |
| [V-JEPA 2 2506.09985](https://arxiv.org/abs/2506.09985) | 未来状态可在潜表示空间预测，不必重建每个观测像素 | `Latent[T, Schema]` 可成为预测目标，但 grounding/决策契约仍需可观测证据；不吸收其 LLM 对齐部分 |
| [Titans 2501.00663](https://arxiv.org/abs/2501.00663) | 长期历史需要可学习的记忆，而非无限扩大精确上下文 | `AdaptiveMemory` 可存有界、可版本化的状态摘要，更新沿用 `MemoryUpdate`/`Delta` 并保留遗忘与重放报告 |
| [OneWorld 2609.30946](https://arxiv.org/abs/2609.30946) / [I Act Therefore I Am 2609.31161](https://arxiv.org/abs/2609.31161) | 不同动作的未来必须受共同机制/不变量约束；准确预测本身不证明因果识别 | `CounterfactualFamily` 共享 base/kernel/world contract；报告干预覆盖和动作可区分性 |
| [MA-WAM 2609.31281](https://arxiv.org/abs/2609.31281) / [NeSyAM 2609.25766](https://arxiv.org/abs/2609.25766) | 联合行动有交互效应；局部观测缺失时动作前置条件仍可能不确定 | 默认显式 `joint` action；状态估计保留历史、缺失项和 residual，因子化须有验证契约 |
| [Brain-Inspired Hierarchical Modularity 2609.25146](https://arxiv.org/abs/2609.25146) | 持续经验要隔离冲突更新，同时组合兼容的模块 | 复用 Delta 域、`reject_on_conflict`、Candidate 与多样性档案，避免单一参数/策略被新任务覆盖 |
| [Predictive Suppression Layers 2609.21583](https://arxiv.org/abs/2609.21583) | SNN 通信也有冗余；预测残差可驱动事件筛选 | 事件路径复用 RoutePlan/CompensationPolicy，残差超界恢复更完整事件；实测通信和硬件能耗 |
| [ActiveArena 2609.24124](https://arxiv.org/abs/2609.24124) | 主动感知需评估多轮取证、记忆维持和分布外视角，而非只测被动识别 | 用现有 `QueryPlan`/`focus` 选择下一观察，统一记录信息价值、预算和后续任务成效 |
| [An Information-Theoretic Definition for Open-Ended Learning 2606.08369](https://arxiv.org/abs/2606.08369) | 开放式增长需要可度量，不应把新颖候选数等同能力增长 | 将 bit-equivalent 保留为实验指标候选，并与覆盖、迁移、保持和单位预算收益联合报告 |
| [XLOG 2609.27203](https://arxiv.org/abs/2609.27203) | 符号推理/概率推理可共享类型化数据平面，但执行边界与认证要求不同 | n-IR 允许精确/采样路径分层，结果携带证明/误差和传输账本；不要求 CUDA 或特定逻辑引擎 |

因此，论文共同带来的启发是：n 应围绕“行动前比较反事实、观察不足时保留未知、更新冲突时隔离、资源受限时按质量/成本选择”建立原生转换契约，而不是把 Transformer、LLM 或任一论文模型变成语言本体。

## 本轮发现与修复

| 风险 | 原问题 | 修复 |
| --- | --- | --- |
| 工具能力伪造 | `Agent.tools` 是普通字段，可能被数据伪造 | 能力由 RuntimeRoot 按 `RootEnvelope` 派生为线性 `ToolCapability`；Agent 只保存 `ToolScope` |
| 行动重放 | `commit/act` 没有一次性票据，崩溃重试可能重复副作用 | `authorize -> ActionTicket -> execute`；票据绑定 nonce、幂等键、输入摘要和预算 |
| exactly-once 过度承诺 | 语言无法控制外部系统事务，且能力可能在运行时动态绑定 | 增加 `at_most_once/exactly_once/replay_only`；静态能力要求类型约束，动态能力在 authorize 时验证，不支持则拒绝 |
| Agent 原生性不足 | `infer`/`Judge` 强制接收外部模型，实质仍是给 LLM 包语法 | 删除核心 `ModelSnapshot`/`model` 效果；认知由 n 的规则、约束、搜索、规划和证据代数实现，LLM 不进入标准运行时 |
| 把 Agent 当成全部 AI | 语言定位只覆盖信念/工具循环，世界建模、学习、连续时间、进化和事件计算只能退回外部框架 | 增加规范 n/AI 层；Agent 改为 AIState/World/Dynamics/Objective/Learner 之上的特化 |
| 模型动物园膨胀核心 | 为世界模型、元学习、SNN 等分别内建语法会制造冲突和不可维护语义 | 只内建状态、时间、现实标签、学习更新、事件、种群和验证轴；具体算法放标准模块 |
| 想象冒充现实 | rollout/预测结果若与观察同类型，可能直接成为行动依据或证据 | 引入 `Observed/Predicted/Imagined/Counterfactual`，禁止隐式提升；授权前需 grounding/约束/风险验证 |
| 学习静默自修改 | 元学习或在线学习直接改写正在运行的策略，回放、回滚和权限边界失效 | `adapt/update` 产生版本化 `Candidate`；evaluate/verify 后凭 PromotionCapability 晋升 |
| 开放式搜索无边界 | “open-ended”被误解为无限运行、无限生成环境或候选继承 RuntimeRoot 根能力 | Population/WorldGenerator/QDArchive 全部受预算、隔离域、谱系和 capability 衰减约束 |
| SNN/连续时间不可重放 | 浮点事件排序、隐藏求解器步长和零延迟环会让结果依赖后端 | 定点/逻辑 EventTime、同 tick 规范批次、EventCycle、显式 solver/容差/最大步数 |
| 来源丢失 | `Evidence` 只有一个 `SourceId`/平面来源集合，无法保留判断和融合派生路径 | 改为规范化内容寻址 Provenance DAG，并投影来源集合供筛选 |
| 未知与冲突混淆 | `Tr=0` 同时表示无证据和正反冲突 | 增加 `status = no_evidence/conflict/directional`，`Tr` 只作为投影 |
| 重复证据放大/顺序依赖 | 只去重来源集合，重复转发仍会重复累加 support/oppose | `Evidence` 保留唯一原子集合；按固定策略快照重新投影，冲突 ID 报错，集合并集提供可测试的交换/结合/幂等律 |
| 融合不可并行 | 未声明结合律/交换律就自动重排 | `FusionPolicy` 显式声明 `associative/commutative/idempotent` |
| 预算不可控 | 只有一个抽象预算，无法覆盖推理、时间和工具次数 | 分成 steps、bytes、compute、time、tool_calls；授权先锁定最坏情况，执行后结算 |
| 记忆无限增长 | Agent 记忆等同于无界日志 | 增加 retention、max_bytes、compact；压缩保留摘要、事件 DAG 根和 residual |
| 提示注入/不可信输入 | 外部文本或 schema 合法的工具结果可能改变权限或策略 | 外部输入默认为 `Untrusted[T]`；schema 校验不去除污点，也不能授予能力或预算 |
| 回放边界不清 | “可重放”可能被误解为重新执行现实世界 | 增加 strict/simulate/audit 三种 ReplayMode；外部工具只使用记录结果 |
| n-IR 不完整 | 判断、委派任务和副作用日志缺少规范 IR 操作 | 增加 authorize、judge、task、effect intent/result、provenance 和 event 操作 |
| 判断黑盒化 | 判断过程只有自然语言描述，问题边界、规则版本和派生路径不可审计 | 增加版本化 `Question`、类型化 `Decision[T]`、`ReasonerDigest`、`InferenceTrace` 和 `judge/decision` n-IR 操作；行动仍必须经过 authorize |
| 置信度误读 | Reasoner 分数被当作概率或真实性证明 | `confidence` 必须由 `EvidencePolicy` 解释；`unknown/conflict` 不得折叠为 `false`，并加入校准和未知率基准 |
| 溯源过于平面 | 只有来源集合，无法说明哪个判断/融合活动使用并派生了哪些证据 | 采用内容寻址 Provenance DAG，表达 Entity/Activity/Agent 及 used/generated/derived/attributed 关系；保留图根摘要和压缩策略 |
| 结构校验误作信任 | schema 合法的工具或外部输入可能仍含恶意指令或错误事实 | `Untrusted[T]` 贯穿 schema 校验；结构正确不自动改变完整性标签，也不能赋予权限 |
| 长任务语义缺失 | `fuse` 被误当作 Agent 通信，跨进程任务没有状态、取消、续问和制品语义 | 分离 `AgentTask` 与 `fuse`；委派使用限权/限预算/限时 grant，协议适配位于 `n.agent.protocol` |
| 副作用崩溃窗口 | 外部动作成功后、结果日志写入前崩溃，重放可能重复执行 | 增加 effect intent/result 和稳定 EffectKey；无法确认时显式 `outcome_unknown`，只在外部幂等协议下自动重试 |
| 旧任务升级歧义 | 事件 schema、n-IR 或程序升级后旧日志可能被新语义错误解释 | 记录 event schema/n-IR/program digest；旧历史必须使用显式、可测试的 replay adapter |
| 全局 barrier 限制异步影响 | epoch barrier 迫使快分支等待慢分支，无法及时把发现反馈给仍在探索的分支 | 默认改为持久 causal mailbox；消息提交后异步投递，接收方在下一个安全点显式 receive；`round_sync` 仅为可选模式 |
| 异步调度改变结果 | 因果就绪不等于处理器合流，不同消息分批可能产生不同计划和分支输出 | `causal_async` 仅接受编译器可从受限 delta/半格形式证明合流的处理器；否则使用 watermark 驱动的 `ordered_async` 或 `round_sync`，实际顺序写入事件 DAG |
| 主干合并丢失更新 | 分支基线过期后按最后写入者覆盖会丢掉另一分支的结论 | 每个分支绑定 `base_event`；主干前进后必须 rebase、产生 `MergeConflict` 或继续只读探索 |
| 异步互相强化 | 分支循环引用彼此的结论会制造“多数共识”假象和无限回归 | MessageId/EvidenceId 去重、依赖组限额、显式最大状态转换数与新颖度门槛；quiescent 不等于事实证明 |
| 并行效率虚高 | 只报告更短墙钟时间会掩盖更多计算/通信消耗或搜索覆盖率下降 | 同时报总成本、消息量、墙钟时间、覆盖率和质量；显式分支预算、调度公平和早停策略 |
| 分支消息误入主干 | peer 启发可能被误当作已接纳事实，或同一增量因双路投递被算两次 | 消息显式声明 peer/trunk 范围；主干只接纳策略许可的增量，`peer_and_trunk` 不产生独立证据 |
| 异步交付丢失或重复 | 分支崩溃可能发生在状态提交、cursor 前移和消息发送之间 | 状态、cursor、durable outbox 原子提交；消息按 MessageId 至少一次投递和幂等消费 |
| 分支爆炸与同质化 | 无上限 fan-out 浪费预算；只按单一收益分数调度会过早收敛到同一假设 | `BranchPolicy` 限定 fan-out/状态转换数/在途消息量/预算；为不同假设保留探索预算，按边际收益调整分支数 |
| 异步系统假收敛 | 暂时无消息不代表没有在途工作，可能过早结束 | 用线性 `WorkCredit` 和 durable 队列检测全局 quiescence；预算耗尽保留 pending mailbox |
| 背压导致丢消息或停不下来 | mailbox 满时丢数据会破坏证据，控制消息与数据共用通道会让取消被堵塞 | publish 显式 await/`Backpressure`；控制通道保留容量；取消进入 draining 并归还 WorkCredit |
| 照搬 LLM 机制 | attention/MoE/RAG 名称可能把 Transformer 和预训练权重重新引入核心 | 只重构为可审计的 `focus/route/retrieve/verify`；禁止把 tokenizer、prompt、next-token 或 LLM 服务作为标准语义 |
| 测试时学习污染长期状态 | TTT/Titans 一类方法若把在线窗口写入全局记忆，会造成数据泄漏、不可重放和隐式自修改 | `test_adapt@k` 只写隔离 `AdaptiveState`；长期记忆和策略更新必须经过 `evaluate -> verify -> promote`，并记录窗口、损失、预算和回滚点 |
| 隐式平衡求解不收敛 | DEQ/隐式层可能不收敛、存在多解或反向梯度不稳定 | `EquilibriumState` 必须携带残差、容差、最大迭代、solver 版本和 `ConvergenceCertificate`；失败返回 `SolverError` |
| 生成/能量分数被当作事实 | Diffusion/EBM 的样本或 energy 只是生成结果/排序值，不能直接成为证据或概率 | 增加 `Generated[T]`、`EnergyFunction`、`SamplerPolicy`；seed、噪声日程、温度和收敛报告进入 provenance，现实提升仍需验证 |
| 长序列执行计划漂移 | RWKV/RetNet/Hyena 等 parallel/recur/chunk 实现若只按性能切换，可能改变状态边界和浮点结果 | 统一 `SequenceOperator`；计划切换须证明同一状态转换、归约顺序和浮点模式，并写入 n-IR 摘要 |
| 不确定性承诺外推 | Conformal coverage 依赖校准域，分布漂移时不能继续宣称覆盖率 | `PredictionSet` 搭配 `CoverageContract`/`CalibrationReport`；域外或失配降级为 `unknown/out_of_calibration` |
| 编译器方言膨胀 | MLIR、GPU DSL 和 array language 的概念若直接进入核心，会造成多套 lowering 和隐藏成本 | 只吸收多级 IR、算法/调度分离、tile、唯一性和验证器；所有扩展先降级到 n-Core-IR 并通过参考解释器/差分测试 |
| 现实标签重复实现 | Observed/Predicted/Imagined/Generated/Counterfactual/Validated 各自做包装，导致转换规则和 ABI 重复 | 统一为 `Tagged[T, RealityTag]`，可读名称只是别名；`validate`/`ground`/`promote` 是唯一标签门，只有带 `GroundingReport` 的 `ground` 结果能进入现实 Evidence |
| 更新机制重复且互相覆盖 | StateDelta、BeliefDelta、EvidenceDelta、TrunkDelta、MemoryUpdate 各自定义 patch/merge，容易出现不同冲突规则 | 统一为 `Delta[D,T]`，显式 `base/precondition/merge_law`；所有领域更新先产生 Delta，再由 `transition.commit` 提交 |
| 状态模型重复 | World、Dynamics、StateSpace、SequenceOperator 分别拥有生命周期、缓存和重放逻辑 | 统一 `TransitionKernel[Input,State,Output,TimeDomain]`；差异只保留 schema、时间域和 solver |
| 事件/来源/证据重复记录 | EventLog、ProvenanceGraph、Evidence 可能各自复制输入和派生历史，产生不一致摘要 | 统一引用一个 `TransitionRecord`，三者只是时间、因果和证据投影，不能互相替代 |
| 晋升与授权边界混淆 | `promote`、`authorize` 都像 commit，但一个改变内部版本，一个产生外部副作用 | 统一 `CommitGate` 接口，分为 `AdmissionGate` 和 `ActionGate`；共享检查契约但禁止共享副作用语义 |
| 预算与并行 credit 重复 | Budget 和 WorkCredit 都在表达“有限资源”，却可能各自铸造/扣减 | 统一线性 `Credit[D]` 和 `CreditLedger`；BudgetToken/WorkCredit 是不同领域特化，必须守恒、拆分、转移、归还 |
| pure 与学习/记忆冲突 | “学习是状态转换”与“函数默认 pure”容易把返回新 Candidate 和持久晋升混为一谈 | 返回新值的 `update/adapt/fuse` 可以 pure；写入持久状态/记忆/版本/事件分别声明 `! state/memory/learn/event` |
| 记忆 API 重复 | `Memory`、`WorkingSet`、`EpisodicMemory`、`AdaptiveMemory`、KV cache 和外部记忆各自定义读写/保留规则 | 统一为 `MemoryStore[K,V,Mode]`；差异只在模式、地址、容量和 retention，所有写入都产生 `MemoryUpdate` Delta |
| 状态提交边界模糊 | kernel 返回 next state、Delta 和持久提交同时存在时，仿真可能偷偷改变现实状态 | kernel 只返回 tagged output + `StateDelta`；`transition.commit` 才提交，`TransitionRecord` 记录 prepared/committed/outcome_unknown |
| Delta 与效果脱节 | 若任意函数都能直接提交 State/Memory/Learn/Event Delta，纯计算和持久副作用会重新混在一起 | `transition.commit` 按 Delta 域自动要求 `! state/memory/learn/event`；纯代码只能构造/验证 Delta |
| 稀疏收益被路由开销吃掉 | 只看省下的内核计算，会忽略选择器、压缩、回填、同步和缓存维护 | `RouteReceipt` 记录路由本身的 `CostVector`；验收同时看质量、延迟、总成本、带宽、同步和能耗 |
| 硬选择不可恢复 | 被省略的单元可能包含低频、局部、时间或拓扑关键信息，错误会在后续状态中放大 | 非空 `omitted` 必须带 `CompensationPolicy`、误差界或精确回退；语义/结构/时间质量分开校验 |
| 路由器系统性偏差 | 代理分数可能长期饿死少数模式或把可量化但不重要的路径排在前面 | 保存 `structural/semantic/temporal` 三类指标，保留探索配额、近失候选和周期性全量审计 |
| 路由元数据陈旧 | 跨层/跨步复用的选择结果可能已不适用于新状态或新设备 | 缓存绑定输入依赖、版本、有效期、失效条件和源 `TransitionRecord`；失效时回退并记录原因 |
| 优化破坏原语义 | 稀疏/量化/设备计划可能改变 schema、状态 Delta、随机流或错误行为 | `CompatibilityContract` 作为计划替换前置条件；不兼容时只能显式降级或拒绝 |
| 离线探索奖励漏洞 | Dream/RSI 可能在回放树里优化代理指标、重复旧路径或利用评估缺口 | `ExplorationTree` 只产生候选；信息增益、相关性、保留集、预算和 `AdmissionGate` 缺一不可 |
| 自主等级越权 | “能改进策略”可能被误解为能直接改权限、工具或现实状态 | `CapabilityLadder` 为每级绑定可写 Delta 域、预算、回滚点和 ActionGate；越级提交编译/运行时拒绝 |
| 多个未来各自合理却彼此矛盾 | 从同一观察独立生成的动作分支可能隐含不同物理规律，预测分数掩盖了反事实坍塌 | 增加共享 base/kernel/world contract 的 `CounterfactualFamily`；比较干预覆盖、动作可区分性和已验证不变量 |
| 多 Agent 动作被错误拆分 | 同时动作存在协同/抵消，单体模型逐个 rollout 再相加不能代表联合转移 | `ActionChoice.joint` 是默认联合接口；factorized 执行必须携带经验证的 `FactorizationContract` |
| 被动观察假设过强 | 快照可能缺少历史上下文，机器人也可能需要移动/检索才能消除关键未知 | `StateEstimate` 保存 history/observability/residual；主动观察复用 `QueryPlan`/`focus`，返回前仍不是 `Observed` |
| 持续更新互相干扰 | 在线经验可能覆盖旧能力，或独立模块未经兼容检查就被拼接 | 更新继续用 `Delta`；冲突域隔离并保留候选，兼容合并经过旧任务回归与保留集 |
| 新颖度冒充开放式能力 | 规模更大的 archive 或更高 novelty 可能只是重复、不可迁移或高预算产物 | 报告任务/行为覆盖、跨环境迁移、能力保持和单位预算增益；版本化指标并用独立环境审计 |

## 仍需实现验证的风险

1. `Evidence` 原子集合、provenance 图和事件 DAG 可能占用大量内存，需要小规模/大规模基准以及摘要压缩策略。
2. Agent 事件日志的规范序列化必须跨平台一致，尤其是浮点、Unicode、时区和二进制工具结果。
3. `ActionTicket` 的撤销、超时和运行时进程崩溃恢复需要真实工具适配器测试。
4. `FusionPolicy` 的代数属性不能只靠用户声明；可选的 `n.proof` 或运行时抽样验证需要单独设计。
5. Reasoner 即使完全由 n 实现，也可能算法错误、规则不全或数据偏置；可回放不等于判断正确，仍需基准、性质测试和对抗输入。
6. Agent-native 语义会引入运行时成本；“零隐藏成本”只适用于核心数值路径，不适用于检索、推理轨迹、日志和工具通信。
7. `Question`/`Decision` 的 schema、Reasoner 版本和校准指标可能漂移；严格回放必须绑定 n-IR/规则摘要，并对版本迁移执行兼容性测试。
8. Provenance DAG 和 evidence atom 集合会随任务规模增长；内容寻址和 Merkle 摘要不能替代按授权策略保留原始叶证据。
9. 分布式取消、超时和断连无法证明远端副作用已撤销；适配器必须区分 `cancel_requested`、`cancelled` 和 `outcome_unknown`，并提供 reconciliation 测试。
10. 数据完整性标签与机密性标签是两类不同属性；后续必须明确跨 Agent、工具和外部输入的数据流策略，不能把 `Untrusted` 当作完整的信息流控制系统。
11. 严格回放、学习价值与存储成本存在张力；加密载荷的密钥生命周期、保留/压缩决策记录和淘汰后的 `ReplayDataUnavailable` 行为必须纳入故障与性能测试。n 不默认最短保留，而要测单位存储/能耗带来的未来任务收益。
12. 异步分支数量、持久 mailbox 和因果消息图会提高缓存、事件存储和调度开销；需要不同 fan-out、消息频率和网络延迟下的端到端基准。
13. `Quiescent` 只代表当前分支策略和预算下没有待处理工作；领域仍可能存在未探索路径，因此不能把它暴露为真实性或完备性证明。
14. 自适应调度的收益估计可能偏向容易量化或短期高产的分支；需要任务级覆盖率/质量指标、不同假设的保留策略和对抗性基准，验证它没有系统性饿死少数路径。
15. 远程消息可能重复、迟到或在进程重启后重投；事件存储、cursor 与 outbox 的原子性、消息保留/压缩和达到上限后的恢复语义仍需故障注入验证。
16. `WorkCredit` 的拆分、转移和归还必须守恒；运行时 bug 可能造成永不停止或过早 quiescent，需要形式化状态空间检查和崩溃恢复测试。
17. `ordered_async` 的 watermark 若由故障节点迟迟不推进，会形成头阻塞；需要故障成员剔除、租约和降级到 `round_sync` 的明确协议。
18. 控制通道虽然保留容量，仍需限制取消风暴、恶意优先级和重复控制消息，避免普通证据永久饥饿。
19. 世界模型可能在训练分布外产生自洽但错误的 rollout；`Imagined` 类型只能防止身份混淆，不能替代校准、不确定性估计和真实环境验证。
20. 元学习的内/外循环、超梯度和保留集隔离会显著增加内存与编译复杂度；首版应限制 `adapt@k`、参数区域和允许的更新算子。
21. 开放式环境生成可能奖励投机、指标漏洞或不可比较的新颖度；BehaviorDescriptor 和晋升门槛必须版本化并接受对抗审计。
22. SNN 的软件稀疏性不自动带来真实能效；不同 neuromorphic 硬件的时间、精度、可塑性和通信能力需要能力表与实测基准。
23. 连续动力学的伴随梯度、刚性系统和事件不连续会导致数值/梯度误差；求解器错误必须进入训练和评估报告。
24. Tensor/Graph/Symbol/EventStream 转换可能丢失顺序、置信度或拓扑信息；转换合约与 provenance 必须可测试，不能仅靠类型名暗示无损。
25. `SequenceOperator` 的 parallel/recur/chunk 计划需要跨 CPU/GPU 的状态布局、归约顺序和浮点一致性测试；仅比较吞吐不足以证明等价。
26. 测试时适应可能把短期窗口、校准集或未来信息泄漏到长期记忆；需要窗口隔离、回滚、污染检测和故障恢复测试。
27. Diffusion/EBM 采样的随机流、温度、拒绝采样和提前停止会影响重放；必须记录完整 noise/sampler 摘要，并验证 `Generated` 永不隐式提升为 `Observed`。
28. DEQ/隐式求解和伴随梯度在刚性、多解或不稳定区域可能失败；需要残差、条件数、最大迭代和梯度误差基准。
29. Conformal/校准契约可能因分布漂移失效；需要按数据域报告覆盖率、区间宽度、拒答率和失配检测，不能只报平均准确率。
30. MLIR/StableHLO/Triton 等外部 IR 会快速演进；n 必须固定自身 dialect、版本摘要和降级兼容矩阵，不能把外部方言等同于稳定语言 ABI。
31. `Delta[D,T]` 的 `replace/join/append_unique/ordered` 合并律若只由用户标注，仍可能造成错误并行；编译器必须对可证明的半格/幂等属性做静态限制，其余只能顺序提交或显式冲突。
32. `TransitionRecord` 若同时记录内部事务和外部副作用，容易把内部 `rolled_back` 误读为现实回滚；必须按 effect 边界区分 `committed`、`outcome_unknown` 和真正可验证的回滚。
33. 统一 `TransitionKernel` 可能让不同时间域的误差被过度抽象；Discrete/Continuous/Event 的 solver、tick、事件排序和容差仍必须作为类型参数或契约字段，不能只靠别名隐藏。
34. `Tagged[T, RealityTag]` 的 `validated(P)` 不是事实真值；只有带 `GroundingReport` 的 ground 结果能作为现实 Evidence，策略版本撤销、校准域变化和证据删除时需要显式失效事件，不能让旧标签永久有效。
35. `MemoryStore` 的 `adaptive/external` 模式可能引入隐藏写入或隐式网络效果；读写必须在 n-IR 标出 `! memory`/`! net`，并记录地址策略、容量和 provenance。
36. `TransitionKernel` 输出的 `StateDelta` 若在多个分支重复提交，可能造成双重状态更新；Delta 必须带 base digest、唯一提交键和幂等/冲突策略，提交后重放只能复用同一记录。
37. `RoutePlan` 的误差界可能只覆盖局部输出，不覆盖后续状态、记忆和行动；必须允许按转换链传播 residual，并在超界时强制 exact fallback 或拒答。
38. `RouteReceipt` 的成本统计若缺少硬件采样或把未知维度记成零，会制造虚假的 Pareto 优势；未知成本必须显式保留，基准需覆盖 CPU/GPU/异构内存和同步。
39. `CompensationPolicy` 的摘要可能与精确路径重复计费，或在归一化/时间顺序上不等价；补偿前后必须有统一的合并契约、误差测试和重复贡献检查。
40. 跨层路由重用的稳定性证明可能依赖特定分布；RouteRelay 类策略只能在声明的漂移界和探测预算内复用，越界必须重算。
41. `ExplorationTree` 可能因树规模、回放版本或敏感数据无限增长；树节点需要 retention、压缩、访问策略和可审计的 ReplayDataUnavailable 行为。
42. `CapabilityLadder` 的升级条件若只由候选自己报告，会形成能力自授予；等级变更必须由 RuntimeRoot 在硬 `RootEnvelope` 内派生 capability，并由独立机器评估通过，不能由 Agent 自签 root authority。
43. `CounterfactualFamily` 使用相同基线和 kernel 仍不保证因果可识别；观测数据可能不覆盖所需干预，必须报告 identifiability/coverage 限制，不能把一致性约束冒充真实物理定律。
44. `FactorizationContract` 可能只在窄状态域成立；跨域、延迟、通信丢失或 agent 策略变化后必须失效并回到联合模型或保守策略。
45. 主动 `QueryPlan` 的信息增益代理可能忽略终局任务收益、数据流标签、传感器动作风险和观测延迟；评估需测任务收益、能力进展与完整采集成本，不只测熵下降。
46. `StateEstimate.history` 可能因记忆压缩、删除或迟到事件不完整；状态后验必须携带缺失引用/残余，重放不足时返回 unknown，而非重构成“完整状态”。
47. 持续学习中的冲突检测会有假阳性/假阴性；候选隔离虽保留旧能力，也可能阻止有益迁移，需要跨任务兼容测试和可撤销合并。
48. 开放式增长指标可被 archive 重复、任务挑选和资源扩大投机；固定预算、held-out 环境、能力保持和指标版本共同进入报告。
49. 预测抑制层的稀疏脉冲可能增加端侧筛选、元数据和恢复流量；必须在目标 neuromorphic/通信硬件测端到端能耗、尾延迟与丢失恢复。
50. 结构化 `ProgramDelta` 若能制造悬垂 value、错类型重连、效果/RealityTag 越级或绕过 ABI 检查，AI 直接 IR 会成为 verifier 旁路；patch 必须带预期摘要并重新验证受影响依赖闭包，失败原子回滚。
51. 自举编译器达到 C1/C2 固定点也可能稳定地编错；必须同时使用父编译器、参考解释器、独立后端、性质语料和差分测试，候选不能把自己的输出当唯一真值。
52. 程序热替换可能在 kernel、异步事件或 Delta 在途时混合两个版本，状态迁移也可能只迁移布局而破坏语义；切换必须发生在 RTST 安全点，并以故障注入验证旧代码/状态可恢复。
53. 自主优化器可能改写 Objective、质量门槛、计时口径或保留集来制造虚假进步；evaluation epoch 必须冻结，`ObjectiveDelta` 由旧版本和独立环境评价，候选不能同时充当自身 gate。
54. 自动调优可能过拟合短样本、隐藏编译/遥测成本，或在温度、频率、形状与并发变化后退化；必须报告冷启动/稳态/p99/能耗，使用 canary、漂移失效和自动回滚。
55. `PlacementPlan` 若只优化 kernel 而忽略传输、重排、collective、拥塞和故障域，会在织网上比单设备更慢或丢状态；数据移动必须入 IR/CostVector，并注入设备、链路和进程故障。
56. 控制面/热数据面分离若错误消除 RealityTag、capability、效果或提交日志，会把“零开销”变成语义缺失；每次消除必须有证明/依赖摘要，debug/reference/release 路径需做差分。
57. 自主程序演化会扩大版本 DAG、机器码缓存、编译时间和回滚制品；内容寻址去重仍不能保证有界，必须按未来收益与恢复价值做 retention，并测代码体积、缓存压力和单位能力增益。
58. 本地 `RootLease` 若在撤销、续期、拓扑变化或跨进程转移时出现竞态，可能让热路径继续使用陈旧 capability/credit；必须测试 lease epoch、失效传播、边界回调和纯计算回退，不能把本地缓存命中当作根权限仍然有效。
59. 多进制/低精度 profile 可能在量化、混合进制分组、特殊值、累加器或随机舍入处静默改变语义；仅比较 bit 数或 kernel 时间还可能忽略解码/LUT、带宽、同步和回退成本。必须按 `NumericContract` 做参考差分、误差/质量传播、完整成本测量和 profile 失效回退，不能把 `Trit` 当作认知 `Tr` 或把未知成本当作零。
60. 结果优先的 opaque reasoner 可能把不可复现、未校准或不完整的结论直接送入 Evidence、现实状态、ActionTicket 或版本晋升；必须绑定 `ReasoningReceipt`、Reasoner/Policy/输入输出摘要和 replay 状态，并按风险等级要求 Evidence/GroundingReport/proof，缺失时只能 `unknown`、隔离或拒绝。

## RTM 0.40 实现审计（2026-09-30）

本轮把设计从文档推进到 `tl-lang` 的最小可运行闭环：

| 项目 | 当前证据 | 边界 |
| --- | --- | --- |
| 新 `.n` 前端 | `n_front.py` 解析 field/wave/echo/commit/goal/synthesize，11 个新测试覆盖 | 仅支持 `add_scalar` 单 field 子集 |
| NIR-RTM | `n_ir.py` 规范 JSON、SHA-256 digest、round-trip 测试通过 | 尚未实现二进制 `.nir` codec |
| 原子状态提交 | `n_rtm.py` 的 epoch/stale/fail/unknown 语义测试通过 | 尚未实现异步 branch/merge |
| CPU 后端 | Reference 与现有 `kernels.dll` 的 `TLNativeBackend` 都实跑成功 | 还不是完整 SIMD/tile 计划器 |
| 测量回执 | `n_measure.py` 绑定 source/NIR/workload/hardware、p50/p99、验证/回退 | 质量门目前是 exact=0，尚未接真实误差预算 |
| 历史回归 | `run_v13.py` 当前 exit=1，失败在既有 v0.12 回归链 | 不把旧失败归因于 RTM 新模块 |

该节保存的是 2026-09-30 的原始记录：当时新闭环为 11/11 通过；它不代表当前
测试总数，当前证据以下方 0.50 审计和新鲜复跑为准。参考和 tl-native CLI 都只证明 `rtm_add_one`
workload 的执行与回执绑定，不构成 n 超过 C/Fortran 的通用性能主张。

补充验证：`RTMGoalTests` 已验证 `goal/synthesize` 能进入 NIR 并按目标顺序选出
`native` 候选；`FabricProbeTests` 已验证 CPU/GPU/NPU/CXL 都有显式状态，缺少的
NPU/CXL 不会伪造可用执行器。当前仍未实现 GPU tile、NPU SRAM 和 CXL executor，
这些项目保持 `open`，等待真实硬件和绑定 workload。

## n 统一编译器 0.50 实现审计（2026-10-01）

| 阶段 | 当前证据 | 尚未证明 |
| --- | --- | --- |
| `.n` -> NIR | `n_compile.py` 调用 n parser/NIR，生成稳定摘要 | 完整类型、效果、borrow/ownership 和通用 SSA/CFG |
| PlanManifest | 绑定 source/NIR/target/shape/type/op/features/fallback；验证摘要和字段契约 | 跨进程格式稳定性、签名/密钥、通用候选计划 admission |
| NIR -> n-LIR -> x86-64 | `n_lir.py` 显式 buffer/effect/loop/numeric contract；`n_codegen_x64.py` 消费 LIR 生成 SSE2 packed f64 add loop | 通用 CFG/SSA、ABI lowering、寄存器分配、目标文件/链接器 |
| Native runtime | Windows x64 通过 W^X 写入、切换 RX、刷新指令缓存并调用生成代码 | 多平台执行、并发压力/崩溃隔离、JIT hardening 审计 |
| RTM 集成 | 原生 Delta 经 exact Echo、epoch/proof 检验后 commit；偶数/奇数/单元素测试 | 多 wave、并发 branch/merge、非精确误差契约 |
| MeasurementReceipt | compile/init/verification、commit/fallback、plan/LIR/code digest 和暖机样本口径 | 足够样本的统计置信区间、能耗/频率/漂移、跨设备成本 |
| goal/synthesize | 语法、NIR 与有限候选确定性排序可运行 | 估值仍非测量，尚未产生/筛选/晋升真实 native 计划 |
| GPU/NPU/CXL | capability 状态显式且可为 unavailable | GPU tile、NPU SRAM、CXL memory 的真实执行器 |
| 自举 | 原 tl 的 bootstrap artifacts/tests 保留 | 不把文件存在当作完成；本轮 n 后端仍由 Python 过渡驱动 |

新增 n 验证：`python -m unittest discover -s tests -p "test_n_*.py" -v`。
`n-native` 的状态只代表当前 Windows x86-64 `f64 add_scalar` 小工作负载；回执不
构成语言整体性能比较。`goal/synthesize` 输入的 metric 数字仍按估值处理，不可冒充
实测回执。历史 `run_v13.py` 状态须另行运行核验，不能由上述新测试替代。

## n 0.7 Unified Phased IR 设计审计（2026-10-01）

本节审计已实现的原生纵切及其开放边界。`NIRModule` 已成为新路径的权威容器；
`LIRKernel` 仍保留为兼容投影，尚未进入移除期。

| 检查项 | 0.7 决策 | 尚未关闭的实现风险 |
| --- | --- | --- |
| IR 数量 | 一个权威 `NIRModule` 数据模型 | `LIRKernel` 仍存在于兼容 API，不能再承载新语义 |
| 阶段边界 | `semantic -> planned -> machine` 已进入编译路径 | operation 集仍是 add-scalar 窄子集，非通用 SSA/CFG |
| lowering | `RewriteDelta` 与父摘要链已实现 | 物理 arena 结构共享、增量摘要和二进制 codec 未实现 |
| PlanManifest | v2 外部索引分两段绑定 planned/machine digest | 通用候选 admission、签名与跨进程 schema 升级未实现 |
| 代码生成 | 新入口只接受 verified machine snapshot | 寄存器分配、目标文件、链接器与第二个实质目标未实现 |
| 契约保留 | field/wave/commit、numeric/fallback/effect 引用进入 machine | ownership/RealityTag/通用误差传播尚未进入机器 verifier |
| 性能主张 | 回执已分开 phase 成本和 kernel 成本 | 尚无 0.50/0.7 编译延迟、分配和峰值内存对照基准 |

设计层已解决的矛盾是：NIR/LIR 可以共享结构，但 lowering 不能消失。完全无 phase
的单层 IR 会允许高层契约与 ABI/寄存器操作任意混用，增加 verifier 状态空间并使
回退不可证明；继续保留两套独立对象又会产生复制、摘要、序列化和维护重复。统一
数据模型加 phase legality 是二者之间的明确取舍。

0.7 的验收必须至少覆盖：

1. semantic/planned/machine 规范 round-trip 与 parent digest lineage；
2. 非法跨 phase operation、悬垂 value、重复定义和效果缺失被拒绝；
3. machine snapshot 可回指原 semantic contract 和 fallback；
4. 0.50 与 0.7 对 `rtm_add_one` 的 reference/native 结果和机器码做差分；
5. source/shape/layout/numeric/target/hardware/objective 任一变化使 manifest 失效；
6. 编译延迟、峰值内存、节点/重写/摘要成本独立于 kernel p50/p99 报告；
7. Echo 失败、能力缺失、漂移或误差超界时不提交并回到 reference/旧计划。

当前状态为 `implemented_in_native_slice / generalization_open`。44 个 n 测试连续两次
通过；machine 新入口和旧 LIR 入口机器码一致；真机 `rtm_add_one` 回执为 committed、
质量损失 0、回退率 0。尚未完成的 arena 结构共享和编译器对照基准不能被写成已获
性能收益；0.50 仍保留为兼容/回滚证据。旧 tl v0.7 与原路线中的 n-0.7 保留为历史
编号，避免修改既有验证记录。

## n 0.8-A measured goal 审计（2026-10-02）

| 检查项 | 当前证据 | 尚未关闭的实现风险 |
| --- | --- | --- |
| 候选集合 | `reference_exact` 与 `cpu_simd_sse2` 的真实候选测量 | 非 CPU 候选仍无 executor |
| 测量绑定 | source/workload/benchmark/hardware digest 全部进入每个 `CandidateMeasurement` | 尚无跨进程签名、置信区间、能耗/频率采样 |
| 选择门 | exact Echo/Commit、零质量损失、已知 p50、绑定一致性 | 只有 add-scalar 窄域，尚无误差预算/近似值 |
| 回退 | SIMD 不可用时选择 exact reference；Echo/摘要/epoch 失败不提交 | 多计划热切换、旧计划保活和崩溃隔离仍未实现 |
| 原生后端 | n-owned x64 encoder，0.7 machine-code digest 保持兼容 | 无通用寄存器分配、目标文件/链接器和第二目标 |

本轮只关闭 Windows x86-64/SSE2 contiguous CPU `f64 add_scalar` 的 measured-goal
纵切；不能据此声称 n 普遍超过 C/Fortran。GPU tile、NPU SRAM、CXL memory 和
更宽泛的目标搜索继续保持 `open`。状态为
`implemented_in_native_slice / measured_goal_cpu_simd / generalization_open`。

## 风险闭环与可证明边界

以下编号对应上面 60 项风险，按主要关闭证据分类；类别不是风险严重度。RuntimeRoot 不变量会横切若干实现项，因此另列覆盖项，不重复计数。

| 关闭路径 | 风险编号 | 可关闭到什么程度 | 未满足时的默认行为 |
| --- | --- | --- | --- |
| 静态规格、类型检查或性质证明 | 4、10、13、24、30、31、33、35、50、56、59、60 | 证明声明的代数律、信息流/效果边界、转换约束、版本、时间域、数值 profile 和 opaque-result 门控规则；性质测试不能替代完整证明 | 拒绝不满足契约的程序/优化；未声明的提升、丢失、副作用、隐式变基或不合格结果一律不推断 |
| 运行时协议、差分测试与故障注入 | 2、3、7、8、9、11、15、16、17、18、26、32、34、36、41、42、46、51、52、55、58 | 验证消息/资源/能力状态机、编译/热替换、租约失效和织网故障在声明模型下可恢复、可审计；不能证明远端世界已回滚 | `outcome_unknown`、隔离候选、保留旧版本/状态、拒绝提交或返回 `unknown` |
| 基准、目标硬件和任务级实证 | 1、5、6、12、14、19、20、21、22、23、25、27、28、29、37、38、39、40、43、44、45、47、48、49、53、54、57 | 只支持已测数据域、预算、设备、版本及基线下的结论；报告置信区间、失败率、尾部成本和误差，而非单一均值 | 不宣称更快、更准或能力增长；退回参考路径/旧版本/窄域能力或拒绝晋升 |

**RuntimeRoot 覆盖项：** 风险 3、9、10、11、18、26、35、41、42、45、53、58 涉及外部副作用、数据完整性/机密性流、控制通道、适应污染、外部记忆、探索树访问、能力晋升、主动观测成本、评价器完整性或本地租约失效。这些不是人类偏好清单，而是机器执行契约：不可伪造 capability、不可隐式降级数据标签、不可把未知副作用当成功、不可超过资源上限、不可在同一 epoch 改写自己的评价器，也不可在根已撤销后继续使用本地 lease。硬不变量由语言/RuntimeRoot 固定；部署 `RootEnvelope` 声明可用资源、接口和数据域。AI 在 envelope 内自主优化 capability 分配、记忆保留/压缩、查询、行动和执行计划；缺少对应 capability 时，只拒绝该外部效果，仍允许独立的本地推理、学习候选和分支探索。这里不采用“一律最小权限/最短保留”：用任务收益、回放/学习价值、尾延迟、存储与能耗测量策略优劣，越界方案交给独立 AdmissionGate 验证或拒绝。

**关闭记录要求：** 风险状态只允许 `open`、`guarded`、`verified_in_scope`、`reopened`。每次标为 `verified_in_scope` 必须附上风险编号、声明域、前提、失败回退、测试/证明/基准产物摘要以及 n-IR、编译器、运行时、后端和数据版本。代码、profile、校准域、权限策略或硬件改变若超出声明域，自动重新打开相关风险。论文、类型声明、代码存在或一次成功运行都不单独构成关闭证据。

## 验收顺序

先冻结第 17 节默认配置与 `RootEnvelope`，实现 M0 的 `.nib/.nir` codec、n-Core verifier、参考解释器、TransitionStore、RootLease loader 和证据运行器；然后实现 RealityTag/Tagged、Delta/TransitionContract、Credit、CommitGate、`version.*` 生命周期和最小 `observe -> delta -> commit` 回放；再加入 ProgramDelta/增量 verifier、AIState、Objective/Learner、Evidence、`ReasoningReceipt`/opaque result、World/Dynamics/rollout、TransitionKernel、SequenceOperator、Memory、参考求解器和 `.n` 无损投影；随后实现 Agent、`retrieve/focus/route/verify`、Provenance DAG、持久 mailbox、StateEstimate、CounterfactualFamily、joint action、主动 QueryPlan 和多进制/低精度 profile 差分；再实现影子执行/热替换、自举编译器、adaptive-fastest、PerformanceReceipt 和 ExecutionFabric；最后接入元学习、QD/open-ended、Diffusion/EBM、Equilibrium、SNN、三档异步一致性与跨范式适配。静态不变量用编译器诊断/性质测试验证，协议风险用故障注入验证，AI 效能用相同任务质量门槛与资源预算的目标基准验证，RuntimeRoot 用能力派生、lease 失效、envelope 越界与评价 epoch 不可变测试验证。没有相应证据，不应宣称 AI-native 语义已经落地。
