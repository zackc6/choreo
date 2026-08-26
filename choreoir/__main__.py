from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .check import check
from .interp import check_value, simulate
from .jsonio import kernel_from_dict, kernel_to_dict
from .lower import lower, materialize


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="choreo",
        description="Admit, simulate, and lower Choreo IR (NVIDIA GPU / Ascend NPU). Data plane only.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="run W/L/S admit; exit 1 if any error")
    c.add_argument("kernel", type=Path)

    s = sub.add_parser("sim", help="CPU interpreter (V-gate if --expected is set)")
    s.add_argument("kernel", type=Path)
    s.add_argument("--tensors", type=Path, required=True)
    s.add_argument("--expected", type=Path, default=None)

    t = sub.add_parser("print", help="admit-gated source (CUDA C++ / TileLang) to stdout")
    t.add_argument("kernel", type=Path)
    t.add_argument(
        "--target",
        default=None,
        help="override Kernel.target (cuda | cuda-sm90 | ascend-a2 | ...)",
    )

    lo = sub.add_parser("lower", help="write NV/Ascend source; optionally try cubin / NPU bin")
    lo.add_argument("kernel", type=Path)
    lo.add_argument("--target", default=None)
    lo.add_argument("-o", "--out", type=Path, required=True)
    lo.add_argument(
        "--emit",
        choices=("source", "cubin", "npu-bin"),
        default="source",
        help="source=CUDA C++ or TileLang (+ Triton M2 sidecar); cubin=nvcc; npu-bin=TileLang/CANN",
    )

    d = sub.add_parser("dump", help="round-trip kernel JSON to stdout")
    d.add_argument("kernel", type=Path)

    args = p.parse_args(argv)
    kernel = kernel_from_dict(_read_json(args.kernel))

    if args.cmd == "check":
        findings = check(kernel)
        print(json.dumps([f.as_dict() for f in findings], indent=2))
        return 1 if any(f.severity == "error" for f in findings) else 0

    if args.cmd == "sim":
        tensors = _read_json(args.tensors)
        if args.expected is not None:
            findings = check_value(kernel, tensors, _read_json(args.expected))
            print(json.dumps([f.as_dict() for f in findings], indent=2))
            return 1 if findings else 0
        store, findings = simulate(kernel, tensors)
        print(json.dumps({"store": store, "findings": [f.as_dict() for f in findings]}, indent=2))
        return 1 if findings else 0

    if args.cmd == "print":
        if args.target:
            kernel.target = args.target
        result = lower(kernel)
        if result.errors():
            print(json.dumps([f.as_dict() for f in result.findings], indent=2))
            return 1
        sys.stdout.write(result.text)
        return 0

    if args.cmd == "lower":
        if args.target:
            kernel.target = args.target
        result = materialize(kernel, args.out, emit=args.emit)
        print(json.dumps(result.as_manifest(), indent=2))
        return 1 if result.errors() else 0

    if args.cmd == "dump":
        print(json.dumps(kernel_to_dict(kernel), indent=2))
        return 0

    return 2


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


if __name__ == "__main__":
    raise SystemExit(main())
