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
        assert kernel_to_dict(k)["compiler_ver"] == "0.1.8"


def test_package_version_matches_kernel_pin():
    """Q1 pins choreoir by version; setuptools version is the Kernel compiler_ver pin."""
    from importlib.metadata import version

    import choreoir
    from choreoir.ast import Kernel

    assert version("choreoir") == "0.1.8"
    assert choreoir.__version__ == "0.1.8"
    assert Kernel.__dataclass_fields__["compiler_ver"].default == "0.1.8"


def test_compiler_ver_roundtrip_pin():
    raw = __import__("json").loads((ROOT / "examples" / "copy.json").read_text())
    k = kernel_from_dict(raw)
    k.compiler_ver = "0.2.0-gate"
    d = kernel_to_dict(k)
    assert d["compiler_ver"] == "0.2.0-gate"
    assert kernel_from_dict(d).compiler_ver == "0.2.0-gate"
