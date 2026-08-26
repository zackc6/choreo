"""Schedule facts consumed by NV GPU and Ascend NPU sinks."""

from __future__ import annotations

from dataclasses import dataclass

from .ast import Barrier, Copy, Kernel, Mma, Pipeline, flatten_ops

YEAR1_KERNELS = frozenset({"copy", "gemm_tile"})


@dataclass(frozen=True)
class ScheduleFacts:
    """Inputs to codegen. Kind-2 knobs plus what the sinks must consume.

    ``num_warps`` / ``num_stages`` are Triton sidecar / ``pin.launch`` knobs and
    may come from ``attrs``. CUDA launch bounds and ``pin.launch.block`` use
    ``partition_warps`` (sum of ``Partition.width``). CUDA/CCE buffer staging
    uses ``pipeline_depth`` (max ``Pipeline.depth``, else 1). Those attrs must
    not shrink the cubin or NPU-bin while loops still walk ``width×32`` /
    ``op.depth``.
    """

    target: str
    family: str  # cuda | ascend
    num_warps: int
    num_stages: int
    pipeline_depth: int
    partition_warps: int
    block: int
    block_m: int
    block_n: int
    block_k: int
    n_barrier: int
    n_copy: int
    n_mma: int
    isa: str
    arch: str

    def as_dict(self) -> dict[str, str | int]:
        return {
            "target": self.target,
            "family": self.family,
            "num_warps": self.num_warps,
            "num_stages": self.num_stages,
            "BLOCK": self.block,
            "BLOCK_M": self.block_m,
            "BLOCK_N": self.block_n,
            "BLOCK_K": self.block_k,
            "n_barrier": self.n_barrier,
            "n_copy": self.n_copy,
            "n_mma": self.n_mma,
            "isa": self.isa,
            "arch": self.arch,
        }


def nv_arch(target: str) -> str:
    t = target.strip()
    if t.startswith("cuda-sm"):
        return "sm_" + t[len("cuda-sm") :].replace("a", "")
    return "sm_80"


def nv_mma_isa(target: str) -> str:
    arch = nv_arch(target)
    if arch.startswith("sm_100") or arch.startswith("sm_12"):
        return "tcgen05.mma"
    if arch.startswith("sm_90"):
        return "wgmma.mma_async"
    return "mma.sync"


def npu_isa(target: str) -> str:
    del target
    return "cube.mmad"


def target_family(target: str) -> str | None:
    t = target.strip()
    if t == "cuda" or t.startswith("cuda-"):
        return "cuda"
    if t == "ascend" or t.startswith("ascend"):
        return "ascend"
    return None


def partition_warps_of(kernel: Kernel) -> int:
    """Sum of ``Partition.width``. CUDA ``__launch_bounds__`` and
    ``pin.launch.block`` use this. ``attrs.num_warps`` is the Triton sidecar
    and must not shrink the cubin block while Copy/Mma/Reduce still stride
    by ``width×32``.
    """
    if not kernel.partitions:
        return 4
    return sum(p.width for p in kernel.partitions)


def pipeline_depth_of(kernel: Kernel) -> int:
    """Max ``Pipeline.depth`` on the AST. ``1`` when the body has no Pipeline.

    CUDA/CCE stage smem from this value. ``attrs.num_stages`` is a Triton
    sidecar and must not shrink (or inflate) that reservation.
    """
    pipes = [op for op in flatten_ops(kernel.body) if isinstance(op, Pipeline)]
    if not pipes:
        return 1
    return max(p.depth for p in pipes)


def facts_from_kernel(kernel: Kernel) -> ScheduleFacts:
    ops = flatten_ops(kernel.body)
    copies = [op for op in ops if isinstance(op, Copy)]
    mmas = [op for op in ops if isinstance(op, Mma)]
    barriers = [op for op in ops if isinstance(op, Barrier)]

    pipe_depth = pipeline_depth_of(kernel)
    part_warps = partition_warps_of(kernel)

    block = 1
    if copies:
        src = kernel.buffer(copies[0].src)
        if src:
            block = max(src.layout.numel(), 1)

    block_m = block_n = block_k = 16
    if mmas:
        a = kernel.buffer(mmas[0].a)
        b = kernel.buffer(mmas[0].b)
        if a and len(a.layout.shape) == 2:
            block_m, block_k = a.layout.shape[0], a.layout.shape[1]
        if b and len(b.layout.shape) == 2:
            block_k, block_n = b.layout.shape[0], b.layout.shape[1]

    def _int_attr(key: str, default: int) -> int:
        raw = kernel.attrs.get(key)
        if raw is None or raw == "":
            return default
        return int(raw)

    family = target_family(kernel.target) or ""
    if family == "ascend":
        arch = "davinci"
        if mmas:
            isa = npu_isa(kernel.target)
        elif copies:
            isa = "copy.ubuf"
        else:
            isa = "none"
    else:
        arch = nv_arch(kernel.target)
        if mmas:
            isa = nv_mma_isa(kernel.target)
        elif copies:
            isa = "copy"
        else:
            isa = "none"
    return ScheduleFacts(
        target=kernel.target,
        family=family,
        num_warps=_int_attr("num_warps", part_warps),
        num_stages=_int_attr("num_stages", pipe_depth),
        pipeline_depth=pipe_depth,
        partition_warps=part_warps,
        block=_int_attr("BLOCK", block),
        block_m=_int_attr("BLOCK_M", block_m),
        block_n=_int_attr("BLOCK_N", block_n),
        block_k=_int_attr("BLOCK_K", block_k),
        n_barrier=len(barriers),
        n_copy=len(copies),
        n_mma=len(mmas),
        isa=isa,
        arch=arch,
    )


def partition_nthreads(width: int) -> int:
    """NVIDIA threads for one partition: ``width`` warps × 32 lanes. Not CuTe."""
    return max(int(width) * 32, 32)


def launch_nthreads(facts: ScheduleFacts) -> int:
    """CUDA block size from summed ``Partition.width``, not ``attrs.num_warps``."""
    return max(facts.partition_warps * 32, 32)


def launch_of(facts: ScheduleFacts) -> dict[str, int]:
    """How to launch the cubin / NPU-bin. Payload, not a cache-key field.

    CUDA: ``<<<grid, block>>>`` with ``block = partition_warps × 32``.
    ``pin.launch.num_warps`` matches that block so serve can run the cubin.
    ``attrs.num_warps`` stays on the Triton sidecar.
    Ascend: year-1 one aicore (``block=1``); ``Partition.width`` is the
    ``block_idx`` predicate, not the launch size.
    """
    if facts.family == "ascend":
        block = 1
        warps = facts.num_warps
    else:
        block = launch_nthreads(facts)
        warps = facts.partition_warps
    return {
        "grid": 1,
        "block": block,
        "num_warps": warps,
        "num_stages": facts.num_stages,
    }


def ident(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in name)
    if not cleaned or cleaned[0].isdigit():
        cleaned = "k_" + cleaned
    return cleaned
