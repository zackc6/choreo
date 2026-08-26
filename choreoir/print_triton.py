from __future__ import annotations

from .ast import Barrier, Copy, Kernel, Mma, Pipeline, Reduce, Yield, flatten_ops
from .knobs import ScheduleFacts, facts_from_kernel, ident


def print_triton(kernel: Kernel, facts: ScheduleFacts | None = None) -> str:
    """NVIDIA GPU sink (Triton). Deterministic. Not an LLM.

    Consumes partition widths (num_warps), Pipeline.depth (tl.range num_stages),
    layouts (BLOCK_*), and Barrier (tl.debug_barrier). Does not emit cubin;
    does not pick WGMMA vs tcgen05. That still needs a named nvcc/triton compile.
    """
    facts = facts or facts_from_kernel(kernel)
    lines: list[str] = [
        f"# Choreo IR → NVIDIA GPU (Triton)  |  kernel {kernel.name!r}  target={kernel.target or 'cuda'!r}",
        f"# @triton.v0 knobs: {facts.as_dict()}",
        "# Sink consumes schedule: BLOCK_* from layout, num_warps from partitions,",
        "# num_stages from Pipeline.depth, tl.debug_barrier from Barrier.",
        "# Not a cubin. Barrier/pipeline are not warp-specialized producer-consumer CUDA.",
    ]
    for p in kernel.partitions:
        lines.append(f"# partition {p.name}: role={p.role} width={p.width}")
    for op in flatten_ops(kernel.body):
        lines.append(f"# {_op_comment(op)}")
    lines += ["", "import triton", "import triton.language as tl", ""]

    copies = [op for op in flatten_ops(kernel.body) if isinstance(op, Copy)]
    mmas = [op for op in flatten_ops(kernel.body) if isinstance(op, Mma)]
    src, dst = _gmem_endpoints(kernel, copies)

    if mmas:
        lines.extend(_gemm_kernel(kernel, mmas[0], facts, dst))
    elif copies and src and dst:
        lines.extend(_copy_kernel(kernel, copies[0], facts, src, dst))
    elif copies:
        lines.extend(_copy_kernel(kernel, copies[0], facts, copies[0].src, copies[0].dst))
    else:
        lines.append(f"# no Copy/Mma in {kernel.name}; nothing to lower")

    return "\n".join(lines) + "\n"


def _op_comment(op: object) -> str:
    if isinstance(op, Copy):
        return f"copy {op.id}: {op.src} -> {op.dst} @{op.partition}"
    if isinstance(op, Mma):
        return f"mma {op.id}: {op.c} += {op.a} @ {op.b} @{op.partition}"
    if isinstance(op, Reduce):
        return f"reduce {op.id}: {op.src} -axis{op.axis}-> {op.dst} @{op.partition}"
    if isinstance(op, Barrier):
        waits = ",".join(op.wait_for)
        return f"barrier {op.id}: wait {waits} arrive {op.arrive}"
    if isinstance(op, Pipeline):
        return f"pipeline {op.id}: depth={op.depth}"
    if isinstance(op, Yield):
        return f"yield {op.id}: {','.join(op.values)}"
    return type(op).__name__


def _gmem_endpoints(kernel: Kernel, copies: list[Copy]) -> tuple[str | None, str | None]:
    """M2 copy/gemm IO is gmem endpoints (yielded outputs), not the smem tile."""
    del copies
    yielded: list[str] = []
    for op in flatten_ops(kernel.body):
        if isinstance(op, Yield):
            yielded.extend(op.values)
    gmem_out = [
        n
        for n in yielded
        if (b := kernel.buffer(n)) is not None and b.space == "gmem"
    ]
    gmem_in = [
        b.name
        for b in kernel.buffers
        if b.space == "gmem" and b.name not in set(gmem_out)
    ]
    src = gmem_in[0] if gmem_in else None
    dst = gmem_out[0] if gmem_out else None
    return src, dst


def _copy_kernel(
    kernel: Kernel, op: Copy, facts: ScheduleFacts, src_name: str, dst_name: str
) -> list[str]:
    src = kernel.buffer(src_name) or kernel.buffer(op.src)
    n = src.layout.numel() if src else 0
    fn = ident(kernel.name)
    return [
        f"@triton.jit",
        f"def {fn}(src_ptr, dst_ptr, n, BLOCK: tl.constexpr = {facts.block}):",
        f"    # numel from layout of {src_name}: {n}; first Copy {op.id} {op.src}->{op.dst}",
        f"    # M2 IO {src_name} -> {dst_name}; launch knob num_warps={facts.num_warps}",
        "    pid = tl.program_id(0)",
        "    offs = pid * BLOCK + tl.arange(0, BLOCK)",
        "    mask = offs < n",
        "    x = tl.load(src_ptr + offs, mask=mask)",
        "    tl.store(dst_ptr + offs, x, mask=mask)",
    ]


def _gemm_kernel(
    kernel: Kernel, op: Mma, facts: ScheduleFacts, out_name: str | None
) -> list[str]:
    fn = ident(kernel.name)
    stages = facts.num_stages
    barrier_line = (
        "        tl.debug_barrier()  # Choreo Barrier: cross-partition handoff"
        if facts.n_barrier
        else None
    )
    loop = f"    for k in tl.range(0, tl.cdiv(K, BLOCK_K), num_stages={stages}):"
    body = [
        f"@triton.jit",
        (
            f"def {fn}(a_ptr, b_ptr, c_ptr, M, N, K, stride_am, stride_ak, stride_bk, "
            f"stride_bn, stride_cm, stride_cn, BLOCK_M: tl.constexpr = {facts.block_m}, "
            f"BLOCK_N: tl.constexpr = {facts.block_n}, BLOCK_K: tl.constexpr = {facts.block_k}):"
        ),
        (
            f"    # tile from Choreo layouts: M={facts.block_m} K={facts.block_k} N={facts.block_n}; "
            f"Mma {op.id}; store {out_name or op.c}; launch num_warps={facts.num_warps}"
        ),
        "    pid_m = tl.program_id(0)",
        "    pid_n = tl.program_id(1)",
        "    offs_m = pid_m * BLOCK_M + tl.arange(0, BLOCK_M)",
        "    offs_n = pid_n * BLOCK_N + tl.arange(0, BLOCK_N)",
        "    offs_k = tl.arange(0, BLOCK_K)",
        "    a_ptrs = a_ptr + offs_m[:, None] * stride_am + offs_k[None, :] * stride_ak",
        "    b_ptrs = b_ptr + offs_k[:, None] * stride_bk + offs_n[None, :] * stride_bn",
        "    acc = tl.zeros((BLOCK_M, BLOCK_N), dtype=tl.float32)",
        loop,
        "        k_remaining = K - k * BLOCK_K",
        "        a = tl.load(a_ptrs, mask=(offs_m[:, None] < M) & (offs_k[None, :] < k_remaining), other=0.0)",
        "        b = tl.load(b_ptrs, mask=(offs_k[:, None] < k_remaining) & (offs_n[None, :] < N), other=0.0)",
    ]
    if barrier_line:
        body.append(barrier_line)
    body.extend(
        [
            "        acc += tl.dot(a, b)",
            "        a_ptrs += BLOCK_K * stride_ak",
            "        b_ptrs += BLOCK_K * stride_bk",
            "    c_ptrs = c_ptr + offs_m[:, None] * stride_cm + offs_n[None, :] * stride_cn",
            "    tl.store(c_ptrs, acc, mask=(offs_m[:, None] < M) & (offs_n[None, :] < N))",
        ]
    )
    return body
