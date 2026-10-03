"""Minimal n-owned Windows x64/SSE2 encoder for the native slice."""

from __future__ import annotations


class X64Encoder:
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


def encode_scalar_f64x2(operation: str) -> bytes:
    """Encode a deterministic two-lane packed-f64 scalar kernel."""

    from n_ops import packed_f64_opcode

    packed_opcode = packed_f64_opcode(operation)

    encoder = X64Encoder()
    encoder.push(6)
    encoder.push(7)
    encoder.push(3)
    encoder.push(12)
    encoder.mov(6, 1)
    encoder.mov(7, 2)
    encoder.mov(3, 8)
    encoder.mov(12, 9)
    encoder.shr(12, 1)
    encoder.xor32(1, 1)
    encoder.label("pair")
    encoder.cmp(1, 12)
    encoder.jge("done")
    encoder.loadupd(0, 6)
    encoder.loadupd(1, 7)
    encoder.emit(0x66)
    encoder.emit(0x0F, packed_opcode, 0xC1)
    encoder.storeupd(0, 3)
    encoder.add_imm32(6, 16)
    encoder.add_imm32(7, 16)
    encoder.add_imm32(3, 16)
    encoder.inc(1)
    encoder.jump("pair")
    encoder.label("done")
    encoder.pop(12)
    encoder.pop(3)
    encoder.pop(7)
    encoder.pop(6)
    encoder.emit(0xC3)
    return encoder.finish()


def encode_add_scalar_f64x2() -> bytes:
    """Compatibility wrapper for the original add kernel encoder."""

    return encode_scalar_f64x2("add_scalar")


__all__ = ["X64Encoder", "encode_add_scalar_f64x2", "encode_scalar_f64x2"]
