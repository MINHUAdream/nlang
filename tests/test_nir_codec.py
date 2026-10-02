import hashlib
import struct
import tempfile
from pathlib import Path
import unittest

from n_compile import compile_source
from n_front import parse
from n_ir import IRPhase, lower
from n_ir_codec import (
    FORMAT_VERSION,
    HEADER_SIZE,
    MAGIC,
    NIRCodecError,
    decode_nir,
    encode_nir,
    read_nir,
    write_nir,
)


HERE = Path(__file__).resolve().parents[1]
SOURCE = (HERE / "examples" / "rtm_add_one.n").read_text(encoding="utf-8")


class NIRCodecTests(unittest.TestCase):
    def setUp(self):
        self.semantic = lower(parse(SOURCE))
        self.compilation = compile_source(SOURCE)

    def test_all_phases_round_trip_with_stable_digest_and_bytes(self):
        for module in (self.semantic, self.compilation.planned, self.compilation.machine):
            encoded = encode_nir(module)
            self.assertEqual(MAGIC, encoded[:4])
            self.assertEqual(FORMAT_VERSION, encoded[4])
            restored = decode_nir(encoded)
            self.assertEqual(module.phase, restored.phase)
            self.assertEqual(module.digest, restored.digest)
            self.assertEqual(encoded, encode_nir(restored))

    def test_codec_rejects_unsupported_legacy_module(self):
        legacy = lower(parse(SOURCE))
        legacy = legacy.__class__(
            schema="n-ir/rtm-0.1",
            module=legacy.module,
            nodes=legacy.nodes,
        )
        with self.assertRaisesRegex(NIRCodecError, "0.7"):
            encode_nir(legacy)

    def test_codec_rejects_truncation_and_trailing_bytes(self):
        encoded = encode_nir(self.semantic)
        with self.assertRaises(NIRCodecError):
            decode_nir(encoded[: HEADER_SIZE - 1])
        with self.assertRaises(NIRCodecError):
            decode_nir(encoded + b"trailing")

    def test_codec_rejects_version_length_and_digest_corruption(self):
        encoded = bytearray(encode_nir(self.semantic))
        encoded[4] = FORMAT_VERSION + 1
        with self.assertRaisesRegex(NIRCodecError, "version"):
            decode_nir(bytes(encoded))

        encoded = bytearray(encode_nir(self.semantic))
        struct.pack_into(">Q", encoded, 5, len(encoded))
        with self.assertRaisesRegex(NIRCodecError, "length"):
            decode_nir(bytes(encoded))

        encoded = bytearray(encode_nir(self.semantic))
        encoded[13] ^= 0xFF
        with self.assertRaisesRegex(NIRCodecError, "digest"):
            decode_nir(bytes(encoded))

    def test_codec_rejects_duplicate_keys_and_noncanonical_json(self):
        encoded = encode_nir(self.semantic)
        payload = encoded[HEADER_SIZE:]
        duplicate = payload.replace(
            b'"module":',
            b'"module":"demo","module":',
            1,
        )
        duplicate_frame = struct.pack(
            ">4sBQ32s", MAGIC, FORMAT_VERSION, len(duplicate), hashlib.sha256(duplicate).digest()
        ) + duplicate
        with self.assertRaisesRegex(NIRCodecError, "duplicate"):
            decode_nir(duplicate_frame)

        noncanonical = payload.replace(b":", b": ", 1)
        noncanonical_frame = struct.pack(
            ">4sBQ32s",
            MAGIC,
            FORMAT_VERSION,
            len(noncanonical),
            hashlib.sha256(noncanonical).digest(),
        ) + noncanonical
        with self.assertRaisesRegex(NIRCodecError, "canonical"):
            decode_nir(noncanonical_frame)

        encoded = bytearray(encode_nir(self.semantic))
        encoded[-1] ^= 0xFF
        with self.assertRaisesRegex(NIRCodecError, "digest"):
            decode_nir(bytes(encoded))

    def test_file_helpers_use_the_same_canonical_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "module.nir"
            write_nir(path, self.compilation.machine)
            self.assertEqual(
                self.compilation.machine.digest,
                read_nir(path).digest,
            )
            self.assertEqual(encode_nir(self.compilation.machine), path.read_bytes())


if __name__ == "__main__":
    unittest.main()
