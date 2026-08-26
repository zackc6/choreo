import hashlib
import json
from pathlib import Path

import pytest

from choreoir.ast import (
    COMPILER_VER,
    Barrier,
    Buffer,
    Copy,
    Kernel,
    Layout,
    Mma,
    Partition,
    Pipeline,
    Reduce,
)
from choreoir.check import check
from choreoir.jsonio import kernel_from_dict
from choreoir.lower import find_ccec, find_nvcc, lower, materialize
from choreoir.print_triton import print_triton

ROOT = Path(__file__).resolve().parents[1]


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
    assert "for _stage in tl.range(0, 3, num_stages=3)" in out.triton_text
    assert "_stage" in out.text


def test_lower_ascend_gemm_emits_l1_copy_gemm_barrier():
    k = _gemm_k(target="ascend-a2")
    out = lower(k)
    assert out.errors() == []
    assert out.family == "ascend"
    assert "__global__ __aicore__" in out.text
    assert "copy_gm_to_ubuf" in out.text
    assert "Ag + i0 * 4 + i1" in out.text
    assert "pipe_barrier(PIPE_ALL)" in out.text
    assert "cube.mmad" in out.text
    assert "vmadd((C + i * 8 + j)," in out.text
    assert "As + i * 4 + kk" in out.text
    assert "Bs + kk * 8 + j" in out.text
    assert "for (int i = 0; i < 8; ++i)" in out.text
    assert "space=smem → L1" in out.text
    assert "T.gemm(As, Bs, C)" in out.tilelang_text
    assert "alloc_L1" in out.tilelang_text
    assert "alloc_L0C" in out.tilelang_text
    assert "T.pipe_barrier" in out.tilelang_text
    assert "T.Scope('C')" in out.tilelang_text
    assert "@triton.jit" not in out.text
    assert "tilelang.language" not in out.text


def test_lower_ascend_pipeline_depth():
    k = _gemm_k(pipeline_depth=3, target="ascend-a2")
    out = lower(k)
    assert out.errors() == []
    assert "depth=3" in out.text
    assert "for (int _stage = 0; _stage < 3; ++_stage)" in out.text
    assert "T.Pipelined(1, num_stages=3)" in out.tilelang_text
    assert "_stage *" in out.text
    assert "pipeline stages=3" in out.text


def test_cce_pipeline_depth_stages_ub():
    """Pipeline.depth stages smem UB the way CUDA stages __shared__[depth]."""
    from choreoir.print_ascendc import print_ascendc

    deep = print_ascendc(_gemm_k(pipeline_depth=3, target="ascend-a2"))
    shallow = print_ascendc(_gemm_k(pipeline_depth=1, target="ascend-a2"))
    assert "_stage *" in deep
    assert "pipeline stages=3" in deep
    assert "_stage *" not in shallow
    assert "pipeline stages=" not in shallow
    assert deep != shallow
    assert "As + _stage *" in deep
    assert "Bs + _stage *" in deep


def test_cce_mma_indexes_layout_stride():
    """CCE vmadd addresses follow shape×stride, matching CUDA scalar MAC."""
    from choreoir.print_ascendc import print_ascendc

    compact = print_ascendc(_gemm_k(target="ascend-a2"))
    assert "vmadd((C + i * 8 + j)," in compact
    assert "As + i * 4 + kk" in compact
    assert "Bs + kk * 8 + j" in compact
    padded = _gemm_k(target="ascend-a2")
    bufs = []
    for b in padded.buffers:
        if b.name == "As":
            bufs.append(Buffer(b.name, b.space, Layout((8, 4), (8, 1)), b.dtype))
        else:
            bufs.append(b)
    padded.buffers = tuple(bufs)
    wide = print_ascendc(padded)
    assert "As + i * 8 + kk" in wide
    assert "As + i * 4 + kk" not in wide
    assert compact != wide


@pytest.mark.skipif(find_ccec() is None, reason="ccec not installed (stand-in writes .cce only)")
def test_ccec_npu_bin_tracks_mma_layout_stride(tmp_path):
    compact = _gemm_k(target="ascend-a2")
    bufs = tuple(
        Buffer(b.name, b.space, Layout((8, 4), (8, 1)), b.dtype) if b.name == "As" else b
        for b in compact.buffers
    )
    padded = Kernel(
        compact.name,
        target="ascend-a2",
        buffers=bufs,
        partitions=compact.partitions,
        body=compact.body,
    )
    c = materialize(compact, tmp_path / "c", emit="npu-bin")
    p = materialize(padded, tmp_path / "p", emit="npu-bin")
    assert c.artifact_kind == "npu-bin" and p.artifact_kind == "npu-bin", (c.findings, p.findings)
    hc = Path(c.artifact_path).read_bytes()
    hp = Path(p.artifact_path).read_bytes()
    assert hc[:4] == hp[:4] == b"\x7fELF"
    assert hashlib.sha256(hc).digest() != hashlib.sha256(hp).digest()


def test_cce_copy_indexes_layout_stride():
    """CCE Copy addresses follow shape×stride, matching CUDA Copy."""
    from choreoir.print_ascendc import print_ascendc

    compact = print_ascendc(_copy_k(target="ascend-a2"))
    assert "copy_gm_to_ubuf" in compact
    assert "A + i0 * 8 + i1" in compact
    assert "S + i0 * 8 + i1" in compact
    assert "for (int i0 = 0; i0 < 8; ++i0)" in compact
    assert "for (int i1 = 0; i1 < 8; ++i1)" in compact
    padded = _copy_k(target="ascend-a2")
    bufs = []
    for b in padded.buffers:
        if b.name == "A":
            bufs.append(Buffer(b.name, b.space, Layout((8, 8), (16, 1)), b.dtype))
        else:
            bufs.append(b)
    padded.buffers = tuple(bufs)
    wide = print_ascendc(padded)
    assert "A + i0 * 16 + i1" in wide
    assert "A + i0 * 8 + i1" not in wide
    assert compact != wide


@pytest.mark.skipif(find_ccec() is None, reason="ccec not installed (stand-in writes .cce only)")
def test_ccec_npu_bin_tracks_copy_layout_stride(tmp_path):
    compact = _copy_k(target="ascend-a2")
    bufs = tuple(
        Buffer(b.name, b.space, Layout((8, 8), (16, 1)), b.dtype) if b.name == "A" else b
        for b in compact.buffers
    )
    padded = Kernel(
        compact.name,
        target="ascend-a2",
        buffers=bufs,
        partitions=compact.partitions,
        body=compact.body,
    )
    c = materialize(compact, tmp_path / "c", emit="npu-bin")
    p = materialize(padded, tmp_path / "p", emit="npu-bin")
    assert c.artifact_kind == "npu-bin" and p.artifact_kind == "npu-bin", (c.findings, p.findings)
    hc = Path(c.artifact_path).read_bytes()
    hp = Path(p.artifact_path).read_bytes()
    assert hc[:4] == hp[:4] == b"\x7fELF"
    assert hashlib.sha256(hc).digest() != hashlib.sha256(hp).digest()


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


def test_find_nvcc_discovers_local_prefix():
    nvcc = find_nvcc()
    if nvcc is None:
        pytest.skip("nvcc not installed")
    assert Path(nvcc).name == "nvcc"
    assert Path(nvcc).is_file()


def test_examples_lower_cuda():
    for name in ("copy.json", "gemm.json"):
        k = kernel_from_dict(json.loads((ROOT / "examples" / name).read_text()))
        out = lower(k)
        assert out.errors() == [], out.findings
        assert out.family == "cuda"
        assert out.compiler_ver == COMPILER_VER
        assert "__global__" in out.text
        assert out.triton_text and "@triton.jit" in out.triton_text
        assert out.cuda_text == out.text
    gemm = kernel_from_dict(json.loads((ROOT / "examples" / "gemm.json").read_text()))
    gout = lower(gemm)
    assert gout.facts is not None
    assert gout.facts.num_stages == 3
    assert "depth=3" in gout.text
    assert "_stage" in gout.text
    assert "[3]" in gout.text or "num_stages=3" in gout.triton_text
    assert "__launch_bounds__" in gout.text
    assert "threadIdx.x" in gout.text


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


def test_cuda_partition_width_is_codegen():
    """Partition.width is a sink input, not a comment. Not CuTe work-partition."""
    from choreoir.print_cuda import print_cuda

    wide = _copy_k(target="cuda")
    narrow = Kernel(
        "copy",
        target="cuda",
        buffers=(
            Buffer("A", "gmem", Layout((8, 8), (8, 1)), "f16"),
            Buffer("S", "smem", Layout((8, 8), (8, 1)), "f16"),
        ),
        partitions=(Partition("load", "load", 1),),
        body=(Copy("c0", "A", "S", "load"),),
    )
    t_wide = print_cuda(wide)
    t_narrow = print_cuda(narrow)
    assert "__launch_bounds__(128)" in t_wide  # 4 warps × 32
    assert "__launch_bounds__(32)" in t_narrow
    assert "threadIdx.x" in t_wide and "threadIdx.x" in t_narrow
    assert "_i += 128" in t_wide  # load width 4
    assert "_i += 32" in t_narrow
    assert t_wide != t_narrow
    assert "copy_launch" in lower(wide).triton_text
    assert "num_warps=4" in lower(wide).triton_text


def test_cce_partition_width_is_codegen():
    from choreoir.print_ascendc import print_ascendc

    wide = _copy_k(target="ascend-a2")
    narrow = Kernel(
        "copy",
        target="ascend-a2",
        buffers=(
            Buffer("A", "gmem", Layout((8, 8), (8, 1)), "f16"),
            Buffer("S", "smem", Layout((8, 8), (8, 1)), "f16"),
        ),
        partitions=(Partition("load", "load", 1),),
        body=(Copy("c0", "A", "S", "load"),),
    )
    t_wide = print_ascendc(wide)
    t_narrow = print_ascendc(narrow)
    assert "block_idx < 4" in t_wide
    assert "block_idx < 1" in t_narrow
    assert t_wide != t_narrow
    assert "T.Kernel(4, is_npu=True)" in lower(wide).tilelang_text


@pytest.mark.skipif(find_nvcc() is None, reason="nvcc not installed (stand-in writes .cu only)")
def test_nvcc_cubin_tracks_partition_width(tmp_path):
    wide = _copy_k(target="cuda")
    narrow = Kernel(
        "copy",
        target="cuda",
        buffers=(
            Buffer("A", "gmem", Layout((8, 8), (8, 1)), "f16"),
            Buffer("S", "smem", Layout((8, 8), (8, 1)), "f16"),
        ),
        partitions=(Partition("load", "load", 1),),
        body=(Copy("c0", "A", "S", "load"),),
    )
    w = materialize(wide, tmp_path / "w", emit="cubin")
    n = materialize(narrow, tmp_path / "n", emit="cubin")
    assert w.artifact_kind == "cubin" and n.artifact_kind == "cubin", (w.findings, n.findings)
    hw = Path(w.artifact_path).read_bytes()
    hn = Path(n.artifact_path).read_bytes()
    assert hw[:4] == hn[:4] == b"\x7fELF"
    assert hashlib.sha256(hw).digest() != hashlib.sha256(hn).digest()


@pytest.mark.skipif(find_ccec() is None, reason="ccec not installed (stand-in writes .cce only)")
def test_ccec_npu_bin_tracks_partition_width(tmp_path):
    wide = _copy_k(target="ascend-a2")
    narrow = Kernel(
        "copy",
        target="ascend-a2",
        buffers=(
            Buffer("A", "gmem", Layout((8, 8), (8, 1)), "f16"),
            Buffer("S", "smem", Layout((8, 8), (8, 1)), "f16"),
        ),
        partitions=(Partition("load", "load", 1),),
        body=(Copy("c0", "A", "S", "load"),),
    )
    w = materialize(wide, tmp_path / "w", emit="npu-bin")
    n = materialize(narrow, tmp_path / "n", emit="npu-bin")
    assert w.artifact_kind == "npu-bin" and n.artifact_kind == "npu-bin", (w.findings, n.findings)
    hw = Path(w.artifact_path).read_bytes()
    hn = Path(n.artifact_path).read_bytes()
    assert hw[:4] == hn[:4] == b"\x7fELF"
    assert hashlib.sha256(hw).digest() != hashlib.sha256(hn).digest()


@pytest.mark.skipif(find_ccec() is None, reason="ccec not installed (stand-in writes .cce only)")
def test_ccec_npu_bin_tracks_pipeline_depth(tmp_path):
    deep = _gemm_k(pipeline_depth=3, target="ascend-a2")
    shallow = _gemm_k(pipeline_depth=1, target="ascend-a2")
    d = materialize(deep, tmp_path / "d3", emit="npu-bin")
    s = materialize(shallow, tmp_path / "d1", emit="npu-bin")
    assert d.artifact_kind == "npu-bin" and s.artifact_kind == "npu-bin", (d.findings, s.findings)
    hd = Path(d.artifact_path).read_bytes()
    hs = Path(s.artifact_path).read_bytes()
    assert hd[:4] == hs[:4] == b"\x7fELF"
    assert hashlib.sha256(hd).digest() != hashlib.sha256(hs).digest()


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
    assert "__gm__ float* Cg" in out.text or "__gm__ float* Cg /*" in out.text
    assert "copy_ubuf_to_gm" in out.text
    assert "L0C" in out.text
    assert "role=store" in out.text
    assert "Cg: T.Buffer" in out.tilelang_text
    assert "T.copy(C, Cg)" in out.tilelang_text
    assert "L0C->GM" in out.tilelang_text


def test_materialize_npu_bin_writes_cce_and_sidecar(tmp_path):
    k = kernel_from_dict(json.loads((ROOT / "examples" / "gemm.json").read_text()))
    k.target = "ascend-a2"
    out = materialize(k, tmp_path, emit="npu-bin")
    assert not out.errors()
    assert (tmp_path / "gemm_tile.cce").is_file()
    assert (tmp_path / "gemm_tile.npu.py").is_file()
    assert "tilelang.language" in (tmp_path / "gemm_tile.npu.py").read_text()
    msgs = " ".join(f.msg for f in out.findings)
    if out.artifact_kind != "npu-bin":
        assert "ccec missing" in msgs or "ccec failed" in msgs
        assert out.artifact_kind == "source"
    pin = json.loads((tmp_path / "pin.json").read_text())
    assert pin["kernel"] == "gemm_tile"
    sink = "ccec.aicore" if out.artifact_kind == "npu-bin" else "ascendc.cce"
    assert pin["sink_id"] == sink
    assert pin["cache_key"]["compiler_ver"] == f"choreoir=={COMPILER_VER};{sink}"
    assert pin["source_sha256"] == out.source_sha256


def test_materialize_writes_pin_for_lintel_k(tmp_path):
    k = kernel_from_dict(json.loads((ROOT / "examples" / "gemm.json").read_text()))
    out = materialize(k, tmp_path, emit="source")
    pin = json.loads((tmp_path / "pin.json").read_text())
    assert pin["kernel"] == "gemm_tile"
    assert pin["cache_key"]["compiler_ver"] == f"choreoir=={COMPILER_VER};cuda.cxx"
    assert pin["source_sha256"] == out.source_sha256
    assert pin["sink_id"] == "cuda.cxx"
    assert pin["cache_key"]["adapter_id"] == "choreo.v0"
    assert "target" not in pin["cache_key"]
    assert pin["target"] == "cuda"
    assert pin["cache_key"]["graph_hash"].startswith("sha256:")
    assert pin["isa"] == "mma.sync"
    assert pin["arch"] == "sm_80"
    assert out.as_k() == pin


def test_pin_isa_follows_schedule_not_family():
    copy = kernel_from_dict(json.loads((ROOT / "examples" / "copy.json").read_text()))
    gpu = lower(copy)
    assert gpu.facts is not None
    assert gpu.facts.isa == "copy"
    assert gpu.as_k()["isa"] == "copy"
    copy.target = "ascend-a2"
    npu = lower(copy)
    assert npu.facts is not None
    assert npu.facts.isa == "copy.ubuf"
    gemm = kernel_from_dict(json.loads((ROOT / "examples" / "gemm.json").read_text()))
    assert lower(gemm).as_k()["isa"] == "mma.sync"
    gemm.target = "ascend-a2"
    assert lower(gemm).as_k()["isa"] == "cube.mmad"


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
    assert man["compiler_ver"] == COMPILER_VER
    assert out.source_sha256


def test_materialize_npu_bin_without_ccec_writes_cce(tmp_path, monkeypatch):
    monkeypatch.setenv("CHOREO_CCEC", "")
    k = kernel_from_dict(json.loads((ROOT / "examples" / "gemm.json").read_text()))
    k.target = "ascend-a2"
    out = materialize(k, tmp_path, emit="npu-bin")
    assert not out.errors()
    assert out.artifact_kind == "source"
    assert "ccec missing" in " ".join(f.msg for f in out.findings)
    assert (tmp_path / "gemm_tile.cce").is_file()
    assert (tmp_path / "gemm_tile.npu.py").is_file()
    pin = json.loads((tmp_path / "pin.json").read_text())
    assert pin["sink_id"] == "ascendc.cce"
    assert pin["cache_key"]["adapter_id"] == "choreo.v0"
    assert pin["artifact_kind"] == "source"
    assert pin["artifact_sha256"] is None


@pytest.mark.skipif(find_nvcc() is None, reason="nvcc not installed (stand-in writes .cu only)")
def test_materialize_cubin_with_nvcc_is_elf(tmp_path):
    k = kernel_from_dict(json.loads((ROOT / "examples" / "gemm.json").read_text()))
    out = materialize(k, tmp_path, emit="cubin")
    assert not out.errors(), out.findings
    assert out.artifact_kind == "cubin", out.findings
    data = Path(out.artifact_path).read_bytes()
    assert data[:4] == b"\x7fELF"
    assert out.artifact_sha256 == hashlib.sha256(data).hexdigest()
    assert "nvcc" in out.toolchain
    man = json.loads((tmp_path / "manifest.json").read_text())
    assert man["artifact_kind"] == "cubin"
    assert man["artifact_sha256"] == out.artifact_sha256
    # copy kernel too
    ck = kernel_from_dict(json.loads((ROOT / "examples" / "copy.json").read_text()))
    cout = materialize(ck, tmp_path / "copy", emit="cubin")
    assert cout.artifact_kind == "cubin", cout.findings
    assert Path(cout.artifact_path).read_bytes()[:4] == b"\x7fELF"
    pin = json.loads((tmp_path / "pin.json").read_text())
    assert pin["kernel"] == "gemm_tile"
    assert pin["sink_id"] == "nvcc.cubin"
    assert pin["cache_key"]["adapter_id"] == "choreo.v0"
    assert pin["artifact_kind"] == "cubin"
    assert pin["artifact_sha256"] == out.artifact_sha256
    assert pin["cache_key"]["graph_hash"].startswith("sha256:")
    assert pin["cache_key"]["compiler_ver"] == f"choreoir=={COMPILER_VER};nvcc.cubin"


def test_find_ccec_discovers_local_bisheng():
    ccec = find_ccec()
    if ccec is None:
        pytest.skip("ccec not installed")
    assert Path(ccec).name == "ccec"
    assert Path(ccec).is_file()


def test_print_ascendc_consumes_copy_barrier_mma_pipeline():
    from choreoir.print_ascendc import print_ascendc

    k = _gemm_k(pipeline_depth=3, target="ascend-a2")
    text = print_ascendc(k)
    assert "__global__ __aicore__" in text
    assert "copy_gm_to_ubuf" in text
    assert "pipe_barrier(PIPE_ALL)" in text
    assert "depth=3" in text
    assert "_stage" in text
    assert "_stage *" in text
    assert "cube.mmad" in text
    assert "role=math" in text
    assert "vmadd(" in text
    assert "i * 4 + kk" in text
    assert "space=smem → L1" in text


def _reduce_k(target: str) -> Kernel:
    return Kernel(
        "red",
        target=target,
        buffers=(
            Buffer("X", "regs", Layout((2, 2), (2, 1)), "f32"),
            Buffer("Y", "regs", Layout((2,), (1,)), "f32"),
        ),
        partitions=(Partition("math", "math", 1),),
        body=(Reduce("r0", "X", "Y", 1, "math"),),
    )


def test_cuda_and_cce_lower_reduce():
    from choreoir.print_ascendc import print_ascendc
    from choreoir.print_cuda import print_cuda

    cuda = print_cuda(_reduce_k("cuda"))
    assert "reduce r0 X-axis1->Y" in cuda
    assert "Y[rz0] = 0.f;" in cuda
    assert "Y[rz0] += (float)X[rz0][rs1];" in cuda
    assert "threadIdx.x" in cuda
    assert "not lowered" not in cuda
    cce = print_ascendc(_reduce_k("ascend-a2"))
    assert "reduce r0 X-axis1->Y" in cce
    assert "vector_dup(Y, 0.f, 1);" in cce
    assert "vadd(Y + rs0, Y + rs0, X + rs0 * 2 + rs1, 1);" in cce
    assert "not lowered" not in cce
    out = lower(_reduce_k("cuda"), sla=False)
    assert out.errors() == []
    assert "reduce r0" in out.text


@pytest.mark.skipif(find_nvcc() is None, reason="nvcc not installed (stand-in writes .cu only)")
def test_materialize_reduce_cubin_is_elf(tmp_path):
    out = materialize(_reduce_k("cuda"), tmp_path, emit="cubin", sla=False)
    assert not out.errors(), out.findings
    assert out.artifact_kind == "cubin"
    assert Path(out.artifact_path).read_bytes()[:4] == b"\x7fELF"


@pytest.mark.skipif(find_ccec() is None, reason="ccec not installed (stand-in writes .cce only)")
def test_materialize_reduce_npu_bin_is_elf(tmp_path):
    out = materialize(_reduce_k("ascend-a2"), tmp_path, emit="npu-bin", sla=False)
    assert not out.errors(), out.findings
    assert out.artifact_kind == "npu-bin"
    assert Path(out.artifact_path).read_bytes()[:4] == b"\x7fELF"


@pytest.mark.skipif(find_ccec() is None, reason="ccec not installed (stand-in writes .cce only)")
def test_materialize_npu_bin_with_ccec_is_elf(tmp_path):
    k = kernel_from_dict(json.loads((ROOT / "examples" / "gemm.json").read_text()))
    k.target = "ascend-a2"
    out = materialize(k, tmp_path, emit="npu-bin")
    assert not out.errors(), out.findings
    assert out.artifact_kind == "npu-bin", out.findings
    data = Path(out.artifact_path).read_bytes()
    assert data[:4] == b"\x7fELF"
    assert out.artifact_sha256 == hashlib.sha256(data).hexdigest()
    assert "ccec" in out.toolchain
    man = json.loads((tmp_path / "manifest.json").read_text())
    assert man["artifact_kind"] == "npu-bin"
    assert man["artifact_sha256"] == out.artifact_sha256
    ck = kernel_from_dict(json.loads((ROOT / "examples" / "copy.json").read_text()))
    ck.target = "ascend-a2"
    cout = materialize(ck, tmp_path / "copy", emit="npu-bin")
    assert cout.artifact_kind == "npu-bin", cout.findings
    assert Path(cout.artifact_path).read_bytes()[:4] == b"\x7fELF"
    pin = json.loads((tmp_path / "pin.json").read_text())
    assert pin["kernel"] == "gemm_tile"
    assert pin["sink_id"] == "ccec.aicore"
    assert pin["cache_key"]["adapter_id"] == "choreo.v0"
    assert pin["artifact_kind"] == "npu-bin"
    assert pin["artifact_sha256"] == out.artifact_sha256
    assert pin["cache_key"]["graph_hash"].startswith("sha256:")
    assert pin["cache_key"]["compiler_ver"] == f"choreoir=={COMPILER_VER};ccec.aicore"
    assert pin["family"] == "ascend"
    assert pin["isa"] == "cube.mmad"
    assert pin["arch"] == "davinci"
    assert pin["cache_key"]["hw_id"] == "ascend.davinci"
    assert "target" not in pin["cache_key"]
    assert "vmadd(" in (tmp_path / "gemm_tile.cce").read_text()
    assert (tmp_path / "gemm_tile.cce").is_file()
    assert (tmp_path / "gemm_tile.npu.py").is_file()

