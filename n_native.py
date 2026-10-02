"""Native executor for n-owned x86-64 machine code."""

from __future__ import annotations

import ctypes
import os
import platform
import threading
from typing import Any, Mapping

from n_backend_types import Capability
from n_codegen_x64 import code_digest, lower_machine_code
from n_compile import Compilation
from n_lir import legacy_lir_view
from n_plan import PlanError, verify_manifest, verify_selection_receipt


class ExecutableKernel:
    def __init__(self, code: bytes):
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32 = kernel32
        alloc = kernel32.VirtualAlloc
        alloc.restype = ctypes.c_void_p
        alloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32]
        protect = kernel32.VirtualProtect
        protect.restype = ctypes.c_int
        protect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
        release = kernel32.VirtualFree
        release.restype = ctypes.c_int
        release.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32]
        flush = kernel32.FlushInstructionCache
        flush.restype = ctypes.c_int
        flush.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        get_process = kernel32.GetCurrentProcess
        get_process.restype = ctypes.c_void_p

        address = alloc(None, len(code), 0x3000, 0x04)
        if not address:
            raise OSError(ctypes.get_last_error(), "VirtualAlloc failed")
        self._release = release
        self.address = address
        try:
            ctypes.memmove(address, code, len(code))
            old = ctypes.c_uint32()
            if not protect(address, len(code), 0x20, ctypes.byref(old)):
                raise OSError(ctypes.get_last_error(), "VirtualProtect failed")
            if not flush(get_process(), address, len(code)):
                raise OSError(ctypes.get_last_error(), "FlushInstructionCache failed")
            signature = ctypes.CFUNCTYPE(
                None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64
            )
            self.function = signature(address)
        except Exception:
            release(address, 0, 0x8000)
            self.address = None
            raise

    def close(self) -> None:
        address = getattr(self, "address", None)
        if address:
            self._release(address, 0, 0x8000)
            self.address = None

    def __del__(self):
        self.close()


class NativeBackend:
    name = "n-native-x64-sse2-f64"

    def __init__(self):
        self._compilation: Compilation | None = None
        self._kernel: ExecutableKernel | None = None
        self._retired: list[ExecutableKernel] = []
        self._lock = threading.RLock()

    def probe(self) -> Capability:
        if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64", "x64"}:
            return Capability("unavailable", frozenset(), "backend requires Windows x86-64")
        if not hasattr(ctypes, "WinDLL"):
            return Capability("unavailable", frozenset(), "Windows executable-memory API is unavailable")
        return Capability("available", frozenset({"cpu", "sse2", "sse2_packed_f64", "add_scalar"}))

    def initialize(self, compilation: Compilation) -> None:
        verify_manifest(compilation.manifest, compilation.source, compilation.nir)
        if compilation.selection_receipt is not None:
            from n_measure import _hardware_digest

            verify_selection_receipt(
                compilation.manifest,
                compilation.semantic,
                compilation.selection_receipt,
                hardware_digest=_hardware_digest(),
            )
        elif compilation.manifest.selection_receipt_digest not in {"", "0" * 64}:
            raise PlanError("goal compilation is missing its selection receipt")
        if compilation.manifest.planned_digest != compilation.planned.digest:
            raise PlanError("planned digest does not match compilation")
        if compilation.machine.parent_digest != compilation.planned.digest:
            raise PlanError("machine snapshot is not derived from compilation plan")
        if code_digest(compilation.code) != compilation.code_digest:
            raise PlanError("machine-code digest does not match compilation")
        expected_lir = legacy_lir_view(compilation.machine, compilation.manifest)
        if compilation.lir != expected_lir:
            raise PlanError("compiled n-LIR does not match deterministic lowering")
        expected_code = lower_machine_code(compilation.machine, compilation.manifest)
        if compilation.code != expected_code:
            raise PlanError("machine code does not match deterministic lowering")
        if compilation.manifest.backend != self.name:
            raise PlanError("compilation targets a different backend")
        capability = self.probe()
        if capability.status != "available":
            raise RuntimeError(capability.detail or "native backend unavailable")
        if not set(compilation.manifest.required_features).issubset(capability.features):
            missing = sorted(set(compilation.manifest.required_features) - set(capability.features))
            raise PlanError("native backend is missing required features: " + ", ".join(missing))
        with self._lock:
            if self._kernel is None or self._compilation.code_digest != compilation.code_digest:
                if self._kernel is not None:
                    self._retired.append(self._kernel)
                self._kernel = ExecutableKernel(compilation.code)
            self._compilation = compilation

    def close(self) -> None:
        with self._lock:
            kernel = self._kernel
            retired = self._retired
            self._kernel = None
            self._retired = []
            self._compilation = None
        for old in retired:
            old.close()

    def compile_source(self, source: str, **kwargs: Any) -> Compilation:
        from n_compile import compile_source

        return compile_source(source, **kwargs)

    def execute(self, wave: Mapping[str, Any], field: Any):
        from n_rtm import Delta

        with self._lock:
            compilation = self._compilation
            kernel = self._kernel
        if compilation is None or kernel is None:
            raise RuntimeError("native backend has not been initialized with an n compilation")
        manifest = compilation.manifest
        if (
            field.name != manifest.field
            or field.dtype != manifest.dtype
            or field.shape != manifest.shape
            or field.layout != manifest.layout
            or field.device != manifest.device
            or wave.get("name") != manifest.wave
            or wave.get("parameter") != manifest.field
            or wave.get("result") != "delta"
            or wave.get("fallback") != "reject"
            or wave.get("echo", {}).get("mode") != "exact"
        ):
            raise PlanError("runtime field or wave does not match the compiled plan")
        operations = list(wave.get("operations", ()))
        if (
            len(operations) != 4
            or [op.get("kind") for op in operations] != ["read", "write", "delta", "delta_value"]
            or operations[0].get("value") != manifest.field
            or operations[1].get("value") != manifest.field
            or operations[2].get("value") != manifest.operation
            or operations[3].get("value") != manifest.scalar
        ):
            raise PlanError("runtime wave operations do not match the compiled plan")
        values = list(field.values)
        count = len(values)
        padded_count = count + (count & 1)
        padded = values + ([0.0] if count & 1 else [])
        rhs = [manifest.scalar] * padded_count
        input_buffer = (ctypes.c_double * padded_count)(*padded)
        rhs_buffer = (ctypes.c_double * padded_count)(*rhs)
        output_buffer = (ctypes.c_double * padded_count)()
        kernel.function(
            ctypes.addressof(input_buffer),
            ctypes.addressof(rhs_buffer),
            ctypes.addressof(output_buffer),
            padded_count,
        )
        return Delta(field.name, field.epoch, list(output_buffer)[:count])


__all__ = ["ExecutableKernel", "NativeBackend"]
