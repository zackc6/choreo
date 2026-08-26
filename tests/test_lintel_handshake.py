"""How Lintel copies Choreo propose onto the session stream.

This tree does not walk the CFG. The mapping is the handshake: Kernel AST
and Finding JSON are the values Lintel stores; reject.where is the CFG letter.
Session-event reject cannot nest finding (additionalProperties false), so
Lintel copies finding as a payload sibling.
"""

from __future__ import annotations

import json
from pathlib import Path

from choreoir.ast import COMPILER_VER
from choreoir.check import check
from choreoir.interp import check_value
from choreoir.jsonio import kernel_from_dict
from choreoir.lower import find_ccec, find_nvcc, materialize
from choreoir.pin import (
    FACE_ADAPTER_ID,
    cache_key,
    cache_key_digest,
    graph_hash_of,
    hw_id_of,
    k_compiler_ver,
    policy_id_of,
)
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
        ("cyclic_wait.json", "S"),
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


def test_nvcc_cubin_pin_is_lintel_payload(tmp_path):
    """GitHub CI fetches official nvcc so this is not a skip on main."""
    import pytest

    if find_nvcc() is None:
        pytest.skip("need official nvcc")
    k = kernel_from_dict(json.loads((ROOT / "examples" / "copy.json").read_text()))
    out = materialize(k, tmp_path, emit="cubin")
    assert not out.errors(), out.findings
    assert out.artifact_kind == "cubin"
    pin = json.loads((tmp_path / "pin.json").read_text())
    assert pin["sink_id"] == "nvcc.cubin"
    assert pin["artifact_kind"] == "cubin"
    assert pin["cache_key"]["adapter_id"] == "choreo.v0"
    assert pin["cache_key"]["compiler_ver"].endswith(";nvcc.cubin")
    assert pin["cache_key_digest"] == cache_key_digest(pin["cache_key"])
    assert Path(out.artifact_path).read_bytes()[:4] == b"\x7fELF"
    assert "target" not in pin["cache_key"]


# Lintel freeze addresses for the same L2 graph, two sinks. Not a third kernel.
_LAND_GRAPH = "sha256:bbcd57f9162e8a42bbf26df28a6b2a3ac2f8793061c036e198afeaf4f65d6db0"
_LAND_NV_K = "sha256:ae48c242ac672c1a2a338c456d1d024af12e1883277e34773d052555ef22e219"
_LAND_NPU_K = "sha256:a6a93f7cfaaff302c51b20a342ec13d83abc267363d249ce4a31fde6e3f163eb"


def test_same_copy_kernel_two_sinks_two_k():
    """Public CI: two %k from pin helpers. ELF dual-sink stays skipif both toolchains."""
    src = json.loads((ROOT / "examples" / "copy.json").read_text())
    nv = kernel_from_dict(src)
    npu = kernel_from_dict(src)
    npu.target = "ascend-a2"
    nv_key = cache_key(
        graph_hash=graph_hash_of(nv),
        hw_id=hw_id_of(nv, "cuda"),
        compiler_ver=k_compiler_ver(nv.compiler_ver, "nvcc.cubin"),
        policy_id=policy_id_of(nv),
    )
    npu_key = cache_key(
        graph_hash=graph_hash_of(npu),
        hw_id=hw_id_of(npu, "ascend"),
        compiler_ver=k_compiler_ver(npu.compiler_ver, "ccec.aicore"),
        policy_id=policy_id_of(npu),
    )
    assert nv_key["adapter_id"] == npu_key["adapter_id"] == FACE_ADAPTER_ID
    assert nv_key["graph_hash"] == npu_key["graph_hash"]
    assert nv_key["hw_id"].startswith("nvidia.")
    assert npu_key["hw_id"] == "ascend.davinci"
    assert nv_key["compiler_ver"].endswith(";nvcc.cubin")
    assert npu_key["compiler_ver"].endswith(";ccec.aicore")
    assert cache_key_digest(nv_key) != cache_key_digest(npu_key)
    assert "target" not in nv_key and "target" not in npu_key


def test_lintel_land_and_ascend_sibling_k_digests():
    """Canonical cache-key.v0 JSON is the freeze address Lintel already recorded."""
    nv = cache_key(
        graph_hash=_LAND_GRAPH,
        hw_id="nvidia.b200.80gb",
        compiler_ver=f"choreoir=={COMPILER_VER};nvcc.cubin",
        policy_id="lintel.specialize.v0",
    )
    npu = cache_key(
        graph_hash=_LAND_GRAPH,
        hw_id="ascend.davinci",
        compiler_ver=f"choreoir=={COMPILER_VER};ccec.aicore",
        policy_id="lintel.specialize.v0",
    )
    assert cache_key_digest(nv) == _LAND_NV_K
    assert cache_key_digest(npu) == _LAND_NPU_K
    assert nv["adapter_id"] == npu["adapter_id"] == FACE_ADAPTER_ID
    assert "target" not in nv and "target" not in npu


def test_stamped_copy_cubin_pin_is_lintel_land_k(tmp_path):
    """Live nvcc cubin pin under Lintel stamps is the land %k, not a source pin."""
    import pytest

    if find_nvcc() is None:
        pytest.skip("need official nvcc")
    k = kernel_from_dict(json.loads((ROOT / "examples" / "copy.json").read_text()))
    out = materialize(
        k,
        tmp_path,
        emit="cubin",
        graph_hash=_LAND_GRAPH,
        hw_id="nvidia.b200.80gb",
    )
    assert not out.errors(), out.findings
    pin = json.loads((tmp_path / "pin.json").read_text())
    assert pin["sink_id"] == "nvcc.cubin"
    assert pin["cache_key_digest"] == _LAND_NV_K
    assert pin["cache_key"]["hw_id"] == "nvidia.b200.80gb"
    assert pin["artifact_kind"] == "cubin"
    assert Path(out.artifact_path).read_bytes()[:4] == b"\x7fELF"
    assert "target" not in pin["cache_key"]


def test_per_target_sinks_split_cache_key(tmp_path):
    """Same copy Kernel, two sinks → two %k. Not a second face. Not a third kernel."""
    import pytest

    if find_nvcc() is None or find_ccec() is None:
        pytest.skip("need official nvcc and ccec")
    src = json.loads((ROOT / "examples" / "copy.json").read_text())
    nv = kernel_from_dict(src)
    npu = kernel_from_dict(src)
    npu.target = "ascend-a2"
    cubin = materialize(nv, tmp_path / "nv", emit="cubin")
    bin_ = materialize(npu, tmp_path / "npu", emit="npu-bin")
    assert cubin.artifact_kind == "cubin" and not cubin.errors(), cubin.findings
    assert bin_.artifact_kind == "npu-bin" and not bin_.errors(), bin_.findings
    nv_pin = json.loads((tmp_path / "nv" / "pin.json").read_text())
    npu_pin = json.loads((tmp_path / "npu" / "pin.json").read_text())
    assert nv_pin["cache_key"]["adapter_id"] == npu_pin["cache_key"]["adapter_id"] == "choreo.v0"
    assert nv_pin["kernel"] == npu_pin["kernel"] == "copy"
    assert nv_pin["sink_id"] == "nvcc.cubin"
    assert npu_pin["sink_id"] == "ccec.aicore"
    assert nv_pin["cache_key"]["hw_id"].startswith("nvidia.")
    assert npu_pin["cache_key"]["hw_id"] == "ascend.davinci"
    assert nv_pin["cache_key_digest"] != npu_pin["cache_key_digest"]
    assert nv_pin["cache_key_digest"] == cache_key_digest(nv_pin["cache_key"])
    assert npu_pin["cache_key_digest"] == cache_key_digest(npu_pin["cache_key"])
    assert Path(cubin.artifact_path).read_bytes()[:4] == b"\x7fELF"
    assert Path(bin_.artifact_path).read_bytes()[:4] == b"\x7fELF"
