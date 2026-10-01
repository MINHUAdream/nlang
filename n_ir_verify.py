"""Composable structural, semantic, phase, and target checks for nIR 0.7."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from n_ir import IRPhase, IRValidationError, NIRModule


@dataclass(frozen=True)
class IRDiagnostic:
    code: str
    message: str
    node_id: str | None = None


_LEGAL_KINDS = {
    IRPhase.SEMANTIC: frozenset({"field", "wave", "commit", "goal", "synthesize"}),
    IRPhase.PLANNED: frozenset(
        {
            "field",
            "wave",
            "commit",
            "goal",
            "synthesize",
            "plan",
            "place",
            "tile",
            "vectorize",
            "layout_cast",
            "buffer",
            "move",
            "candidate_set",
            "selection",
        }
    ),
    IRPhase.MACHINE: frozenset(
        {
            "field",
            "wave",
            "commit",
            "machine.kernel",
            "machine.buffer",
            "machine.loop",
            "machine.add_scalar",
            "machine.effect",
            "machine.move",
            "machine.return",
            "candidate_set",
            "selection",
        }
    ),
}


def _node_id(item: Mapping[str, Any]) -> str | None:
    value = item.get("id")
    return value if isinstance(value, str) and value else None


def _check_ids(
    label: str,
    items: Sequence[Mapping[str, Any]],
    diagnostics: list[IRDiagnostic],
) -> set[str]:
    seen: set[str] = set()
    for item in items:
        item_id = _node_id(item)
        if item_id is None:
            diagnostics.append(
                IRDiagnostic("IR_MISSING_ID", f"{label} entry requires a stable id")
            )
            continue
        if item_id in seen:
            diagnostics.append(
                IRDiagnostic(
                    "IR_DUPLICATE_ID",
                    f"duplicate {label} id {item_id!r}",
                    item_id,
                )
            )
        seen.add(item_id)
    return seen


def _verify_structure(module: NIRModule, diagnostics: list[IRDiagnostic]) -> None:
    if module.schema != "n-ir/0.7":
        diagnostics.append(
            IRDiagnostic("IR_SCHEMA", f"phase verifier requires n-ir/0.7, got {module.schema!r}")
        )
        return

    operation_ids = _check_ids("operation", module.operations, diagnostics)
    _check_ids("value", module.values, diagnostics)
    _check_ids("region", module.regions, diagnostics)

    for value in module.values:
        defining_operation = value.get("defined_by")
        if defining_operation is not None and defining_operation not in operation_ids:
            diagnostics.append(
                IRDiagnostic(
                    "IR_DANGLING_VALUE",
                    f"value references unknown defining operation {defining_operation!r}",
                    _node_id(value),
                )
            )
    for region in module.regions:
        for operation_id in region.get("operations", ()):
            if operation_id not in operation_ids:
                diagnostics.append(
                    IRDiagnostic(
                        "IR_DANGLING_REGION",
                        f"region references unknown operation {operation_id!r}",
                        _node_id(region),
                    )
                )

    if module.phase == IRPhase.SEMANTIC:
        if module.parent_digest is not None or module.rewrite is not None:
            diagnostics.append(
                IRDiagnostic("IR_SEMANTIC_PARENT", "semantic phase cannot have a rewrite parent")
            )
    else:
        if module.parent_digest is None or module.rewrite is None:
            diagnostics.append(
                IRDiagnostic("IR_REWRITE_MISSING", f"{module.phase.value} phase requires rewrite lineage")
            )
        elif module.rewrite.parent_digest != module.parent_digest:
            diagnostics.append(
                IRDiagnostic("IR_REWRITE_PARENT", "rewrite parent does not match snapshot parent")
            )


def _verify_semantics(module: NIRModule, diagnostics: list[IRDiagnostic]) -> None:
    for operation in module.operations:
        kind = operation.get("kind")
        operation_id = _node_id(operation)
        if kind == "field":
            required = ("name", "dtype", "shape", "layout", "device")
            missing = [name for name in required if name not in operation]
            if missing:
                diagnostics.append(
                    IRDiagnostic(
                        "IR_FIELD_CONTRACT",
                        f"field is missing {', '.join(missing)}",
                        operation_id,
                    )
                )
        elif kind == "wave":
            if not operation.get("fallback"):
                diagnostics.append(
                    IRDiagnostic(
                        "IR_WAVE_FALLBACK",
                        "wave requires an explicit fallback",
                        operation_id,
                    )
                )
            echo = operation.get("echo")
            if not isinstance(echo, Mapping) or not echo.get("mode"):
                diagnostics.append(
                    IRDiagnostic(
                        "IR_WAVE_ECHO",
                        "wave requires an explicit echo mode",
                        operation_id,
                    )
                )
            nested = operation.get("operations")
            if not isinstance(nested, (tuple, list)):
                diagnostics.append(
                    IRDiagnostic(
                        "IR_WAVE_EFFECTS",
                        "wave requires explicit read/write/delta operations",
                        operation_id,
                    )
                )
            else:
                kinds = [item.get("kind") for item in nested if isinstance(item, Mapping)]
                if kinds[:2] != ["read", "write"]:
                    diagnostics.append(
                        IRDiagnostic(
                            "IR_WAVE_EFFECTS",
                            "wave must declare read then write effects",
                            operation_id,
                        )
                    )


def _verify_legality(module: NIRModule, diagnostics: list[IRDiagnostic]) -> None:
    legal = _LEGAL_KINDS[module.phase]
    for operation in module.operations:
        kind = operation.get("kind")
        if kind not in legal:
            diagnostics.append(
                IRDiagnostic(
                    "IR_PHASE_ILLEGAL",
                    f"operation {kind!r} is illegal in {module.phase.value} phase",
                    _node_id(operation),
                )
            )


def _verify_target(
    module: NIRModule,
    target: str | None,
    diagnostics: list[IRDiagnostic],
) -> None:
    if target is None:
        return
    if target != "x86_64-windows":
        diagnostics.append(
            IRDiagnostic("IR_TARGET_UNSUPPORTED", f"unsupported machine target {target!r}")
        )
    if module.phase != IRPhase.MACHINE:
        diagnostics.append(
            IRDiagnostic("IR_TARGET_PHASE", "target verification requires machine phase")
        )


def verify_phase(module: NIRModule, target: str | None = None) -> None:
    diagnostics: list[IRDiagnostic] = []
    _verify_structure(module, diagnostics)
    if module.schema == "n-ir/0.7":
        _verify_semantics(module, diagnostics)
        _verify_legality(module, diagnostics)
        _verify_target(module, target, diagnostics)
    if diagnostics:
        ordered = tuple(sorted(diagnostics, key=lambda item: (item.node_id or "", item.code)))
        message = "; ".join(f"{item.code}: {item.message}" for item in ordered)
        raise IRValidationError(message, ordered)


__all__ = ["IRDiagnostic", "verify_phase"]
