import contextlib
import io
import json
import unittest

import n


class NCLITests(unittest.TestCase):
    def test_n_entrypoint_dispatches_n_source(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = n.main(["examples/rtm_add_one.n", "--backend", "reference", "--samples", "1", "--json"])
        payload = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "committed")

    def test_n_entrypoint_exposes_cpu_simd_backend(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = n.main(["examples/rtm_add_one.n", "--backend", "cpu-simd", "--samples", "1", "--json"])
        payload = json.loads(output.getvalue())
        self.assertIn(payload["status"], {"committed", "unavailable"})
        if payload["status"] == "committed":
            self.assertEqual(code, 0)
            self.assertEqual(payload["backend"], "cpu-simd-sse2-f64")
        else:
            self.assertEqual(code, 2)

    def test_n_entrypoint_exposes_n_native_compiler_backend(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = n.main(["examples/rtm_add_one.n", "--backend", "n-native", "--samples", "1", "--json"])
        payload = json.loads(output.getvalue())
        self.assertIn(payload["status"], {"committed", "unavailable"})
        if payload["status"] == "committed":
            self.assertEqual(code, 0)
            self.assertEqual(payload["backend"], "n-native-x64-sse2-f64")
            self.assertIsNotNone(payload["plan_digest"])
            self.assertIsNotNone(payload["code_digest"])
        else:
            self.assertEqual(code, 2)

    def test_goal_synthesize_cli_reports_measured_selection(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = n.main(
                [
                    "examples/goal_synthesis.n",
                    "--synthesize",
                    "add_one_plan",
                    "--samples",
                    "1",
                    "--warmup-samples",
                    "0",
                    "--json",
                ]
            )
        payload = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "selected")
        self.assertIn(payload["selected"], {"reference_exact", "cpu_simd_sse2"})
        self.assertEqual(len(payload["selection_receipt_digest"]), 64)
        self.assertEqual(len(payload["measurements"]), 2)


if __name__ == "__main__":
    unittest.main()
