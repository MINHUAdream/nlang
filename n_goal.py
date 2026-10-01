"""Deterministic goal synthesis over NIR-RTM options."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Mapping

from n_ir import NIRModule


@dataclass(frozen=True)
class GoalDecision:
    goal: str
    selected: str | None
    search_count: int
    status: str
    digest: str
    detail: str | None = None


def _decision_digest(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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


__all__ = ["GoalDecision", "synthesize"]
