"""Run an n RTM source file and print a workload-bound JSON receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from n_backend_tl import ReferenceBackend, TLNativeBackend
from n_backend_simd import CPUSIMDBackend
from n_compile import compile_source
from n_front import parse
from n_goal import SelectionReceipt
from n_ir import IRPhase, lower
from n_ir_codec import write_nir
from n_measure import measure
from n_native import NativeBackend


def _default_initial(source: str) -> dict[str, list[float]]:
    module = lower(parse(source))
    values: dict[str, list[float]] = {}
    for node in module.nodes:
        if node["kind"] != "field":
            continue
        size = 1
        for dimension in node["shape"]:
            size *= int(dimension)
        values[str(node["name"])] = [float(index + 1) for index in range(size)]
    return values


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="n-run")
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--backend",
        choices=("reference", "tl-native", "cpu-simd", "n-native"),
        default="reference",
    )
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--warmup-samples", type=int, default=1)
    parser.add_argument("--synthesize", metavar="GOAL")
    parser.add_argument("--selection-receipt-in", type=Path)
    parser.add_argument("--selection-receipt-out", type=Path)
    parser.add_argument("--emit-nir", type=Path)
    parser.add_argument(
        "--emit-phase",
        choices=tuple(phase.value for phase in IRPhase),
        default=IRPhase.SEMANTIC.value,
        help="nIR phase to emit when --emit-nir is provided",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    source = args.source.read_text(encoding="utf-8")
    saved_receipt = None
    if args.selection_receipt_in is not None:
        saved_receipt = SelectionReceipt.from_json(
            args.selection_receipt_in.read_text(encoding="utf-8")
        )
    if args.emit_nir is not None:
        if args.emit_phase == IRPhase.SEMANTIC.value:
            artifact = lower(parse(source))
        else:
            compilation = compile_source(
                source,
                initial=_default_initial(source),
                samples=args.samples,
                warmup_samples=args.warmup_samples,
                selection_receipt=saved_receipt,
            )
            artifact = (
                compilation.planned
                if args.emit_phase == IRPhase.PLANNED.value
                else compilation.machine
            )
        args.emit_nir.parent.mkdir(parents=True, exist_ok=True)
        write_nir(args.emit_nir, artifact)
        payload = {
            "status": "emitted",
            "artifact": str(args.emit_nir),
            "phase": artifact.phase.value,
            "nir_digest": artifact.digest,
            "bytes": args.emit_nir.stat().st_size,
        }
        print(json.dumps(payload, sort_keys=True, ensure_ascii=False))
        return 0
    if args.synthesize:
        compilation = compile_source(
            source,
            initial=_default_initial(source),
            samples=args.samples,
            warmup_samples=args.warmup_samples,
            selection_receipt=saved_receipt,
        )
        decision = compilation.goal_decision
        receipt = compilation.selection_receipt
        if decision is None or receipt is None or decision.goal != args.synthesize:
            print(
                json.dumps(
                    {
                        "status": "unavailable",
                        "detail": f"goal {args.synthesize!r} was not measured",
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                )
            )
            return 2
        if args.selection_receipt_out is not None:
            args.selection_receipt_out.parent.mkdir(parents=True, exist_ok=True)
            args.selection_receipt_out.write_text(
                receipt.canonical_json() + "\n",
                encoding="utf-8",
            )
        payload = dict(decision.__dict__)
        payload.update(
            {
                "candidate_set_digest": receipt.candidate_set_digest,
                "selection_receipt_digest": receipt.digest,
                "measurements": [item.to_dict() for item in receipt.measurements],
                "policy": receipt.policy,
            }
        )
        print(json.dumps(payload, sort_keys=True, ensure_ascii=False))
        return 0 if decision.selected is not None else 2
    backend = {
        "reference": ReferenceBackend,
        "tl-native": TLNativeBackend,
        "cpu-simd": CPUSIMDBackend,
        "n-native": NativeBackend,
    }[args.backend]()
    receipt = measure(
        source,
        _default_initial(source),
        backend,
        samples=args.samples,
        warmup_samples=args.warmup_samples,
    )
    print(json.dumps(receipt.to_dict(), sort_keys=True, ensure_ascii=False))
    return 0 if receipt.status == "committed" else 2


if __name__ == "__main__":
    sys.exit(main())
