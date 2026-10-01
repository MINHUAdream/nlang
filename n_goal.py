"""Deterministic goal synthesis over NIR-RTM options."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Iterable, Mapping, Sequence

from n_ir import NIRModule


@dataclass(frozen=True)
class GoalDecision:
    goal: str
    selected: str | None
    search_count: int
    status: str
    digest: str
    detail: str | None = None
    candidate_set_digest: str | None = None
    selection_receipt_digest: str | None = None


@dataclass(frozen=True)
class CandidateSpec:
    name: str
    backend: str
    required_features: tuple[str, ...]
    operation: str = "add_scalar"
    numeric_contract: str = "exact-reference-f64"
    fallback: str = "reference_exact"

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "backend": self.backend,
            "required_features": list(self.required_features),
            "operation": self.operation,
            "numeric_contract": self.numeric_contract,
            "fallback": self.fallback,
        }


@dataclass(frozen=True)
class CandidateMeasurement:
    candidate: str
    status: str
    p50_ms: float | None
    p99_ms: float | None
    quality_loss: float | None
    verification_cost_ms: float | None
    fallback_rate: float | None
    commit_count: int | None
    detail: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate": self.candidate,
            "status": self.status,
            "p50_ms": self.p50_ms,
            "p99_ms": self.p99_ms,
            "quality_loss": self.quality_loss,
            "verification_cost_ms": self.verification_cost_ms,
            "fallback_rate": self.fallback_rate,
            "commit_count": self.commit_count,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SelectionReceipt:
    goal: str
    policy: str
    candidate_set_digest: str
    selected_candidate: str | None
    search_count: int
    measurements: tuple[CandidateMeasurement, ...]
    detail: str | None = None

    @property
    def digest(self) -> str:
        return _decision_digest(
            {
                "goal": self.goal,
                "policy": self.policy,
                "candidate_set_digest": self.candidate_set_digest,
                "selected_candidate": self.selected_candidate,
                "search_count": self.search_count,
                "measurements": [item.to_dict() for item in self.measurements],
                "detail": self.detail,
            }
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "goal": self.goal,
            "policy": self.policy,
            "candidate_set_digest": self.candidate_set_digest,
            "selected_candidate": self.selected_candidate,
            "search_count": self.search_count,
            "measurements": [item.to_dict() for item in self.measurements],
            "detail": self.detail,
            "digest": self.digest,
        }


def _decision_digest(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def candidate_set_digest(candidates: Sequence[CandidateSpec]) -> str:
    payload = [candidate.to_dict() for candidate in sorted(candidates, key=lambda item: item.name)]
    return _decision_digest({"candidates": payload})


def candidate_specs(module: NIRModule, goal_name: str) -> tuple[CandidateSpec, ...]:
    goals = [node for node in module.nodes if node["kind"] == "goal" and node["name"] == goal_name]
    if len(goals) != 1:
        raise ValueError(f"expected exactly one goal {goal_name!r}")
    names = {str(option["name"]) for option in goals[0].get("options", ())}
    expected = {"reference_exact", "cpu_simd_sse2"}
    if names != expected:
        raise ValueError("goal must declare exactly reference_exact and cpu_simd_sse2 options")
    return (
        CandidateSpec("reference_exact", "reference", ("reference", "add_scalar")),
        CandidateSpec(
            "cpu_simd_sse2",
            "n-native-x64-sse2-f64",
            ("cpu", "sse2", "sse2_packed_f64"),
        ),
    )


def select_measured(
    goal_name: str,
    candidates: Sequence[CandidateSpec],
    measurements: Sequence[CandidateMeasurement],
    *,
    policy: str = "adaptive-fastest",
) -> SelectionReceipt:
    candidate_names = {candidate.name for candidate in candidates}
    usable = [
        measurement
        for measurement in measurements
        if (
            measurement.candidate in candidate_names
            and measurement.status == "committed"
            and measurement.quality_loss is not None
            and measurement.quality_loss <= 0.0
            and measurement.p50_ms is not None
        )
    ]
    usable.sort(key=lambda item: (float(item.p50_ms), item.candidate))
    selected = usable[0].candidate if usable else None
    detail = None if selected is not None else "no measured candidate satisfied the exact quality contract"
    return SelectionReceipt(
        goal_name,
        policy,
        candidate_set_digest(candidates),
        selected,
        len(candidates),
        tuple(measurements),
        detail,
    )


def synthesize(
    module: NIRModule,
    goal_name: str,
    *,
    available_features: Iterable[str] = (),
) -> GoalDecision:
    goals = [node for node in module.nodes if node["kind"] == "goal" and node["name"] == goal_name]
    if not goals:
        raise ValueError(f"unknown goal {goal_name!r}")
    goal = goals[0]
    required = set(goal.get("required_features", ()))
    available = set(available_features)
    if not required.issubset(available):
        detail = "missing features: " + ", ".join(sorted(required - available))
        payload = {"goal": goal_name, "selected": None, "status": "unavailable", "detail": detail}
        return GoalDecision(goal_name, None, 0, "unavailable", _decision_digest(payload), detail)
    targets = [dict(target) for target in goal["targets"]]
    candidates = list(goal["options"])
    search_count = len(candidates)
    scored: list[tuple[tuple[float, ...], str]] = []
    for candidate in candidates:
        metrics = dict(candidate["metrics"])
        try:
            key = tuple(
                (-float(metrics[target["metric"]]) if target["direction"] == "maximize" else float(metrics[target["metric"]]))
                for target in targets
            )
        except KeyError:
            continue
        scored.append((key, str(candidate["name"])))
    if not scored:
        payload = {"goal": goal_name, "selected": None, "status": "infeasible", "search_count": search_count}
        return GoalDecision(goal_name, None, search_count, "infeasible", _decision_digest(payload), "no option satisfies target metrics")
    _, selected = min(scored, key=lambda item: (item[0], item[1]))
    payload = {
        "goal": goal_name,
        "selected": selected,
        "status": "selected",
        "search_count": search_count,
        "targets": targets,
    }
    return GoalDecision(goal_name, selected, search_count, "selected", _decision_digest(payload))


__all__ = [
    "CandidateMeasurement",
    "CandidateSpec",
    "GoalDecision",
    "SelectionReceipt",
    "candidate_set_digest",
    "candidate_specs",
    "select_measured",
    "synthesize",
]
