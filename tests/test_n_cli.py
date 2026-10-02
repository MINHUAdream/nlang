import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import n
from n_ir import IRPhase
from n_ir_codec import read_nir


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

    def test_goal_synthesize_cli_saves_and_replays_selection_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt_path = Path(directory) / "selection.json"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                first_code = n.main(
                    [
                        "examples/goal_synthesis.n",
                        "--synthesize",
                        "add_one_plan",
                        "--samples",
                        "1",
                        "--warmup-samples",
                        "0",
                        "--selection-receipt-out",
                        str(receipt_path),
                        "--json",
                    ]
                )
            first_payload = json.loads(output.getvalue())
            self.assertEqual(first_code, 0)
            self.assertTrue(receipt_path.exists())
            saved = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["digest"], first_payload["selection_receipt_digest"])

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                replay_code = n.main(
                    [
                        "examples/goal_synthesis.n",
                        "--synthesize",
                        "add_one_plan",
                        "--samples",
                        "1",
                        "--warmup-samples",
                        "0",
                        "--selection-receipt-in",
                        str(receipt_path),
                        "--json",
                    ]
                )
            replay_payload = json.loads(output.getvalue())
            self.assertEqual(replay_code, 0)
            self.assertEqual(
                replay_payload["selection_receipt_digest"],
                first_payload["selection_receipt_digest"],
            )

    def test_n_entrypoint_emits_semantic_nir_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_path = Path(directory) / "module.nir"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = n.main(
                    [
                        "examples/rtm_add_one.n",
                        "--emit-nir",
                        str(artifact_path),
                        "--json",
                    ]
                )
            payload = json.loads(output.getvalue())
            artifact = read_nir(artifact_path)
            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "emitted")
            self.assertEqual(payload["phase"], IRPhase.SEMANTIC.value)
            self.assertEqual(payload["nir_digest"], artifact.digest)
            self.assertEqual(payload["bytes"], artifact_path.stat().st_size)

    def test_n_entrypoint_emits_verified_planned_and_machine_phases(self):
        for phase in ("planned", "machine"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                artifact_path = Path(directory) / f"{phase}.nir"
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = n.main(
                        [
                            "examples/rtm_add_one.n",
                            "--emit-nir",
                            str(artifact_path),
                            "--emit-phase",
                            phase,
                            "--json",
                        ]
                    )
                payload = json.loads(output.getvalue())
                artifact = read_nir(artifact_path)
                self.assertEqual(code, 0)
                self.assertEqual(payload["phase"], phase)
                self.assertEqual(artifact.phase.value, phase)
                self.assertEqual(payload["nir_digest"], artifact.digest)


if __name__ == "__main__":
    unittest.main()
