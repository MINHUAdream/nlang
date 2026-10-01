"""Explicit execution-fabric capability probing for n backends."""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
import os
import platform
from typing import Mapping


@dataclass(frozen=True)
class FabricCapability:
    kind: str
    status: str
    features: frozenset[str]
    detail: str | None = None


def _probe_cpu() -> FabricCapability:
    architecture = platform.machine().lower() or "unknown"
    features = {"scalar", architecture}
    if architecture in {"amd64", "x86_64", "x64"}:
        features.add("sse2")
    return FabricCapability("cpu", "available", frozenset(features), architecture)


def _probe_gpu() -> FabricCapability:
    names = ("nvcuda.dll",) if os.name == "nt" else ("libcuda.so", "libcuda.so.1")
    for name in names:
        try:
            loader = ctypes.WinDLL if os.name == "nt" else ctypes.CDLL
            library = loader(name)
            init = library.cuInit
            init.argtypes = [ctypes.c_uint]
            init.restype = ctypes.c_int
            count = library.cuDeviceGetCount
            count.argtypes = [ctypes.POINTER(ctypes.c_int)]
            count.restype = ctypes.c_int
            if init(0) != 0:
                return FabricCapability("gpu", "unavailable", frozenset(), f"CUDA driver init failed: {name}")
            devices = ctypes.c_int(0)
            if count(ctypes.byref(devices)) != 0 or devices.value < 1:
                return FabricCapability("gpu", "unavailable", frozenset(), f"no CUDA devices: {name}")
            return FabricCapability(
                "gpu", "available", frozenset({"cuda"}), f"{name} devices={devices.value}"
            )
        except OSError:
            continue
        except AttributeError as exc:
            return FabricCapability("gpu", "unavailable", frozenset(), f"CUDA probe incomplete: {exc}")
    return FabricCapability("gpu", "unavailable", frozenset(), "no CUDA runtime or device library")


def _probe_npu() -> FabricCapability:
    return FabricCapability("npu", "unavailable", frozenset(), "no registered NPU executor")


def _probe_cxl() -> FabricCapability:
    return FabricCapability("cxl", "unavailable", frozenset(), "no portable CXL memory provider registered")


def probe_fabric() -> Mapping[str, FabricCapability]:
    """Return capability facts without claiming execution support."""

    return {
        "cpu": _probe_cpu(),
        "gpu": _probe_gpu(),
        "npu": _probe_npu(),
        "cxl": _probe_cxl(),
    }


__all__ = ["FabricCapability", "probe_fabric"]
