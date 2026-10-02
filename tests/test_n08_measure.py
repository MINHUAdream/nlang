import unittest
from dataclasses import replace

from n_front import parse
from n_backend_types import Capability
from n_goal import CandidateMeasurement, CandidateSpec, candidate_specs, select_measured
from n_ir import lower
from n_measure import measure, measure_candidates
from n_rtm import Delta

from tests.test_n08_goal_simd import GOAL_SOURCE


class CandidateMeasurementTests(unittest.TestCase):
    def test_candidates_share_workload_binding_and_unknown_cost_is_not_zero(self):
        semantic = lower(parse(GOAL_SOURCE))
        candidates = candidate_specs(semantic, "add_one_plan")
        measurements = measure_candidates(
            GOAL_SOURCE,
            {"x": [1.0, 2.0, 3.0, 4.0]},
            candidates,
            samples=2,
            warmup_samples=1,
        )
        self.assertEqual(len(measurements), 2)
        source_digests = {item.source_digest for item in measurements}
        workload_digests = {item.workload_digest for item in measurements}
        self.assertEqual(len(source_digests), 1)
        self.assertEqual(len(workload_digests), 1)
        missing = CandidateSpec("missing", "backend-does-not-exist", ("never",))
        unavailable = measure_candidates(
            GOAL_SOURCE,
            {"x": [1.0, 2.0, 3.0, 4.0]},
            (missing,),
            samples=1,
            warmup_samples=0,
        )[0]
        self.assertEqual(unavailable.status, "unavailable")
        self.assertIsNone(unavailable.p50_ms)
        self.assertIsNone(unavailable.p99_ms)

    def test_selection_rejects_failed_echo_candidate(self):
        semantic = lower(parse(GOAL_SOURCE))
        candidates = candidate_specs(semantic, "add_one_plan")
        measurements = measure_candidates(
            GOAL_SOURCE,
            {"x": [1.0, 2.0, 3.0, 4.0]},
            candidates,
            samples=2,
            warmup_samples=0,
        )
        receipt = select_measured("add_one_plan", candidates, measurements)
        self.assertIn(receipt.selected_candidate, {"reference_exact", "cpu_simd_sse2"})
        self.assertEqual(receipt.search_count, 2)
        self.assertEqual(len(receipt.digest), 64)

    def test_selection_rejects_mismatched_measurement_binding(self):
        semantic = lower(parse(GOAL_SOURCE))
        candidates = candidate_specs(semantic, "add_one_plan")
        measurements = measure_candidates(
            GOAL_SOURCE,
            {"x": [1.0, 2.0, 3.0, 4.0]},
            candidates,
            samples=2,
            warmup_samples=0,
        )
        forged = replace(measurements[1], hardware_digest="0" * 64)
        receipt = select_measured(
            "add_one_plan", candidates, (measurements[0], forged)
        )
        self.assertIsNone(receipt.selected_candidate)
        self.assertIn("binding", receipt.detail or "")

    def test_selection_rejects_missing_measurement_binding(self):
        semantic = lower(parse(GOAL_SOURCE))
        candidates = candidate_specs(semantic, "add_one_plan")
        measurements = measure_candidates(
            GOAL_SOURCE,
            {"x": [1.0, 2.0, 3.0, 4.0]},
            candidates,
            samples=1,
            warmup_samples=0,
        )
        forged = replace(measurements[0], source_digest=None)
        receipt = select_measured(
            "add_one_plan", candidates, (forged, measurements[1])
        )
        self.assertIsNone(receipt.selected_candidate)
        self.assertIn("binding", receipt.detail or "")

    def test_failed_echo_never_reports_a_commit(self):
        class WrongBackend:
            name = "test-wrong"

            def probe(self):
                return Capability("available", frozenset({"cpu"}))

            def execute(self, node, field):
                return Delta(field.name, field.epoch, [value + 2.0 for value in field.values])

        receipt = measure(
            GOAL_SOURCE.split("goal add_one_plan", 1)[0]
            + "commit add_one into x;\n",
            {"x": [1.0, 2.0, 3.0, 4.0]},
            WrongBackend(),
            samples=1,
            warmup_samples=0,
        )
        self.assertEqual(receipt.status, "echo_failed")
        self.assertEqual(receipt.commit_count, 0)
        self.assertIsNone(receipt.quality_loss)

    def test_unavailable_candidate_cannot_win_over_exact_reference(self):
        candidates = (
            CandidateSpec("reference_exact", "reference", ("reference", "add_scalar")),
            CandidateSpec("cpu_simd_sse2", "n-native-x64-sse2-f64", ("cpu", "sse2")),
        )
        binding = {
            "source_digest": "a" * 64,
            "workload_digest": "b" * 64,
            "benchmark_digest": "c" * 64,
            "hardware_digest": "d" * 64,
        }
        receipt = select_measured(
            "add_one_plan",
            candidates,
            (
                CandidateMeasurement(
                    "reference_exact", "committed", 1.0, 1.0, 0.0, 0.0, 0.0, 1, **binding
                ),
                CandidateMeasurement("cpu_simd_sse2", "unavailable", None, None, None, None, None, None, **binding),
            ),
        )
        self.assertEqual(receipt.selected_candidate, "reference_exact")


if __name__ == "__main__":
    unittest.main()
