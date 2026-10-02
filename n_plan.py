"""Digest-bound execution plans and semantic-to-planned nIR rewriting."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
from typing import Any, Mapping

from n_front import parse
from n_goal import (
    CandidateSpec,
    SelectionReceipt,
    candidate_set_digest,
    candidate_specs,
    select_measured,
)
from n_ir import IRPhase, IRValidationError, NIRModule, RewriteDelta, lower
from n_ir_verify import verify_phase


class PlanError(ValueError):
    """A plan cannot safely describe or execute the supplied nIR."""


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


_PLANNED_VERIFIER_DIGEST = _canonical_digest(
    {"schema": "n-ir/0.7", "verifier": "structural+semantic+phase", "phase": "planned"}
)


@dataclass(frozen=True)
class PlanManifest:
    schema: str
    source_digest: str
    nir_digest: str
    semantic_digest: str
    planned_digest: str
    machine_digest: str
    verifier_digest: str
    objective_epoch: int
    target: str
    backend: str
    field: str
    dtype: str
    shape: tuple[int, ...]
    layout: str
    device: str
    wave: str
    operation: str
    scalar: float
    required_features: tuple[str, ...]
    fallback: str
    candidate_set_digest: str = ""
    selected_candidate: str = "cpu_simd_sse2"
    selection_receipt_digest: str = ""

    @property
    def digest(self) -> str:
        return _canonical_digest(self._body())

    def _body(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "source_digest": self.source_digest,
            "nir_digest": self.nir_digest,
            "semantic_digest": self.semantic_digest,
            "planned_digest": self.planned_digest,
            "machine_digest": self.machine_digest,
            "verifier_digest": self.verifier_digest,
            "objective_epoch": self.objective_epoch,
            "target": self.target,
            "backend": self.backend,
            "field": self.field,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "layout": self.layout,
            "device": self.device,
            "wave": self.wave,
            "operation": self.operation,
            "scalar": self.scalar,
            "required_features": list(self.required_features),
            "fallback": self.fallback,
            "candidate_set_digest": self.candidate_set_digest,
            "selected_candidate": self.selected_candidate,
            "selection_receipt_digest": self.selection_receipt_digest,
        }

    def _intent_body(self) -> dict[str, Any]:
        body = self._body()
        body.pop("planned_digest")
        body.pop("machine_digest")
        return body

    def to_dict(self) -> dict[str, Any]:
        return {**self._body(), "digest": self.digest}

    def bind_planned(self, planned: NIRModule) -> "PlanManifest":
        if planned.phase != IRPhase.PLANNED:
            raise PlanError("plan manifest can bind only a planned snapshot")
        if planned.semantic_digest != self.semantic_digest:
            raise PlanError("planned snapshot does not refine the manifest semantic module")
        return replace(self, planned_digest=planned.digest, machine_digest="")

    def bind_machine(self, machine: NIRModule) -> "PlanManifest":
        if machine.phase != IRPhase.MACHINE:
            raise PlanError("plan manifest can bind only a machine snapshot")
        if not self.planned_digest or machine.parent_digest != self.planned_digest:
            raise PlanError("machine snapshot does not refine the bound planned snapshot")
        return replace(self, machine_digest=machine.digest)

    @classmethod
    def create(
        cls,
        source: str,
        nir: NIRModule,
        *,
        target: str = "x86_64-windows",
        selected_candidate: str | None = None,
        selection_receipt_digest: str = "",
    ) -> "PlanManifest":
        return _create_manifest(
            source,
            nir,
            target=target,
            selected_candidate=selected_candidate,
            selection_receipt_digest=selection_receipt_digest,
        )


def _of_kind(nir: NIRModule, kind: str) -> list[Mapping[str, Any]]:
    return [node for node in nir.operations if node.get("kind") == kind]


def _create_manifest(
    source: str,
    nir: NIRModule,
    *,
    target: str = "x86_64-windows",
    selected_candidate: str | None = None,
    selection_receipt_digest: str = "",
) -> PlanManifest:
    if nir.schema != "n-ir/0.7" or nir.phase != IRPhase.SEMANTIC:
        raise PlanError("native planning requires an n-ir/0.7 semantic module")
    try:
        verify_phase(nir)
    except IRValidationError as exc:
        raise PlanError(f"semantic nIR failed verification: {exc}") from exc
    if target != "x86_64-windows":
        raise PlanError(f"unsupported native target {target!r}")
    goals = _of_kind(nir, "goal")
    syntheses = _of_kind(nir, "synthesize")
    goal_candidates: tuple[CandidateSpec, ...] = ()
    goal_name: str | None = None
    if goals or syntheses:
        if len(goals) != 1 or len(syntheses) != 1:
            raise PlanError("native goal planning requires exactly one goal and synthesize operation")
        goal_name = str(syntheses[0].get("goal"))
        if goals[0].get("name") != goal_name:
            raise PlanError("synthesize goal does not match the declared goal")
        try:
            goal_candidates = candidate_specs(nir, goal_name)
        except ValueError as exc:
            raise PlanError(str(exc)) from exc
        candidate_names = {candidate.name for candidate in goal_candidates}
        selected_candidate = selected_candidate or "cpu_simd_sse2"
        if selected_candidate not in candidate_names:
            raise PlanError(f"unknown selected candidate {selected_candidate!r}")
    else:
        selected_candidate = selected_candidate or "cpu_simd_sse2"
    fields = _of_kind(nir, "field")
    waves = _of_kind(nir, "wave")
    commits = _of_kind(nir, "commit")
    if len(fields) != 1 or len(waves) != 1 or len(commits) != 1:
        raise PlanError("native slice requires exactly one field, wave, and commit")
    field, wave, commit = fields[0], waves[0], commits[0]
    if field.get("dtype") != "f64":
        raise PlanError("native slice requires f64 field")
    if field.get("layout") != "contiguous":
        raise PlanError("native slice requires contiguous field layout")
    if field.get("device") != "cpu":
        raise PlanError("native slice requires cpu field placement")
    shape = tuple(int(size) for size in field.get("shape", ()))
    if not shape or any(size <= 0 for size in shape):
        raise PlanError("native slice requires positive static field shape")
    if math.prod(shape) > 2_147_483_646:
        raise PlanError("native slice field exceeds the current kernel count ABI")
    if wave.get("result") != "delta" or wave.get("fallback") != "reject":
        raise PlanError("native slice requires a delta result and reject fallback")
    if commit.get("wave") != wave.get("name") or commit.get("field") != field.get("name"):
        raise PlanError("commit does not match the native wave and field")
    operations = list(wave.get("operations", ()))
    if len(operations) != 4 or [operation.get("kind") for operation in operations] != [
        "read",
        "write",
        "delta",
        "delta_value",
    ]:
        raise PlanError("native slice requires read/write/add_scalar operations")
    field_name = str(field["name"])
    if operations[0].get("value") != field_name or operations[1].get("value") != field_name:
        raise PlanError("wave read/write set does not match the field")
    if operations[2].get("value") != "add_scalar":
        raise PlanError("native slice supports only add_scalar")
    scalar = operations[3].get("value")
    if not isinstance(scalar, (int, float)) or not math.isfinite(float(scalar)):
        raise PlanError("add_scalar value must be a finite number")
    candidate_by_name = {
        candidate.name: candidate for candidate in goal_candidates
    }
    if not goal_candidates:
        goal_candidates = (
            CandidateSpec(
                "cpu_simd_sse2",
                "n-native-x64-sse2-f64",
                ("cpu", "sse2", "sse2_packed_f64"),
            ),
        )
        candidate_by_name = {candidate.name: candidate for candidate in goal_candidates}
    selected = candidate_by_name[selected_candidate]
    return PlanManifest(
        schema="n-plan/2",
        source_digest=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        nir_digest=nir.digest,
        semantic_digest=nir.digest,
        planned_digest="",
        machine_digest="",
        verifier_digest=_PLANNED_VERIFIER_DIGEST,
        objective_epoch=0,
        target=target,
        backend=selected.backend,
        field=field_name,
        dtype="f64",
        shape=shape,
        layout="contiguous",
        device="cpu",
        wave=str(wave["name"]),
        operation="add_scalar",
        scalar=float(scalar),
        required_features=selected.required_features,
        fallback=(
            "reference_exact_reject_on_mismatch"
            if selected.name != "reference_exact"
            else "reference_exact"
        ),
        candidate_set_digest=candidate_set_digest(goal_candidates),
        selected_candidate=selected.name,
        selection_receipt_digest=selection_receipt_digest,
    )


def plan_module(nir: NIRModule, manifest: PlanManifest) -> NIRModule:
    if nir.phase != IRPhase.SEMANTIC or manifest.semantic_digest != nir.digest:
        raise PlanError("plan does not match semantic snapshot")
    if manifest.planned_digest or manifest.machine_digest:
        raise PlanError("planning requires an unbound manifest intent")
    plan_id = f"op:plan:{manifest.wave}"
    plan_operation = {
        "id": plan_id,
        "kind": "plan",
        "target": manifest.target,
        "backend": manifest.backend,
        "field": manifest.field,
        "wave": manifest.wave,
        "layout": manifest.layout,
        "device": manifest.device,
        "vector_width": 2,
        "numeric_contract": "exact-reference-f64",
        "required_features": list(manifest.required_features),
        "fallback": manifest.fallback,
        "objective_epoch": manifest.objective_epoch,
        "candidate_set_digest": manifest.candidate_set_digest,
        "selected_candidate": manifest.selected_candidate,
        "selection_receipt_digest": manifest.selection_receipt_digest,
    }
    goal_operations: tuple[Mapping[str, Any], ...] = ()
    if any(operation.get("kind") == "goal" for operation in nir.operations):
        goal_operations = (
            {
                "id": f"op:candidate_set:{manifest.wave}",
                "kind": "candidate_set",
                "digest": manifest.candidate_set_digest,
                "candidates": [manifest.selected_candidate, "reference_exact"],
            },
            {
                "id": f"op:selection:{manifest.wave}",
                "kind": "selection",
                "candidate": manifest.selected_candidate,
                "receipt_digest": manifest.selection_receipt_digest,
                "policy": "adaptive-fastest",
            },
        )
    delta = RewriteDelta(
        parent_digest=nir.digest,
        rule_id="plan.x86_64.sse2.add_scalar",
        changed_node_ids=(plan_id,),
        verifier_digest=manifest.verifier_digest,
    )
    planned = nir.rewrite_to(
        IRPhase.PLANNED,
        delta,
        (*nir.operations, plan_operation, *goal_operations),
    )
    try:
        verify_phase(planned)
    except IRValidationError as exc:
        raise PlanError(f"planned nIR failed verification: {exc}") from exc
    return planned


def verify_manifest(manifest: PlanManifest, source: str, nir: NIRModule) -> None:
    source_digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if manifest.source_digest != source_digest:
        raise PlanError("source digest does not match plan manifest")
    parsed_nir = lower(parse(source))
    if parsed_nir.digest != nir.digest:
        raise PlanError("NIR digest does not match the supplied source")
    if manifest.nir_digest != nir.digest or manifest.semantic_digest != nir.digest:
        raise PlanError("NIR digest does not match plan manifest")
    expected = PlanManifest.create(
        source,
        nir,
        target=manifest.target,
        selected_candidate=manifest.selected_candidate,
        selection_receipt_digest=manifest.selection_receipt_digest,
    )
    if expected._intent_body() != manifest._intent_body():
        raise PlanError("plan manifest fields do not match source and NIR")


def verify_selection_receipt(
    manifest: PlanManifest,
    semantic: NIRModule,
    receipt: SelectionReceipt,
    *,
    bindings: Mapping[str, str] | None = None,
    hardware_digest: str | None = None,
) -> None:
    """Verify measured goal evidence before a selected plan can execute."""

    goals = _of_kind(semantic, "goal")
    syntheses = _of_kind(semantic, "synthesize")
    if len(goals) != 1 or len(syntheses) != 1:
        raise PlanError("selection receipt requires exactly one goal and synthesize operation")
    goal_name = str(syntheses[0].get("goal"))
    candidates = candidate_specs(semantic, goal_name)
    if receipt.goal != goal_name:
        raise PlanError("selection receipt goal does not match semantic NIR")
    if receipt.candidate_set_digest != manifest.candidate_set_digest:
        raise PlanError("selection receipt candidate set does not match manifest")
    if receipt.selected_candidate != manifest.selected_candidate:
        raise PlanError("selection receipt candidate does not match manifest")
    if receipt.digest != manifest.selection_receipt_digest:
        raise PlanError("selection receipt digest does not match manifest")
    expected_names = {candidate.name for candidate in candidates}
    measured_names = [item.candidate for item in receipt.measurements]
    if len(measured_names) != len(set(measured_names)) or set(measured_names) != expected_names:
        raise PlanError("selection receipt candidate set is incomplete or contains duplicates")
    expected_bindings = dict(bindings or {})
    if hardware_digest is not None:
        expected_bindings["hardware_digest"] = hardware_digest
    for item in receipt.measurements:
        for field, expected in expected_bindings.items():
            if getattr(item, field, None) != expected:
                raise PlanError(f"selection receipt {field} does not match replay workload")
    replayed = select_measured(
        goal_name,
        candidates,
        receipt.measurements,
        policy=receipt.policy,
    )
    if replayed.digest != receipt.digest or replayed.selected_candidate != receipt.selected_candidate:
        raise PlanError("selection receipt cannot be replayed from its measurements")
    if hardware_digest is not None:
        measured_hardware = {
            item.hardware_digest
            for item in receipt.measurements
            if item.status == "committed"
        }
        if measured_hardware != {hardware_digest}:
            raise PlanError("selection receipt hardware digest does not match host")


__all__ = [
    "PlanError",
    "PlanManifest",
    "plan_module",
    "verify_manifest",
    "verify_selection_receipt",
]
