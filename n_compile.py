"""n source-to-machine-code compilation driver for the initial native subset."""

from __future__ import annotations

from dataclasses import dataclass, replace
import time

from n_codegen_x64 import code_digest, lower_lir, lower_machine_code
from n_front import parse
from n_ir import NIRModule, lower
from n_ir_verify import verify_phase
from n_lir import LIRKernel, legacy_lir_view, lower_machine
from n_plan import PlanManifest, plan_module


@dataclass(frozen=True)
class Compilation:
    source: str
    source_digest: str
    semantic: NIRModule
    planned: NIRModule
    machine: NIRModule
    manifest: PlanManifest
    lir: LIRKernel
    code: bytes
    code_digest: str
    serialization_cost_ms: float
    phase_verify_cost_ms: float

    @property
    def nir(self) -> NIRModule:
        """Compatibility projection for RTM and 0.50 callers."""

        return self.semantic


def compile_source(source: str, target: str = "x86_64-windows") -> Compilation:
    module = parse(source)
    semantic = lower(module)
    manifest = PlanManifest.create(source, semantic, target=target)
    planned = plan_module(semantic, manifest)
    manifest = manifest.bind_planned(planned)
    machine = lower_machine(planned, manifest)
    manifest = manifest.bind_machine(machine)
    lir = legacy_lir_view(machine, manifest)
    code = lower_machine_code(machine, manifest)
    verify_started = time.perf_counter_ns()
    verify_phase(semantic)
    verify_phase(planned)
    verify_phase(machine, target=target)
    phase_verify_cost_ms = (time.perf_counter_ns() - verify_started) / 1_000_000.0
    serialization_started = time.perf_counter_ns()
    semantic.canonical_json()
    planned.canonical_json()
    machine.canonical_json()
    serialization_cost_ms = (
        time.perf_counter_ns() - serialization_started
    ) / 1_000_000.0
    return Compilation(
        source=source,
        source_digest=manifest.source_digest,
        semantic=semantic,
        planned=planned,
        machine=machine,
        manifest=manifest,
        lir=lir,
        code=code,
        code_digest=code_digest(code),
        serialization_cost_ms=serialization_cost_ms,
        phase_verify_cost_ms=phase_verify_cost_ms,
    )


def compile_source_legacy(
    source: str, target: str = "x86_64-windows"
) -> Compilation:
    """Compatibility probe using the old LIR-to-code entry after verified planning."""

    compilation = compile_source(source, target=target)
    code = lower_lir(compilation.lir, compilation.manifest)
    return replace(compilation, code=code, code_digest=code_digest(code))


__all__ = ["Compilation", "compile_source", "compile_source_legacy"]
