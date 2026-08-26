"""Schedule facts consumed by NV GPU and Ascend NPU sinks."""

from __future__ import annotations

from dataclasses import dataclass

from .ast import Barrier, Copy, Kernel, Mma, Pipeline, flatten_ops

YEAR1_KERNELS = frozenset({"copy", "gemm_tile"})


@dataclass(frozen=True)
class ScheduleFacts:
    """Inputs to codegen. Kind-2 knobs plus what the sinks must consume."""

    target: str
    family: str  # cuda | ascend
    num_warps: int
    num_stages: int
    block: int
    block_m: int
    block_n: int
    block_k: int
    n_barrier: int
    n_copy: int
    n_mma: int

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
        }


def target_family(target: str) -> str | None:
    t = target.strip()
    if t == "cuda" or t.startswith("cuda-"):
        return "cuda"
    if t == "ascend" or t.startswith("ascend"):
        return "ascend"
    return None


def facts_from_kernel(kernel: Kernel) -> ScheduleFacts:
    ops = flatten_ops(kernel.body)
    pipes = [op for op in ops if isinstance(op, Pipeline)]
    copies = [op for op in ops if isinstance(op, Copy)]
    mmas = [op for op in ops if isinstance(op, Mma)]
    barriers = [op for op in ops if isinstance(op, Barrier)]

    num_stages = max((p.depth for p in pipes), default=1)
    num_warps = sum(p.width for p in kernel.partitions) if kernel.partitions else 4

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
    return ScheduleFacts(
        target=kernel.target,
        family=family,
        num_warps=_int_attr("num_warps", num_warps),
        num_stages=_int_attr("num_stages", num_stages),
        block=_int_attr("BLOCK", block),
        block_m=_int_attr("BLOCK_M", block_m),
        block_n=_int_attr("BLOCK_N", block_n),
        block_k=_int_attr("BLOCK_K", block_k),
        n_barrier=len(barriers),
        n_copy=len(copies),
        n_mma=len(mmas),
    )


def ident(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in name)
    if not cleaned or cleaned[0].isdigit():
        cleaned = "k_" + cleaned
    return cleaned
