"""Backend capability types shared by the n execution adapters."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    status: str
    features: frozenset[str]
    detail: str | None = None


__all__ = ["Capability"]
