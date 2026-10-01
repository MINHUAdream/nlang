# n RTM Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `tl-lang` 中实现不依赖旧 tl AST 的 n RTM 最小闭环，并复用现有自研 CPU 内核作为可验证后端。

**Architecture:** 新 `n_front.py` 解析 `.n` 语法并生成 `n_ir.py` 中的规范 IR；`n_rtm.py` 负责 Field/Wave/Echo/Commit 的原子语义；`n_backend_tl.py` 适配 `tl_native`/`tl_emit`，不把旧 VM 引入 n 语义。旧 tl 文件和回归脚本保持不变。

**Tech Stack:** Python 3 标准库、现有 `tl_native.py`、现有 `tl_emit.py`、pytest-like `unittest`（不新增第三方依赖）。

**Spec:** `docs/superpowers/specs/2026-09-30-n-rtm-foundation-design.md`

**Execution status:** Tasks 1-6 are implemented; the new suite has 11 passing tests.
Task 7 documentation is updated. The historical `run_v13.py` command remains exit=1
because its existing v0.12 regression reports failure; that is tracked separately.

## Global Constraints

- `.tl`、`tl.py`、`tlb.py`、`tl_emit.py`、`tl_native.py` 和 v09-v13 回归继续可运行。
- 新 `.n` 前端不生成旧 tl AST，直接生成 NIR-RTM。
- `Wave` 不能直接改变 `Field`；只有通过 `Echo` 的 delta 才能 commit。
- `unknown` 不能升级为证明；不可用后端不能伪造 measured 数据。
- NIR round-trip 必须保持 SHA-256 digest 不变。
- 旧回归失败必须与新 RTM 测试分开报告。

---

### Task 1: 建立 RTM 失败测试

**Files:**
- Create: `tests/test_n_rtm.py`
- Create: `examples/rtm_add_one.n`

**Interfaces:**
- Tests import `n_front.parse`, `n_ir.lower`, `n_rtm.Runtime`, `n_backend_tl.ReferenceBackend`.
- The tests define the exact public behavior required by later tasks.

- [ ] **Step 1: Write the failing tests**

```python
def test_parse_lower_round_trip():
    module = parse(open("examples/rtm_add_one.n", encoding="utf-8").read())
    nir = lower(module)
    assert NIRModule.from_dict(nir.to_dict()).digest == nir.digest

def test_exact_commit_advances_epoch():
    runtime = Runtime(reference_backend())
    receipt = runtime.run(source, {"x": [1.0, 2.0, 3.0, 4.0]})
    assert receipt.status == "committed"
    assert runtime.field("x").values == [2.0, 3.0, 4.0, 5.0]
    assert runtime.field("x").epoch == 1

def test_stale_wave_and_echo_failure_do_not_mutate_field():
    runtime = Runtime(reference_backend())
    wave = runtime.prepare_wave("add_one", "x")
    runtime.commit(wave, runtime.echo_exact(wave))
    assert runtime.commit(wave, runtime.echo_exact(wave)).status == "stale"
    bad = runtime.prepare_wave("add_one", "x", expected=[99.0, 99.0, 99.0, 99.0])
    assert runtime.commit(bad, runtime.echo_exact(bad)).status == "echo_failed"
    assert runtime.field("x").values == [2.0, 3.0, 4.0, 5.0]
```

- [ ] **Step 2: Run the new test to verify it fails**

Run: `python -m unittest tests.test_n_rtm -v`

Expected: FAIL with import errors for `n_front`, `n_ir`, `n_rtm`, or the missing runtime interfaces.

- [ ] **Step 3: Add the example source**

The example must contain exactly one `f32[4]` field named `x`, one `add_one` wave, an exact echo, and a `commit add_one into x;` statement.

- [ ] **Step 4: Re-run the test and confirm the failure is still feature-related**

Run: `python -m unittest tests.test_n_rtm -v`

Expected: import/API failures only; no parser syntax typo or missing test fixture.

### Task 2: Implement the standalone n lexer/parser

**Files:**
- Create: `n_front.py`
- Modify: `tests/test_n_rtm.py`

**Interfaces:**
- `parse(source: str) -> NModule`
- `NModule.fields: tuple[NFieldDecl, ...]`
- `NModule.waves: tuple[NWaveDecl, ...]`
- `NModule.commits: tuple[NCommitDecl, ...]`
- `NWaveDecl.operations: tuple[NWaveOp, ...]`

- [ ] **Step 1: Add parser-only assertions**

```python
def test_parser_preserves_field_wave_and_commit_order():
    module = parse(SOURCE)
    assert module.fields[0].name == "x"
    assert module.waves[0].operations[0].kind == "read"
    assert module.waves[0].operations[1].kind == "write"
    assert module.commits[0].wave == "add_one"
```

- [ ] **Step 2: Run the parser test and verify it fails**

Run: `python -m unittest tests.test_n_rtm.RTMParserTests.test_parser_preserves_field_wave_and_commit_order -v`

Expected: FAIL because `n_front.py` does not exist.

- [ ] **Step 3: Implement minimal lexer and recursive-descent parser**

The lexer recognizes identifiers, decimal numbers, `:`, `[`, `]`, `(`, `)`, `{`, `}`, `;`, `->`, and keywords `module`, `field`, `layout`, `device`, `wave`, `read`, `write`, `delta`, `echo`, `exact`, `fallback`, `reject`, `commit`, `into`. Every parse error includes the byte offset. Reject duplicate field/wave names and unknown wave operations.

- [ ] **Step 4: Run the parser tests**

Run: `python -m unittest tests.test_n_rtm -v`

Expected: parser assertions pass; lower/runtime tests still fail on missing modules.

### Task 3: Implement canonical NIR-RTM

**Files:**
- Create: `n_ir.py`
- Modify: `tests/test_n_rtm.py`

**Interfaces:**
- `NIRModule.to_dict() -> dict`
- `NIRModule.from_dict(payload) -> NIRModule`
- `NIRModule.canonical_json() -> str`
- `NIRModule.digest -> str`
- `lower(module: NModule) -> NIRModule`

- [ ] **Step 1: Add digest and lowering assertions**

```python
def test_nir_contains_explicit_rtm_nodes():
    nir = lower(parse(SOURCE))
    assert [node["kind"] for node in nir.nodes] == ["field", "wave", "commit"]
    assert nir.digest == NIRModule.from_dict(json.loads(nir.canonical_json())).digest
```

- [ ] **Step 2: Run the test and verify the intended failure**

Run: `python -m unittest tests.test_n_rtm.RTMIRTests -v`

Expected: FAIL because `n_ir.py` does not exist.

- [ ] **Step 3: Implement deterministic IR**

Use frozen dataclasses or immutable mappings. Sort object keys and wave operations only where the source semantics declares them unordered; preserve source order for operations and commits. Hash UTF-8 canonical JSON with `hashlib.sha256`.

- [ ] **Step 4: Run all RTM tests**

Run: `python -m unittest tests.test_n_rtm -v`

Expected: parser and IR tests pass; runtime tests still fail until Task 4.

### Task 4: Implement Field/Wave/Echo/Commit runtime

**Files:**
- Create: `n_rtm.py`
- Modify: `tests/test_n_rtm.py`

**Interfaces:**
- `Runtime(backend: Backend)`
- `Runtime.load(module: NIRModule, initial: Mapping[str, Sequence[float]]) -> None`
- `Runtime.prepare_wave(wave_name: str, field_name: str, expected=None) -> PreparedWave`
- `Runtime.echo_exact(wave: PreparedWave) -> EchoResult`
- `Runtime.commit(wave: PreparedWave, echo: EchoResult) -> CommitResult`
- `Runtime.field(name: str) -> RuntimeField`

- [ ] **Step 1: Add failure-mode assertions**

```python
def test_unknown_fallback_is_not_a_commit():
    runtime = Runtime(reference_backend())
    wave = runtime.prepare_wave("add_one", "x")
    result = runtime.commit(wave, EchoResult("unknown", None))
    assert result.status == "fallback_required"
    assert runtime.field("x").epoch == 0
```

- [ ] **Step 2: Run and verify red**

Run: `python -m unittest tests.test_n_rtm -v`

Expected: runtime import or missing method failures.

- [ ] **Step 3: Implement atomic runtime**

`RuntimeField` owns a copied value and integer epoch. `PreparedWave` captures the base epoch and the backend-produced delta. `EchoResult` has `status` in `pass/fail/unknown`. `commit` checks status, epoch, expected output, and write set before copying values and incrementing epoch. A failed operation leaves values and epoch unchanged.

- [ ] **Step 4: Run RTM tests**

Run: `python -m unittest tests.test_n_rtm -v`

Expected: all parser, IR, and runtime tests pass except any backend adapter test reserved for Task 5.

### Task 5: Add reference and tl-native backend adapters

**Files:**
- Create: `n_backend_tl.py`
- Modify: `tests/test_n_rtm.py`

**Interfaces:**
- `Capability(status: str, features: frozenset[str], detail: str | None)`
- `ReferenceBackend.probe() -> Capability`
- `ReferenceBackend.execute(wave: IRWave, field: RuntimeField) -> Delta`
- `TLNativeBackend.probe() -> Capability`
- `TLNativeBackend.execute(wave: IRWave, field: RuntimeField) -> Delta`

- [ ] **Step 1: Add adapter parity test**

```python
def test_tl_native_or_unavailable_is_explicit():
    backend = TLNativeBackend()
    capability = backend.probe()
    if capability.status == "available":
        assert backend.execute(ADD_ONE_WAVE, FIELD).values == REFERENCE_VALUES
    else:
        assert capability.status == "unavailable"
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `python -m unittest tests.test_n_rtm.RTMBackendTests -v`

Expected: FAIL because `n_backend_tl.py` does not exist.

- [ ] **Step 3: Implement adapters**

Reference execution performs `add_scalar` over a copied flat float sequence. The tl adapter imports `tl_native` lazily and uses an existing elementwise/add kernel only when the module and symbol are available; otherwise it returns `Capability("unavailable", frozenset(), reason)`. It must never label Python fallback as native.

- [ ] **Step 4: Run adapter and full RTM tests**

Run: `python -m unittest tests.test_n_rtm -v`

Expected: all RTM tests pass and unavailable hardware is reported explicitly.

### Task 6: Add receipt generation and regression entrypoint

**Files:**
- Create: `n_measure.py`
- Create: `n_run.py`
- Create: `tests/test_n_measure.py`

**Interfaces:**
- `RTMReceipt.to_dict() -> dict`
- `measure(source, initial, backend) -> RTMReceipt`
- `n_run.py <path> --json` prints one JSON receipt and exits nonzero for compile/commit failure.

- [ ] **Step 1: Write receipt binding tests**

Assert that source, NIR, backend, workload, status, search count, verification calls, fallback count, p50, p99, and quality loss keys exist; unavailable values are `None`, not `0`.

- [ ] **Step 2: Run to verify red**

Run: `python -m unittest tests.test_n_measure -v`

Expected: import failure for `n_measure`.

- [ ] **Step 3: Implement deterministic receipt and CLI**

Use `time.perf_counter_ns()` for samples, `statistics.quantiles` only when at least two samples exist, and SHA-256 for source/workload/NIR identities. Keep measurement status separate from capability status.

- [ ] **Step 4: Run measurement tests and the CLI**

Run: `python -m unittest tests.test_n_measure -v`

Run: `python n_run.py examples/rtm_add_one.n --json`

Expected: exit 0 with one JSON receipt whose status is `committed` and whose digest fields are non-empty.

### Task 7: Run old and new verification suites

**Files:**
- Modify: `README.md`
- Modify: `N_DESIGN.md`
- Modify: `N_DESIGN_AUDIT.md`

- [ ] **Step 1: Run new suite**

Run: `python -m unittest discover -s tests -v`

Expected: all new RTM tests pass.

- [ ] **Step 2: Run syntax/build checks**

Run: `python -m compileall -q n_front.py n_ir.py n_rtm.py n_backend_tl.py n_measure.py n_run.py`

Expected: exit code 0 with no traceback.

- [ ] **Step 3: Run the historical regression without reinterpreting it**

Run: `python run_v13.py`

Record the exit code and every failed check. Do not change old claims or mark the old suite green unless the command actually exits 0.

- [ ] **Step 4: Document status**

Add a short section linking the RTM spec, the CLI, the exact new test command, and any pre-existing v13 failures. Do not claim GPU/NPU/CXL availability without a probe result.
