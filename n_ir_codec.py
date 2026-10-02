"""Deterministic, integrity-checked binary artifacts for unified nIR modules."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
from typing import Any, Mapping

from n_ir import IRValidationError, NIRModule


MAGIC = b"NIR1"
FORMAT_VERSION = 1
MAX_PAYLOAD_SIZE = 64 * 1024 * 1024
_HEADER = struct.Struct(">4sBQ32s")
HEADER_SIZE = _HEADER.size


class NIRCodecError(ValueError):
    """The binary nIR envelope or canonical payload is invalid."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NIRCodecError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _payload(module: NIRModule) -> bytes:
    if module.schema != "n-ir/0.7":
        raise NIRCodecError("binary nIR codec requires n-ir/0.7")
    payload = module.canonical_json().encode("utf-8")
    if len(payload) > MAX_PAYLOAD_SIZE:
        raise NIRCodecError("nIR payload exceeds codec size limit")
    return payload


def encode_nir(module: NIRModule) -> bytes:
    """Encode a unified nIR module into a deterministic binary artifact."""

    payload = _payload(module)
    return _HEADER.pack(
        MAGIC,
        FORMAT_VERSION,
        len(payload),
        hashlib.sha256(payload).digest(),
    ) + payload


def decode_nir(data: bytes | bytearray | memoryview) -> NIRModule:
    """Validate and decode one complete binary nIR artifact."""

    try:
        raw = bytes(data)
    except (TypeError, ValueError) as exc:
        raise NIRCodecError("nIR artifact must be bytes-like") from exc
    if len(raw) < HEADER_SIZE:
        raise NIRCodecError("nIR artifact is truncated before its header")
    magic, version, payload_length, expected_digest = _HEADER.unpack_from(raw)
    if magic != MAGIC:
        raise NIRCodecError("invalid nIR magic")
    if version != FORMAT_VERSION:
        raise NIRCodecError(f"unsupported nIR format version {version}")
    if payload_length > MAX_PAYLOAD_SIZE:
        raise NIRCodecError("nIR payload exceeds codec size limit")
    actual_length = len(raw) - HEADER_SIZE
    if payload_length != actual_length:
        raise NIRCodecError("nIR payload length does not match artifact length")
    payload = raw[HEADER_SIZE:]
    if hashlib.sha256(payload).digest() != expected_digest:
        raise NIRCodecError("nIR payload digest does not match envelope")
    try:
        text = payload.decode("utf-8")
        parsed = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except NIRCodecError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NIRCodecError("nIR payload is not valid UTF-8 JSON") from exc
    if not isinstance(parsed, Mapping):
        raise NIRCodecError("nIR payload root must be an object")
    try:
        module = NIRModule.from_dict(parsed)
        if module.schema != "n-ir/0.7":
            raise NIRCodecError("binary nIR codec requires n-ir/0.7")
        canonical = module.canonical_json().encode("utf-8")
    except NIRCodecError:
        raise
    except (KeyError, TypeError, ValueError, IRValidationError) as exc:
        raise NIRCodecError("nIR payload failed module validation") from exc
    if canonical != payload:
        raise NIRCodecError("nIR payload is not canonical JSON")
    return module


def write_nir(path: str | Path, module: NIRModule) -> None:
    """Write one nIR artifact without changing the source module."""

    Path(path).write_bytes(encode_nir(module))


def read_nir(path: str | Path) -> NIRModule:
    """Read and validate one nIR artifact from disk."""

    return decode_nir(Path(path).read_bytes())


__all__ = [
    "FORMAT_VERSION",
    "HEADER_SIZE",
    "MAGIC",
    "MAX_PAYLOAD_SIZE",
    "NIRCodecError",
    "decode_nir",
    "encode_nir",
    "read_nir",
    "write_nir",
]
