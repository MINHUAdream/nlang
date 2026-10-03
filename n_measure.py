"""Workload-bound measurement receipts for the RTM subset."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import platform
import time
from typing import Any, Mapping, Sequence

from n_front import parse
from n_goal import CandidateMeasurement, CandidateSpec
from n_ir import lower
from n_ir_verify import verify_phase
from n_rtm import Runtime


def _digest(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_digest(names: Sequence[str]) -> str:
    root = __import__("pathlib").Path(__file__).resolve().parent
    sources = {name: (root / name).read_bytes().hex() for name in names}
    return _digest(sources)


def _hardware_digest() -> str:
    from n_fabric import probe_fabric

    return _digest(
        {
            "platform": platform.uname()._asdict(),
            "fabric": {
                name: {
                    "status": capability.status,
                    "features": sorted(capability.features),
                    "detail": capability.detail,
                }
                for name, capability in probe_fabric().items()
            },
        }
    )


def selection_bindings(
    source: str,
    initial: Mapping[str, Sequence[float]],
    *,
    samples: int,
    warmup_samples: int,
) -> dict[str, str]:
    """Return the immutable bindings required to replay goal selection."""

    return {
        "source_digest": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "workload_digest": _digest(
            {name: list(values) for name, values in sorted(initial.items())}
        ),
        "benchmark_digest": _digest(
            {
                "samples": samples,
                "warmup_samples": warmup_samples,
                "measured_region": "rtm.run:prepare+execute+echo+commit",
                "selection_policy": "adaptive-fastest",
            }
        ),
        "hardware_digest": _hardware_digest(),
    }


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def measure_candidates(
    source: str,
    initial: Mapping[str, Sequence[float]],
    candidates: Sequence[CandidateSpec],
    *,
    samples: int = 5,
    warmup_samples: int = 1,
) -> tuple[CandidateMeasurement, ...]:
    """Measure declared candidates against one immutable workload binding."""

    if samples < 1:
        raise ValueError("samples must be positive")
    if warmup_samples < 0:
        raise ValueError("warmup_samples cannot be negative")
    bindings = selection_bindings(
        source,
        initial,
        samples=samples,
        warmup_samples=warmup_samples,
    )
    semantic = lower(parse(source))
    results: list[CandidateMeasurement] = []
    for candidate in candidates:
        if candidate.name not in {"reference_exact", "cpu_simd_sse2"}:
            measurement = CandidateMeasurement(
                candidate.name,
                "unavailable",
                None,
                None,
                None,
                None,
                None,
                None,
                "no executor registered for candidate backend",
            )
        else:
            from n_compile import _measure_candidate

            measurement = _measure_candidate(
                source,
                semantic,
                candidate.name,
                target="x86_64-windows",
                initial=initial,
                samples=samples,
                warmup_samples=warmup_samples,
            )
        results.append(
            replace(
                measurement,
                **bindings,
            )
        )
    return tuple(results)


@dataclass(frozen=True)
class RTMReceipt:
    status: str
    backend: str
    source_digest: str
    nir_digest: str
    workload_digest: str
    hardware_digest: str
    compiler_digest: str
    runtime_digest: str
    backend_digest: str
    benchmark_digest: str
    result_digest: str | None
    plan_digest: str | None
    lir_digest: str | None
    code_digest: str | None
    compile_cost_ms: float
    backend_init_ms: float
    verification_cost_ms: float | None
    search_count: int | None
    verification_calls: int | None
    p50_ms: float | None
    p99_ms: float | None
    quality_loss: float | None
    fallback_count: int | None
    commit_count: int | None
    fallback_rate: float | None
    samples: int
    warmup_samples: int
    semantic_digest: str
    planned_digest: str | None
    machine_digest: str | None
    semantic_nodes: int
    planned_nodes: int | None
    machine_nodes: int | None
    rewrite_count: int
    serialization_cost_ms: float
    phase_verify_cost_ms: float
    detail: str | None = None
    candidate_set_digest: str | None = None
    selected_candidate: str | None = None
    selection_receipt_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def measure(
    source: str,
    initial: Mapping[str, Sequence[float]],
    backend: Any,
    *,
    samples: int = 5,
    warmup_samples: int = 1,
) -> RTMReceipt:
    if samples < 1:
        raise ValueError("samples must be positive")
    if warmup_samples < 0:
        raise ValueError("warmup_samples cannot be negative")
    source_digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    compile_started = time.perf_counter_ns()
    compiler = getattr(backend, "compile_source", None)
    compilation = (
        compiler(
            source,
            initial=initial,
            samples=samples,
            warmup_samples=warmup_samples,
        )
        if callable(compiler)
        else None
    )
    nir = compilation.nir if compilation is not None else lower(parse(source))
    if compilation is not None:
        semantic_digest = compilation.semantic.digest
        planned_digest = compilation.planned.digest
        machine_digest = compilation.machine.digest
        semantic_nodes = len(compilation.semantic.operations)
        planned_nodes = len(compilation.planned.operations)
        machine_nodes = len(compilation.machine.operations)
        rewrite_count = sum(
            snapshot.rewrite is not None
            for snapshot in (compilation.semantic, compilation.planned, compilation.machine)
        )
        serialization_cost_ms = compilation.serialization_cost_ms
        phase_verify_cost_ms = compilation.phase_verify_cost_ms
    else:
        verify_started = time.perf_counter_ns()
        verify_phase(nir)
        phase_verify_cost_ms = (time.perf_counter_ns() - verify_started) / 1_000_000.0
        serialization_started = time.perf_counter_ns()
        nir.canonical_json()
        serialization_cost_ms = (
            time.perf_counter_ns() - serialization_started
        ) / 1_000_000.0
        semantic_digest = nir.digest
        planned_digest = None
        machine_digest = None
        semantic_nodes = len(nir.operations)
        planned_nodes = None
        machine_nodes = None
        rewrite_count = 0
    compile_cost_ms = (time.perf_counter_ns() - compile_started) / 1_000_000.0
    plan_digest = compilation.manifest.digest if compilation is not None else None
    lir_digest = compilation.lir.digest if compilation is not None else None
    code_digest = compilation.code_digest if compilation is not None else None
    candidate_set_digest = (
        compilation.manifest.candidate_set_digest if compilation is not None else None
    )
    selected_candidate = (
        compilation.manifest.selected_candidate if compilation is not None else None
    )
    selection_receipt_digest = (
        compilation.manifest.selection_receipt_digest if compilation is not None else None
    )
    workload_digest = _digest({name: list(values) for name, values in sorted(initial.items())})
    hardware_digest = _hardware_digest()
    compiler_digest = _file_digest(
        (
            "n_front.py",
            "n_ir.py",
            "n_ir_verify.py",
            "n_goal.py",
            "n_plan.py",
            "n_lir.py",
            "n_codegen_x64.py",
            "n_machine_encoder_x64.py",
            "n_compile.py",
            "n_ops.py",
        )
    )
    runtime_digest = _file_digest(("n_rtm.py",))
    backend_files = {
        "n-native-x64-sse2-f64": (
            "n_native.py",
            "n_backend_types.py",
            "n_codegen_x64.py",
            "n_machine_encoder_x64.py",
            "n_ops.py",
        ),
        "cpu-simd-sse2-f64": (
            "n_backend_simd.py",
            "n_backend_types.py",
            "n_machine_encoder_x64.py",
            "n_ops.py",
        ),
        "tl-native": ("n_backend_tl.py", "n_backend_types.py", "n_ops.py"),
        "reference": ("n_backend_tl.py", "n_backend_types.py", "n_ops.py"),
    }.get(getattr(backend, "name", ""), ("n_backend_tl.py", "n_backend_types.py", "n_ops.py"))
    backend_digest = _file_digest(backend_files)
    benchmark_digest = _digest(
        {
            "samples": samples,
            "warmup_samples": warmup_samples,
            "clock": "perf_counter_ns",
            "measured_region": "rtm.run:prepare+execute+echo+commit",
            "compile_region": "parse+lower+plan+codegen",
            "backend_init_region": "probe+executable_load",
            "percentile_method": "linear_interpolation",
        }
    )
    from n_backend_tl import ReferenceBackend

    execution_backend = (
        ReferenceBackend()
        if selected_candidate == "reference_exact"
        else backend
    )
    receipt_backend_name = getattr(execution_backend, "name", type(execution_backend).__name__)
    init_started = time.perf_counter_ns()
    capability = execution_backend.probe()
    if (
        capability.status == "available"
        and compilation is not None
        and hasattr(execution_backend, "initialize")
    ):
        execution_backend.initialize(compilation)
    backend_init_ms = (time.perf_counter_ns() - init_started) / 1_000_000.0

    search_count = (
        compilation.selection_receipt.search_count
        if compilation is not None and compilation.selection_receipt is not None
        else 0
    )
    if compilation is None or compilation.selection_receipt is None:
        for node in nir.nodes:
            if node.get("kind") == "synthesize":
                from n_goal import synthesize

                decision = synthesize(
                    nir,
                    str(node["goal"]),
                    available_features=capability.features,
                )
                search_count += decision.search_count
                if decision.status != "selected":
                    return RTMReceipt(
                        status=f"planning_{decision.status}",
                        backend=receipt_backend_name,
                    source_digest=source_digest,
                    nir_digest=nir.digest,
                    workload_digest=workload_digest,
                    hardware_digest=hardware_digest,
                    compiler_digest=compiler_digest,
                    runtime_digest=runtime_digest,
                    backend_digest=backend_digest,
                    benchmark_digest=benchmark_digest,
                    result_digest=None,
                    plan_digest=plan_digest,
                    lir_digest=lir_digest,
                    code_digest=code_digest,
                    compile_cost_ms=compile_cost_ms,
                    backend_init_ms=backend_init_ms,
                    verification_cost_ms=None,
                    search_count=search_count,
                    verification_calls=None,
                    p50_ms=None,
                    p99_ms=None,
                    quality_loss=None,
                    fallback_count=None,
                    commit_count=None,
                    fallback_rate=None,
                    samples=0,
                    warmup_samples=warmup_samples,
                    semantic_digest=semantic_digest,
                    planned_digest=planned_digest,
                    machine_digest=machine_digest,
                    semantic_nodes=semantic_nodes,
                    planned_nodes=planned_nodes,
                    machine_nodes=machine_nodes,
                    rewrite_count=rewrite_count,
                    serialization_cost_ms=serialization_cost_ms,
                    phase_verify_cost_ms=phase_verify_cost_ms,
                        detail=decision.detail,
                        candidate_set_digest=candidate_set_digest,
                        selected_candidate=selected_candidate,
                        selection_receipt_digest=selection_receipt_digest,
                    )
    if capability.status != "available":
        return RTMReceipt(
            status="unavailable",
            backend=receipt_backend_name,
            source_digest=source_digest,
            nir_digest=nir.digest,
            workload_digest=workload_digest,
            hardware_digest=hardware_digest,
            compiler_digest=compiler_digest,
            runtime_digest=runtime_digest,
            backend_digest=backend_digest,
            benchmark_digest=benchmark_digest,
            result_digest=None,
            plan_digest=plan_digest,
            lir_digest=lir_digest,
            code_digest=code_digest,
            compile_cost_ms=compile_cost_ms,
            backend_init_ms=backend_init_ms,
            verification_cost_ms=None,
            search_count=search_count if search_count else None,
            verification_calls=None,
            p50_ms=None,
            p99_ms=None,
            quality_loss=None,
            fallback_count=None,
            commit_count=None,
            fallback_rate=None,
            samples=0,
            warmup_samples=warmup_samples,
            semantic_digest=semantic_digest,
            planned_digest=planned_digest,
            machine_digest=machine_digest,
            semantic_nodes=semantic_nodes,
            planned_nodes=planned_nodes,
            machine_nodes=machine_nodes,
            rewrite_count=rewrite_count,
            serialization_cost_ms=serialization_cost_ms,
            phase_verify_cost_ms=phase_verify_cost_ms,
            detail=capability.detail,
            candidate_set_digest=candidate_set_digest,
            selected_candidate=selected_candidate,
            selection_receipt_digest=selection_receipt_digest,
        )
    elapsed: list[float] = []
    verification_calls = 0
    verification_time_ns = 0
    fallback_count = 0
    commit_count = 0
    final_status = "committed"
    sample_results: list[dict[str, Any]] = []
    for sample_index in range(warmup_samples + samples):
        runtime = Runtime(execution_backend)
        runtime.load(nir, initial)
        start = time.perf_counter_ns()
        receipt = runtime.run()
        duration = (time.perf_counter_ns() - start) / 1_000_000.0
        if sample_index < warmup_samples:
            continue
        elapsed.append(duration)
        verification_calls += receipt.verification_calls
        verification_time_ns += receipt.verification_time_ns
        fallback_count += receipt.fallback_count
        commit_count += receipt.commits
        sample_results.append(
            {
                "status": receipt.status,
                "fields": {
                    name: {"values": list(field.values), "epoch": field.epoch}
                    for name, field in sorted(runtime._fields.items())
                },
            }
        )
        if receipt.status != "committed":
            final_status = receipt.status
    quality_loss = 0.0 if final_status == "committed" else None
    return RTMReceipt(
        status=final_status,
        backend=receipt_backend_name,
        source_digest=source_digest,
        nir_digest=nir.digest,
        workload_digest=workload_digest,
        hardware_digest=hardware_digest,
        compiler_digest=compiler_digest,
        runtime_digest=runtime_digest,
        backend_digest=backend_digest,
        benchmark_digest=benchmark_digest,
        result_digest=_digest(sample_results),
        plan_digest=plan_digest,
        lir_digest=lir_digest,
        code_digest=code_digest,
        compile_cost_ms=compile_cost_ms,
        backend_init_ms=backend_init_ms,
        verification_cost_ms=(
            verification_time_ns / max(1, len(elapsed)) / 1_000_000.0
            if verification_calls
            else None
        ),
        search_count=search_count,
        verification_calls=verification_calls,
        p50_ms=_percentile(elapsed, 0.50),
        p99_ms=_percentile(elapsed, 0.99),
        quality_loss=quality_loss,
        fallback_count=fallback_count,
        commit_count=commit_count,
        fallback_rate=(fallback_count / verification_calls if verification_calls else None),
        samples=samples,
        warmup_samples=warmup_samples,
        semantic_digest=semantic_digest,
        planned_digest=planned_digest,
        machine_digest=machine_digest,
        semantic_nodes=semantic_nodes,
        planned_nodes=planned_nodes,
        machine_nodes=machine_nodes,
        rewrite_count=rewrite_count,
        serialization_cost_ms=serialization_cost_ms,
        phase_verify_cost_ms=phase_verify_cost_ms,
        candidate_set_digest=candidate_set_digest,
        selected_candidate=selected_candidate,
        selection_receipt_digest=selection_receipt_digest,
    )


__all__ = ["RTMReceipt", "measure", "measure_candidates", "selection_bindings"]
