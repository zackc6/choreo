import json
from pathlib import Path

import pytest

from choreoir.ast import (
    Barrier,
    Buffer,
    Copy,
    Kernel,
    Layout,
    Mma,
    Partition,
    Pipeline,
)
from choreoir.check import check
from choreoir.jsonio import kernel_from_dict
from choreoir.lower import find_nvcc, lower, materialize
from choreoir.print_triton import print_triton


def _copy_k(**kwargs) -> Kernel:
    return Kernel(
        "copy",
        buffers=(
            Buffer("A", "gmem", Layout((8, 8), (8, 1)), "f16"),
            Buffer("S", "smem", Layout((8, 8), (8, 1)), "f16"),
        ),
        partitions=(Partition("load", "load", 4),),
        body=(Copy("c0", "A", "S", "load"),),
        **kwargs,
    )


def _gemm_k(*, pipeline_depth: int | None = None, **kwargs) -> Kernel:
    copies = (
        Copy("cA", "Ag", "As", "load"),
        Copy("cB", "Bg", "Bs", "load"),
    )
    rest = (
        Barrier("b0", wait_for=("load",), arrive="math"),
        Mma("m0", "As", "Bs", "C", "math"),
    )
    if pipeline_depth is not None:
        body: tuple = (Pipeline("p0", pipeline_depth, copies + rest),)
    else:
        body = copies + rest
    return Kernel(
        "gemm_tile",
        buffers=(
            Buffer("Ag", "gmem", Layout((8, 4), (4, 1)), "f16"),
            Buffer("Bg", "gmem", Layout((4, 8), (8, 1)), "f16"),
            Buffer("As", "smem", Layout((8, 4), (4, 1)), "f16"),
            Buffer("Bs", "smem", Layout((4, 8), (8, 1)), "f16"),
            Buffer("C", "regs", Layout((8, 8), (8, 1)), "f32"),
        ),
        partitions=(
            Partition("load", "load", 4),
            Partition("math", "math", 4),
        ),
        body=body,
        **kwargs,
    )


def test_lower_cuda_copy_fills_block_and_warps():
    k = _copy_k(target="cuda")
    assert check(k) == []
    out = lower(k)
    assert out.errors() == []
    assert out.family == "cuda"
    assert out.facts is not None
    assert out.facts.num_warps == 4
    assert out.facts.block == 64
    assert "__global__" in out.text
    assert "__shared__" in out.text
    assert "BLOCK: tl.constexpr = 64" in out.triton_text
    assert "num_warps=4" in out.triton_text
    assert "@triton.jit" in out.triton_text


def test_lower_cuda_gemm_consumes_barrier_and_layouts():
    k = _gemm_k(target="cuda")
    out = lower(k)
    assert out.errors() == []
    assert out.facts is not None
    assert out.facts.num_warps == 8
    assert out.facts.n_barrier == 1
    assert "__syncthreads();" in out.text
    assert "BLOCK_M: tl.constexpr = 8" in out.triton_text
    assert "tl.debug_barrier()" in out.triton_text
    assert "num_stages=1" in out.triton_text


def test_lower_cuda_pipeline_depth_is_num_stages():
    k = _gemm_k(pipeline_depth=3, target="cuda")
    assert check(k) == []
    out = lower(k)
    assert out.errors() == []
    assert out.facts is not None
    assert out.facts.num_stages == 3
    assert "num_stages=3" in out.triton_text
    assert "_stage" in out.text


def test_lower_ascend_gemm_emits_l1_copy_gemm_barrier():
    k = _gemm_k(target="ascend-a2")
    out = lower(k)
    assert out.errors() == []
    assert out.family == "ascend"
    assert "tilelang.language" in out.text
    assert "alloc_L1" in out.text
    assert "alloc_L0C" in out.text
    assert "T.copy(Ag, As)" in out.text
    assert "T.gemm(As, Bs, C)" in out.text
    assert "T.pipe_barrier" in out.text
    assert "T.Scope('C')" in out.text
    assert "@triton.jit" not in out.text


def test_lower_ascend_pipeline_depth():
    k = _gemm_k(pipeline_depth=3, target="ascend-a2")
    out = lower(k)
    assert out.errors() == []
    assert "T.Pipelined(1, num_stages=3)" in out.text


def test_lower_requires_named_target():
    k = _copy_k()
    out = lower(k)
    assert out.text == ""
    assert any("named target" in f.msg for f in out.errors())


def test_lower_refuses_admit_error():
    k = Kernel(
        "copy",
        target="cuda",
        buffers=(Buffer("A", "gmem", Layout((8, 8), (8, 1)), "f16"),),
        partitions=(Partition("load", "load", 4),),
        body=(Copy("c0", "A", "missing", "load"),),
    )
    out = lower(k)
    assert out.text == ""
    assert any(f.gate == "W" for f in out.errors())


def test_lower_sla_allowlist():
    k = Kernel(
        "attn",
        target="cuda",
        buffers=(
            Buffer("A", "gmem", Layout((4, 4), (4, 1)), "f16"),
            Buffer("S", "smem", Layout((4, 4), (4, 1)), "f16"),
        ),
        partitions=(Partition("load", "load", 1),),
        body=(Copy("c0", "A", "S", "load"),),
    )
    assert check(k) == []
    out = lower(k)
    assert any("allowlists" in f.msg for f in out.errors())
    out2 = lower(k, sla=False)
    assert out2.errors() == []


def test_print_triton_still_works_without_target():
    text = print_triton(_copy_k())
    assert "@triton.jit" in text


ROOT = Path(__file__).resolve().parents[1]


def test_examples_lower_cuda():
    for name in ("copy.json", "gemm.json"):
        k = kernel_from_dict(json.loads((ROOT / "examples" / name).read_text()))
        out = lower(k)
        assert out.errors() == [], out.findings
        assert out.family == "cuda"
        assert out.compiler_ver == "0.1.1"
        assert "__global__" in out.text
        assert out.triton_text and "@triton.jit" in out.triton_text
        assert out.cuda_text == out.text


def test_cuda_cpp_consumes_smem_barrier_mma_isa():
    from choreoir.print_cuda import print_cuda

    k = _gemm_k(target="cuda-sm90")
    text = print_cuda(k)
    assert "__shared__" in text
    assert "__syncthreads();" in text
    assert "wgmma.mma_async" in text
    assert "copy cA" in text
    sm100 = print_cuda(_gemm_k(target="cuda-sm100"))
    assert "tcgen05.mma" in sm100


def test_cuda_cpp_pipeline_stages_shared():
    from choreoir.print_cuda import print_cuda

    k = _gemm_k(pipeline_depth=3, target="cuda")
    text = print_cuda(k)
    assert "num_stages=3" in text or "depth=3" in text
    assert "[3]" in text or "_stage" in text


def test_cuda_cpp_writeback_gmem():
    from choreoir.print_cuda import print_cuda

    k = kernel_from_dict(json.loads((ROOT / "examples" / "gemm.json").read_text()))
    text = print_cuda(k)
    assert "float* Cg" in text or "float* Cg /*" in text
    assert "Cg[" in text
    assert "role=store" in text
    assert "cC" in text


def test_ascend_gmem_signature_and_store():
    k = kernel_from_dict(json.loads((ROOT / "examples" / "gemm.json").read_text()))
    k.target = "ascend-a2"
    out = lower(k)
    assert out.errors() == []
    assert "Cg: T.Buffer" in out.text
    assert "T.copy(C, Cg)" in out.text
    assert "L0C->GM" in out.text


def test_materialize_cubin_without_nvcc_writes_cu(tmp_path):
    k = kernel_from_dict(json.loads((ROOT / "examples" / "gemm.json").read_text()))
    out = materialize(k, tmp_path, emit="cubin")
    assert not out.errors()
    assert (tmp_path / "gemm_tile.cu").is_file()
    assert (tmp_path / "gemm_tile.triton.py").is_file()
    msgs = " ".join(f.msg for f in out.findings)
    if out.artifact_kind != "cubin":
        assert "nvcc missing" in msgs or "nvcc failed" in msgs
        assert out.artifact_kind == "source"
    assert (tmp_path / "manifest.json").is_file()
    man = json.loads((tmp_path / "manifest.json").read_text())
    assert man["compiler_ver"] == "0.1.1"
    assert out.source_sha256


def test_materialize_npu_bin_without_tilelang(tmp_path):
    k = kernel_from_dict(json.loads((ROOT / "examples" / "gemm.json").read_text()))
    k.target = "ascend-a2"
    out = materialize(k, tmp_path, emit="npu-bin")
    assert not out.errors()
    assert "tilelang" in " ".join(f.msg for f in out.findings).lower() or "CANN" in " ".join(
        f.msg for f in out.findings
    )
    assert (tmp_path / "gemm_tile.npu.py").is_file()


@pytest.mark.skipif(find_nvcc() is None, reason="nvcc not installed (stand-in writes .cu only)")
def test_materialize_cubin_with_nvcc_is_elf(tmp_path):
    k = kernel_from_dict(json.loads((ROOT / "examples" / "gemm.json").read_text()))
    out = materialize(k, tmp_path, emit="cubin")
    assert not out.errors(), out.findings
    assert out.artifact_kind == "cubin"
    data = Path(out.artifact_path).read_bytes()
    assert data[:4] == b"\x7fELF"
