"""Reference RTM state machine: Field -> Wave -> Echo -> Commit."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import secrets
import struct
import threading
import time
from collections.abc import Mapping
from typing import Any, Sequence


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def cast_value(value: float, dtype: str) -> float:
    value = float(value)
    if dtype == "f64":
        return value
    if dtype == "f32":
        try:
            return struct.unpack("<f", struct.pack("<f", value))[0]
        except OverflowError as exc:
            raise ValueError("f32 value overflow") from exc
    raise ValueError(f"unsupported numeric type {dtype!r}")


@dataclass(frozen=True)
class Delta:
    field: str
    base_epoch: int
    values: tuple[float, ...]

    def __init__(self, field: str, base_epoch: int, values: Sequence[float]):
        object.__setattr__(self, "field", field)
        object.__setattr__(self, "base_epoch", int(base_epoch))
        object.__setattr__(self, "values", tuple(float(value) for value in values))


@dataclass(frozen=True)
class RuntimeField:
    name: str
    dtype: str
    shape: tuple[int, ...]
    layout: str
    device: str
    values: tuple[float, ...]
    epoch: int = 0

    def __post_init__(self):
        object.__setattr__(self, "values", tuple(float(value) for value in self.values))


@dataclass(frozen=True)
class PreparedWave:
    name: str
    field_name: str
    base_epoch: int
    node: Mapping[str, Any]
    delta: Delta
    expected: tuple[float, ...] | None = None

    @property
    def digest(self) -> str:
        payload = {
            "name": self.name,
            "field": self.field_name,
            "base_epoch": self.base_epoch,
            "node": _json_value(self.node),
            "delta": {
                "field": self.delta.field,
                "base_epoch": self.delta.base_epoch,
                "values": list(self.delta.values),
            },
            "expected": list(self.expected) if self.expected is not None else None,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EchoResult:
    status: str
    values: tuple[float, ...] | None
    wave_digest: str | None = None
    proof: str | None = None


@dataclass(frozen=True)
class CommitResult:
    status: str
    epoch: int | None


@dataclass(frozen=True)
class RuntimeReceipt:
    status: str
    commits: int
    verification_calls: int
    fallback_count: int
    verification_time_ns: int = 0


class Runtime:
    def __init__(self, backend: Any):
        self.backend = backend
        self.module = None
        self._fields: dict[str, RuntimeField] = {}
        self._waves: dict[str, Mapping[str, Any]] = {}
        self._commits: tuple[Mapping[str, Any], ...] = ()
        self.verification_calls = 0
        self.verification_time_ns = 0
        self._echo_secret = secrets.token_bytes(32)
        self._lock = threading.RLock()

    def load(self, module: Any, initial: Mapping[str, Sequence[float]]) -> None:
        with self._lock:
            self.module = module
            self.verification_calls = 0
            self.verification_time_ns = 0
            field_nodes = [node for node in module.nodes if node["kind"] == "field"]
            wave_nodes = [node for node in module.nodes if node["kind"] == "wave"]
            self._commits = tuple(node for node in module.nodes if node["kind"] == "commit")
            self._fields.clear()
            self._waves = {str(node["name"]): node for node in wave_nodes}
            for node in field_nodes:
                name = str(node["name"])
                if name not in initial:
                    raise ValueError(f"missing initial value for field {name!r}")
                dtype = str(node["dtype"])
                values = tuple(cast_value(value, dtype) for value in initial[name])
                shape = tuple(int(value) for value in node["shape"])
                expected_size = 1
                for dimension in shape:
                    expected_size *= dimension
                if len(values) != expected_size:
                    raise ValueError(
                        f"field {name!r} expects {expected_size} values, got {len(values)}"
                    )
                self._fields[name] = RuntimeField(
                    name,
                    dtype,
                    shape,
                    str(node["layout"]),
                    str(node["device"]),
                    values,
                )

    def field(self, name: str) -> RuntimeField:
        with self._lock:
            try:
                return self._fields[name]
            except KeyError as exc:
                raise KeyError(f"unknown runtime field {name!r}") from exc

    def prepare_wave(
        self,
        wave_name: str,
        field_name: str,
        expected: Sequence[float] | None = None,
    ) -> PreparedWave:
        if wave_name not in self._waves:
            raise KeyError(f"unknown wave {wave_name!r}")
        field = self.field(field_name)
        node = self._waves[wave_name]
        delta = self.backend.execute(node, field)
        if delta.field != field_name or delta.base_epoch != field.epoch:
            raise ValueError("backend returned a delta for the wrong field or epoch")
        return PreparedWave(
            wave_name,
            field_name,
            field.epoch,
            node,
            delta,
            tuple(cast_value(value, field.dtype) for value in expected) if expected is not None else None,
        )

    def echo_exact(self, wave: PreparedWave) -> EchoResult:
        started = time.perf_counter_ns()
        try:
            return self._echo_exact(wave)
        finally:
            self.verification_time_ns += time.perf_counter_ns() - started

    def _echo_exact(self, wave: PreparedWave) -> EchoResult:
        self.verification_calls += 1
        field = self.field(wave.field_name)
        if field.epoch != wave.base_epoch:
            return EchoResult("fail", None)
        from n_backend_tl import ReferenceBackend

        reference = ReferenceBackend().execute(wave.node, field)
        if wave.expected is not None and tuple(wave.expected) != reference.values:
            return EchoResult("fail", reference.values)
        if wave.delta.values != reference.values:
            return EchoResult("fail", reference.values)
        wave_digest = wave.digest
        proof = hmac.new(self._echo_secret, wave_digest.encode("ascii"), hashlib.sha256).hexdigest()
        return EchoResult("pass", reference.values, wave_digest, proof)

    def commit(self, wave: PreparedWave, echo: EchoResult) -> CommitResult:
        with self._lock:
            field = self.field(wave.field_name)
            if field.epoch != wave.base_epoch or wave.delta.base_epoch != field.epoch:
                return CommitResult("stale", field.epoch)
            if echo.status == "unknown":
                return CommitResult("fallback_required", field.epoch)
            if echo.status != "pass":
                return CommitResult("echo_failed", field.epoch)
            if len(wave.delta.values) != len(field.values):
                return CommitResult("conflict", field.epoch)
            expected_proof = hmac.new(
                self._echo_secret, wave.digest.encode("ascii"), hashlib.sha256
            ).hexdigest()
            if (
                echo.wave_digest != wave.digest
                or echo.values != wave.delta.values
                or echo.proof is None
                or not hmac.compare_digest(echo.proof, expected_proof)
            ):
                return CommitResult("invalid_echo", field.epoch)
            self._fields[wave.field_name] = RuntimeField(
                field.name,
                field.dtype,
                field.shape,
                field.layout,
                field.device,
                wave.delta.values,
                field.epoch + 1,
            )
            return CommitResult("committed", field.epoch + 1)

    def run(self) -> RuntimeReceipt:
        commits = 0
        fallback_count = 0
        for commit in self._commits:
            wave = self.prepare_wave(str(commit["wave"]), str(commit["field"]))
            echo = self.echo_exact(wave)
            result = self.commit(wave, echo)
            if result.status != "committed":
                if result.status == "fallback_required":
                    fallback_count += 1
                return RuntimeReceipt(
                    result.status,
                    commits,
                    self.verification_calls,
                    fallback_count,
                    self.verification_time_ns,
                )
            commits += 1
        return RuntimeReceipt(
            "committed",
            commits,
            self.verification_calls,
            fallback_count,
            self.verification_time_ns,
        )


__all__ = [
    "CommitResult",
    "Delta",
    "EchoResult",
    "PreparedWave",
    "Runtime",
    "RuntimeField",
    "RuntimeReceipt",
    "cast_value",
]
