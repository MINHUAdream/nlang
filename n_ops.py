"""Operation registry shared by n's semantic, reference, and native paths."""

from __future__ import annotations


SCALAR_OPERATIONS = ("add_scalar", "sub_scalar", "mul_scalar")

_MACHINE_OPCODES = {
    "add_scalar": 0x58,
    "sub_scalar": 0x5C,
    "mul_scalar": 0x59,
}


def validate_scalar_operation(operation: str) -> str:
    if operation not in SCALAR_OPERATIONS:
        raise ValueError(f"unsupported scalar operation {operation!r}")
    return operation


def apply_scalar(operation: str, value: float, scalar: float) -> float:
    validate_scalar_operation(operation)
    if operation == "add_scalar":
        return float(value) + float(scalar)
    if operation == "sub_scalar":
        return float(value) - float(scalar)
    return float(value) * float(scalar)


def packed_f64_opcode(operation: str) -> int:
    validate_scalar_operation(operation)
    return _MACHINE_OPCODES[operation]


def machine_operation_kind(operation: str) -> str:
    return f"machine.{validate_scalar_operation(operation)}"


__all__ = [
    "SCALAR_OPERATIONS",
    "apply_scalar",
    "machine_operation_kind",
    "packed_f64_opcode",
    "validate_scalar_operation",
]
