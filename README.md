# n / tl v0.13 —— n 语言原型：自研机器码后端 → x86-64 机器码

> **语言正式名称已改为 n。** 本目录中的 `tl` 是迁移期间的兼容实现名称；新的语言设计基线见 [N_DESIGN.md](N_DESIGN.md)。
> 本轮设计审查记录见 [N_DESIGN_AUDIT.md](N_DESIGN_AUDIT.md)。
> 现有 `.tl` 文件、`tl.py` 和 `tl` 命令暂不删除，以保持原有回归链。新代码使用 `.n` 和 `n` 命令时，按同一核心语义迁移。
> **n AI-native 设计基线：Draft 0.15 Contract-Carrying Transition Machine。** n 的首要执行者是自主 AI；世界、状态、现实/想象、预测、目标、学习、适应、连续/事件时间、种群演化和 Agent 进入类型、n-IR 与运行时，而不是外置框架。人类可读表面是检查/互操作界面，不是核心优化中心。
> **n 不采用 LLM 作为语言基础。** 标准运行时不需要 LLM 模型、API、tokenizer 或提示词；可组合规则/搜索、世界模型、元学习、质量多样性、SNN、连续动力学和 Agent。现实 `Observed` 与 `Predicted/Imagined/Counterfactual` 强类型隔离，学习只产生待验证、待晋升的新版本。
> **n 的独有机制是 RTST（Reality-Tagged State Transition）。** 所有 AI/Agent/学习/记忆/分支/工具动作都降级为带现实标签的 `TransitionContract`；更新统一为 `Delta[D,T]`，候选晋升与行动授权统一为受约束 `CommitGate`，预算与并行工作统一为线性 `Credit[D]`。
> RTST 的提交边界由效果精化约束：纯代码只能构造/验证 Delta；提交状态、记忆、学习版本或 durable 事件分别要求 `! state`、`! memory`、`! learn`、`! event`。
> **架构研究已扩展。** Draft 0.10 加入选择性转换、误差补偿、反事实一致性、联合行动、主动观测、持续适应隔离和多维成本；Draft 0.11 冻结跨平台语义；Draft 0.12 确立 AI-first 效能宪法、RuntimeRoot 机器契约、`adaptive-fastest` 默认执行，以及 RTST 控制面/热数据面分离；Draft 0.13 将 `.nib/.nir`、n-Core verifier、参考解释器、RootLease 和统一 ArtifactVersion 生命周期前置为机器起点；Draft 0.14 加入语义主权四件套、G9 语料单源、负例优先、报告不可伪造和 `Quantity[Unit, SemanticTag, Rep]`；Draft 0.15 将 n 收敛为 CCTM：一等 `ExecutionPlan`、统一 `derive`、`Approx[T]` 误差界/精确回退，以及可归因的摘要绑定基准。目标是在质量与完整性不变量内最大化能力进展、吞吐和单位资源效能。
> **CCTM 核心闭环：** `derive` 生成候选分析/计划 → `ExecutionPlan` 携带证明、布局、设备、精度、成本和 fallback → `plan.execute` 产生可回放 `PlanReceipt` → residual 超界时在安全点回退 → `CommitGate` 决定是否晋升。计划、推导和近似值都不能绕过 RTST。
> **机器自治而非人工逐次审批。** AI 可在 `RootEnvelope` 内自主分配 capability/预算、选择精度/设备/布局/路由/缓存/记忆和并行 fan-out，并通过影子验证、`AdmissionGate`、自动晋升与回滚持续优化；候选不能改写评价自己的目标、计费口径或保留集。
> **结果优先、解释可选。** Reasoner 可在内部搜索和低风险控制中直接返回 `result_only`，不必生成自然语言推理链；`ReasoningReceipt` 仍绑定输入/输出摘要、版本、质量/残差和 replay 状态。现实状态、外部行动和版本晋升按风险策略要求机器证据，而不是要求可读解释。
> **AI 可直接进化程序本身。** `.n` 是可读投影；AI 可生成 `.nib`/n-Core-IR，以结构化 `ProgramDelta` 修改程序或编译器，经增量 verifier、多阶段自举、影子执行和 RTST 安全点事务热替换。`ExecutionFabric` 将 CPU/GPU/NPU/neuromorphic、内存层级与网络作为可联合优化的机器织网，数据移动和恢复成本不能隐藏。
> 同一 `CounterfactualFamily` 共享状态基线与世界契约；不完整观察保留历史与未知项；事件稀疏化复用 `RoutePlan` 并测量真实通信和能耗。
> **编译器研究同样进入边界。** MLIR/StableHLO、Halide、Triton、Futhark、Dex、Lean/F*/Dafny、Pony、Roc/Unison 的经验被重构为多级 n-IR、算法/调度分离、tile、契约、能力隔离和可复现摘要；AD 是 n-IR 规范变换，不是独立效果。
> **数值表示也采用多进制候选。** n 不把三进制强加给所有程序，而是让 AI 在 `RadixSpec`/`EncodingProfile` 中选择二进制、平衡三进制、低比特浮点、定点、LUT/codebook 或 mixed-radix；误差、解码、带宽、同步、能耗和回退都进入 `NumericContract`/`CostVector`。`Trit` 是数值表示，认知 `Tr` ABI 保持独立。
> **Agent 多螺旋使用持久异步 mailbox。** 经证明合流的处理器采用 `causal_async`，其他处理器使用 watermark 驱动的 `ordered_async` 或 `round_sync`；快分支仍可影响慢分支后续推演，只有显式许可的增量能合并进主干。
> 目录中的 Transformer/attention 程序保留为张量、自动微分、内存规划和机器码后端的压力测试，不代表 n Agent 采用 Transformer 或语言模型。

> **v0.12 革命点：VM 槽值从嵌套 list 改为扁平 double buffer（Buf），热内核零拷贝直通 C**——
> 彻底省掉 `_flat/_buf/_unflat` 三趟 Python 往返（v0.11 的 ctypes 搬运开销），
> 小矩阵也吃到原生收益。**模型级加速比 v0.11 提升 4–8 倍**：big 1.2x→**8.1x**、
> large 2.0x→**16.2x**（vs Python VM）；内核级 28.1x 保持。同时**基准口径切换**：
> 写纯 C 参考训练循环（bench_c.exe，同图同内核），报告 tl 相对纯 C 的**调度开销**——
> big 400ep **~15–22x**、large 50ep **~5.5–6.1x**（多次实测区间；该开销全部来自 Python VM 调度层 + ctypes FFI，
> 内核本身与 C 同源、逐位一致，可被"调度下沉 C"消除）。**训练全程逐位一致**
> （Buf 模式 == list 模式，small 24ep + large 50ep loss 序列全同）。

> **v0.11 革命点：数值内核从 Python 下沉为自研 C 内核**——
> 热内核（matmul / softmax / 融合算子 / 反向 / 累加）用 C 重写并编译为
> `kernels.dll`（zig 构建，仅作构建期工具；tl 运行时零第三方），ctypes 加载。
> 内核级加速 **28.1x**（256×256 matmul）。**训练全程与 Python 路径逐位一致**——包括 24-epoch 小模型与
> 50-epoch large 模型 loss 序列。**数值内核全自研：连 `exp` 都不依赖 libm**——
> 自研 `tl_exp`（k=floor(x/ln2)+r 分解 + 16 阶 Taylor Horner + ldexp），
> C / Python / tl.py 前端三端同源、逐位一致。这是"摆脱 Python 运行时"的第二块真砖，
> 也是阶段 2 大型张量计算图与 PyTorch 对照测试的入场券。

> 语义核心（v0.1-v0.7）之上，v0.8 补齐**工程形态**：
> `tl` 成为独立命令行工具链——`tl run / check / info / train FILE.tl` 直接编译运行 .tl 源码。
> 语言本体是 .tl 文件 + tl 编译器；`tl.py` 只是当前实现载体（早期 CPython 用 C 写同理），
> 摆脱 Python 的路由是后端自举（见"下一步"）。
>
> **v0.10 革命点：形状系统从"编译期检查"升级为"代码生成器"**——
> 字节码编译期槽表已知全部形状，把每条指令的形状分支在编译期绑定成专用 kernel，
> 运行时零判断、零 dispatch。后端执行性能：字节码 VM 比解释快 **1.75x**（小模型），
> 规模放大（8×16×d=32）后达 **2.32x**——加速比随规模放大。
> `tl build` 把 .tl 编译成 **tl 字节码（.tlb）**（槽位分配 + 嵌套表达式展开 + fwd/back 指令），
> 由**自研 VM** 执行。零 LLVM、零第三方。字节码训练与前端 naive / checkpoint / 增量路径
> **全部逐位一致**。这是摆脱 Python 运行时的第一块真砖。

> 一门「张量一等公民 + 自动微分原生 + 形状编译期检查 + **训练编译器 + 内存后端 + 增量训练**」的原型语言。
> 早期以 Transformer 作为高强度计算图样例；Draft 0.10 已将产品方向重构为多范式原生 AI 语言，Transformer 不再定义语言架构。
>
> **v0.5 让训练本身成为编译目标**；**v0.6 让显存决策成为真实执行**；
> **v0.7 让编译器静态知道"训练循环里哪些计算可以不做"**：
>
> `TrainingPlan.run_incremental(epochs, lr, seed, update)` 每步只重算
> **update 参数集的传递影响闭包**（静态子图）；冻结参数（不在 update 中）的
> 影响闭包在初始 forward 后**永久复用**——适用于冻结主干、局部更新和大型增量计算图。
>
> 实测：全参数增量前向语句 **10 vs 17（↓44%）**；冻结 FFN（只训 W1/b1）
> **3 vs 17（↓83%）**，且与朴素全量重算、与 v0.5/v0.6 编译训练 **loss 序列逐位一致**。
> PyTorch 的 autograd 图每步重建、永远无法跨步复用任何中间——这是"训练循环在图内"
> 的直接红利，也是 v0.5 那 10.84x 之后第二块语言级优化砖。

> **v0.13 革命点：数值内核用 tl 语言写，并由 tl 自己编译成 x86-64 机器码**——
> 9 个内核（mm2 / relu / elem2_add/sub/mul / scale / upd / relu_mask / sqg）用 **tl 源码
> （kernels.tl）**描述，`tl_emit.py` 是**纯自研 x86-64 发射器**（REX/SIB/ModRM 编码、
> 寄存器分配、Windows x64 ABI、跳转重定位全部手写，零 LLVM、零汇编器、零第三方），
> VirtualAlloc 直接装载可执行内存经 ctypes 调用。**机器码 == tl 参考 VM == tlb Python 内核，
> 逐位一致（20 轮随机）**；mm2 机器码与 C 内核（kernels.dll）逐位一致，
> 且 256×256 快 **35%**（163ms vs 252ms）。这是"摆脱 Python / 摆脱 C / 摆脱 LLVM"路线
> 的第一块真砖：语言自己描述内核、自己发射机器码，为 v0.14 内核全机器码化 + 编译器自举铺路。

## 零第三方依赖

连数值引擎（NDArray / 矩阵乘 / softmax / 反向传播 / 融合算子反向 / 训练编译器 / 检查点反向 / 显存池 / 增量影响分析）都是手写的。v0.11 起**数值内核下沉为自研 C（kernels.dll）**：16 个导出内核全部手写，连 `exp` 都是自研（不依赖 libm）。

系统只需 Python 3；构建期用 `pip install ziglang`（仅当需要重新编译 kernels.dll 时）。

## 文件

| 文件                     | 作用                                                          |
| ---------------------- | ----------------------------------------------------------- |
| `tl.py`                | 语言实现：lexer → parser → checker → engine + optimize + **compile_training + 内存后端 + 增量影响分析** |
| `demo.tl`              | 用 tl 写的 3→2→1 两层小网络                                         |
| `run_demo.py`          | v0.1 验证：形状检查抓错、AD vs 有限差分                                   |
| `train_demo.py`        | v0.1 训练闭环（宿主 Python 驱动）                                     |
| `attention.tl`         | v0.2：单头 scaled dot-product attention 前向（2D）                 |
| `run_v02.py`           | v0.2 验证：softmax 性质、attention 数值正确、语言内训练收敛                   |
| `attention3d.tl`       | v0.3：多头 attention 前向（3D \[2,3,2]，H=2）                       |
| `transformer_block.tl` | v0.3：完整 encoder block（Q/K/V 投影 + 注意力 + 残差 + FFN + 残差 + MSE） |
| `run_v03.py`           | v0.3 验证：多头 attn / Transformer block / 多参数训练 / 图优化雏形 / 回归    |
| `run_v04.py`           | v0.4 验证：融合算子 forward / 全网络融合等价 / 图规模缩减 / 融合训练 / 回归          |
| `run_v05.py`           | v0.5 验证：训练编译正确性 / 内存规划 / 编译收敛 / 编译 vs 解释 / 回归            |
| `run_v06.py`           | v0.6 验证：三策略峰值实测 / 单步等价 / 24 epoch 全程等价 / 收敛 / 回归      |
| `run_v07.py`           | v0.7 验证：影响子图 / 增量==朴素 / 增量==编译训练 / 语句量 / 冻结收敛 / 回归 |
| `tl.bat`               | v0.8：`tl` 命令入口（Windows），包装 `python tl.py`                    |
| `tlb.py`               | v0.9：全自研后端——tl 字节码（.tlb）+ 编译器 pass + 自研 VM（v0.10 调度器编译 + v0.11 native 优先包装 + v0.12 Buf 扁平化快路径） |
| `run_v09.py`           | v0.9 验证：forward/训练/检查点/增量/round-trip/CLI/回归 逐位一致       |
| `tb.tlb`               | v0.9 示例产物：transformer_block 编译出的 tl 字节码（可审计文本）     |
| `run_v10.py`           | v0.10 验证：调度器编译正确性 + 四路执行对比 + 规模测速             |
| `transformer_block_big.tl` | v0.10 规模测速模型：[8,16] 单样本、d=32 encoder block        |
| `kernels.c`            | v0.11：自研 C 数值内核（16 导出内核：mm2/mm2v/mm2_back/elem2/relu/sq/scale/scg/upd/relu_mask/sqg/softmax/total/softmax_grad/transpose/colsum/scaled_mm(_t)(_back)/affine2(_v)(_back)，含自研 tl_exp） |
| `kernels.dll`          | v0.11：zig `-O2 -ffp-contract=off` 编译产物（209920 bytes，运行时加载） |
| `build_kernels.py`     | v0.11：构建脚本（定位 zig.exe → `zig cc -O2 -ffp-contract=off -shared`） |
| `tl_native.py`         | v0.11：ctypes 包装 NativeKernels（全部内核方法 + 展平/回填 + exp_test）；v0.12 追加 `Buf` 类（扁平 buffer + 预 cast 指针）+ `_BufKernels`（Buf 版内核，零拷贝直通） |
| `run_v11.py`           | v0.11 验证：内核级逐位 / 训练逐位 / 256mm 加速 / 模型测速 / 回归 |
| `bench_c.c`            | v0.12：纯 C 参考训练循环（transformer_block 前向+反向+update，全部用 kernels.c 自研内核）——"和 C 比"的基准 |
| `build_bench.py`       | v0.12：构建 bench_c.exe（zig cc -O2 -ffp-contract=off）            |
| `bench_c.exe`          | v0.12：纯 C 训练基准可执行文件（big 400ep / large 50ep）           |
| `run_v12.py`           | v0.12 验证：Buf 内核逐位 29/29 / 训练逐位（Buf==list）/ 性能（tl vs 纯C）/ 回归 |
| `transformer_block_large.tl` | v0.11 测速模型：[16,32]×d=64 encoder block（由 gen_large.py 生成） |
| `gen_large.py`         | v0.11：transformer_block_large.tl 的生成脚本（可再生成）             |
| `kernels.tl`            | v0.13：9 个数值内核的 **tl 源码**（mm2/relu/elem2_add/sub/mul/scale/upd/relu_mask/sqg）——语言自己描述内核 |
| `tl_kern.py`            | v0.13：kernels.tl 的解析器 + AST + 参考 VM（tl 内核子集的语义基准） |
| `tl_emit.py`            | v0.13：**自研 x86-64 机器码发射器**——指令编码/寄存器分配/ABI 全手写（REX/SIB/ModRM、SSE2、跳转重定位），VirtualAlloc 装载可执行内存，零 LLVM/汇编器/第三方 |
| `run_v13.py`            | v0.13 验证：kernels.tl 参考语义 / 机器码 20 轮随机逐位 / mm2 vs C / 性能 / 回归 |

## 运行

```
python run_demo.py    # v0.1 演示 + 验证
python train_demo.py  # v0.1 训练闭环
python run_v02.py     # v0.2 attention + 语言内训练验证
python run_v03.py     # v0.3 多头 attention + Transformer block + 图优化验证
python run_v04.py     # v0.4 融合算子真执行验证
python run_v05.py     # v0.5 训练编译器验证
python run_v06.py     # v0.6 内存后端验证（三策略峰值 + 语义等价）
python run_v07.py     # v0.7 增量优化验证（影响子图 + 冻结复用 + 逐位一致）
python run_v09.py     # v0.9 字节码后端验证
python run_v10.py     # v0.10 调度器编译验证
python run_v11.py     # v0.11 原生内核验证（内核级 23/23 + 训练逐位 + 28x + 模型测速 + 回归）
python run_v12.py     # v0.12 验证（Buf 内核 29/29 + 训练逐位 + tl vs 纯C 调度开销 + 回归）
python run_v13.py     # v0.13 验证（kernels.tl 参考语义 + 自研机器码 20 轮随机逐位 + mm2 vs C + 性能 + 回归）
.ench_c.exe big 400 # v0.12 纯 C 训练基准（big；large 用 `large 50`）
```

### tl 命令（v0.8 工具链）

```
tl run   demo.tl               # 编译并执行 .tl 程序，打印全部变量
tl check demo.tl               # 只编译：形状检查 + 图优化报告（编译期抓错）
tl info  transformer_block.tl  # 训练编译报告：融合 / 内存规划 / 增量影响
tl train transformer_block.tl --epochs 24 --seed 7 --mem checkpoint
tl train transformer_block.tl --incremental --update W1,b1   # 冻结主干微调
tl build transformer_block.tl -o tb.tlb        # v0.9：编译成自研字节码
tl train tb.tlb --epochs 24 --seed 7            # v0.9：字节码训练（VM 执行）
tl run   tb.tlb                                # v0.9：字节码前向执行
```
（`tl.bat` 在 Windows 命令行直接可用；也可 `python tl.py run ...`。）

## tl 语法 v0.7

```
let X = tensor([[1.0, 0.0, 0.5, 0.2], [0.3, 1.0, 0.1, 0.4], [0.2, 0.5, 1.0, 0.3]])
let Wq = param([4, 4])
let Q = matmul(X, Wq)
let K = matmul(X, Wk)
let scores = scale(matmul(Q, transpose(K)), d)   # 源写法（3 个算子）
let attn = softmax(scores)
let ctx = matmul(attn, V)
let h = add(ctx, X)
let f = add(matmul(relu(h), W1), b1)
let out = add(f, h)
let loss = mean(square(sub(out, target)))
```

训练编译器入口（v0.5）+ 内存策略（v0.6）+ 增量训练（v0.7）：

```
plan = compile_training(code)                        # 融合 + 形状检查 + 内存规划
losses, eng = plan.run(24, lr=0.2, seed=7, mem_strategy="checkpoint")   # 内存后端
losses, eng = plan.run_incremental(24, lr=0.2, seed=7)                 # 增量（全参数）
losses, eng = plan.run_incremental(24, lr=0.2, seed=7, update=["W1", "b1"])  # 冻结主干
```

`TrainingPlan` 契约：`ast / fwd / params / mem / fused / release_map / loss_names / impact_stmts`；
`run_incremental(epochs, lr, seed, update)` 每步更新 `update`（默认全部参数），
forward 只执行 update 参数集的传递影响闭包（静态子图）。

v0.7 新增机制：
- **影响子图分析** `analyze_incremental`：对每个参数计算"传递依赖闭包"——
  参数变化会波及哪些 let（Wq/Wk→8 条、Wv→6 条、W1/b1→3 条），用 frontier 迭代到不动点。
- **静态增量执行**：每步重算子图 = ∪ 影响闭包(update)。未更新的参数不变
  → 依赖它们的中间值不变 → 跨步复用。冻结参数影响闭包只在初始 forward 算一次。
- **正确性保证**：复用值 == 朴素全量重算值（依赖参数未变），故与全量重算
  逐位一致——增量不是近似，是编译器证明可跳过。

基础算子：`tensor / param / add / sub / mul / matmul / relu / sum / mean / square / transpose / scale / softmax`。
融合算子（编译期自动生成）：`scaled_mm_t / scaled_mm / affine / bias_relu`。
语句：`let / print / update(name, lr)`。

## 已验证（可证伪）

v0.1：

1. **编译期形状检查**：add/matmul 形状不匹配在编译阶段被拒绝，程序不执行。
2. **AD 梯度数值正确**：11 个梯度元素全非零，vs 有限差分最大误差 1.97e-11 < 1e-6。
3. **训练闭环**：loss 76.78 → 0.000001，预测 6.9993（目标 7.0）。

v0.2：

4. **softmax 性质**：attention 权重每行和为 1。
5. **attention 前向数值正确**：单头 scaled dot-product attention 与参考最大误差 0.0。
6. **语言内训练**：`update(W, lr)` 20 步，loss 49.0 → 0.000000 单调下降。

v0.3：

7. **多头 attention 数值正确**：H=2、3D 数据，attn/ctx 与逐头 2D 参考误差 0.00e+00。
8. **完整 Transformer encoder block 前向正确**：与纯 Python 参考误差 4.44e-16。
9. **语言内多参数训练收敛**：5 组参数（含广播 bias），24 epoch loss 0.0680 → 0.005264。
10. **图优化雏形**：常量折叠 + 融合模式识别。

v0.4：

11. **融合算子 forward 正确**：scaled_mm / scaled_mm_t / affine / bias_relu 与纯 Python 参考**误差 0.00e+00**。
12. **融合是等价变换**：完整 Transformer block 融合前后，loss 误差 0、out 误差 4.44e-16、
    **全部 5 组参数梯度最大误差 1.11e-16** —— 优化不改变语义（含反向）。
13. **图规模真实缩减**：同一程序算子调用 16 → 13（消除 3 个中间算子）。
14. **融合版训练收敛**：融合路径（含 bias 广播梯度）24 epoch loss 0.0680 → 0.005264，与未融合完全一致。
15. **回归**：v0.1 / v0.2 / v0.3 全部 exit=0。

v0.5：

16. **训练 = 编译目标**：`compile_training` 产出固定训练计划；
    编译单步与手动 forward/backward/update 逐值一致（loss 0.068012969906，12 位小数）。
17. **内存规划 pass（编译器自动决策）**：反向读值分析 + 激活生命周期 →
    反向必须保留 `Q / K / V / attn / ctx / f / h / out`；可释放 `d / scores / loss`；
    检查点候选 `Q / K / V / ctx / f / h / out`（理论 ↓41.5%）。
18. **编译训练收敛**：`plan.run(24)` loss 0.068 → 0.0055 单调下降。
19. **编译执行 vs 解释执行**：同样 24 epoch，解释 80.3 ms vs 编译 7.4 ms —— **加速 10.84x**。
20. **回归**：v0.1 / v0.2 / v0.3 / v0.4 全部 exit=0。

v0.6：

21. **内存后端真执行**：三档策略实测峰值（真实显存池账本）——
    `naive 1568 B → conservative 1488 B（↓5.1%）→ checkpoint 848 B（↓45.9%）`。
22. **单步语义等价**：三策略单步 loss 逐位一致（0.068012969906）。
23. **24 epoch 全程语义等价**：三策略 loss 序列**逐位一致** —— 检查点 + 重算 = 零语义损失。
24. **检查点训练收敛**：checkpoint 24 epoch 0.068 → 0.0055。
25. **回归**：v0.1 / v0.2 / v0.3 / v0.4 / v0.5 全部 exit=0。

v0.7（本轮）：

26. **影响子图分析**：每个参数的传递依赖闭包（Wq/Wk→8 条、Wv→6 条、W1/b1→3 条），
    与独立复算逐一致；全参数并集 10 条、冻结 FFN 并集 3 条（vs 全图 17/18 条）。
27. **增量 == 朴素（逐位一致）**：三种更新集（全参数 / 冻结 FFN / 单 Wq）下，
    增量执行与"同样更新序列 + 每步全 forward 重算"的 loss 序列**逐位一致**。
28. **增量 == 编译训练（逐位一致）**：`run_incremental(24, update=None)` 与
    `plan.run(24)` 的 24 epoch loss 序列**逐位一致**（0.068012970 → 0.005472795）。
29. **前向语句量**：全参数增量每步 10 vs 17（**↓44%**）；冻结 FFN（只训 W1/b1）
    每步 3 vs 17（**↓83%**）—— 冻结参数影响闭包永久复用。
30. **冻结主干收敛**：只训 W1/b1（冻结 Q/K/V 投影）24 epoch loss
    0.068013 → **0.005417**（甚至略优于全参数增量 0.005473——本 toy 网络的
    loss 主导项在 FFN 输出路径，全参数更新反而引入干扰；诚实记录，不引申）。
31. **回归**：v0.1 / v0.2 / v0.3 / v0.4 / v0.5 / v0.6 全部 exit=0。

v0.9（上一轮）：

32. **全自研后端**：`tl build` 产出自研字节码 `.tlb`（槽位分配、嵌套表达式展开、
    fwd/back 指令），自研 VM 执行；零 LLVM。transformer_block：21 槽 / 13 fwd / 13 back。
33. **字节码 forward == 前端解释**：全部命名中间与损失逐位一致。
34. **字节码训练 == plan.run(naive)**：24 epoch loss 序列逐位一致（0.068012969906 → 0.005472795053）。
35. **字节码训练 == plan.run(checkpoint)**：与前端检查点路径逐位一致（后端语义 = 前端最优路径）。
36. **字节码增量 == run_incremental**（update=[W1,b1]）：逐位一致（0.068012969906 → 0.005416846751）。
37. **.tlb round-trip 无损**：to_text → from_text → 训练逐位一致；CLI build/train 子进程通过。
38. **回归**：v0.1 / v0.2 / v0.3 / v0.4 / v0.5 / v0.6 / v0.7 全部 exit=0。

后端正确性路上修掉的真问题：嵌套指令未入队（fwd 缺 relu/sub/square）；
.tlb const 序列化被 shape 占位破坏（X init 解析成 int）；**浮点累加对齐**——
Python 3.12+ 内置 `sum()` 是补偿求和，与前端朴素 `s +=` 循环逐位不同，
训练会漂移 1e-16：矩阵乘对齐循环累加、scaled_mm_t 对齐内积 `sum()`。

v0.10（上一轮）：

39. **调度器编译**：`compile_kernels(prog)` 编译期按槽形状为每条 fwd/back 指令选择
    专用 kernel（零运行时形状判断、零 if-elif dispatch、无 Insn 属性访问）。
40. **kernel == 原路径逐位一致**：24 epoch loss 序列逐位相同（自动成为 v0.9 默认执行路径）。
41. **四路执行 loss 逐位一致**：解释 / naive / checkpoint / 字节码 kernel，200 epoch 全部相同
    （末 0.000016898359）。
42. **后端性能**：200 epoch 中位耗时 解释 68.8ms / naive 74.5ms / checkpoint 98.9ms /
    字节码 VM 39.2ms——VM vs 解释 **1.75x**、vs naive **1.90x**。
43. **规模放大**：transformer_block_big（[8,16]×d=32）200 epoch 解释 1108.7ms vs VM 478.2ms，
    加速比 **2.32x**——调度器编译优势随规模放大（阶段 2 试金石预演）。
44. **`_matmul2` 微优化**：enumerate 去一次索引（累加顺序不变，逐位保持）。

v0.11（本轮）：

45. **原生内核后端**：热内核全部下沉为自研 C（kernels.dll，zig `-O2 -ffp-contract=off`
    构建）；VM 调度 + ctypes 原生计算。**内核级逐位一致 23/23**（原生 == Python，
    含矩阵乘 / softmax / 融合算子前向与反向 / 累加——朴素与 Neumaier 双累加契约）。
46. **自研 exp**：`tl_exp` 不依赖 libm（k=floor(x/ln2)+r 分解 + 16 阶 Taylor Horner +
    ldexp），C / tlb / tl.py 三端同源；C == Python 100000 随机点逐位一致。
    修复了 zig libm 的 exp 与 CPython math.exp 1 ulp 差异导致的 large 模型漂移。
47. **训练逐位一致**：24-epoch 小模型 **与** 50-epoch large 模型（[16,32]×d=64）
    原生 VM vs Python VM loss 序列**逐位一致**（小 0.068012969906 → 0.005472795053；
    large 0.971579 → 0.170217）。
48. **性能**：256×256 matmul×10 原生 228.7ms vs Python 6642.8ms —— **28.1x**；
    模型级 big 1.2x / large **2.0x**（large 374ms vs 736ms；ctypes 拷贝开销所限，
    5x+ 模型级目标留给 v0.12 扁平化数据表示）。
49. **回归**：v0.1 / v0.2 / v0.3 / v0.4 / v0.5 / v0.6 / v0.7 / v0.9 / v0.10 全部 exit=0。

v0.12（本轮）：

50. **Buf 扁平化内核 29/29 逐位一致**：BufKernels（ctypes buffer 直通）== NativeKernels
    （list 中转）——含矩阵乘/softmax/融合前向与反向/累加/嵌套分组 total。
51. **训练逐位一致（Buf == list）**：small [3,4] 24 epoch 与 large [16,32] 50 epoch
    loss 序列**逐位全同**（small 0.068012969906 → 0.005472795053；
    large 0.971579 → 0.170217）。
52. **性能——基准口径切换"和纯 C 比"**：纯 C 参考训练循环（bench_c.exe，同图同内核）
    big 400ep **~7–8ms** / large 50ep **~7–8ms**；tl(Buf VM) big **119–155ms**（调度开销
    **~15–22x**）/ large **~43–47ms**（**~5.5–6.1x**，多次实测区间）。开销全部来自 Python VM 调度层 + ctypes FFI，
    内核本身与 C 同源——"调度下沉 C"即可消除（v0.13 路线）。vs Python VM 基线：
    big 8.1x / large 16.2x（v0.11 的 1.2x/2.0x → **模型级提速 4–8 倍**）。
53. **回归**：v0.1 / v0.2 / v0.3 / v0.4 / v0.5 / v0.6 / v0.7 / v0.9 / v0.10 / v0.11 全部 exit=0。


v0.13（本轮）：

54. **kernels.tl 参考语义 == tlb Python 内核**：9 个内核用 tl 源码描述，tl 解析器+参考 VM 执行结果与 tlb 内核逐位一致。
55. **自研机器码 == tl 参考 VM（逐位一致）**：9 个内核全部通过 20 轮随机逐位一致
    （含 relu 分支、scale/upd 标量参数、mm2 三重循环 + 浮点累加顺序对齐）。
56. **机器码 mm2 == C tl_mm2（逐位一致）**：与 kernels.dll 的 C 内核逐位相同（累加契约对齐）。
57. **性能 vs C**：256×256×10 机器码 163.2ms vs C 252.2ms —— **机器码/C = 0.65**（朴素循环已快于同源 C）。
58. **回归**：v0.1 / v0.2 / v0.3 / v0.4 / v0.5 / v0.6 / v0.7 / v0.9 / v0.10 / v0.11 / v0.12 全部 exit=0。

> **当前复跑状态（2026-09-29）**：历史记录 54–58 保留为当时的验证结果，但本机用 `python -X utf8 run_v13.py` 复跑时，`run_v12.py` 在嵌套 `run_v11.py` 回归处返回 exit=1；`run_v11.py` 又报告 large 模型逐位一致失败及更早版本回归失败。未修复这些实现/回归问题前，不能把 58 条历史记录表述为当前全链路通过。普通 `python run_v12.py` 还会因 Windows 默认 GBK 解码子进程输出而出现 `UnicodeDecodeError`，应使用 UTF-8 配置后再诊断。

修掉的真问题（机器码调试实录）：SIB 无索引编码、jcc 重定位按指令长 6/5 字节修正、
CFUNCTYPE 首元素是 restype（指针参数被 c_int 截断成 32 位）、REX 前缀必须在 66 之前
（movq xmm, r64 变 movd）、imul 0F AF 的 reg=目标（与 mov 89 相反）、mm2 累加缺 addsd / 操作数错位。

## 已知限制（v0.13 诚实清单）


* **机器码后端覆盖 9 个内核子集**：tl_emit 目前发射 mm2 与 8 个逐元素内核；
  softmax / 融合算子（scaled_mm 系）/ 3D 路径 / 反向内核尚未机器码化——v0.14 按
  kernels.c 的 16 个导出内核清单逐一补齐（含反向与 tl_exp）。
* **机器码与 C 同速甚至略快、但调度层未下沉**：内核级已和 C 逐位一致且快 35%，
  VM 调度层仍是 Python（tlb.py）；v0.14 把调度器编译产物直接链接到机器码内核（tl/C < 2x 收官）。
* **Buf 分配未池化**：每个内核输出都新建 ctypes array（每 epoch 约 20 次分配）；
  内存池复用（v0.6 arena 思路下沉）是 v0.13 的低垂果实。
* **3D 融合算子（scaled_mm3/affine3 等）仍走 list fallback**：Buf 模式下 3D 张量
  会降级转 list（保逐位一致），多头注意力的大模型路径尚未全 Buf。
* **VM 载体仍是 Python**：`tlb.py` 的 VM 是 Python 实现（自研指令集已独立，执行器未独立）；
  语言形态（.tl 源码 + tl 命令 + 编译错误）已独立，运行时后端独立是 v0.13。
* **VM 载体仍是 Python**：`tlb.py` 的 VM 是 Python 实现（自研指令集已独立，执行器未独立）；
  语言形态（.tl 源码 + tl 命令 + 编译错误）已独立，运行时后端独立是下一步。
* 数值引擎朴素（三重循环），性能无意义 —— 但"消除中间张量 / 消除解释开销 /
  显存自动规划 / 跨步计算复用 / 原生数值内核"都是语义层面可量化的优化证据，
  真性能留待编译器后端。
* **增量只作用在前向**：反向仍是全图（loss 依赖所有参数）。反向增量（稀疏梯度
  传播 / 只反传播到 update 参数的闭包）是下一块。
* 增量与内存后端（检查点释放）尚未组合：`run_incremental` 目前是 naive 保留
  语义（复用依赖中间常驻）。组合后冻结场景可同时吃"显存 ↓"与"计算 ↓"。
* 检查点粒度是"整链恢复"；释放是值释放（`value=None`），字节级回收留待后端。
* 融合只覆盖 4 个模式；尚无 fused-attention、函数/模块/控制流、符号化形状、编译器后端。

## 下一步（路 A 延续）

* **v0.14 内核全机器码化 + 调度下沉**：tl_emit 覆盖 kernels.c 全部 16 个导出内核
  （softmax / 融合算子 / 反向 / 3D），VM 调度器编译产物直接调用机器码内核——
  消除 Python VM 调度层 + ctypes FFI（"和 C 比"收官：tl/C < 2x，且内核是 tl 自产的机器码）。
* **Buf 内存池**：内核输出复用预分配 buffer（v0.6 arena 思路下沉 C），消除每 epoch
  ~20 次 ctypes 分配；就地 update 消除参数拷贝。
* **3D 全 Buf**：多头 attention 的 3D 张量路径（scaled_mm3/affine3）接入 Buf 内核，
  消除 list fallback——阶段 2 试金石（千万参数 Transformer）需要 3D 快路径。
* **后端独立（摆脱 Python）**：编译器后端（LLVM/MLIR 或自研）把 tl 编译成
  原生码/字节码，运行时独立于 Python；终局是**自举**（tl 编译器用 tl 写）。
* **阶段 2 试金石**：tl 写小 Transformer 端到端训练 vs PyTorch 同配置（届时基准口径
  已切换为纯 C/PyTorch 双对照）。
* **后端独立（摆脱 Python）**：编译器后端（LLVM/MLIR 或自研）把 tl 编译成
  原生码/字节码，运行时独立于 Python；终局是**自举**（tl 编译器用 tl 写）。
  `tl.py` 的定位是语义原型载体，语言形态已独立（.tl + tl 命令）。
* **v0.8 反向增量 + 增量×检查点组合**：反向只传播到 update 参数的影响闭包
  （稀疏梯度路径），并与 v0.6 内存后端叠加——冻结微调同时拿显存与计算红利。
* **分段检查点**：按段恢复 + 用前即弃，逼近 912 B 的理论下界。
* **fused-attention**：softmax(scale(matmul(...))) → 单算子（含反向）。
* **符号化形状** `[B, S, H]` → 跨层形状检查。
* **阶段 2 试金石**：tl 写小 Transformer 端到端训练 vs PyTorch 同配置。

## RTM 0.40 基础闭环（2026-09-30）

`n_front.py`、`n_ir.py`、`n_rtm.py` 和 `n_backend_tl.py` 已加入一个不依赖旧
tl AST 的最小 RTM 前端与执行闭环：`.n` 源码直接降低为规范化 NIR-RTM，
`field -> wave -> echo -> commit` 的状态转换具有 epoch 检查、精确回显验证、
stale/fail/unknown 拒绝和原子提交语义。`TLNativeBackend` 只在 `kernels.dll`
实际可加载并执行时标记可用，否则返回 `unavailable`。

可运行示例：

```text
python n_run.py examples/rtm_add_one.n --backend reference --samples 5 --json
python n_run.py examples/rtm_add_one.n --backend tl-native --samples 5 --json
python -m unittest discover -s tests -v
```

回执绑定源、NIR、工作负载、硬件摘要、搜索次数、验证次数、p50/p99、质量损失
和回退计数。该闭环的实测结果只代表绑定的 `rtm_add_one` workload；它不构成
n 普遍超过 C/Fortran 的结论。旧 `run_v13.py` 当前仍暴露 v0.12 历史回归失败，
与 RTM 新测试分开维护。

目标综合也已进入同一前端/IR：`goal` 保存目标顺序、候选指标和硬件要求，
`synthesize` 通过 `n_goal.py` 做确定性选择；例如：

```text
python n_run.py examples/goal_synthesis.n --synthesize add_one_plan --json
```

`n_fabric.py` 提供 CPU/GPU/NPU/CXL 的显式 capability probe。probe 只说明运行时
或设备是否可发现，不能替代具体 workload executor；当前缺少的 NPU/CXL 会保留为
`unavailable`，不会写成零成本或零回退。

## n 0.8-A Measured Goal + CPU SIMD（2026-10-02）

0.8-A 把 `goal/synthesize` 从声明指标排序推进为 workload-bound measured selection：

```text
.n -> semantic nIR -> measured candidate set -> planned nIR -> machine nIR -> x86-64 bytes
```

当前候选集合固定为 `reference_exact` 与 `cpu_simd_sse2`。每个候选都在同一 source、
workload、benchmark protocol 和 hardware digest 下测量；只有 RTM exact Echo/Commit
成功、quality loss 为零且 p50 已知的结果才可晋升。p50/p99、验证成本、搜索次数、
回退率和 selection receipt digest 都保留在回执中。任何缺失或不一致的绑定都会 fail
closed，未知延迟不会被写成 0。

在 SIMD 不可用时，选择器只能选择 `reference_exact`；reference executor 是安全的
可执行回退，不是对 SIMD 成本的模拟。Echo 失败、stale epoch、伪造 receipt 或计划
摘要不一致均不得提交状态。

本轮将 x64 SSE2 emitter 收敛为 n-owned `n_machine_encoder_x64.py`，历史 0.7 add-scalar
机器码摘要保持兼容。真实范围仍是 Windows x86-64/SSE2、contiguous CPU `f64`
`add_scalar` 单 field/wave/commit。GPU tile、NPU SRAM、CXL memory executor、通用
SSA/CFG、寄存器分配、自举和广泛性能优越性均保持 open；必须在对应硬件与绑定
workload 上取得新鲜回执后才能扩大结论。

可运行验证：

```text
python n_run.py examples/goal_synthesis.n --backend n-native --samples 3 --warmup-samples 1 --json
python n_run.py examples/goal_synthesis.n --synthesize add_one_plan --json
python -m unittest discover -s tests -p "test_n_*.py" -v
```

状态标签：`implemented_in_native_slice / measured_goal_cpu_simd / generalization_open`。

### n 0.8-B Selection Receipt Replay（2026-10-02）

0.8-B 为 measured selection 增加了可持久化、可校验的规范 receipt。`SelectionReceipt`
和 `CandidateMeasurement` 支持 canonical JSON round-trip；缺失或篡改 digest、未知策略、
缺失/重复候选都会 fail closed。回放路径不重新测量候选，而是重新验证 source、workload、
benchmark protocol、hardware、候选集和 receipt digest，随后复用相同的 planned -> machine
lowering。命令行通过 `--selection-receipt-in` 与 `--selection-receipt-out` 读写回执。

回放证据只对绑定的主机、工作负载、采样参数和当前实现有效；它不提供跨硬件或跨 workload
的性能结论。跨进程签名、通用 artifact store 和二进制 `.nib` 程序包仍未实现。

### n 0.8-C Binary nIR Artifact Codec（2026-10-02）

`n_ir_codec.py` 为统一 `n-ir/0.7` 增加确定性的 `.nir` 二进制 envelope：`NIR1` magic、
版本、payload 长度、SHA-256 和 canonical JSON。编解码覆盖 semantic/planned/machine
三个 phase，round-trip 保持 phase、模块 digest 和字节稳定；截断、尾随字节、未知版本、
长度/摘要错误、重复 key、旧 schema、非 canonical JSON 和超大 payload 都 fail closed。

该 codec 只保证 artifact 完整性与跨进程可恢复，不提供签名、schema migration、通用
artifact store 或跨硬件性能结论。

### n 0.8-D CLI nIR Artifact Emission（2026-10-03）

`n-run` 现在可以直接把 `.n` 源码导出为确定性的 `.nir` artifact：

```text
python n_run.py examples/rtm_add_one.n --emit-nir out/semantic.nir --json
python n_run.py examples/rtm_add_one.n --emit-nir out/machine.nir --emit-phase machine --json
```

默认 phase 为 `semantic`。`planned` 和 `machine` 导出会复用完整的
`compile_source -> PlanManifest -> phase verifier` 链；导出失败时不会写出不完整
artifact。JSON 回执报告 `phase`、`nir_digest` 和 `bytes`，不把 artifact 完整性误报为
签名、性能或跨硬件真实性证明。

## n 原生编译纵切 0.50（2026-10-01）

架构主线已收敛为 n：`.n -> n_front -> NIR -> PlanManifest -> n-LIR -> n-owned x86-64
lowering -> executable -> RTM Echo/Commit -> receipt`。旧 tl parser、AST、VM、
固定内核分派和 C DLL 不参与 `.n` 的新原生路径；旧 `.tl`、自举材料和回归仍保留。

当前真实原生范围严格限于 Windows x86-64/SSE2、contiguous CPU `f64`
`add_scalar` 单 field/wave/commit。可运行：

```text
python n_run.py examples/rtm_add_one.n --backend n-native --samples 5 --warmup-samples 1 --json
python -m unittest discover -s tests -p "test_n_*.py" -v
```

后端把 `.n` 解析并降低的 NIR 转为带 buffer/effect/loop/numeric contract 的 n-LIR，
再编译为 SSE2 packed-double 指令，经 RW->RX
内存保护转换执行；exact Echo 与 epoch 校验通过后才提交。回执另行记录编译成本、
后端初始化、验证成本、提交数、回退率以及 plan/code digest。现有 `goal/synthesize`
仍是候选指标排序原型，声明的 cost/quality 不是实测值，也尚未驱动原生计划选择。

这证明了一个端到端 native workload，不代表通用 n-LIR、寄存器分配、完整编译器、
自举完成或普遍快于 C/Fortran。GPU tile、NPU SRAM、CXL 执行器和 measured-goal
搜索仍未实现；旧 tl stage 状态须由可重放的构建、摘要比较和真机执行单独核验。

## n 0.7 Unified Phased IR（原生纵切已实现）

0.7 将当前独立的 NIR 与 n-LIR 容器合并为一个有阶段约束的 `nIRModule`：

```text
.n -> nIR.semantic -> nIR.planned -> nIR.machine -> machine code
```

三个 phase 共用 value/type/shape/effect/region/provenance/digest 数据模型；lowering
改为同一模块上的 `RewriteDelta` 或结构共享快照，不再完整复制并重建另一棵 IR。
每个 phase 仍有严格的 operation legality 和 verifier：语义阶段不能出现寄存器/ABI，
机器阶段不能保留未解析的 `goal/synthesize`，代码生成器只接受已验证的 `machine`
snapshot。`PlanManifest` 退回为候选选择、证据、硬件、回退和摘要索引，不成为第三套
IR。

当前原生路径已经迁移为 `semantic -> planned -> machine` 摘要链：`n_ir.py` 提供
`IRPhase`、统一 operation/value/region 表和 `RewriteDelta`，`n_ir_verify.py` 分层验证
结构、语义、phase 和 target；`PlanManifest` 作为外部不可变索引绑定三阶段摘要，
`n_codegen_x64.py` 的权威入口只接受通过 machine verifier 的模块。`LIRKernel` 和旧
`lower_lir` 仍是只读兼容投影，差分测试证明它与 machine 新入口生成相同机器码。

本轮 44 个 n 测试连续两次通过，Windows x86-64/SSE2 真机 CLI 返回 `committed`。
回执分别记录 semantic/planned/machine digest、节点数、rewrite 数、序列化和 phase
验证成本，以及 kernel p50/p99、质量损失和回退率。该实现仍只覆盖 contiguous CPU
`f64 add_scalar`；尚未实现 arena 结构共享、通用 CFG/SSA、完整寄存器分配或跨设备
后端，因此不能仅凭“少一层”宣称运行时或编译器普遍更快。

设计和迁移计划：

- `docs/superpowers/specs/2026-10-01-n-0.7-unified-phased-ir-design.md`
- `docs/superpowers/plans/2026-10-01-n-0.7-unified-phased-ir.md`

旧 tl v0.7（增量训练）和原 n-0.7（MemoryStore/多螺旋）保留为历史编号；本方案
使用完整名称 **n 0.7 Unified Phased IR**，不覆盖历史验证记录。
