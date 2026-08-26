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


def test_cli_print_triton(capsys):
    assert main(["print", str(ROOT / "examples" / "copy.json")]) == 0
    assert "@triton.jit" in capsys.readouterr().out
