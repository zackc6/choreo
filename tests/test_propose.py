"""adapter-proposal.v0: {where} is a CFG edge, not a freeze."""

import json
from pathlib import Path

from choreoir.__main__ import main
from choreoir.check import check
from choreoir.jsonio import kernel_from_dict, kernel_to_dict, load_kernel_doc
from choreoir.propose import adapter_proposal

ROOT = Path(__file__).resolve().parents[1]


def test_pascalcase_ops_roundtrip_to_lowercase():
    raw = {
        "name": "copy",
        "target": "cuda",
        "compiler_ver": "0.1.7",
        "buffers": [
            {
                "name": "A",
                "space": "gmem",
                "dtype": "f16",
                "layout": {"shape": [2, 2], "stride": [2, 1]},
            },
            {
                "name": "S",
                "space": "smem",
                "dtype": "f16",
                "layout": {"shape": [2, 2], "stride": [2, 1]},
            },
        ],
        "partitions": [{"name": "load", "role": "load", "width": 1}],
        "body": [{"op": "Copy", "id": "c0", "src": "A", "dst": "S", "partition": "load"}],
        "attrs": {},
    }
    k = kernel_from_dict(raw)
    assert k.body[0].id == "c0"
    dumped = kernel_to_dict(k)
    assert dumped["body"][0]["op"] == "copy"


def test_propose_admit_ok_has_no_reject():
    k = kernel_from_dict(json.loads((ROOT / "examples" / "copy.json").read_text()))
    doc = adapter_proposal(k)
    assert doc["schema"] == "lintel.adapter_proposal.v0"
    assert doc["adapter_id"] == "choreo.v0"
    assert doc["enum_id"] == "copy"
    assert doc["gates"] == ["W", "L", "S", "V"]
    assert "compile_ok" not in doc["gates"]
    assert "reject" not in doc
    assert doc["kernel"]["body"][0]["op"] == "copy"
    assert doc["kernel"]["target"] == "cuda"
    assert doc["compiler_ver"].startswith("choreoir==")
    assert doc["hw_id"] == "nvidia.sm_80"
    assert "target" not in doc or doc.get("target") is None


def test_propose_layout_fail_is_cfg_edge():
    k = kernel_from_dict(json.loads((ROOT / "examples" / "fails" / "layout_cover.json").read_text()))
    fs = check(k)
    assert any(f.gate == "L" for f in fs)
    doc = adapter_proposal(k, fs)
    rej = doc["reject"]
    assert rej["ok"] is False
    assert rej["where"] == "L"
    assert "where" not in rej["finding"]
    assert rej["finding"]["gate"] == "L"
    assert rej["hint"] == rej["finding"]["node"]


def test_load_proposal_envelope_stamps_hw_id():
    inner = json.loads((ROOT / "examples" / "copy.json").read_text())
    envelope = {
        "schema": "lintel.adapter_proposal.v0",
        "adapter_id": "choreo.v0",
        "graph_hash": "sha256:" + "ab" * 32,
        "hw_id": "nvidia.b200.80gb",
        "enum_id": "copy",
        "kernel": inner,
        "gates": ["W", "L", "S", "V"],
    }
    k = load_kernel_doc(envelope)
    assert k.attrs["hw_id"] == "nvidia.b200.80gb"
    assert k.attrs["graph_hash"].startswith("sha256:")
    assert k.attrs["enum_id"] == "copy"


def test_cli_propose_reject_exit(tmp_path, capsys):
    rc = main(["propose", str(ROOT / "examples" / "fails" / "sync_race.json")])
    assert rc == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["reject"]["where"] == "S"
    out = tmp_path / "ok.json"
    rc2 = main(["propose", str(ROOT / "examples" / "copy.json"), "-o", str(out)])
    assert rc2 == 0
    saved = json.loads(out.read_text())
    assert "reject" not in saved
    assert saved["adapter_id"] == "choreo.v0"


def test_handshake_goldens_match_live_propose():
    for name in ("copy", "gemm"):
        k = kernel_from_dict(json.loads((ROOT / "examples" / f"{name}.json").read_text()))
        gold = json.loads((ROOT / "examples" / f"{name}.proposal.json").read_text())
        assert adapter_proposal(k) == gold
    k = kernel_from_dict(json.loads((ROOT / "examples" / "fails" / "layout_cover.json").read_text()))
    gold = json.loads((ROOT / "examples" / "fails" / "layout_cover.proposal.json").read_text())
    assert adapter_proposal(k) == gold
    assert gold["reject"]["where"] == "L"
