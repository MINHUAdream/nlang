"""Digest-bound execution plans and semantic-to-planned nIR rewriting."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
from typing import Any, Mapping

from n_front import parse
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
    ) -> "PlanManifest":
        return _create_manifest(source, nir, target=target)


def _of_kind(nir: NIRModule, kind: str) -> list[Mapping[str, Any]]:
    return [node for node in nir.operations if node.get("kind") == kind]


def _create_manifest(
    source: str,
    nir: NIRModule,
    *,
    target: str = "x86_64-windows",
) -> PlanManifest:
    if nir.schema != "n-ir/0.7" or nir.phase != IRPhase.SEMANTIC:
        raise PlanError("native planning requires an n-ir/0.7 semantic module")
    try:
        verify_phase(nir)
    except IRValidationError as exc:
        raise PlanError(f"semantic nIR failed verification: {exc}") from exc
    if target != "x86_64-windows":
        raise PlanError(f"unsupported native target {target!r}")
    if _of_kind(nir, "synthesize"):
        raise PlanError("goal/synthesize is not yet connected to executable plan selection")
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
        backend="n-native-x64-sse2-f64",
        field=field_name,
        dtype="f64",
        shape=shape,
        layout="contiguous",
        device="cpu",
        wave=str(wave["name"]),
        operation="add_scalar",
        scalar=float(scalar),
        required_features=("cpu", "sse2", "sse2_packed_f64"),
        fallback="reference_exact_reject_on_mismatch",
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
    }
    delta = RewriteDelta(
        parent_digest=nir.digest,
        rule_id="plan.x86_64.sse2.add_scalar",
        changed_node_ids=(plan_id,),
        verifier_digest=manifest.verifier_digest,
    )
    planned = nir.rewrite_to(
        IRPhase.PLANNED,
        delta,
        (*nir.operations, plan_operation),
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
    expected = PlanManifest.create(source, nir, target=manifest.target)
    if expected._intent_body() != manifest._intent_body():
        raise PlanError("plan manifest fields do not match source and NIR")


__all__ = ["PlanError", "PlanManifest", "plan_module", "verify_manifest"]
