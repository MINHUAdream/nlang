"""RTM backend adapters.

The reference backend defines the semantics.  TLNativeBackend is an optional
executor for the same operation and reports unavailable instead of silently
falling back when the native artifact is absent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from n_backend_types import Capability


def _scalar(wave: Mapping[str, Any]) -> float:
    values = [
        item["value"]
        for item in wave["operations"]
        if item.get("kind") == "delta_value"
    ]
    if len(values) != 1 or not isinstance(values[0], (int, float)):
        raise ValueError("wave must contain exactly one numeric delta_value")
    return float(values[0])


class ReferenceBackend:
    name = "reference"

    def probe(self) -> Capability:
        return Capability("available", frozenset({"reference", "add_scalar"}))

    def execute(self, wave: Mapping[str, Any], field: Any):
        from n_rtm import Delta, cast_value

        scalar = _scalar(wave)
        values = [cast_value(float(value) + scalar, field.dtype) for value in field.values]
        return Delta(field.name, field.epoch, values)


class TLNativeBackend:
    name = "tl-native"

    def __init__(self, dll_path: str | Path | None = None):
        self.dll_path = Path(dll_path) if dll_path is not None else Path(__file__).with_name("kernels.dll")
        self._kernels = None
        self._detail: str | None = None

    def probe(self) -> Capability:
        if self._kernels is not None:
            return Capability("available", frozenset({"native", "add_scalar"}))
        try:
            import tl_native

            self._kernels = tl_native.load(str(self.dll_path))
        except Exception as exc:  # capability probing must not abort compilation
            self._detail = f"tl_native import failed: {exc}"
            return Capability("unavailable", frozenset(), self._detail)
        if self._kernels is None:
            self._detail = f"native artifact unavailable: {self.dll_path}"
            return Capability("unavailable", frozenset(), self._detail)
        return Capability("available", frozenset({"native", "add_scalar"}))

    def execute(self, wave: Mapping[str, Any], field: Any):
        from n_rtm import Delta, cast_value

        capability = self.probe()
        if capability.status != "available":
            raise RuntimeError(capability.detail or "tl-native backend unavailable")
        scalar = _scalar(wave)
        values = list(field.values)
        output = self._kernels.elem2(values, [scalar] * len(values), 0)
        return Delta(
            field.name,
            field.epoch,
            [cast_value(value, field.dtype) for value in output],
        )


__all__ = ["Capability", "ReferenceBackend", "TLNativeBackend"]
