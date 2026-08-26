"""T5-lite fail corpus: localized {where} for Lintel to classify across jobs.

These JSON kernels are the year-1 Undergo evidence. A recurring {where} may
drive a commit on main (new gate/sink). They must not rewrite check mid-walk.
"""

import json
from pathlib import Path

from choreoir.check import check
from choreoir.interp import check_value
from choreoir.jsonio import kernel_from_dict

ROOT = Path(__file__).resolve().parents[1] / "examples" / "fails"

# filename → (where, node substring)
EXPECT = {
    "unknown_buffer.json": ("W", "c0"),
    "layout_cover.json": ("L", "buffer.A"),
    "sync_race.json": ("S", "c1"),
    "role_mismatch.json": ("W", "c1"),
    "mma_shape.json": ("L", "m0"),
    "pipeline_depth.json": ("W", "p0"),
}

V_CASE = (
    "value_mismatch.json",
    "value_mismatch.tensors.json",
    "value_mismatch.expected.json",
    "B",
)


def test_t5_corpus_localizes_where():
    seen = set()
    for name, (where, node) in EXPECT.items():
        k = kernel_from_dict(json.loads((ROOT / name).read_text()))
        fs = check(k)
        hits = [f for f in fs if f.gate == where and node in f.node]
        assert hits, f"{name}: expected {where} at {node}, got {[(f.gate, f.node, f.msg) for f in fs]}"
        d = hits[0].as_dict()
        assert d["where"] == where
        if where == "L":
            assert d["element"] is not None
        if where == "S":
            assert d["thread"] == 0
            assert d["partition"]
        seen.add(where)
    kern, tensors, expected, node = V_CASE
    k = kernel_from_dict(json.loads((ROOT / kern).read_text()))
    assert check(k) == []
    fs = check_value(k, json.loads((ROOT / tensors).read_text()), json.loads((ROOT / expected).read_text()))
    hits = [f for f in fs if f.gate == "V" and node in f.node]
    assert hits, f"{kern}: expected V at {node}, got {[(f.gate, f.node, f.msg) for f in fs]}"
    d = hits[0].as_dict()
    assert d["where"] == "V"
    assert d["element"] == [0, 0]
    seen.add("V")
    assert seen >= {"W", "L", "S", "V"}
