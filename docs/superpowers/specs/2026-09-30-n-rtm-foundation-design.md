# n RTM 基础闭环设计

## 目标

把 n 的执行核心从旧 tl 的“语句 AST + Python 调度”提升为可验证的
Resonant Transition Machine（RTM）基础闭环，同时保留 tl 的历史程序、
自研 C 内核和 x86-64 发射器作为兼容/后端资产。第一阶段只实现可独立验收的
`field -> wave -> echo -> commit` 路径，不承诺所有物理启发或所有设备后端。

## 设计决定

### 1. 兼容边界

- `.tl`、`tl.py`、`tlb.py`、`tl_emit.py`、`tl_native.py` 和 v09-v13 回归继续可运行。
- 新 `.n` 前端不生成旧 tl AST；它直接生成 NIR-RTM。
- 兼容只存在于 `n_backend_tl.py` 适配层：NIR-RTM 可调用已验证的 `tl_emit`/`tl_native` 内核。
- n 语义不依赖 Python 对象图、旧 VM 槽值或旧 parser；后续可以替换这些适配层而不改变 n-IR。

### 2. 核心对象

```text
Field[T] = { name, epoch, shape, layout, device, values, dependencies }
Wave[T] = { name, base_epoch, reads, writes, delta, error, cost, fallback }
Echo     = { mode, sample, residual_max, reference }
Commit   = { field, delta, verified, new_epoch }
Regime   = { stable | critical | congested | frozen | failed, score }
```

`Wave` 永远不能直接改变 `Field`。只有 `Echo` 返回 `pass` 且 epoch 未过期时，
`commit` 才能应用 delta。`unknown` 和 `fail` 都走 fallback 或返回拒绝。

### 3. 语法子集

第一阶段支持下面的最小语法，其他内容必须产生带位置的编译错误：

```n
module demo;

field x: f32[4] layout contiguous device cpu;

wave add_one(x) -> delta {
    read x;
    write x;
    delta add_scalar 1.0;
    echo exact;
    fallback reject;
}

commit add_one into x;
```

`field` 初始值由运行 API 提供；没有隐式零初始化。`wave` 的 `delta add_scalar`
是第一阶段唯一内置操作，用于验证状态、验证和后端接口；真实 kernel 通过
`BackendRegistry` 注册，不在 parser 中硬编码。

### 4. NIR-RTM

NIR 使用规范化 JSON 作为审计格式，同时计算 SHA-256 digest。IR 节点必须只含
标量、数组和映射，不保存 Python 对象引用。`NIRModule.from_dict(module.to_dict())`
必须得到相同 digest。规范节点为 `module`、`field`、`wave`、`echo`、`commit`。

### 5. 后端契约

```python
class Backend(Protocol):
    name: str
    def probe(self) -> Capability: ...
    def execute(self, wave: IRWave, field: RuntimeField) -> Delta: ...
```

`probe` 只能说明设备/运行时存在；`execute` 成功执行具体工作负载后才允许产生
`measured` 结果。第一阶段提供 `ReferenceBackend` 和 `TLNativeBackend`：后者
复用现有 `tl_native` 的逐位内核，并在模块不可导入或 kernel 缺失时返回明确的
`unavailable`，不能静默伪造数据。

### 6. 失败和并发规则

- `base_epoch != field.epoch` 返回 `StaleWave`，不改变 field。
- delta 写集重叠且没有 merge law 时返回 `Conflict`。
- `echo=exact` 用 reference backend 比较完整结果；采样 echo 只能返回
  `pass/fail/unknown`，不能把 unknown 升级为证明。
- commit 是原子操作：验证失败、冲突或 fallback 拒绝时不留下半更新。
- 第一阶段只实现单 field 单 wave；异步 branch/merge 接口预留，但不假装已经并行。

### 7. 性能与测量

每次执行生成 `RTMReceipt`，绑定 `source_digest`、`nir_digest`、`backend`、
`hardware_digest`、`workload_digest`、搜索次数、验证调用数、p50/p99、质量损失、
回退次数和状态。未知字段为 `null`，不可用后端状态为 `unavailable`。

验收不使用“理论超过 C/Fortran”作为结论；必须在相同 workload、输入、线程、
编译/调度计时口径和正确性门槛下比较。

## 明确延后

`regime` 的自动切换、局部 refine、异步 mailbox、multi-radix、GPU tile、NPU SRAM、
CXL memory、`derive` 多目标分析和真实 branch/merge 都作为后续阶段；它们只能复用
本规格的 Field/Wave/Echo/Commit 边界，不能另起一套状态提交机制。

## 验收标准

1. 新 parser 能解析上述 `.n` 示例，并拒绝未知 wave 操作、重复 field 和非法 commit。
2. NIR round-trip digest 稳定。
3. ReferenceBackend 能执行 `add_scalar`，exact echo 通过时 epoch 加一。
4. stale wave、echo fail、fallback reject 和写冲突均保持 field 不变。
5. TLNativeBackend 在当前机器可用时逐位等于参考结果；不可用时返回可检查状态。
6. 新测试通过，且 `run_v13.py` 的旧回归输出保持原状（旧回归自身失败必须单独报告）。
