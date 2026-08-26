"""Year-1 Lintel consume contract: machine checker, not freeze/F."""

import json
from pathlib import Path

import pytest

from choreoir.__main__ import main
from choreoir.ast import COMPILER_VER
from choreoir.consume_check import consume_check
from choreoir.pin import (
    FACE_ADAPTER_ID,
    cache_key,
    cache_key_digest,
    unspecified_graph_hash,
)

LINTEL = Path("/tmp/lintel-probe")
SCHEMAS = (
    "cache-key.v0.schema.json",
    "adapter-proposal.v0.schema.json",
    "session-event.v0.schema.json",
    "admit-record.v0.schema.json",
)


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n")


def _kernel(name: str = "copy") -> dict:
    return {
        "name": name,
        "target": "cuda",
        "compiler_ver": COMPILER_VER,
        "params": [],
        "buffers": [
            {
                "name": "A",
                "space": "gmem",
                "dtype": "f16",
                "layout": {"shape": [2, 2], "stride": [2, 1]},
            }
        ],
        "partitions": [{"name": "load", "role": "load", "width": 4}],
        "body": [{"op": "copy", "id": "c0", "src": "A", "dst": "A", "partition": "load"}],
        "attrs": {},
    }


def _nv_key() -> dict:
    return cache_key(
        graph_hash=unspecified_graph_hash(),
        hw_id="nvidia.b200.80gb",
        compiler_ver=f"choreoir=={COMPILER_VER};nvcc.cubin",
        policy_id="lintel.specialize.v0",
    )


def _launch_cuda() -> dict:
    return {"grid": 1, "block": 256, "num_warps": 8, "num_stages": 1}


def _admit(key: dict, *, enum_id: str = "copy", kind: str = "cubin", launch: dict | None = None) -> dict:
    art: dict = {
        "digest": "sha256:" + "ab" * 32,
        "kind": kind,
        "uri": "git://example/copy.cubin",
    }
    if launch is not None:
        art["launch"] = launch
    return {
        "schema_version": "admit-record.v0",
        "record_id": "rec_test",
        "created_at": "2026-01-01T00:00:00Z",
        "region": {
            "region_id": "gemm.tile.hot",
            "graph_hash": key["graph_hash"],
            "op_family": "gemm",
        },
        "pins": {
            "hw_id": key["hw_id"],
            "compiler_ver": key["compiler_ver"],
            "adapter_id": FACE_ADAPTER_ID,
            "model_id": "vendor.test",
            "policy_id": key["policy_id"],
        },
        "actions": [{"kind": "propose_kernel", "enum_id": enum_id, "kernel": _kernel(enum_id)}],
        "cache_key": key,
        "cache_key_digest": cache_key_digest(key),
        "oracles": [
            {
                "name": "adapter.WLS",
                "version": "0.1.0",
                "result": "pass",
                "false_neg_owner": "kernels@test",
            }
        ],
        "artifact": art,
        "fitness": {"F_name": "F", "traces": ["t"], "usd_per_compile": 0},
        "decision": "freeze",
        "fallback": "last_good",
    }


def _session_lines(key: dict) -> str:
    digest = cache_key_digest(key)
    start = {
        "schema_version": "session-event.v0",
        "event_id": "e0",
        "seq": 0,
        "ts": "2026-01-01T00:00:00Z",
        "session_id": "ses_test",
        "parent_session_id": None,
        "kind": "session.start",
        "payload": {
            "policy_id": key["policy_id"],
            "adapter_id": FACE_ADAPTER_ID,
            "compiler_ver": key["compiler_ver"],
        },
    }
    propose = {
        "schema_version": "session-event.v0",
        "event_id": "e1",
        "seq": 1,
        "ts": "2026-01-01T00:00:01Z",
        "session_id": "ses_test",
        "parent_session_id": None,
        "kind": "propose",
        "payload": {
            "enum_id": "copy",
            "adapter_id": FACE_ADAPTER_ID,
            "kernel": _kernel(),
        },
    }
    gate = {
        "schema_version": "session-event.v0",
        "event_id": "e2",
        "seq": 2,
        "ts": "2026-01-01T00:00:02Z",
        "session_id": "ses_test",
        "parent_session_id": None,
        "kind": "gate",
        "payload": {
            "seam": "adapter",
            "passed": False,
            "finding": {
                "gate": "L",
                "severity": "error",
                "node": "buffer.A",
                "msg": "stride does not cover shape",
            },
            "reject": {"where": "L", "hint": "buffer.A", "reason": "stride does not cover shape"},
        },
    }
    freeze = {
        "schema_version": "session-event.v0",
        "event_id": "e3",
        "seq": 3,
        "ts": "2026-01-01T00:00:03Z",
        "session_id": "ses_test",
        "parent_session_id": None,
        "kind": "freeze",
        "payload": {
            "cache_key": key,
            "cache_key_digest": digest,
            "digest": "sha256:" + "ab" * 32,
            "kind": "cubin",
            "launch": _launch_cuda(),
        },
    }
    return "".join(json.dumps(ev) + "\n" for ev in (start, propose, gate, freeze))


def _good_tree(tmp_path: Path) -> Path:
    root = tmp_path / "lintel"
    for name in SCHEMAS:
        (root / "schemas" / name).parent.mkdir(parents=True, exist_ok=True)
        (root / "schemas" / name).write_text("{}\n")
    key = _nv_key()
    _write(root / "examples" / "admit-record.json", _admit(key, launch=_launch_cuda()))
    (root / "examples" / "session-log.jsonl").write_text(_session_lines(key))
    _write(root / "examples" / "choreo" / "copy.json", _kernel())
    _write(
        root / "examples" / "later" / "attn.json",
        {"enum_id": "choreo.attn.d3.w4", "adapter_id": "triton.v0"},
    )
    _write(
        root / "examples" / "poc" / "job.json",
        {
            "schema_version": "lintel-ir.poc",
            "pins": {
                "adapter_id": FACE_ADAPTER_ID,
                "compiler_ver": f"choreoir=={COMPILER_VER};nvcc.cubin",
            },
            "plan": {
                "blocks": [
                    {"id": "try0", "enum_id": "copy", "kernel": _kernel("copy")},
                    {"id": "try1", "enum_id": "gemm_tile", "kernel": _kernel("gemm_tile")},
                ]
            },
        },
    )
    return root


def test_good_tree_is_clean(tmp_path):
    root = _good_tree(tmp_path)
    assert consume_check(root) == []
    assert main(["consume-check", str(root)]) == 0


def test_later_attn_is_skipped(tmp_path, capsys):
    root = _good_tree(tmp_path)
    assert main(["consume-check", str(root)]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_src_dir_is_forbidden(tmp_path):
    root = _good_tree(tmp_path)
    (root / "src").mkdir()
    errs = consume_check(root)
    assert any("src/" in e for e in errs)


def test_year1_enum_rejects_attn(tmp_path):
    root = _good_tree(tmp_path)
    key = _nv_key()
    _write(root / "examples" / "admit-record.json", _admit(key, enum_id="choreo.attn.d3.w4", launch=_launch_cuda()))
    errs = consume_check(root)
    assert any("choreo.attn.d3.w4" in e for e in errs)


def test_freeze_requires_launch(tmp_path):
    root = _good_tree(tmp_path)
    key = _nv_key()
    _write(root / "examples" / "admit-record.json", _admit(key, launch=None))
    errs = consume_check(root)
    assert any("missing launch" in e for e in errs)


def test_triton_sink_is_rejected(tmp_path):
    root = _good_tree(tmp_path)
    key = cache_key(
        graph_hash=unspecified_graph_hash(),
        hw_id="nvidia.b200.80gb",
        compiler_ver="choreoir==0.1.0;triton==3.3.0+cu128",
        policy_id="lintel.specialize.v0",
    )
    doc = _admit(key, launch=_launch_cuda())
    doc["artifact"]["kind"] = "choreo_kernel"
    _write(root / "examples" / "admit-record.json", doc)
    errs = consume_check(root)
    assert any("Triton" in e for e in errs)
    assert any("cubin" in e and "choreo_kernel" in e for e in errs)


def test_session_reject_must_not_nest_finding(tmp_path):
    root = _good_tree(tmp_path)
    key = _nv_key()
    lines = _session_lines(key)
    events = [json.loads(line) for line in lines.splitlines() if line]
    for ev in events:
        if ev["kind"] == "gate":
            ev["payload"]["reject"]["finding"] = ev["payload"]["finding"]
            del ev["payload"]["finding"]
    (root / "examples" / "session-log.jsonl").write_text("".join(json.dumps(ev) + "\n" for ev in events))
    errs = consume_check(root)
    assert any("sibling of reject" in e for e in errs)
    assert any("must not nest finding" in e for e in errs)


def test_propose_kernel_stub_is_rejected(tmp_path):
    root = _good_tree(tmp_path)
    key = _nv_key()
    lines = _session_lines(key)
    events = [json.loads(line) for line in lines.splitlines() if line]
    for ev in events:
        if ev["kind"] == "propose":
            ev["payload"]["kernel"] = {"name": "copy", "target": "cuda"}
    (root / "examples" / "session-log.jsonl").write_text("".join(json.dumps(ev) + "\n" for ev in events))
    errs = consume_check(root)
    assert any("kernel stub missing" in e for e in errs)


def test_digest_mismatch_is_rejected(tmp_path):
    root = _good_tree(tmp_path)
    key = _nv_key()
    doc = _admit(key, launch=_launch_cuda())
    doc["cache_key_digest"] = "sha256:" + "00" * 32
    _write(root / "examples" / "admit-record.json", doc)
    errs = consume_check(root)
    assert any("cache_key_digest mismatch" in e for e in errs)


def test_origin_shaped_tree_fails(tmp_path):
    root = _good_tree(tmp_path)
    key = cache_key(
        graph_hash=unspecified_graph_hash(),
        hw_id="nvidia.b200.80gb",
        compiler_ver="choreoir==0.1.0;triton==3.3.0+cu128",
        policy_id="lintel.specialize.v0",
    )
    doc = _admit(key, enum_id="choreo.attn.d3.w4", kind="choreo_kernel", launch=None)
    _write(root / "examples" / "admit-record.json", doc)
    errs = consume_check(root)
    blob = "\n".join(errs)
    assert "Triton" in blob
    assert "choreo.attn.d3.w4" in blob
    assert "choreo_kernel" in blob
    assert main(["consume-check", str(root)]) == 1


@pytest.mark.skipif(not LINTEL.is_dir(), reason="local lintel clone")
def test_local_lintel_probe_matches_contract():
    assert consume_check(LINTEL) == []
