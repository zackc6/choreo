from pathlib import Path

from choreoir.jsonio import kernel_from_dict, kernel_to_dict
from choreoir.check import check

ROOT = Path(__file__).resolve().parents[1]


def test_examples_roundtrip_and_admit():
    for name in ("copy.json", "gemm.json"):
        raw = __import__("json").loads((ROOT / "examples" / name).read_text())
        k = kernel_from_dict(raw)
        assert kernel_to_dict(k)["name"] == raw["name"]
        assert check(k) == []
        again = kernel_from_dict(kernel_to_dict(k))
        assert kernel_to_dict(again) == kernel_to_dict(k)
        assert kernel_to_dict(k)["compiler_ver"] == "0.1.3"


def test_compiler_ver_roundtrip_pin():
    raw = __import__("json").loads((ROOT / "examples" / "copy.json").read_text())
    k = kernel_from_dict(raw)
    k.compiler_ver = "0.2.0-gate"
    d = kernel_to_dict(k)
    assert d["compiler_ver"] == "0.2.0-gate"
    assert kernel_from_dict(d).compiler_ver == "0.2.0-gate"
