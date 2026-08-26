from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .check import check
from .interp import check_value, simulate
from .jsonio import kernel_to_dict, load_kernel_doc
from .lower import lower, materialize
from .pin import apply_pin_stamps, cache_key_digest, cache_key_errors, extract_cache_key
from .propose import adapter_proposal


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="choreo",
        description="Admit, simulate, and lower Choreo IR (NVIDIA GPU / Ascend NPU). Data plane only.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="run W/L/S admit (and V if --tensors/--expected); exit 1 if any error")
    c.add_argument("kernel", type=Path)
    c.add_argument("--tensors", type=Path, default=None, help="with --expected, also run V-gate")
    c.add_argument("--expected", type=Path, default=None)

    s = sub.add_parser("sim", help="CPU interpreter (V-gate if --expected is set)")
    s.add_argument("kernel", type=Path)
    s.add_argument("--tensors", type=Path, required=True)
    s.add_argument("--expected", type=Path, default=None)

    t = sub.add_parser("print", help="admit-gated source (CUDA C++ / CCE) to stdout")
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
        help="source=CUDA C++ or CCE (+ Triton/TileLang sidecars); cubin=nvcc; npu-bin=ccec",
    )
    lo.add_argument(
        "--graph-hash",
        default=None,
        help="Lintel graph_hash (sha256:<64 hex>). Default: unspecified digest, not a Kernel hash.",
    )
    lo.add_argument(
        "--hw-id",
        default=None,
        help="Lintel hw_id stamp (not Kernel.target). Default: nvidia.sm_* / ascend.davinci from arch.",
    )
    lo.add_argument(
        "--policy-id",
        default=None,
        help="Lintel policy_id stamp. Default: lintel.specialize.v0",
    )

    pinp = sub.add_parser("pin", help="validate pin.json cache_key.v0 (Lintel handshake)")
    pinp.add_argument("pin", type=Path)

    prp = sub.add_parser(
        "propose",
        help="emit lintel.adapter_proposal.v0 (W/L/S as CFG edges; V if --tensors/--expected)",
    )
    prp.add_argument("kernel", type=Path)
    prp.add_argument("-o", "--out", type=Path, default=None)
    prp.add_argument("--graph-hash", default=None)
    prp.add_argument("--hw-id", default=None)
    prp.add_argument("--enum-id", default=None)
    prp.add_argument(
        "--tensors",
        type=Path,
        default=None,
        help="with --expected, fold V into reject.where",
    )
    prp.add_argument(
        "--expected",
        type=Path,
        default=None,
        help="with --tensors, fold V into reject.where",
    )

    d = sub.add_parser("dump", help="round-trip kernel JSON to stdout")
    d.add_argument("kernel", type=Path)

    args = p.parse_args(argv)
    if args.cmd == "pin":
        doc = _read_json(args.pin)
        key = extract_cache_key(doc)
        if key is None:
            print(json.dumps(["no cache_key.v0 object in file"], indent=2))
            return 1
        errs = cache_key_errors(key)
        stored = doc.get("cache_key_digest") if isinstance(doc, dict) else None
        if isinstance(stored, str) and stored:
            want = cache_key_digest(key)
            if stored != want:
                errs.append(f"cache_key_digest mismatch: stored {stored}, canonical {want}")
        print(json.dumps(errs, indent=2))
        return 1 if errs else 0

    kernel = load_kernel_doc(_read_json(args.kernel))

    if args.cmd == "check":
        findings = check(kernel)
        if (
            args.tensors is not None
            and args.expected is not None
            and not any(f.severity == "error" for f in findings)
        ):
            findings.extend(check_value(kernel, _read_json(args.tensors), _read_json(args.expected)))
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
        result = materialize(
            kernel,
            args.out,
            emit=args.emit,
            graph_hash=args.graph_hash,
            hw_id=args.hw_id,
            policy_id=args.policy_id,
        )
        print(json.dumps(result.as_manifest(), indent=2))
        return 1 if result.errors() else 0

    if args.cmd == "propose":
        apply_pin_stamps(kernel, graph_hash=args.graph_hash, hw_id=args.hw_id)
        if (args.tensors is None) ^ (args.expected is None):
            print("propose: --tensors and --expected must be given together", file=sys.stderr)
            return 2
        tensors = expected = None
        if args.tensors is not None:
            tensors = _read_json(args.tensors)
            expected = _read_json(args.expected)
        doc = adapter_proposal(
            kernel, tensors=tensors, expected=expected, enum_id=args.enum_id
        )
        text = json.dumps(doc, indent=2) + "\n"
        if args.out is not None:
            args.out.write_text(text)
        else:
            sys.stdout.write(text)
        return 1 if "reject" in doc else 0

    if args.cmd == "dump":
        print(json.dumps(kernel_to_dict(kernel), indent=2))
        return 0

    return 2


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


if __name__ == "__main__":
    raise SystemExit(main())
