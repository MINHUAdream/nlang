import unittest

from n_backend_simd import CPUSIMDBackend
from n_backend_tl import ReferenceBackend
from n_rtm import RuntimeField


class CPUSIMDTests(unittest.TestCase):
    def test_packed_sse2_matches_reference_for_even_and_odd_lengths(self):
        backend = CPUSIMDBackend()
        capability = backend.probe()
        if capability.status != "available":
            self.skipTest(capability.detail or "SSE2 backend unavailable")
        node = {
            "kind": "wave",
            "name": "add_one",
            "operations": [
                {"kind": "delta", "value": "add_scalar"},
                {"kind": "delta_value", "value": 0.125},
            ],
        }
        for size in (0, 1, 2, 3, 4, 7, 32, 33):
            field = RuntimeField(
                "x", "f64", (max(1, size),), "contiguous", "cpu",
                [index * 0.5 - 1.0 for index in range(size)],
            )
            simd_result = backend.execute(node, field)
            reference = ReferenceBackend().execute(node, field)
            self.assertEqual(simd_result.values, reference.values)

    def test_capability_only_claims_packed_sse2_when_executor_exists(self):
        capability = CPUSIMDBackend().probe()
        self.assertIn(capability.status, {"available", "unavailable"})
        if capability.status == "available":
            self.assertIn("sse2_packed_f64", capability.features)
        else:
            self.assertTrue(capability.detail)


if __name__ == "__main__":
    unittest.main()
