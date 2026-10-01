"""Windows x86-64 SSE2 backend for packed float64 elementwise transitions."""

from __future__ import annotations

import ctypes
import os
import platform
import threading
from typing import Any, Mapping

from n_backend_tl import Capability, _scalar


class _ExecutableKernel:
    def __init__(self, code: bytes):
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
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

        address = alloc(None, len(code), 0x3000, 0x04)  # MEM_COMMIT|RESERVE, PAGE_READWRITE
        if not address:
            raise OSError(ctypes.get_last_error(), "VirtualAlloc failed")
        self._kernel32 = kernel32
        self.address = address
        self._release = release
        try:
            ctypes.memmove(address, code, len(code))
            old = ctypes.c_uint32()
            if not protect(address, len(code), 0x20, ctypes.byref(old)):  # PAGE_EXECUTE_READ
                raise OSError(ctypes.get_last_error(), "VirtualProtect failed")
            if not flush(get_process(), address, len(code)):
                raise OSError(ctypes.get_last_error(), "FlushInstructionCache failed")
            signature = ctypes.CFUNCTYPE(
                None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int
            )
            self.function = signature(address)
        except Exception:
            release(address, 0, 0x8000)  # MEM_RELEASE
            self.address = None
            raise

    def close(self) -> None:
        if self.address:
            self._release(self.address, 0, 0x8000)
            self.address = None

    def __del__(self):
        self.close()


def _build_add_f64x2() -> bytes:
    from tl_emit import Enc

    e = Enc()
    e.push_r64(0x6)   # rsi: source
    e.push_r64(0x7)   # rdi: rhs
    e.push_r64(0x3)   # rbx: output
    e.push_r64(0xC)   # r12: pair count
    e.mov_r64_r64(0x6, 0x1)
    e.mov_r64_r64(0x7, 0x2)
    e.mov_r64_r64(0x3, 0x8)
    e.mov_r64_r64(0xC, 0x9)
    e.shr_r64_imm(0xC, 1)
    e.xor_r32_r32(1, 1)
    e.label("L_pair")
    e.cmp_r64_r64(1, 0xC)
    e.jge("L_done")
    e.movupd_load_xmm(0, 0x6)
    e.movupd_load_xmm(1, 0x7)
    e.addpd_xmm_xmm(0, 1)
    e.movupd_store_xmm(0, 0x3)
    e.add_r64_imm(0x6, 16)
    e.add_r64_imm(0x7, 16)
    e.add_r64_imm(0x3, 16)
    e.inc_r64(1)
    e.jmp("L_pair")
    e.label("L_done")
    e.pop_r64(0xC)
    e.pop_r64(0x3)
    e.pop_r64(0x7)
    e.pop_r64(0x6)
    e.ret()
    e.patch()
    return bytes(e.code)


class CPUSIMDBackend:
    """Two-lane SSE2 float64 add with explicit zero-padded vector tail."""

    name = "cpu-simd-sse2-f64"

    def __init__(self):
        self._kernel: _ExecutableKernel | None = None
        self._lock = threading.Lock()
        self._detail: str | None = None

    def probe(self) -> Capability:
        if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64", "x64"}:
            return Capability("unavailable", frozenset(), "backend requires Windows x86-64")
        try:
            with self._lock:
                if self._kernel is None:
                    self._kernel = _ExecutableKernel(_build_add_f64x2())
            return Capability("available", frozenset({"cpu", "sse2", "sse2_packed_f64", "add_scalar"}))
        except Exception as exc:
            self._detail = f"SSE2 executor initialization failed: {exc}"
            return Capability("unavailable", frozenset(), self._detail)

    def execute(self, wave: Mapping[str, Any], field: Any):
        from n_rtm import Delta

        capability = self.probe()
        if capability.status != "available":
            raise RuntimeError(capability.detail or "CPU SIMD backend unavailable")
        if field.dtype != "f64":
            raise TypeError("cpu-simd-sse2-f64 requires field dtype f64")
        values = [float(value) for value in field.values]
        count = len(values)
        padded_count = count + (count & 1)
        padded = values + ([0.0] if count & 1 else [])
        rhs = [_scalar(wave)] * padded_count
        storage_size = max(2, padded_count)
        input_buffer = (ctypes.c_double * storage_size)(*(padded + [0.0] * (storage_size - padded_count)))
        rhs_buffer = (ctypes.c_double * storage_size)(*(rhs + [0.0] * (storage_size - padded_count)))
        output_buffer = (ctypes.c_double * storage_size)()
        self._kernel.function(
            ctypes.addressof(input_buffer),
            ctypes.addressof(rhs_buffer),
            ctypes.addressof(output_buffer),
            padded_count,
        )
        return Delta(field.name, field.epoch, list(output_buffer)[:count])


__all__ = ["CPUSIMDBackend"]
