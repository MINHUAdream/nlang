import unittest
from dataclasses import replace

from n_compile import compile_source
from n_plan import PlanError
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

    def test_goal_source_rejects_stale_candidate_selection(self):
        result = compile_source(GOAL_SOURCE, initial={"x": [1.0, 2.0, 3.0, 4.0]})
        altered = replace(result.manifest, selected_candidate="forged")
        with self.assertRaisesRegex(PlanError, "candidate"):
            lower_machine(result.planned, altered)


if __name__ == "__main__":
    unittest.main()
