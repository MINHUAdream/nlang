"""Typed, canonical low-level IR for n execution plans."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Any

from n_ir import IRPhase, IRValidationError, NIRModule, RewriteDelta
from n_ir_verify import verify_phase
from n_plan import PlanError, PlanManifest


@dataclass(frozen=True)
class LIRBuffer:
    name: str
    role: str
    dtype: str
    shape: tuple[int, ...]
    layout: str
    device: str


@dataclass(frozen=True)
class LIROperation:
    opcode: str
    inputs: tuple[str, ...]
    output: str
    scalar: float | None = None


@dataclass(frozen=True)
class LIRKernel:
    schema: str
    name: str
    buffers: tuple[LIRBuffer, ...]
    loop_extent: int
    operations: tuple[LIROperation, ...]
    effects: tuple[str, ...]
    numeric_contract: str
    fallback: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def lower_to_lir(nir: NIRModule, manifest: PlanManifest) -> LIRKernel:
    semantic_digest = nir.digest if nir.phase == IRPhase.SEMANTIC else nir.semantic_digest
    if manifest.semantic_digest != semantic_digest:
        raise PlanError("NIR digest does not match plan during LIR lowering")
    fields = [node for node in nir.operations if node.get("kind") == "field"]
    waves = [node for node in nir.operations if node.get("kind") == "wave"]
    commits = [node for node in nir.operations if node.get("kind") == "commit"]
    if len(fields) != 1 or len(waves) != 1 or len(commits) != 1:
        raise PlanError("LIR lowering requires one field, wave, and commit")
    field, wave, commit = fields[0], waves[0], commits[0]
    shape = tuple(int(value) for value in field.get("shape", ()))
    operations = list(wave.get("operations", ()))
    if (
        field.get("name") != manifest.field
        or field.get("dtype") != manifest.dtype
        or shape != manifest.shape
        or field.get("layout") != manifest.layout
        or field.get("device") != manifest.device
        or wave.get("name") != manifest.wave
        or wave.get("result") != "delta"
        or wave.get("fallback") != "reject"
        or wave.get("echo", {}).get("mode") != "exact"
        or commit.get("wave") != manifest.wave
        or commit.get("field") != manifest.field
        or len(operations) != 4
        or [op.get("kind") for op in operations] != ["read", "write", "delta", "delta_value"]
        or operations[0].get("value") != manifest.field
        or operations[1].get("value") != manifest.field
        or operations[2].get("value") != manifest.operation
        or operations[3].get("value") != manifest.scalar
    ):
        raise PlanError("NIR nodes do not match the validated plan during LIR lowering")
    output_name = f"delta:{manifest.field}"
    return LIRKernel(
        schema="n-lir/1",
        name=manifest.wave,
        buffers=(
            LIRBuffer(
                manifest.field,
                "input",
                manifest.dtype,
                manifest.shape,
                manifest.layout,
                manifest.device,
            ),
            LIRBuffer(
                output_name,
                "output",
                manifest.dtype,
                manifest.shape,
                manifest.layout,
                manifest.device,
            ),
        ),
        loop_extent=math.prod(shape),
        operations=(
            LIROperation("add_scalar", (manifest.field,), output_name, manifest.scalar),
        ),
        effects=(f"read:{manifest.field}", f"write:{output_name}"),
        numeric_contract="exact-reference-f64",
        fallback=manifest.fallback,
    )


def lower_machine(planned: NIRModule, manifest: PlanManifest) -> NIRModule:
    """Lower planned nIR to a machine-phase snapshot with a compatibility view."""

    if planned.phase != IRPhase.PLANNED:
        raise PlanError("machine lowering requires a planned snapshot")
    if manifest.planned_digest != planned.digest:
        raise PlanError("planned snapshot does not match manifest")
    try:
        verify_phase(planned)
    except IRValidationError as exc:
        raise PlanError(f"planned snapshot failed verification: {exc}") from exc
    semantic_ops = tuple(
        operation
        for operation in planned.operations
        if operation.get("kind") in {"field", "wave", "commit"}
    )
    plan_nodes = [
        operation for operation in planned.operations if operation.get("kind") == "plan"
    ]
    if len(plan_nodes) != 1:
        raise PlanError("planned snapshot lacks exactly one plan operation")
    plan_node = plan_nodes[0]
    if any(
        plan_node.get(key) != expected
        for key, expected in {
            "target": manifest.target,
            "backend": manifest.backend,
            "field": manifest.field,
            "wave": manifest.wave,
            "layout": manifest.layout,
            "device": manifest.device,
            "fallback": manifest.fallback,
            "objective_epoch": manifest.objective_epoch,
        }.items()
    ):
        raise PlanError("planned snapshot does not match manifest fields")
    field = next((op for op in semantic_ops if op.get("kind") == "field"), None)
    wave = next((op for op in semantic_ops if op.get("kind") == "wave"), None)
    if field is None or wave is None:
        raise PlanError("planned snapshot lacks native field or wave contract")
    machine_operations = (
        {
            "id": f"machine:kernel:{manifest.wave}",
            "kind": "machine.kernel",
            "target": manifest.target,
            "backend": manifest.backend,
            "wave": manifest.wave,
            "abi": "win64(rcx,rdx,r8,r9)",
        },
        {
            "id": f"machine:buffer:{manifest.field}",
            "kind": "machine.buffer",
            "name": manifest.field,
            "role": "input",
            "dtype": manifest.dtype,
            "shape": list(manifest.shape),
            "layout": manifest.layout,
            "device": manifest.device,
        },
        {
            "id": f"machine:loop:{manifest.wave}",
            "kind": "machine.loop",
            "extent": math.prod(manifest.shape),
            "vector_width": 2,
        },
        {
            "id": f"machine:add_scalar:{manifest.wave}",
            "kind": "machine.add_scalar",
            "input": manifest.field,
            "output": f"delta:{manifest.field}",
            "scalar": manifest.scalar,
            "numeric_contract": "exact-reference-f64",
        },
        {
            "id": f"machine:effect:{manifest.wave}",
            "kind": "machine.effect",
            "effects": [f"read:{manifest.field}", f"write:delta:{manifest.field}"],
        },
        {
            "id": f"machine:return:{manifest.wave}",
            "kind": "machine.return",
            "fallback": manifest.fallback,
        },
    )
    delta = RewriteDelta(
        parent_digest=planned.digest,
        rule_id="lower.machine.x86_64.sse2",
        changed_node_ids=tuple(operation["id"] for operation in machine_operations),
        verifier_digest=manifest.verifier_digest,
    )
    machine = planned.rewrite_to(
        IRPhase.MACHINE,
        delta,
        (*semantic_ops, *machine_operations),
    )
    try:
        verify_phase(machine, target=manifest.target)
    except IRValidationError as exc:
        raise PlanError(f"machine snapshot failed verification: {exc}") from exc
    return machine


def legacy_lir_view(machine: NIRModule, manifest: PlanManifest) -> LIRKernel:
    if machine.phase != IRPhase.MACHINE:
        raise PlanError("LIR compatibility projection requires a machine snapshot")
    return lower_to_lir(machine, manifest)


__all__ = [
    "LIRBuffer",
    "LIRKernel",
    "LIROperation",
    "legacy_lir_view",
    "lower_machine",
    "lower_to_lir",
]
