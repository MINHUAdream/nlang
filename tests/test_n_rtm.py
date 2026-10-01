import json
import unittest
from dataclasses import replace

from n_backend_tl import ReferenceBackend, TLNativeBackend
from n_front import parse
from n_ir import NIRModule, lower
from n_goal import synthesize
from n_rtm import EchoResult, Runtime, RuntimeField


HERE = __import__("pathlib").Path(__file__).resolve().parents[1]
SOURCE = (HERE / "examples" / "rtm_add_one.n").read_text(encoding="utf-8")


class RTMParserTests(unittest.TestCase):
    def test_parser_preserves_field_wave_and_commit_order(self):
        module = parse(SOURCE)
        self.assertEqual(module.fields[0].name, "x")
        self.assertEqual(module.waves[0].operations[0].kind, "read")
        self.assertEqual(module.waves[0].operations[1].kind, "write")
        self.assertEqual(module.commits[0].wave, "add_one")

    def test_parser_rejects_unimplemented_numeric_types(self):
        with self.assertRaisesRegex(ValueError, "unsupported field type"):
            parse(SOURCE.replace("f64", "f128"))


class RTMIRTests(unittest.TestCase):
    def test_parse_lower_round_trip(self):
        nir = lower(parse(SOURCE))
        restored = NIRModule.from_dict(json.loads(nir.canonical_json()))
        self.assertEqual(restored.digest, nir.digest)

    def test_nir_contains_explicit_rtm_nodes(self):
        nir = lower(parse(SOURCE))
        self.assertEqual([node["kind"] for node in nir.nodes], ["field", "wave", "commit"])
        with self.assertRaises(TypeError):
            nir.nodes[0]["name"] = "mutated"


class RTMRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.runtime = Runtime(ReferenceBackend())
        self.runtime.load(lower(parse(SOURCE)), {"x": [1.0, 2.0, 3.0, 4.0]})

    def test_exact_commit_advances_epoch(self):
        receipt = self.runtime.run()
        self.assertEqual(receipt.status, "committed")
        self.assertEqual(self.runtime.field("x").values, (2.0, 3.0, 4.0, 5.0))
        self.assertEqual(self.runtime.field("x").epoch, 1)

    def test_stale_wave_and_echo_failure_do_not_mutate_field(self):
        wave = self.runtime.prepare_wave("add_one", "x")
        self.assertEqual(self.runtime.commit(wave, self.runtime.echo_exact(wave)).status, "committed")
        self.assertEqual(self.runtime.commit(wave, self.runtime.echo_exact(wave)).status, "stale")
        bad = self.runtime.prepare_wave(
            "add_one", "x", expected=[99.0, 99.0, 99.0, 99.0]
        )
        self.assertEqual(self.runtime.commit(bad, self.runtime.echo_exact(bad)).status, "echo_failed")
        self.assertEqual(self.runtime.field("x").values, (2.0, 3.0, 4.0, 5.0))

    def test_unknown_fallback_is_not_a_commit(self):
        wave = self.runtime.prepare_wave("add_one", "x")
        result = self.runtime.commit(wave, EchoResult("unknown", None))
        self.assertEqual(result.status, "fallback_required")
        self.assertEqual(self.runtime.field("x").epoch, 0)

    def test_f32_add_uses_float32_rounding(self):
        source = SOURCE.replace("f32[4]", "f32[1]")
        source = source.replace("f32[1]", "f32[1]")
        source = source.replace("f64[4]", "f32[1]")
        source = source.replace("add_scalar 1.0", "add_scalar 1.0")
        runtime = Runtime(ReferenceBackend())
        runtime.load(lower(parse(source)), {"x": [16777216.0]})
        receipt = runtime.run()
        self.assertEqual(receipt.status, "committed")
        self.assertEqual(runtime.field("x").values, (16777216.0,))

    def test_forged_pass_receipt_cannot_commit(self):
        wave = self.runtime.prepare_wave("add_one", "x")
        forged = EchoResult("pass", (2.0, 3.0, 4.0, 5.0))
        result = self.runtime.commit(wave, forged)
        self.assertEqual(result.status, "invalid_echo")
        self.assertEqual(self.runtime.field("x").values, (1.0, 2.0, 3.0, 4.0))
        self.assertEqual(self.runtime.field("x").epoch, 0)

    def test_echo_is_bound_to_exact_prepared_wave(self):
        wave = self.runtime.prepare_wave("add_one", "x")
        echo = self.runtime.echo_exact(wave)
        tampered = replace(wave, delta=type(wave.delta)("x", 0, [10.0, 10.0, 10.0, 10.0]))
        result = self.runtime.commit(tampered, echo)
        self.assertEqual(result.status, "invalid_echo")
        self.assertEqual(self.runtime.field("x").epoch, 0)

    def test_backend_receives_immutable_field_snapshot(self):
        class MutatingBackend:
            def execute(inner_self, node, field):
                with self.assertRaises((AttributeError, TypeError)):
                    field.values[0] = 50.0
                return ReferenceBackend().execute(node, field)

        runtime = Runtime(MutatingBackend())
        runtime.load(lower(parse(SOURCE)), {"x": [1.0, 2.0, 3.0, 4.0]})
        wave = runtime.prepare_wave("add_one", "x")
        self.assertEqual(runtime.field("x").values, (1.0, 2.0, 3.0, 4.0))
        self.assertEqual(runtime.commit(wave, runtime.echo_exact(wave)).status, "committed")


class RTMBackendTests(unittest.TestCase):
    def test_tl_native_or_unavailable_is_explicit(self):
        backend = TLNativeBackend()
        capability = backend.probe()
        field = RuntimeField("x", "f32", (4,), "contiguous", "cpu", [1.0, 2.0, 3.0, 4.0])
        wave = {
            "kind": "wave",
            "name": "add_one",
            "operations": [
                {"kind": "delta", "value": "add_scalar"},
                {"kind": "delta_value", "value": 1.0},
            ],
        }
        if capability.status == "available":
            self.assertEqual(backend.execute(wave, field).values, (2.0, 3.0, 4.0, 5.0))
        else:
            self.assertEqual(capability.status, "unavailable")


class RTMGoalTests(unittest.TestCase):
    def test_goal_and_synthesize_lower_and_select_deterministically(self):
        source = """module planning;
goal add_one {
 target minimize cost;
 target maximize quality;
 require [cpu];
 option reference { cost: 1.0; quality: 1.0; };
 option native { cost: 0.5; quality: 0.99; };
}
synthesize add_one;
"""
        module = parse(source)
        self.assertEqual(module.goals[0].name, "add_one")
        nir = lower(module)
        self.assertEqual([node["kind"] for node in nir.nodes], ["goal", "synthesize"])
        decision = synthesize(nir, "add_one", available_features={"cpu"})
        self.assertEqual(decision.selected, "native")
        self.assertEqual(decision.search_count, 2)


if __name__ == "__main__":
    unittest.main()
