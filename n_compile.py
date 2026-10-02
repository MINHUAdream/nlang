"""n source-to-machine-code compilation driver for the initial native subset."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import time
from typing import Mapping, Sequence

from n_backend_tl import ReferenceBackend
from n_codegen_x64 import code_digest, lower_lir, lower_machine_code
from n_goal import (
    CandidateMeasurement,
    GoalDecision,
    SelectionReceipt,
    candidate_specs,
    select_measured,
)
from n_front import parse
from n_ir import NIRModule, lower
from n_ir_verify import verify_phase
from n_lir import LIRKernel, legacy_lir_view, lower_machine
from n_plan import PlanError, PlanManifest, plan_module, verify_selection_receipt
from n_rtm import Runtime


@dataclass(frozen=True)
class Compilation:
    source: str
    source_digest: str
    semantic: NIRModule
    planned: NIRModule
    machine: NIRModule
    manifest: PlanManifest
    lir: LIRKernel
    code: bytes
    code_digest: str
    serialization_cost_ms: float
    phase_verify_cost_ms: float
    goal_decision: GoalDecision | None = None
    selection_receipt: SelectionReceipt | None = None

    @property
    def nir(self) -> NIRModule:
        """Compatibility projection for RTM and 0.50 callers."""

        return self.semantic


def _compile_semantic(
    source: str,
    semantic: NIRModule,
    manifest: PlanManifest,
    *,
    goal_decision: GoalDecision | None = None,
    selection_receipt: SelectionReceipt | None = None,
) -> Compilation:
    planned = plan_module(semantic, manifest)
    manifest = manifest.bind_planned(planned)
    machine = lower_machine(planned, manifest)
    manifest = manifest.bind_machine(machine)
    lir = legacy_lir_view(machine, manifest)
    code = (
        b""
        if manifest.backend == "reference"
        else lower_machine_code(machine, manifest)
    )
    verify_started = time.perf_counter_ns()
    verify_phase(semantic)
    verify_phase(planned)
    verify_phase(machine, target=manifest.target)
    phase_verify_cost_ms = (time.perf_counter_ns() - verify_started) / 1_000_000.0
    serialization_started = time.perf_counter_ns()
    semantic.canonical_json()
    planned.canonical_json()
    machine.canonical_json()
    serialization_cost_ms = (
        time.perf_counter_ns() - serialization_started
    ) / 1_000_000.0
    return Compilation(
        source=source,
        source_digest=manifest.source_digest,
        semantic=semantic,
        planned=planned,
        machine=machine,
        manifest=manifest,
        lir=lir,
        code=code,
        code_digest=code_digest(code),
        serialization_cost_ms=serialization_cost_ms,
        phase_verify_cost_ms=phase_verify_cost_ms,
        goal_decision=goal_decision,
        selection_receipt=selection_receipt,
    )


def _goal_initial(
    semantic: NIRModule,
    initial: Mapping[str, Sequence[float]] | None,
) -> dict[str, list[float]]:
    fields = [node for node in semantic.operations if node.get("kind") == "field"]
    if len(fields) != 1:
        raise PlanError("goal measurement requires exactly one field")
    field = fields[0]
    name = str(field["name"])
    size = math.prod(int(value) for value in field["shape"])
    if initial is None:
        return {name: [0.0] * size}
    if name not in initial:
        raise PlanError(f"goal measurement is missing initial field {name!r}")
    return {name: [float(value) for value in initial[name]]}


def _measure_candidate(
    source: str,
    semantic: NIRModule,
    candidate_name: str,
    *,
    target: str,
    initial: Mapping[str, Sequence[float]],
    samples: int,
    warmup_samples: int,
) -> CandidateMeasurement:
    from n_native import NativeBackend

    backend = ReferenceBackend() if candidate_name == "reference_exact" else NativeBackend()
    capability = backend.probe()
    if capability.status != "available":
        return CandidateMeasurement(
            candidate_name,
            "unavailable",
            None,
            None,
            None,
            None,
            None,
            None,
            capability.detail,
        )
    compilation: Compilation | None = None
    if candidate_name != "reference_exact":
        provisional_manifest = PlanManifest.create(
            source,
            semantic,
            target=target,
            selected_candidate=candidate_name,
            selection_receipt_digest="0" * 64,
        )
        compilation = _compile_semantic(source, semantic, provisional_manifest)
        backend.initialize(compilation)
    durations: list[float] = []
    verification_time_ns = 0
    verification_calls = 0
    fallback_count = 0
    commit_count = 0
    final_status = "committed"
    try:
        for sample_index in range(warmup_samples + samples):
            runtime = Runtime(backend)
            runtime.load(semantic, initial)
            started = time.perf_counter_ns()
            receipt = runtime.run()
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
            if sample_index < warmup_samples:
                continue
            durations.append(elapsed_ms)
            verification_time_ns += receipt.verification_time_ns
            verification_calls += receipt.verification_calls
            fallback_count += receipt.fallback_count
            commit_count += receipt.commits
            if receipt.status != "committed":
                final_status = receipt.status
    finally:
        if isinstance(backend, NativeBackend):
            backend.close()
    if final_status != "committed":
        return CandidateMeasurement(
            candidate_name,
            final_status,
            None,
            None,
            None,
            None,
            (fallback_count / verification_calls if verification_calls else None),
            commit_count,
            "candidate failed exact RTM commit",
        )
    ordered = sorted(durations)
    position = (len(ordered) - 1) * 0.99
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    p99 = ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction
    p50 = ordered[len(ordered) // 2] if len(ordered) % 2 else (
        ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]
    ) / 2
    return CandidateMeasurement(
        candidate_name,
        "committed",
        p50,
        p99,
        0.0,
        verification_time_ns / max(1, len(durations)) / 1_000_000.0,
        (fallback_count / verification_calls if verification_calls else 0.0),
        commit_count,
    )


def _measure_goal_selection(
    source: str,
    semantic: NIRModule,
    *,
    target: str,
    initial: Mapping[str, Sequence[float]] | None,
    samples: int,
    warmup_samples: int,
) -> tuple[GoalDecision, SelectionReceipt]:
    syntheses = [node for node in semantic.operations if node.get("kind") == "synthesize"]
    if len(syntheses) != 1:
        raise PlanError("goal measurement requires exactly one synthesize operation")
    goal_name = str(syntheses[0]["goal"])
    candidates = candidate_specs(semantic, goal_name)
    workload = _goal_initial(semantic, initial)
    if target != "x86_64-windows":
        raise PlanError(f"unsupported native target {target!r}")
    from n_measure import measure_candidates

    measurements = measure_candidates(
        source,
        workload,
        candidates,
        samples=samples,
        warmup_samples=warmup_samples,
    )
    selection = select_measured(goal_name, candidates, measurements)
    if selection.selected_candidate is None:
        raise PlanError(selection.detail or "goal selection produced no executable candidate")
    decision = GoalDecision(
        goal_name,
        selection.selected_candidate,
        selection.search_count,
        "selected",
        selection.digest,
        selection.detail,
        selection.candidate_set_digest,
        selection.digest,
    )
    return decision, selection


def compile_source(
    source: str,
    target: str = "x86_64-windows",
    *,
    initial: Mapping[str, Sequence[float]] | None = None,
    samples: int = 3,
    warmup_samples: int = 1,
    selection_receipt: SelectionReceipt | Mapping[str, object] | None = None,
) -> Compilation:
    module = parse(source)
    semantic = lower(module)
    has_goal = any(node.get("kind") == "synthesize" for node in semantic.operations)
    if has_goal:
        if selection_receipt is not None:
            if isinstance(selection_receipt, Mapping):
                selection_receipt = SelectionReceipt.from_dict(selection_receipt)
            if not isinstance(selection_receipt, SelectionReceipt):
                raise PlanError("selection receipt has an unsupported type")
            from n_measure import selection_bindings

            workload = _goal_initial(semantic, initial)
            if target != "x86_64-windows":
                raise PlanError(f"unsupported native target {target!r}")
            bindings = selection_bindings(
                source,
                workload,
                samples=samples,
                warmup_samples=warmup_samples,
            )
            manifest = PlanManifest.create(
                source,
                semantic,
                target=target,
                selected_candidate=selection_receipt.selected_candidate,
                selection_receipt_digest=selection_receipt.digest,
            )
            verify_selection_receipt(
                manifest,
                semantic,
                selection_receipt,
                bindings=bindings,
            )
            decision = GoalDecision(
                selection_receipt.goal,
                selection_receipt.selected_candidate,
                selection_receipt.search_count,
                "selected",
                selection_receipt.digest,
                selection_receipt.detail,
                selection_receipt.candidate_set_digest,
                selection_receipt.digest,
            )
            return _compile_semantic(
                source,
                semantic,
                manifest,
                goal_decision=decision,
                selection_receipt=selection_receipt,
            )
        goal_decision, selection = _measure_goal_selection(
            source,
            semantic,
            target=target,
            initial=initial,
            samples=samples,
            warmup_samples=warmup_samples,
        )
        manifest = PlanManifest.create(
            source,
            semantic,
            target=target,
            selected_candidate=goal_decision.selected,
            selection_receipt_digest=selection.digest,
        )
        return _compile_semantic(
            source,
            semantic,
            manifest,
            goal_decision=goal_decision,
            selection_receipt=selection,
        )
    manifest = PlanManifest.create(source, semantic, target=target)
    return _compile_semantic(source, semantic, manifest)


def compile_source_legacy(
    source: str, target: str = "x86_64-windows"
) -> Compilation:
    """Compatibility probe using the old LIR-to-code entry after verified planning."""

    compilation = compile_source(source, target=target)
    code = lower_lir(compilation.lir, compilation.manifest)
    return replace(compilation, code=code, code_digest=code_digest(code))


__all__ = ["Compilation", "compile_source", "compile_source_legacy"]
