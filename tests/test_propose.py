"""adapter-proposal.v0: {where} is a CFG edge, not a freeze."""

import json
from pathlib import Path

from choreoir.__main__ import main
from choreoir.ast import COMPILER_VER
from choreoir.check import check
from choreoir.interp import check_value
from choreoir.jsonio import kernel_from_dict, kernel_to_dict, load_kernel_doc
from choreoir.propose import adapter_proposal

ROOT = Path(__file__).resolve().parents[1]


def test_pascalcase_ops_roundtrip_to_lowercase():
    raw = {
        "name": "copy",
        "target": "cuda",
        "compiler_ver": COMPILER_VER,
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


def test_propose_empty_pipeline_is_cfg_edge():
    k = kernel_from_dict(json.loads((ROOT / "examples" / "fails" / "pipeline_empty.json").read_text()))
    fs = check(k)
    assert any(f.gate == "W" and "empty" in f.msg for f in fs)
    doc = adapter_proposal(k)
    assert doc["reject"]["where"] == "W"
    assert doc["reject"]["hint"] == "p0"
    assert "where" not in doc["reject"]["finding"]


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


def test_propose_value_fail_is_cfg_edge():
    fails = ROOT / "examples" / "fails"
    k = kernel_from_dict(json.loads((fails / "value_mismatch.json").read_text()))
    tensors = json.loads((fails / "value_mismatch.tensors.json").read_text())
    expected = json.loads((fails / "value_mismatch.expected.json").read_text())
    assert check(k) == []
    fs = check_value(k, tensors, expected)
    assert any(f.gate == "V" for f in fs)
    doc = adapter_proposal(k, tensors=tensors, expected=expected)
    rej = doc["reject"]
    assert rej["ok"] is False
    assert rej["where"] == "V"
    assert "where" not in rej["finding"]
    assert rej["finding"]["gate"] == "V"
    assert rej["finding"]["node"] == "B"
    assert rej["finding"]["element"] == [0, 0]
    assert rej["hint"] == "B"


def test_propose_without_tensors_skips_v():
    """V is opt-in: Kernel-only propose does not invent a V edge."""
    k = kernel_from_dict(json.loads((ROOT / "examples" / "fails" / "value_mismatch.json").read_text()))
    doc = adapter_proposal(k)
    assert "reject" not in doc


def test_cli_propose_value_reject(capsys):
    fails = ROOT / "examples" / "fails"
    rc = main(
        [
            "propose",
            str(fails / "value_mismatch.json"),
            "--tensors",
            str(fails / "value_mismatch.tensors.json"),
            "--expected",
            str(fails / "value_mismatch.expected.json"),
        ]
    )
    assert rc == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["reject"]["where"] == "V"
    assert doc["reject"]["finding"]["gate"] == "V"
    assert doc["reject"]["finding"]["element"] == [0, 0]


def test_cli_propose_tensors_without_expected(capsys):
    rc = main(
        [
            "propose",
            str(ROOT / "examples" / "fails" / "value_mismatch.json"),
            "--tensors",
            str(ROOT / "examples" / "fails" / "value_mismatch.tensors.json"),
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "--tensors and --expected must be given together" in err


def test_handshake_goldens_match_live_propose():
    for name in ("copy", "gemm"):
        k = kernel_from_dict(json.loads((ROOT / "examples" / f"{name}.json").read_text()))
        gold = json.loads((ROOT / "examples" / f"{name}.proposal.json").read_text())
        assert adapter_proposal(k) == gold
    fails = ROOT / "examples" / "fails"
    k = kernel_from_dict(json.loads((fails / "layout_cover.json").read_text()))
    gold = json.loads((fails / "layout_cover.proposal.json").read_text())
    assert adapter_proposal(k) == gold
    assert gold["reject"]["where"] == "L"
    k = kernel_from_dict(json.loads((fails / "value_mismatch.json").read_text()))
    tensors = json.loads((fails / "value_mismatch.tensors.json").read_text())
    expected = json.loads((fails / "value_mismatch.expected.json").read_text())
    gold = json.loads((fails / "value_mismatch.proposal.json").read_text())
    assert adapter_proposal(k, tensors=tensors, expected=expected) == gold
    assert gold["reject"]["where"] == "V"
