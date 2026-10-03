import unittest

from n_backend_tl import ReferenceBackend
from n_compile import compile_source
from n_front import NParseError, parse
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


if __name__ == "__main__":
    unittest.main()
