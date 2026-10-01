import unittest

from n_backend_tl import ReferenceBackend, TLNativeBackend
from n_measure import measure


SOURCE = """module demo;
field x: f32[4] layout contiguous device cpu;
wave add_one(x) -> delta {
 read x;
 write x;
 delta add_scalar 1.0;
 echo exact;
 fallback reject;
}
commit add_one into x;
"""


class MeasurementTests(unittest.TestCase):
    def test_receipt_binds_workload_and_latency(self):
        receipt = measure(SOURCE, {"x": [1.0, 2.0, 3.0, 4.0]}, ReferenceBackend(), samples=3)
        payload = receipt.to_dict()
        for key in (
            "source_digest",
            "nir_digest",
            "workload_digest",
            "hardware_digest",
            "compiler_digest",
            "runtime_digest",
            "backend_digest",
            "benchmark_digest",
            "result_digest",
            "lir_digest",
            "compile_cost_ms",
            "backend_init_ms",
            "verification_cost_ms",
            "commit_count",
            "fallback_rate",
            "search_count",
            "verification_calls",
            "p50_ms",
            "p99_ms",
            "quality_loss",
            "fallback_count",
        ):
            self.assertIn(key, payload)
        self.assertEqual(receipt.status, "committed")
        self.assertEqual(receipt.quality_loss, 0.0)
        self.assertGreaterEqual(receipt.p99_ms, receipt.p50_ms)
        self.assertGreaterEqual(receipt.verification_cost_ms, 0.0)
        self.assertEqual(receipt.commit_count, 3)
        self.assertEqual(receipt.fallback_rate, 0.0)
        for key in (
            "source_digest",
            "nir_digest",
            "workload_digest",
            "hardware_digest",
            "compiler_digest",
            "runtime_digest",
            "backend_digest",
            "benchmark_digest",
            "result_digest",
        ):
            self.assertEqual(len(payload[key]), 64)
        self.assertIsNone(receipt.lir_digest)

    def test_unavailable_backend_does_not_use_zero_for_unknown(self):
        receipt = measure(
            SOURCE,
            {"x": [1.0, 2.0, 3.0, 4.0]},
            TLNativeBackend("missing-kernels.dll"),
            samples=1,
        )
        self.assertEqual(receipt.status, "unavailable")
        self.assertIsNone(receipt.p50_ms)
        self.assertIsNone(receipt.quality_loss)
        self.assertIsNone(receipt.search_count)


if __name__ == "__main__":
    unittest.main()
