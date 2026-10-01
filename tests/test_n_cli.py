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


if __name__ == "__main__":
    unittest.main()
