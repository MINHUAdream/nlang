import unittest
from dataclasses import replace

from n_compile import compile_source
from n_plan import PlanError, verify_selection_receipt
from n_lir import lower_machine


GOAL_SOURCE = """module measured;
field x: f64[4] layout contiguous device cpu;
wave add_one(x) -> delta {
  read x;
  write x;
  delta add_scalar 1.0;
  echo exact;
  fallback reject;
}
commit add_one into x;
goal add_one_plan {
  target minimize cost;
  target maximize quality;
  require [cpu];
  option reference_exact { cost: 1.0; quality: 1.0; };
  option cpu_simd_sse2 { cost: 0.5; quality: 1.0; };
}
synthesize add_one_plan;
"""


class GoalSelectionCompilerTests(unittest.TestCase):
    def test_goal_source_selects_a_declared_candidate(self):
        result = compile_source(GOAL_SOURCE, initial={"x": [1.0, 2.0, 3.0, 4.0]})
        self.assertIsNotNone(result.goal_decision)
        self.assertEqual(result.goal_decision.status, "selected")
        self.assertIn(result.goal_decision.selected, {"reference_exact", "cpu_simd_sse2"})
        self.assertEqual(result.manifest.selected_candidate, result.goal_decision.selected)
        self.assertEqual(len(result.manifest.candidate_set_digest), 64)
        self.assertEqual(len(result.manifest.selection_receipt_digest), 64)

    def test_goal_selection_receipt_binds_every_candidate_measurement(self):
        result = compile_source(GOAL_SOURCE, initial={"x": [1.0, 2.0, 3.0, 4.0]})
        self.assertIsNotNone(result.selection_receipt)
        for measurement in result.selection_receipt.measurements:
            self.assertEqual(len(measurement.source_digest or ""), 64)
            self.assertEqual(len(measurement.workload_digest or ""), 64)
            self.assertEqual(len(measurement.benchmark_digest or ""), 64)
            self.assertEqual(len(measurement.hardware_digest or ""), 64)

    def test_measurement_receipt_does_not_change_emitted_machine_bytes(self):
        first = compile_source(GOAL_SOURCE, initial={"x": [1.0, 2.0, 3.0, 4.0]})
        second = compile_source(GOAL_SOURCE, initial={"x": [1.0, 2.0, 3.0, 4.0]})
        self.assertEqual(first.code_digest, second.code_digest)
        self.assertEqual(first.code, second.code)

    def test_goal_source_rejects_stale_candidate_selection(self):
        result = compile_source(GOAL_SOURCE, initial={"x": [1.0, 2.0, 3.0, 4.0]})
        altered = replace(result.manifest, selected_candidate="forged")
        with self.assertRaisesRegex(PlanError, "candidate"):
            lower_machine(result.planned, altered)

    def test_native_rejects_mutated_selection_receipt(self):
        result = compile_source(GOAL_SOURCE, initial={"x": [1.0, 2.0, 3.0, 4.0]})
        forged_receipt = replace(
            result.selection_receipt,
            measurements=(
                replace(
                    result.selection_receipt.measurements[0],
                    hardware_digest="0" * 64,
                ),
                *result.selection_receipt.measurements[1:],
            ),
        )
        with self.assertRaisesRegex(PlanError, "receipt"):
            verify_selection_receipt(result.manifest, result.semantic, forged_receipt)

    def test_goal_selection_can_replay_a_saved_receipt(self):
        first = compile_source(
            GOAL_SOURCE,
            initial={"x": [1.0, 2.0, 3.0, 4.0]},
            samples=1,
            warmup_samples=0,
        )
        replayed = compile_source(
            GOAL_SOURCE,
            initial={"x": [1.0, 2.0, 3.0, 4.0]},
            samples=1,
            warmup_samples=0,
            selection_receipt=first.selection_receipt,
        )
        self.assertEqual(replayed.manifest.selection_receipt_digest, first.manifest.selection_receipt_digest)
        self.assertEqual(replayed.code, first.code)

    def test_goal_replay_rejects_a_different_workload(self):
        first = compile_source(
            GOAL_SOURCE,
            initial={"x": [1.0, 2.0, 3.0, 4.0]},
            samples=1,
            warmup_samples=0,
        )
        with self.assertRaisesRegex(PlanError, "workload"):
            compile_source(
                GOAL_SOURCE,
                initial={"x": [4.0, 3.0, 2.0, 1.0]},
                samples=1,
                warmup_samples=0,
                selection_receipt=first.selection_receipt,
            )


if __name__ == "__main__":
    unittest.main()
