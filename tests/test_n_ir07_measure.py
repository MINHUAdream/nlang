import unittest

from n_measure import measure
from n_native import NativeBackend


HERE = __import__("pathlib").Path(__file__).resolve().parents[1]
SOURCE = (HERE / "examples" / "rtm_add_one.n").read_text(encoding="utf-8")


class UnifiedIRMeasurementTests(unittest.TestCase):
    def test_native_receipt_separates_phase_and_kernel_costs(self):
        backend = NativeBackend()
        capability = backend.probe()
        if capability.status != "available":
            self.skipTest(capability.detail or "native backend unavailable")

        receipt = measure(
            SOURCE,
            {"x": [1.0, 2.0, 3.0, 4.0]},
            backend,
            samples=2,
            warmup_samples=0,
        )
        payload = receipt.to_dict()

        self.assertEqual("committed", receipt.status)
        self.assertEqual(receipt.nir_digest, receipt.semantic_digest)
        for name in ("semantic_digest", "planned_digest", "machine_digest"):
            self.assertEqual(64, len(payload[name]))
        self.assertEqual(3, receipt.semantic_nodes)
        self.assertEqual(4, receipt.planned_nodes)
        self.assertEqual(9, receipt.machine_nodes)
        self.assertEqual(2, receipt.rewrite_count)
        self.assertGreaterEqual(receipt.serialization_cost_ms, 0.0)
        self.assertGreaterEqual(receipt.phase_verify_cost_ms, 0.0)
        self.assertGreaterEqual(receipt.compile_cost_ms, receipt.serialization_cost_ms)
        self.assertIsNotNone(receipt.p50_ms)
        backend.close()


if __name__ == "__main__":
    unittest.main()
