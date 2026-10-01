"""Run an n RTM source file and print a workload-bound JSON receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from n_backend_tl import ReferenceBackend, TLNativeBackend
from n_backend_simd import CPUSIMDBackend
from n_front import parse
from n_goal import synthesize
from n_ir import lower
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
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    source = args.source.read_text(encoding="utf-8")
    if args.synthesize:
        decision = synthesize(lower(parse(source)), args.synthesize, available_features={"cpu"})
        print(json.dumps(decision.__dict__, sort_keys=True, ensure_ascii=False))
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
