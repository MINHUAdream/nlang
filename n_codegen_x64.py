"""Small n-owned Windows x64/SSE2 lowering for validated NIR plans."""

from __future__ import annotations

import hashlib
import math

from n_ir import IRPhase, IRValidationError, NIRModule
from n_ir_verify import verify_phase
from n_machine_encoder_x64 import encode_scalar_f64x2
from n_lir import LIRKernel, legacy_lir_view, lower_to_lir
from n_ops import validate_scalar_operation
from n_plan import PlanError, PlanManifest


def lower_lir(lir: LIRKernel, manifest: PlanManifest) -> bytes:
    if manifest.schema not in {"n-plan/1", "n-plan/2"} or manifest.backend != "n-native-x64-sse2-f64":
        raise PlanError("unsupported native plan schema or backend")
    if manifest.target != "x86_64-windows":
        raise PlanError("target does not match native plan")
    try:
        operation = validate_scalar_operation(manifest.operation)
    except ValueError as exc:
        raise PlanError(str(exc)) from exc
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
        or operation != manifest.operation
        or manifest.required_features
        != ("cpu", "sse2", "sse2_packed_f64", manifest.operation)
        or manifest.fallback != "reference_exact_reject_on_mismatch"
    ):
        raise PlanError("native plan does not match typed n-LIR")

    return encode_scalar_f64x2(manifest.operation)


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
