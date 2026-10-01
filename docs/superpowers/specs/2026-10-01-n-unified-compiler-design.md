# n Unified Compiler Architecture

## Decision

n is the single language and compiler architecture. The old tl compiler remains a
compatibility and bootstrap asset while n grows its own typed IR, lowering stages,
machine-code backend, runtime, and eventual self-hosting path. Shared historical
claims do not make tl's parser, AST, VM, or fixed kernel table part of n semantics.

The authoritative path is:

```text
.n source
  -> n frontend and semantic validation
  -> canonical NIR
  -> measured/constraint-checked plan manifest
  -> target-specific n-LIR
  -> n-owned machine-code lowering
  -> native executable artifact
  -> RTM Echo/Commit runtime
  -> digest-bound measurement receipt
```

The compiler plan and runtime state machine are distinct. A plan describes how a
program may execute and is immutable, content-addressed, and validated against
the exact source, NIR, target, shape, numeric profile, and required capabilities.
RTM waves create candidate state; only a valid Echo at the matching epoch may
commit it. Neither layer may silently substitute a backend or change the program's
objective.

## Compiler Boundaries

### Frontend and NIR

`n_front.py` owns `.n` lexing and parsing. `n_ir.py` owns deterministic lowering
and serialization. NIR is the semantic contract between parsing, optimization,
planning, and backends; Python AST objects and legacy tl nodes do not cross this
boundary. The current NIR schema is a prototype and must be versioned before
persisted artifacts become a compatibility promise.

The next NIR revision must separate value flow, effects, shape/layout, numeric
contracts, and device placement instead of encoding every decision in loosely
typed JSON nodes. Runtime versions and branch/merge state remain RTM concerns;
they are not compiler optimization metadata.

### Plans and evidence

`PlanManifest` is the checked contract between a candidate plan and a backend. It
binds source and NIR digests, plan identity, target ABI, field shape/layout/type,
operation, numeric semantics, fallback, and required features. The backend rejects
stale, malformed, unsupported, or digest-mismatched manifests.

`goal`/`synthesize` may enumerate and rank declared candidates, but declared metric
numbers are estimates, not measurements. A performance-based selection is valid
only when each scored metric comes from receipts for the same frozen workload,
objective, hardware, and measurement protocol. Unknown costs are not zero. The
current `n_goal.py` behavior remains a deterministic planning prototype until
measured-candidate admission is implemented.

### Lowering and native execution

The initial target-neutral n-LIR is typed and canonical: it makes buffers, read/write
effects, loop extent, numeric operation, numeric contract, and fallback explicit.
The general form still needs control-flow regions, conversions, vector scheduling,
and data movement. Backends consume n-LIR, not source syntax or goal declarations.

The first native slice supports only contiguous CPU `f64` `add_scalar` waves on
Windows x86-64/SSE2. It lowers validated NIR into the initial n-LIR and then into
n-owned x86-64 bytes, executing them through a write-then-execute memory transition.
The n-LIR must be generalized before adding a second substantial backend or a broad
set of operations. Unsupported targets and
operations return an explicit unavailable/unsupported result; the reference
backend remains the semantic oracle. This slice is evidence that the
source-to-machine-code path exists, not evidence of general compiler maturity or
superiority over C/Fortran.

### Runtime and measurement

RTM remains the one state-transition protocol: `Field -> Wave -> Echo -> Commit`.
Backends return candidate deltas and never mutate fields. Exact Echo compares with
the reference semantics; commit verifies the proof token, write size, and epoch.

Receipts distinguish frontend/lowering/code-generation time, backend initialization,
execution/verification latency, commit count, candidate search count, fallback
rate, quality loss, and unavailable/unknown values. They bind source, NIR, plan,
machine code, workload, hardware, compiler, runtime, backend, benchmark protocol,
and result digests. A p99 from too few samples is still labeled with its sample
count and is not a general performance claim.

## Legacy tl Migration

- Preserve `.tl`, historical command dispatch, bootstrap artifacts, and regression
  scripts while they remain useful and reproducible.
- Do not route `.n` through `tl.py`, `tl_kern.py`, `tl_native.py`, or legacy tl AST.
- The fixed `tl_emit` kernel table is not n's backend architecture.
- Retain old tl code-generation experiments as compatibility/reference material;
  migrate only independently tested instruction-encoding primitives into n-owned
  modules.
- Python may host the transitional driver, tests, and reference oracle. It is not
  the final n runtime or self-hosting proof.
- Do not claim stage1/stage2 self-hosting based on artifact presence. Each stage
  requires a reproducible bootstrap command, output digest comparison, and runtime
  execution check.

## Increment Scope

This increment adds a real `.n` to x86-64 code path for the one supported f64
operation, validates a digest-bound manifest, integrates its compile/init/verify/
commit costs into receipts, and exposes the backend in the n CLI. It does not
implement general n-LIR, register allocation, GPU/NPU/CXL executors, automatic
measured goal search, a portable object format/linker, or self-hosted compilation.

## Acceptance

1. A supported `.n` source produces stable NIR, a manifest bound to source/NIR,
   and non-empty n-owned machine code.
2. Changing the source, NIR, shape, type, operation, or target invalidates the
   previous manifest.
3. The supported native operation matches the reference result for even, odd,
   and one-element vectors; exact Echo and RTM commit are required.
4. Unsupported type, layout, device, wave shape, and operation are rejected before
   execution; unavailable hardware never reports fabricated latency.
5. Measurement receipts include compile cost, backend initialization, verification
   cost, commit count, and fallback rate, with the corresponding digests.
6. New n tests pass independently. Historical tl failures are reported separately
   and are not silently rewritten as passing.
