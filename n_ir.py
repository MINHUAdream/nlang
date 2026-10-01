"""Canonical, phase-aware IR for n's RTM and native compilation path."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from n_front import NModule


class IRPhase(str, Enum):
    SEMANTIC = "semantic"
    PLANNED = "planned"
    MACHINE = "machine"


class IRValidationError(ValueError):
    """The module or a requested phase transition violates an IR invariant."""

    def __init__(self, message: str, diagnostics: Sequence[Any] = ()):
        super().__init__(message)
        self.diagnostics = tuple(diagnostics)


@dataclass(frozen=True)
class RewriteDelta:
    parent_digest: str
    rule_id: str
    changed_node_ids: tuple[str, ...]
    verifier_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_digest": self.parent_digest,
            "rule_id": self.rule_id,
            "changed_node_ids": list(self.changed_node_ids),
            "verifier_digest": self.verifier_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RewriteDelta":
        return cls(
            parent_digest=str(payload["parent_digest"]),
            rule_id=str(payload["rule_id"]),
            changed_node_ids=tuple(str(value) for value in payload["changed_node_ids"]),
            verifier_digest=str(payload["verifier_digest"]),
        )


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        _thaw(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class NIRModule:
    schema: str
    module: str | None
    nodes: tuple[Mapping[str, Any], ...]
    phase: IRPhase = IRPhase.SEMANTIC
    values: tuple[Mapping[str, Any], ...] = ()
    regions: tuple[Mapping[str, Any], ...] = ()
    parent_digest: str | None = None
    rewrite: RewriteDelta | None = None
    legacy_digest: str | None = None
    semantic_digest: str | None = None

    @property
    def operations(self) -> tuple[Mapping[str, Any], ...]:
        """The 0.7 operation table; ``nodes`` remains its compatibility alias."""

        return self.nodes

    def to_dict(self) -> dict[str, Any]:
        if self.schema == "n-ir/rtm-0.1":
            return {
                "schema": self.schema,
                "module": self.module,
                "nodes": [_thaw(node) for node in self.nodes],
            }
        if self.schema != "n-ir/0.7":
            raise IRValidationError(f"unsupported NIR schema {self.schema!r}")
        return {
            "schema": self.schema,
            "module": self.module,
            "phase": self.phase.value,
            "operations": [_thaw(node) for node in self.nodes],
            "values": [_thaw(value) for value in self.values],
            "regions": [_thaw(region) for region in self.regions],
            "parent_digest": self.parent_digest,
            "rewrite": None if self.rewrite is None else self.rewrite.to_dict(),
            "legacy_digest": self.legacy_digest,
            "semantic_digest": self.semantic_digest,
        }

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

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "NIRModule":
        schema = str(payload["schema"])
        if schema == "n-ir/rtm-0.1":
            return cls(
                schema=schema,
                module=payload.get("module"),
                nodes=tuple(_freeze(node) for node in payload["nodes"]),
            )
        if schema != "n-ir/0.7":
            raise IRValidationError(f"unsupported NIR schema {schema!r}")
        rewrite_payload = payload.get("rewrite")
        return cls(
            schema=schema,
            module=payload.get("module"),
            nodes=tuple(_freeze(node) for node in payload["operations"]),
            phase=IRPhase(str(payload["phase"])),
            values=tuple(_freeze(value) for value in payload.get("values", ())),
            regions=tuple(_freeze(region) for region in payload.get("regions", ())),
            parent_digest=payload.get("parent_digest"),
            rewrite=(
                None
                if rewrite_payload is None
                else RewriteDelta.from_dict(rewrite_payload)
            ),
            legacy_digest=payload.get("legacy_digest"),
            semantic_digest=payload.get("semantic_digest"),
        )

    def rewrite_to(
        self,
        phase: IRPhase,
        delta: RewriteDelta,
        operations: Sequence[Mapping[str, Any]],
        *,
        values: Sequence[Mapping[str, Any]] | None = None,
        regions: Sequence[Mapping[str, Any]] | None = None,
    ) -> "NIRModule":
        if self.schema != "n-ir/0.7":
            raise IRValidationError("legacy NIR must be upgraded before rewriting")
        if delta.parent_digest != self.digest:
            raise IRValidationError("rewrite parent digest does not match module")
        next_phase = {
            IRPhase.SEMANTIC: IRPhase.PLANNED,
            IRPhase.PLANNED: IRPhase.MACHINE,
        }.get(self.phase)
        if phase != next_phase:
            raise IRValidationError(
                f"illegal phase transition {self.phase.value!r} -> {phase.value!r}"
            )
        return NIRModule(
            schema="n-ir/0.7",
            module=self.module,
            nodes=tuple(_freeze(operation) for operation in operations),
            phase=phase,
            values=(
                self.values
                if values is None
                else tuple(_freeze(value) for value in values)
            ),
            regions=(
                self.regions
                if regions is None
                else tuple(_freeze(region) for region in regions)
            ),
            parent_digest=self.digest,
            rewrite=delta,
            legacy_digest=self.legacy_digest,
            semantic_digest=self.semantic_digest or self.digest,
        )


def _operation_id(node: Mapping[str, Any], index: int) -> str:
    kind = str(node.get("kind", "unknown"))
    identity = node.get("name")
    if identity is None and kind == "commit":
        identity = f"{node.get('wave')}:{node.get('field')}"
    if identity is None and kind == "synthesize":
        identity = node.get("goal")
    if identity is None:
        identity = _canonical_digest(node)[:16]
    return f"op:{kind}:{identity}:{index}"


def upgrade_legacy(module: NIRModule) -> NIRModule:
    """Map the stable 0.1 projection into a phase-aware 0.7 semantic module."""

    if module.schema == "n-ir/0.7":
        return module
    if module.schema != "n-ir/rtm-0.1":
        raise IRValidationError(f"cannot upgrade schema {module.schema!r}")

    operations: list[Mapping[str, Any]] = []
    values: list[Mapping[str, Any]] = []
    wave_regions: list[Mapping[str, Any]] = []
    operation_ids: list[str] = []
    for index, node in enumerate(module.nodes):
        payload = _thaw(node)
        operation_id = _operation_id(payload, index)
        payload = {"id": operation_id, **payload}
        operations.append(_freeze(payload))
        operation_ids.append(operation_id)
        if payload["kind"] == "field":
            values.append(
                _freeze(
                    {
                        "id": f"value:field:{payload['name']}",
                        "kind": "field",
                        "dtype": payload["dtype"],
                        "shape": payload["shape"],
                        "layout": payload["layout"],
                        "device": payload["device"],
                        "defined_by": operation_id,
                    }
                )
            )
        elif payload["kind"] == "wave":
            values.append(
                _freeze(
                    {
                        "id": f"value:delta:{payload['name']}",
                        "kind": "delta",
                        "defined_by": operation_id,
                    }
                )
            )
            wave_regions.append(
                _freeze(
                    {
                        "id": f"region:wave:{payload['name']}",
                        "kind": "wave",
                        "owner": operation_id,
                        "operation_kinds": [
                            operation["kind"] for operation in payload["operations"]
                        ],
                    }
                )
            )

    regions = (
        _freeze(
            {
                "id": "region:module",
                "kind": "module",
                "operations": operation_ids,
            }
        ),
        *wave_regions,
    )
    return NIRModule(
        schema="n-ir/0.7",
        module=module.module,
        nodes=tuple(operations),
        phase=IRPhase.SEMANTIC,
        values=tuple(values),
        regions=tuple(regions),
        legacy_digest=module.digest,
        semantic_digest=None,
    )


def lower_legacy(module: NModule) -> NIRModule:
    """Lower n frontend nodes to the stable 0.1 compatibility projection."""

    nodes: list[Mapping[str, Any]] = []
    for field in module.fields:
        nodes.append(
            {
                "kind": "field",
                "name": field.name,
                "dtype": field.dtype,
                "shape": list(field.shape),
                "layout": field.layout,
                "device": field.device,
            }
        )
    for wave in module.waves:
        nodes.append(
            {
                "kind": "wave",
                "name": wave.name,
                "parameter": wave.parameter,
                "result": wave.result,
                "operations": [
                    {"kind": operation.kind, "value": operation.value}
                    for operation in wave.operations
                ],
                "echo": {"mode": wave.echo.mode},
                "fallback": wave.fallback,
            }
        )
    for commit in module.commits:
        nodes.append({"kind": "commit", "wave": commit.wave, "field": commit.field})
    for goal in module.goals:
        nodes.append(
            {
                "kind": "goal",
                "name": goal.name,
                "targets": [
                    {"direction": target.direction, "metric": target.metric}
                    for target in goal.targets
                ],
                "required_features": list(goal.required_features),
                "options": [
                    {"name": option.name, "metrics": dict(option.metrics)}
                    for option in goal.options
                ],
            }
        )
    for synthesis in module.syntheses:
        nodes.append(
            {
                "kind": "synthesize",
                "goal": synthesis.goal,
                "max_rounds": synthesis.max_rounds,
            }
        )
    return NIRModule(
        "n-ir/rtm-0.1",
        module.name,
        tuple(_freeze(node) for node in nodes),
    )


def lower(module: NModule) -> NIRModule:
    """Lower source into the authoritative 0.7 semantic phase."""

    return upgrade_legacy(lower_legacy(module))


__all__ = [
    "IRPhase",
    "IRValidationError",
    "NIRModule",
    "RewriteDelta",
    "lower",
    "lower_legacy",
    "upgrade_legacy",
]
