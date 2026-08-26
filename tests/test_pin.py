"""Lintel cache-key.v0 handshake: pin.json is the payload, not a freeze."""

import hashlib
import json
from pathlib import Path

from choreoir.__main__ import main
from choreoir.ast import COMPILER_VER
from choreoir.jsonio import kernel_from_dict, kernel_to_dict
from choreoir.lower import lower, materialize
from choreoir.pin import (
    FACE_ADAPTER_ID,
    POLICY_ID_DEFAULT,
    cache_key_digest,
    cache_key_errors,
    unspecified_graph_hash,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "cache-key.v0.schema.json").read_text())


def _assert_lintel_key(key: dict) -> None:
    assert SCHEMA["required"] == [
        "schema_version",
        "graph_hash",
        "hw_id",
        "compiler_ver",
        "adapter_id",
        "policy_id",
    ]
    assert cache_key_errors(key) == []
    assert key["adapter_id"] == FACE_ADAPTER_ID
    assert "target" not in key
    assert "kernel" not in key
    assert "model_id" not in key
    assert "enum_id" not in key
    assert "cache_key_digest" not in key


def test_default_graph_hash_is_unspecified_not_kernel_json(tmp_path):
    k = kernel_from_dict(json.loads((ROOT / "examples" / "gemm.json").read_text()))
    pin = materialize(k, tmp_path, emit="source").as_k()
    key = pin["cache_key"]
    _assert_lintel_key(key)
    assert key["graph_hash"] == unspecified_graph_hash()
    dumped = json.dumps(kernel_to_dict(k), sort_keys=True).encode()
    kernel_digest = "sha256:" + hashlib.sha256(dumped).hexdigest()
    assert key["graph_hash"] != kernel_digest
    assert pin["target"] == "cuda"
    assert pin["sink_id"] == "cuda.cxx"
    assert key["compiler_ver"] == f"choreoir=={COMPILER_VER};cuda.cxx"
    assert key["hw_id"] == "nvidia.sm_80"
    assert key["policy_id"] == POLICY_ID_DEFAULT


def test_attrs_graph_hash_and_hw_id_stamps(tmp_path):
    k = kernel_from_dict(json.loads((ROOT / "examples" / "copy.json").read_text()))
    digest = "sha256:" + "ab" * 32
    k.attrs["graph_hash"] = digest
    k.attrs["hw_id"] = "nvidia.b200.80gb"
    k.attrs["policy_id"] = "lintel.specialize.v0"
    pin = materialize(k, tmp_path, emit="source").as_k()
    key = pin["cache_key"]
    _assert_lintel_key(key)
    assert key["graph_hash"] == digest
    assert key["hw_id"] == "nvidia.b200.80gb"


def test_materialize_kwargs_stamp_lintel_fields(tmp_path):
    k = kernel_from_dict(json.loads((ROOT / "examples" / "copy.json").read_text()))
    digest = "sha256:" + "cd" * 32
    pin = materialize(
        k,
        tmp_path,
        emit="source",
        graph_hash=digest,
        hw_id="nvidia.b200.80gb",
        policy_id="lintel.specialize.v0",
    ).as_k()
    key = pin["cache_key"]
    _assert_lintel_key(key)
    assert key["graph_hash"] == digest
    assert key["hw_id"] == "nvidia.b200.80gb"
    assert "target" not in key


def test_hw_id_from_arch_not_kernel_target():
    k = kernel_from_dict(json.loads((ROOT / "examples" / "gemm.json").read_text()))
    k.target = "cuda-sm90"
    out = lower(k)
    pin = out.as_k()
    _assert_lintel_key(pin["cache_key"])
    assert pin["target"] == "cuda-sm90"
    assert pin["cache_key"]["hw_id"] == "nvidia.sm_90"
    assert pin["arch"] == "sm_90"
    k.target = "ascend-a2"
    npu = lower(k).as_k()
    assert npu["cache_key"]["hw_id"] == "ascend.davinci"
    assert npu["target"] == "ascend-a2"
    assert "target" not in npu["cache_key"]


def test_cli_pin_validates_cache_key(tmp_path, capsys):
    k = kernel_from_dict(json.loads((ROOT / "examples" / "copy.json").read_text()))
    materialize(k, tmp_path, emit="source")
    pin_path = tmp_path / "pin.json"
    assert main(["pin", str(pin_path)]) == 0
    assert json.loads(capsys.readouterr().out) == []
    bad = tmp_path / "bad.json"
    doc = json.loads(pin_path.read_text())
    doc["cache_key"]["target"] = "cuda"
    bad.write_text(json.dumps(doc))
    assert main(["pin", str(bad)]) == 1
    errs = json.loads(capsys.readouterr().out)
    assert any("additional properties" in e for e in errs)
    mismatched = tmp_path / "mismatch.json"
    doc2 = json.loads(pin_path.read_text())
    doc2["cache_key_digest"] = "sha256:" + "00" * 32
    mismatched.write_text(json.dumps(doc2))
    assert main(["pin", str(mismatched)]) == 1
    errs2 = json.loads(capsys.readouterr().out)
    assert any("cache_key_digest mismatch" in e for e in errs2)


def test_cache_key_digest_is_sorted_compact_json():
    key = {
        "policy_id": "lintel.specialize.v0",
        "adapter_id": "choreo.v0",
        "compiler_ver": f"choreoir=={COMPILER_VER};nvcc.cubin",
        "hw_id": "nvidia.b200.80gb",
        "graph_hash": "sha256:" + "bb" * 32,
        "schema_version": "cache-key.v0",
    }
    canonical = (
        f'{{"adapter_id":"choreo.v0","compiler_ver":"choreoir=={COMPILER_VER};nvcc.cubin",'
        '"graph_hash":"sha256:' + "bb" * 32 + '",'
        '"hw_id":"nvidia.b200.80gb","policy_id":"lintel.specialize.v0",'
        '"schema_version":"cache-key.v0"}'
    )
    from choreoir.pin import cache_key_canonical

    assert cache_key_canonical(key) == canonical
    assert cache_key_digest(key) == "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def test_cli_lower_stamps_graph_hash(tmp_path, capsys):
    digest = "sha256:" + "ef" * 32
    rc = main(
        [
            "lower",
            str(ROOT / "examples" / "copy.json"),
            "-o",
            str(tmp_path),
            "--graph-hash",
            digest,
            "--hw-id",
            "nvidia.b200.80gb",
        ]
    )
    assert rc == 0
    capsys.readouterr()
    pin = json.loads((tmp_path / "pin.json").read_text())
    _assert_lintel_key(pin["cache_key"])
    assert pin["cache_key"]["graph_hash"] == digest
    assert pin["cache_key"]["hw_id"] == "nvidia.b200.80gb"
    assert pin["target"] == "cuda"


def test_handshake_goldens_match_live_source_pin(tmp_path):
    for name in ("copy", "gemm"):
        k = kernel_from_dict(json.loads((ROOT / "examples" / f"{name}.json").read_text()))
        live = materialize(k, tmp_path / name, emit="source").as_k()
        gold = json.loads((ROOT / "examples" / f"{name}.pin.json").read_text())
        _assert_lintel_key(live["cache_key"])
        assert live["cache_key_digest"] == cache_key_digest(live["cache_key"])
        assert live == gold
        assert gold["sink_id"] == "cuda.cxx"
        assert gold["cache_key"]["adapter_id"] == FACE_ADAPTER_ID
        assert gold["cache_key_digest"] == cache_key_digest(gold["cache_key"])
