"""Carrier check for the IR-design stage (replaces the pytest suite, 2026-10-23).

examples/*.json           must admit (check == []) and lower to source on their target
examples/fails/*.json     must be rejected with at least one localized finding
*.tensors.json/*.expected.json pairs, where present, must pass the tiny-tile V gate

Illustrative carriers, not a correctness contract (AGENTS.md, "IR-design stage").
Exit 1 on any mismatch; prints one line per carrier.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from choreoir.check import check
from choreoir.interp import check_value
from choreoir.jsonio import load_kernel_doc
from choreoir.lower import lower

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"
FAILS = EX / "fails"


def _load(p: Path):
    return load_kernel_doc(json.loads(p.read_text()))


def _pair(p: Path) -> tuple[Path, Path] | None:
    stem = p.with_suffix("")
    t, e = Path(f"{stem}.tensors.json"), Path(f"{stem}.expected.json")
    return (t, e) if t.exists() and e.exists() else None


def _kernel_files(d: Path) -> list[Path]:
    return sorted(
        p for p in d.glob("*.json")
        if not any(p.name.endswith(s) for s in (".tensors.json", ".expected.json", ".pin.json", ".proposal.json"))
    )


def main() -> int:
    bad = 0
    for p in _kernel_files(EX):
        k = _load(p)
        f = check(k)
        if f:
            print(f"FAIL admit   {p.relative_to(ROOT)}: {[x.as_dict() for x in f][:2]}")
            bad += 1
            continue
        low = lower(k)
        if not low.text:
            print(f"FAIL lower   {p.relative_to(ROOT)}: empty source for {k.target}")
            bad += 1
            continue
        line = f"ok   admit+lower {p.relative_to(ROOT)} ({low.family})"
        pr = _pair(p)
        if pr:
            v = check_value(k, json.loads(pr[0].read_text()), json.loads(pr[1].read_text()))
            if v:
                print(f"FAIL value   {p.relative_to(ROOT)}: {[x.as_dict() for x in v][:2]}")
                bad += 1
                continue
            line += " +V"
        print(line)
    for p in _kernel_files(FAILS):
        try:
            k = _load(p)
            f = check(k)
            if not f:
                pr = _pair(p)
                if pr:
                    f = check_value(k, json.loads(pr[0].read_text()), json.loads(pr[1].read_text()))
        except Exception as exc:  # a malformed carrier is a wellformed reject
            f = [exc]
        if not f:
            print(f"FAIL reject  {p.relative_to(ROOT)}: admitted, expected a finding")
            bad += 1
            continue
        first = f[0]
        where = getattr(first, "gate", type(first).__name__)
        node = getattr(first, "node", "")
        print(f"ok   reject {p.relative_to(ROOT)} {{where: {where}, node: {node}}}")
    print(f"\n{'FAILED' if bad else 'ok'}: {bad} mismatch(es)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
