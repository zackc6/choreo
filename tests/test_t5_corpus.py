"""T5-lite fail corpus: localized {where} for Lintel to classify across jobs.

These JSON kernels are the year-1 Undergo evidence. A recurring {where} may
drive a commit on main (new gate/sink). They must not rewrite check mid-walk.
"""

from pathlib import Path

from choreoir.check import check
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


def test_t5_corpus_localizes_where():
    seen = set()
    for name, (where, node) in EXPECT.items():
        k = kernel_from_dict(__import__("json").loads((ROOT / name).read_text()))
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
    assert seen >= {"W", "L", "S"}
