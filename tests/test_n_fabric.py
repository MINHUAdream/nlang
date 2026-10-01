import unittest

from n_fabric import probe_fabric


class FabricProbeTests(unittest.TestCase):
    def test_fabric_has_explicit_capabilities(self):
        fabric = probe_fabric()
        self.assertEqual(set(fabric), {"cpu", "gpu", "npu", "cxl"})
        self.assertEqual(fabric["cpu"].status, "available")
        for capability in fabric.values():
            self.assertIn(capability.status, {"available", "unavailable"})
            if capability.status == "unavailable":
                self.assertTrue(capability.detail)


if __name__ == "__main__":
    unittest.main()
