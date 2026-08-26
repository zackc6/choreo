import json
from pathlib import Path

from choreoir.__main__ import main

ROOT = Path(__file__).resolve().parents[1]


def test_cli_check_copy_ok(capsys):
    assert main(["check", str(ROOT / "examples" / "copy.json")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out == []


def test_cli_check_value_gate(capsys):
    rc = main(
        [
            "check",
            str(ROOT / "examples" / "gemm.json"),
            "--tensors",
            str(ROOT / "examples" / "gemm.tensors.json"),
            "--expected",
            str(ROOT / "examples" / "gemm.expected.json"),
        ]
    )
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == []


def test_cli_check_value_mismatch_localizes(tmp_path, capsys):
    bad = tmp_path / "want.json"
    bad.write_text('{"Cg": [[0.0, 0.0], [0.0, 0.0]]}\n')
    rc = main(
        [
            "check",
            str(ROOT / "examples" / "gemm.json"),
            "--tensors",
            str(ROOT / "examples" / "gemm.tensors.json"),
            "--expected",
            str(bad),
        ]
    )
    assert rc == 1
    fs = json.loads(capsys.readouterr().out)
    v = [f for f in fs if f["where"] == "V"]
    assert v and v[0]["element"] == [0, 0]


def test_cli_sim_gemm_expected(capsys):
    rc = main(
        [
            "sim",
            str(ROOT / "examples" / "gemm.json"),
            "--tensors",
            str(ROOT / "examples" / "gemm.tensors.json"),
            "--expected",
            str(ROOT / "examples" / "gemm.expected.json"),
        ]
    )
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == []


def test_cli_print_cuda(capsys):
    assert main(["print", str(ROOT / "examples" / "copy.json")]) == 0
    out = capsys.readouterr().out
    assert "__global__" in out
    assert "__shared__" in out
    assert "role=store" in out


def test_cli_print_ascend(capsys):
    assert main(["print", str(ROOT / "examples" / "gemm.json"), "--target", "ascend-a2"]) == 0
    out = capsys.readouterr().out
    assert "__aicore__" in out
    assert "copy_gm_to_ubuf" in out
    assert "pipe_barrier(PIPE_ALL)" in out
    assert "cube.mmad" in out
    assert "vmadd(" in out
    assert "T.gemm" not in out


def test_cli_print_refuses_without_target(tmp_path, capsys):
    p = tmp_path / "notarget.json"
    p.write_text((ROOT / "examples" / "copy.json").read_text().replace('"target": "cuda"', '"target": ""'))
    assert main(["print", str(p)]) == 1
    findings = json.loads(capsys.readouterr().out)
    assert any("named target" in f["msg"] for f in findings)


def test_cli_lower_cubin_manifest(tmp_path, capsys):
    rc = main(
        ["lower", str(ROOT / "examples" / "gemm.json"), "-o", str(tmp_path), "--emit", "cubin"]
    )
    assert rc == 0
    man = json.loads(capsys.readouterr().out)
    assert man["family"] == "cuda"
    assert (tmp_path / "gemm_tile.cu").is_file()
    assert man["source_sha256"]
    assert "artifact_sha256" in man
    if man["artifact_kind"] == "cubin":
        assert Path(man["artifact_path"]).read_bytes()[:4] == b"\x7fELF"
        assert man["artifact_sha256"]
        assert "nvcc" in man["toolchain"]
        assert man["k"]["adapter_id"] == "nvcc.cubin"
        assert (tmp_path / "pin.json").is_file()
        pin = json.loads((tmp_path / "pin.json").read_text())
        assert pin == man["k"]


def test_cli_lower_npu_bin_manifest(tmp_path, capsys):
    rc = main(
        [
            "lower",
            str(ROOT / "examples" / "gemm.json"),
            "-o",
            str(tmp_path),
            "--target",
            "ascend-a2",
            "--emit",
            "npu-bin",
        ]
    )
    assert rc == 0
    man = json.loads(capsys.readouterr().out)
    assert man["family"] == "ascend"
    assert (tmp_path / "gemm_tile.cce").is_file()
    assert (tmp_path / "gemm_tile.npu.py").is_file()
    assert man["source_sha256"]
    if man["artifact_kind"] == "npu-bin":
        assert Path(man["artifact_path"]).read_bytes()[:4] == b"\x7fELF"
        assert man["artifact_sha256"]
        assert "ccec" in man["toolchain"]
        assert man["k"]["adapter_id"] == "ccec.aicore"
        pin = json.loads((tmp_path / "pin.json").read_text())
        assert pin == man["k"]
