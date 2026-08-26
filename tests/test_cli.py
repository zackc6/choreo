import json
from pathlib import Path

from choreoir.__main__ import main

ROOT = Path(__file__).resolve().parents[1]


def test_cli_check_copy_ok(capsys):
    assert main(["check", str(ROOT / "examples" / "copy.json")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out == []


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
    assert "T.gemm" in out
    assert "alloc_L1" in out
    assert "Cg: T.Buffer" in out


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
