import pathlib
import hashlib
import unittest

import n_machine_encoder_x64
from n_machine_encoder_x64 import encode_add_scalar_f64x2


class NOwnedEncoderTests(unittest.TestCase):
    def test_n_encoder_does_not_import_tl_emitter(self):
        source = pathlib.Path(n_machine_encoder_x64.__file__).read_text(encoding="utf-8")
        self.assertNotIn("tl_emit", source)

    def test_add_scalar_encoder_is_deterministic(self):
        first = encode_add_scalar_f64x2()
        second = encode_add_scalar_f64x2()
        self.assertEqual(first, second)
        self.assertIn(bytes.fromhex("660f58"), first)
        self.assertEqual(
            hashlib.sha256(first).hexdigest(),
            "f863698c4643bc4d3d41bef3f61bd6a6077a56bc262b05ea1b0ef01ccc163ec6",
        )


if __name__ == "__main__":
    unittest.main()
