import unittest

from n_backend_simd import CPUSIMDBackend
from n_backend_tl import ReferenceBackend
from n_compile import compile_source
from n_front import NParseError, parse
from n_measure import _file_digest, measure
from n_native import NativeBackend
from n_rtm import Runtime


def source_for(operation: str, scalar: float = 2.0, size: int = 5) -> str:
    return f"""module kernel_family;

field x: f64[{size}] layout contiguous device cpu;

wave transform(x) -> delta {{
    read x;
    write x;
    delta {operation} {scalar};
    echo exact;
    fallback reject;
}}

commit transform into x;
"""


def goal_source_for(operation: str) -> str:
    return source_for(operation, scalar=1.0, size=4) + """
goal transform_plan {
  target minimize cost;
  target maximize quality;
  require [cpu];
  option reference_exact { cost: 1.0; quality: 1.0; };
  option cpu_simd_sse2 { cost: 0.5; quality: 1.0; };
}
synthesize transform_plan;
"""


class KernelFamilyParserTests(unittest.TestCase):
    def test_parser_accepts_add_sub_and_mul_scalar(self):
        for operation in ("add_scalar", "sub_scalar", "mul_scalar"):
            with self.subTest(operation=operation):
                module = parse(source_for(operation))
                self.assertEqual(module.waves[0].operations[2].value, operation)

    def test_parser_rejects_unknown_scalar_operation(self):
        with self.assertRaisesRegex(NParseError, "unknown wave delta operation"):
            parse(source_for("div_scalar"))


class KernelFamilyReferenceTests(unittest.TestCase):
    def test_reference_backend_executes_sub_and_mul_scalar(self):
        for operation, expected in (
            ("sub_scalar", (-1.0, 0.0, 1.0, 2.0, 3.0)),
            ("mul_scalar", (2.0, 4.0, 6.0, 8.0, 10.0)),
        ):
            with self.subTest(operation=operation):
                compilation = compile_source(source_for(operation))
                runtime = Runtime(ReferenceBackend())
                runtime.load(compilation.semantic, {"x": [1.0, 2.0, 3.0, 4.0, 5.0]})
                receipt = runtime.run()
                self.assertEqual(receipt.status, "committed")
                self.assertEqual(runtime.field("x").values, expected)


class KernelFamilyCompilerTests(unittest.TestCase):
    def test_measured_goal_compiles_each_scalar_operation(self):
        for operation in ("add_scalar", "sub_scalar", "mul_scalar"):
            with self.subTest(operation=operation):
                compilation = compile_source(
                    goal_source_for(operation),
                    initial={"x": [1.0, 2.0, 3.0, 4.0]},
                    samples=1,
                    warmup_samples=0,
                )
                self.assertEqual(compilation.manifest.operation, operation)
                self.assertEqual(compilation.goal_decision.status, "selected")
                self.assertEqual(compilation.selection_receipt.search_count, 2)

    def test_operation_flows_through_plan_lir_machine_and_code(self):
        expected_opcode = {
            "add_scalar": bytes.fromhex("660f58"),
            "sub_scalar": bytes.fromhex("660f5c"),
            "mul_scalar": bytes.fromhex("660f59"),
        }
        for operation, opcode in expected_opcode.items():
            with self.subTest(operation=operation):
                compilation = compile_source(source_for(operation))
                self.assertEqual(compilation.manifest.operation, operation)
                self.assertEqual(compilation.lir.operations[0].opcode, operation)
                self.assertIn(f"machine.{operation}", {item["kind"] for item in compilation.machine.operations})
                self.assertIn(opcode, compilation.code)
                self.assertEqual(compilation.code, compile_source(source_for(operation)).code)

    def test_native_backend_executes_kernel_family_when_available(self):
        backend = NativeBackend()
        if backend.probe().status != "available":
            self.skipTest("n-owned native backend unavailable on this host")
        try:
            for operation, expected in (
                ("add_scalar", (3.0, 4.0, 5.0, 6.0, 7.0)),
                ("sub_scalar", (-1.0, 0.0, 1.0, 2.0, 3.0)),
                ("mul_scalar", (2.0, 4.0, 6.0, 8.0, 10.0)),
            ):
                with self.subTest(operation=operation):
                    compilation = compile_source(source_for(operation))
                    backend.initialize(compilation)
                    runtime = Runtime(backend)
                    runtime.load(compilation.semantic, {"x": [1.0, 2.0, 3.0, 4.0, 5.0]})
                    self.assertEqual(runtime.run().status, "committed")
                    self.assertEqual(runtime.field("x").values, expected)
        finally:
            backend.close()


class KernelFamilyReceiptTests(unittest.TestCase):
    def test_receipt_digests_include_operation_registry(self):
        receipt = measure(
            source_for("mul_scalar"),
            {"x": [1.0, 2.0, 3.0, 4.0, 5.0]},
            ReferenceBackend(),
            samples=1,
            warmup_samples=0,
        )
        self.assertEqual(receipt.status, "committed")
        self.assertEqual(
            receipt.compiler_digest,
            _file_digest(
                (
                    "n_front.py",
                    "n_ir.py",
                    "n_ir_verify.py",
                    "n_goal.py",
                    "n_plan.py",
                    "n_lir.py",
                    "n_codegen_x64.py",
                    "n_machine_encoder_x64.py",
                    "n_compile.py",
                    "n_ops.py",
                )
            ),
        )
        self.assertEqual(
            receipt.backend_digest,
            _file_digest(("n_backend_tl.py", "n_backend_types.py", "n_ops.py")),
        )

    def test_cpu_simd_receipt_binds_encoder_and_operation_registry(self):
        receipt = measure(
            source_for("sub_scalar"),
            {"x": [1.0, 2.0, 3.0, 4.0, 5.0]},
            CPUSIMDBackend(),
            samples=1,
            warmup_samples=0,
        )
        if receipt.status == "unavailable":
            self.skipTest("CPU SIMD backend unavailable")
        self.assertEqual(receipt.status, "committed")
        self.assertEqual(
            receipt.backend_digest,
            _file_digest(
                (
                    "n_backend_simd.py",
                    "n_backend_types.py",
                    "n_machine_encoder_x64.py",
                    "n_ops.py",
                )
            ),
        )


if __name__ == "__main__":
    unittest.main()
