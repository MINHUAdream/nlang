import json
import unittest
from dataclasses import replace

from n_front import parse
from n_ir import (
    IRPhase,
    IRValidationError,
    NIRModule,
    RewriteDelta,
    lower_legacy,
    upgrade_legacy,
)
from n_ir_verify import verify_phase


HERE = __import__("pathlib").Path(__file__).resolve().parents[1]
SOURCE = (HERE / "examples" / "rtm_add_one.n").read_text(encoding="utf-8")


class UnifiedIRContractTests(unittest.TestCase):
    def test_legacy_upgrade_preserves_old_digest_and_builds_unified_tables(self):
        legacy = lower_legacy(parse(SOURCE))
        old_digest = legacy.digest

        semantic = upgrade_legacy(legacy)

        self.assertEqual("n-ir/rtm-0.1", legacy.schema)
        self.assertEqual(old_digest, legacy.digest)
        self.assertEqual("n-ir/0.7", semantic.schema)
        self.assertEqual(IRPhase.SEMANTIC, semantic.phase)
        self.assertEqual(old_digest, semantic.legacy_digest)
        self.assertEqual(3, len(semantic.operations))
        self.assertEqual("field", semantic.operations[0]["kind"])
        self.assertEqual("value:field:x", semantic.values[0]["id"])
        self.assertEqual("region:module", semantic.regions[0]["id"])
        self.assertTrue(all("id" in operation for operation in semantic.operations))

    def test_unified_module_round_trip_preserves_phase_and_digest(self):
        semantic = upgrade_legacy(lower_legacy(parse(SOURCE)))

        restored = NIRModule.from_dict(json.loads(semantic.canonical_json()))

        self.assertEqual(IRPhase.SEMANTIC, restored.phase)
        self.assertEqual(semantic.digest, restored.digest)
        self.assertEqual(semantic.operations, restored.operations)
        self.assertEqual(semantic.values, restored.values)
        self.assertEqual(semantic.regions, restored.regions)

    def test_rewrite_rejects_wrong_parent_digest(self):
        semantic = upgrade_legacy(lower_legacy(parse(SOURCE)))
        delta = RewriteDelta("0" * 64, "plan.cpu", (), "1" * 64)

        with self.assertRaisesRegex(IRValidationError, "parent digest"):
            semantic.rewrite_to(IRPhase.PLANNED, delta, semantic.operations)

    def test_rewrite_records_parent_and_phase(self):
        semantic = upgrade_legacy(lower_legacy(parse(SOURCE)))
        delta = RewriteDelta(semantic.digest, "plan.cpu", (), "1" * 64)

        planned = semantic.rewrite_to(IRPhase.PLANNED, delta, semantic.operations)

        self.assertEqual(IRPhase.PLANNED, planned.phase)
        self.assertEqual(semantic.digest, planned.parent_digest)
        self.assertEqual(delta, planned.rewrite)
        self.assertEqual(semantic.legacy_digest, planned.legacy_digest)


class UnifiedIRVerifierTests(unittest.TestCase):
    def setUp(self):
        self.semantic = upgrade_legacy(lower_legacy(parse(SOURCE)))

    def _with_operations(self, module, operations):
        payload = module.to_dict()
        payload["operations"] = operations
        return NIRModule.from_dict(payload)

    def test_valid_semantic_and_planned_modules_pass(self):
        verify_phase(self.semantic)
        delta = RewriteDelta(self.semantic.digest, "plan.cpu", (), "1" * 64)
        planned = self.semantic.rewrite_to(
            IRPhase.PLANNED, delta, self.semantic.operations
        )
        verify_phase(planned)

    def test_semantic_rejects_machine_operation(self):
        operations = [dict(operation) for operation in self.semantic.operations]
        operations.append({"id": "op:x86:addpd", "kind": "x86.sse2.addpd"})
        forged = self._with_operations(self.semantic, operations)

        with self.assertRaises(IRValidationError) as raised:
            verify_phase(forged)

        self.assertEqual("IR_PHASE_ILLEGAL", raised.exception.diagnostics[0].code)

    def test_machine_rejects_unresolved_goal(self):
        machine = NIRModule(
            schema="n-ir/0.7",
            module="planning",
            nodes=({"id": "op:goal:x", "kind": "goal"},),
            phase=IRPhase.MACHINE,
            parent_digest="a" * 64,
            rewrite=RewriteDelta("a" * 64, "machine.x64", (), "b" * 64),
        )

        with self.assertRaises(IRValidationError) as raised:
            verify_phase(machine, target="x86_64-windows")

        self.assertIn(
            "IR_PHASE_ILLEGAL", {item.code for item in raised.exception.diagnostics}
        )

    def test_duplicate_operation_id_is_rejected(self):
        operations = [dict(operation) for operation in self.semantic.operations]
        operations.append(dict(operations[0]))
        forged = self._with_operations(self.semantic, operations)

        with self.assertRaises(IRValidationError) as raised:
            verify_phase(forged)

        self.assertIn("IR_DUPLICATE_ID", {item.code for item in raised.exception.diagnostics})

    def test_wave_without_fallback_is_rejected(self):
        operations = [dict(operation) for operation in self.semantic.operations]
        wave_index = next(
            index for index, operation in enumerate(operations)
            if operation["kind"] == "wave"
        )
        operations[wave_index].pop("fallback")
        forged = self._with_operations(self.semantic, operations)

        with self.assertRaises(IRValidationError) as raised:
            verify_phase(forged)

        self.assertIn("IR_WAVE_FALLBACK", {item.code for item in raised.exception.diagnostics})


if __name__ == "__main__":
    unittest.main()
