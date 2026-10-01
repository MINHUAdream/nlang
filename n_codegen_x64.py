"""Small n-owned Windows x64/SSE2 lowering for validated NIR plans."""

from __future__ import annotations

import hashlib
import math

from n_ir import IRPhase, IRValidationError, NIRModule
from n_ir_verify import verify_phase
from n_machine_encoder_x64 import encode_add_scalar_f64x2
from n_lir import LIRKernel, legacy_lir_view, lower_to_lir
from n_plan import PlanError, PlanManifest


class _X64Encoder:
    def __init__(self):
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str]] = []

    def emit(self, *values: int) -> None:
        self.code.extend(value & 0xFF for value in values)

    def imm32(self, value: int) -> None:
        self.code.extend(int(value).to_bytes(4, "little", signed=True))

    def label(self, name: str) -> None:
        self.labels[name] = len(self.code)

    def push(self, register: int) -> None:
        if register >= 8:
            self.emit(0x41)
        self.emit(0x50 + (register & 7))

    def pop(self, register: int) -> None:
        if register >= 8:
            self.emit(0x41)
        self.emit(0x58 + (register & 7))

    def mov(self, destination: int, source: int) -> None:
        rex = 0x48 | ((source >> 3) << 2) | (destination >> 3)
        self.emit(rex, 0x89, 0xC0 | ((source & 7) << 3) | (destination & 7))

    def shr(self, register: int, amount: int) -> None:
        self.emit(0x48 | (register >> 3), 0xC1, 0xE8 | (register & 7), amount)

    def xor32(self, destination: int, source: int) -> None:
        self.emit(0x31, 0xC0 | ((source & 7) << 3) | (destination & 7))

    def cmp(self, left: int, right: int) -> None:
        rex = 0x48 | ((right >> 3) << 2) | (left >> 3)
        self.emit(rex, 0x39, 0xC0 | ((right & 7) << 3) | (left & 7))

    def inc(self, register: int) -> None:
        self.emit(0x48 | (register >> 3), 0xFF, 0xC0 | (register & 7))

    def add_imm32(self, register: int, value: int) -> None:
        self.emit(0x48 | (register >> 3), 0x81, 0xC0 | (register & 7))
        self.imm32(value)

    def _mem_xmm(self, opcode: int, xmm: int, base: int) -> None:
        self.emit(0x66)
        rex = 0x40 | ((xmm >> 3) << 2) | (base >> 3)
        if rex != 0x40:
            self.emit(rex)
        self.emit(0x0F, opcode, ((xmm & 7) << 3) | 4, 0x20 | (base & 7))

    def loadupd(self, xmm: int, base: int) -> None:
        self._mem_xmm(0x10, xmm, base)

    def storeupd(self, xmm: int, base: int) -> None:
        self._mem_xmm(0x11, xmm, base)

    def addpd(self, destination: int, source: int) -> None:
        self.emit(0x66)
        rex = 0x40 | ((destination >> 3) << 2) | (source >> 3)
        if rex != 0x40:
            self.emit(rex)
        self.emit(0x0F, 0x58, 0xC0 | ((destination & 7) << 3) | (source & 7))

    def jge(self, label: str) -> None:
        self.emit(0x0F, 0x8D)
        self.fixups.append((len(self.code), label))
        self.imm32(0)

    def jump(self, label: str) -> None:
        self.emit(0xE9)
        self.fixups.append((len(self.code), label))
        self.imm32(0)

    def finish(self) -> bytes:
        for position, target in self.fixups:
            if target not in self.labels:
                raise ValueError(f"undefined machine-code label {target!r}")
            relative = self.labels[target] - (position + 4)
            self.code[position : position + 4] = relative.to_bytes(4, "little", signed=True)
        return bytes(self.code)


def lower_lir(lir: LIRKernel, manifest: PlanManifest) -> bytes:
    if manifest.schema not in {"n-plan/1", "n-plan/2"} or manifest.backend != "n-native-x64-sse2-f64":
        raise PlanError("unsupported native plan schema or backend")
    if manifest.target != "x86_64-windows":
        raise PlanError("target does not match native plan")
    output_name = f"delta:{manifest.field}"
    if (
        lir.schema != "n-lir/1"
        or lir.name != manifest.wave
        or len(lir.buffers) != 2
        or lir.buffers[0].name != manifest.field
        or lir.buffers[0].role != "input"
        or lir.buffers[1].name != output_name
        or lir.buffers[1].role != "output"
        or any(buffer.dtype != manifest.dtype for buffer in lir.buffers)
        or any(buffer.shape != manifest.shape for buffer in lir.buffers)
        or any(buffer.layout != manifest.layout for buffer in lir.buffers)
        or any(buffer.device != manifest.device for buffer in lir.buffers)
        or lir.loop_extent != math.prod(manifest.shape)
        or len(lir.operations) != 1
        or lir.operations[0].opcode != manifest.operation
        or lir.operations[0].inputs != (manifest.field,)
        or lir.operations[0].output != output_name
        or lir.operations[0].scalar != manifest.scalar
        or lir.effects != (f"read:{manifest.field}", f"write:{output_name}")
        or lir.numeric_contract != "exact-reference-f64"
        or lir.fallback != manifest.fallback
        or manifest.dtype != "f64"
        or manifest.layout != "contiguous"
        or manifest.device != "cpu"
        or manifest.operation != "add_scalar"
        or manifest.required_features != ("cpu", "sse2", "sse2_packed_f64")
        or manifest.fallback != "reference_exact_reject_on_mismatch"
    ):
        raise PlanError("native plan does not match typed n-LIR")

    return encode_add_scalar_f64x2()


def lower_plan(nir: NIRModule, manifest: PlanManifest) -> bytes:
    """Compatibility entry point; native codegen itself consumes typed n-LIR."""

    return lower_lir(lower_to_lir(nir, manifest), manifest)


def lower_machine_code(machine: NIRModule, manifest: PlanManifest) -> bytes:
    """Generate code only from a verified, manifest-bound machine snapshot."""

    if machine.phase != IRPhase.MACHINE:
        raise PlanError("native code generation requires machine phase nIR")
    if manifest.machine_digest != machine.digest:
        raise PlanError("machine digest does not match plan manifest")
    if manifest.planned_digest != machine.parent_digest:
        raise PlanError("machine parent does not match planned manifest digest")
    try:
        verify_phase(machine, target=manifest.target)
    except IRValidationError as exc:
        raise PlanError(f"machine nIR failed verification: {exc}") from exc
    return lower_lir(legacy_lir_view(machine, manifest), manifest)


def code_digest(code: bytes) -> str:
    return hashlib.sha256(code).hexdigest()


__all__ = ["code_digest", "lower_lir", "lower_machine_code", "lower_plan"]
