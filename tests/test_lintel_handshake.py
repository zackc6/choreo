"""How Lintel copies Choreo propose onto the session stream.

This tree does not walk the CFG. The mapping is the handshake: Kernel AST
and Finding JSON are the values Lintel stores; reject.where is the CFG letter.
Session-event reject cannot nest finding (additionalProperties false), so
Lintel copies finding as a payload sibling.
"""

from __future__ import annotations

import json
from pathlib import Path

from choreoir.check import check
from choreoir.interp import check_value
from choreoir.jsonio import kernel_from_dict
from choreoir.propose import adapter_proposal

ROOT = Path(__file__).resolve().parents[1]
FAILS = ROOT / "examples" / "fails"

FINDING_KEYS = ("gate", "severity", "node", "msg", "partition", "thread", "element")


def session_adapter_gate(proposal: dict) -> dict:
    """Lintel adapter.gate payload. Not a freeze, land, or F."""
    rej = proposal["reject"]
    return {
        "seam": "adapter",
        "passed": False,
        "finding": rej["finding"],
        "reject": {
            "where": rej["where"],
            "hint": rej["hint"],
            "reason": rej["reason"],
        },
    }


def session_propose_kernel(proposal: dict) -> dict:
    """Propose payload kernel is the AST, not a {name, target} stub."""
    k = proposal["kernel"]
    for key in ("name", "buffers", "partitions", "body"):
        assert key in k, key
    return k


def _assert_finding(finding: dict, where: str) -> None:
    assert set(finding) <= set(FINDING_KEYS)
    for key in ("gate", "severity", "node", "msg"):
        assert key in finding
    assert finding["gate"] == where
    assert "where" not in finding


def test_t5_fails_copy_onto_session_gate():
    cases = [
        ("unknown_buffer.json", "W"),
        ("role_mismatch.json", "W"),
        ("pipeline_empty.json", "W"),
        ("layout_cover.json", "L"),
        ("mma_shape.json", "L"),
        ("sync_race.json", "S"),
    ]
    seen: set[str] = set()
    for name, where in cases:
        k = kernel_from_dict(json.loads((FAILS / name).read_text()))
        env = adapter_proposal(k)
        assert env["reject"]["where"] == where, name
        _assert_finding(env["reject"]["finding"], where)
        gate = session_adapter_gate(env)
        assert gate["finding"] == env["reject"]["finding"]
        assert "finding" not in gate["reject"]
        assert gate["reject"]["where"] == where
        assert gate["reject"]["hint"] == env["reject"]["finding"]["node"]
        session_propose_kernel(env)
        seen.add(where)
    k = kernel_from_dict(json.loads((FAILS / "value_mismatch.json").read_text()))
    assert check(k) == []
    tensors = json.loads((FAILS / "value_mismatch.tensors.json").read_text())
    expected = json.loads((FAILS / "value_mismatch.expected.json").read_text())
    env = adapter_proposal(k, tensors=tensors, expected=expected)
    assert env["reject"]["where"] == "V"
    _assert_finding(env["reject"]["finding"], "V")
    gate = session_adapter_gate(env)
    assert gate["finding"]["element"] == [0, 0]
    assert "finding" not in gate["reject"]
    session_propose_kernel(env)
    seen.add("V")
    assert seen == {"W", "L", "S", "V"}


def test_value_findings_stay_opt_in():
    k = kernel_from_dict(json.loads((FAILS / "value_mismatch.json").read_text()))
    assert "reject" not in adapter_proposal(k)
    fs = check_value(
        k,
        json.loads((FAILS / "value_mismatch.tensors.json").read_text()),
        json.loads((FAILS / "value_mismatch.expected.json").read_text()),
    )
    assert any(f.gate == "V" for f in fs)
