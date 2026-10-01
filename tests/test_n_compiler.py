import unittest
from dataclasses import replace
import hashlib

from n_compile import compile_source, compile_source_legacy
from n_native import NativeBackend
from n_plan import PlanError, verify_manifest
from n_front import parse
from n_codegen_x64 import lower_lir, lower_machine_code, lower_plan
from n_ir import IRPhase, lower
from n_lir import lower_machine
from n_rtm import Runtime


HERE = __import__("pathlib").Path(__file__).resolve().parents[1]
SOURCE = (HERE / "examples" / "rtm_add_one.n").read_text(encoding="utf-8")


class NativeCompilerTests(unittest.TestCase):
    def test_compile_binds_source_nir_plan_and_machine_code(self):
        compilation = compile_source(SOURCE)
        repeated = compile_source(SOURCE)
        payload = compilation.manifest.to_dict()
        self.assertEqual(payload["source_digest"], compilation.source_digest)
        self.assertEqual(payload["nir_digest"], compilation.nir.digest)
        self.assertEqual(payload["semantic_digest"], compilation.semantic.digest)
        self.assertEqual(payload["planned_digest"], compilation.planned.digest)
        self.assertEqual(payload["machine_digest"], compilation.machine.digest)
        self.assertEqual(IRPhase.SEMANTIC, compilation.semantic.phase)
        self.assertEqual(IRPhase.PLANNED, compilation.planned.phase)
        self.assertEqual(compilation.semantic.digest, compilation.planned.parent_digest)
        self.assertEqual(IRPhase.MACHINE, compilation.machine.phase)
        self.assertEqual(compilation.planned.digest, compilation.machine.parent_digest)
        self.assertEqual(compilation.lir.schema, "n-lir/1")
        self.assertEqual(compilation.lir.effects, ("read:x", "write:delta:x"))
        self.assertEqual(compilation.lir.loop_extent, 4)
        self.assertEqual(len(compilation.lir.digest), 64)
        self.assertEqual(len(payload["digest"]), 64)
        self.assertEqual(len(compilation.code_digest), 64)
        self.assertTrue(compilation.code)
        self.assertIn(bytes.fromhex("660f58"), compilation.code)
        self.assertEqual(compilation.code, repeated.code)
        self.assertEqual(compilation.semantic.digest, repeated.semantic.digest)
        self.assertEqual(compilation.planned.digest, repeated.planned.digest)
        self.assertEqual(compilation.machine.digest, repeated.machine.digest)
        self.assertEqual(compilation.lir.digest, repeated.lir.digest)
        self.assertEqual(compilation.code_digest, repeated.code_digest)
        self.assertNotEqual(
            compilation.manifest.digest,
            compile_source(SOURCE.replace("1.0", "2.0")).manifest.digest,
        )

    def test_changed_manifest_cannot_lower_bound_planned_snapshot(self):
        compilation = compile_source(SOURCE)
        altered = replace(compilation.manifest, fallback="unchecked")

        with self.assertRaisesRegex(PlanError, "planned snapshot"):
            lower_machine(compilation.planned, altered)

    def test_codegen_rejects_non_machine_phase(self):
        compilation = compile_source(SOURCE)

        with self.assertRaisesRegex(PlanError, "machine phase"):
            lower_machine_code(compilation.planned, compilation.manifest)

    def test_codegen_rejects_machine_snapshot_not_bound_by_manifest(self):
        compilation = compile_source(SOURCE)
        altered = replace(compilation.manifest, machine_digest="f" * 64)

        with self.assertRaisesRegex(PlanError, "machine digest"):
            lower_machine_code(compilation.machine, altered)

    def test_legacy_lir_projection_matches_machine_codegen(self):
        unified = compile_source(SOURCE)
        legacy = compile_source_legacy(SOURCE)

        self.assertEqual(unified.semantic.digest, legacy.semantic.digest)
        self.assertEqual(unified.lir.digest, legacy.lir.digest)
        self.assertEqual(unified.code_digest, legacy.code_digest)
        self.assertEqual(unified.code, legacy.code)

    def test_native_loader_rejects_broken_phase_lineage(self):
        compilation = compile_source(SOURCE)
        forged_machine = replace(compilation.machine, parent_digest="0" * 64)
        forged = replace(compilation, machine=forged_machine)

        with self.assertRaisesRegex(PlanError, "not derived"):
            NativeBackend().initialize(forged)

    def test_objective_epoch_change_invalidates_planned_snapshot(self):
        compilation = compile_source(SOURCE)
        altered = replace(compilation.manifest, objective_epoch=1)

        with self.assertRaisesRegex(PlanError, "planned snapshot"):
            lower_machine(compilation.planned, altered)

    def test_compile_rejects_unsupported_native_type_layout_device_and_target(self):
        cases = (
            (SOURCE.replace("f64", "f32"), "requires f64"),
            (SOURCE.replace("contiguous", "strided"), "requires contiguous"),
            (SOURCE.replace("device cpu", "device gpu"), "requires cpu"),
        )
        for source, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(PlanError, message):
                    compile_source(source)
        with self.assertRaisesRegex(PlanError, "unsupported native target"):
            compile_source(SOURCE, target="aarch64")

    def test_lowering_rejects_manifest_with_changed_fallback_contract(self):
        compilation = compile_source(SOURCE)
        altered = replace(compilation.manifest, fallback="unchecked")
        with self.assertRaisesRegex(PlanError, "does not match typed n-LIR"):
            lower_plan(compilation.nir, altered)

    def test_lowering_rejects_lir_with_wrong_loop_extent(self):
        compilation = compile_source(SOURCE)
        altered = replace(compilation.lir, loop_extent=1)
        with self.assertRaisesRegex(PlanError, "does not match typed n-LIR"):
            lower_lir(altered, compilation.manifest)

    def test_native_loader_rejects_self_consistent_but_unexpected_code(self):
        compilation = compile_source(SOURCE)
        forged_code = b"\xC3"
        forged = replace(
            compilation,
            code=forged_code,
            code_digest=hashlib.sha256(forged_code).hexdigest(),
        )
        with self.assertRaisesRegex(PlanError, "does not match deterministic lowering"):
            NativeBackend().initialize(forged)

    def test_manifest_rejects_changed_source(self):
        compilation = compile_source(SOURCE)
        changed = SOURCE.replace("1.0", "2.0")
        with self.assertRaisesRegex(PlanError, "source digest"):
            verify_manifest(compilation.manifest, changed, lower(parse(changed)))

    def test_native_backend_executes_n_source_when_host_supports_it(self):
        from n_measure import measure

        backend = NativeBackend()
        capability = backend.probe()
        if capability.status != "available":
            self.skipTest(capability.detail or "native backend unavailable")
        receipt = measure(
            SOURCE,
            {"x": [1.0, 2.0, 3.0, 4.0]},
            backend,
            samples=2,
        )
        self.assertEqual(receipt.status, "committed")
        self.assertEqual(receipt.backend, "n-native-x64-sse2-f64")
        self.assertIsNotNone(receipt.plan_digest)
        self.assertIsNotNone(receipt.lir_digest)
        self.assertIsNotNone(receipt.code_digest)
        self.assertEqual(receipt.quality_loss, 0.0)
        for values in ([1.0, 2.0, 3.0], [7.0]):
            source = SOURCE.replace("f64[4]", f"f64[{len(values)}]")
            compilation = compile_source(source)
            backend.initialize(compilation)
            runtime = Runtime(backend)
            runtime.load(compilation.nir, {"x": values})
            run_receipt = runtime.run()
            self.assertEqual(run_receipt.status, "committed")
            self.assertEqual(
                runtime.field("x").values,
                tuple(value + 1.0 for value in values),
            )
            self.assertGreaterEqual(run_receipt.verification_time_ns, 0)
        backend.close()
        self.assertEqual(backend._retired, [])


if __name__ == "__main__":
    unittest.main()
