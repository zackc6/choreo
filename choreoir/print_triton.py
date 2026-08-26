from __future__ import annotations

from .ast import Barrier, Copy, Kernel, Mma, Pipeline, Reduce, Yield, flatten_ops


def print_triton(kernel: Kernel) -> str:
    """Pretty-print a Triton snippet for copy and GEMM-tile kernels.

    This is a deterministic printer of the AST, not a compiler and not an
    LLM. Generated code is a starting sketch keyed off layouts and partitions.
    """
    lines: list[str] = [
        f"# Choreo IR → Triton  |  kernel {kernel.name!r}",
        "# Not an execution compiler. Layout/sync admit must pass before use.",
    ]
    for p in kernel.partitions:
        lines.append(f"# partition {p.name}: role={p.role} width={p.width}")
    for op in flatten_ops(kernel.body):
        lines.append(f"# { _op_comment(op)}")
    lines += ["", "import triton", "import triton.language as tl", ""]

    copies = [op for op in flatten_ops(kernel.body) if isinstance(op, Copy)]
    mmas = [op for op in flatten_ops(kernel.body) if isinstance(op, Mma)]

    if mmas:
        lines.extend(_gemm_kernel(kernel, mmas[0]))
    elif copies:
        lines.extend(_copy_kernel(kernel, copies[0]))
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


def _copy_kernel(kernel: Kernel, op: Copy) -> list[str]:
    src = kernel.buffer(op.src)
    n = src.layout.numel() if src else 0
    fn = _ident(kernel.name)
    return [
        "@triton.jit",
        f"def {fn}(src_ptr, dst_ptr, n, BLOCK: tl.constexpr):",
        f"    # numel from layout of {op.src}: {n}",
        "    pid = tl.program_id(0)",
        "    offs = pid * BLOCK + tl.arange(0, BLOCK)",
        "    mask = offs < n",
        "    x = tl.load(src_ptr + offs, mask=mask)",
        "    tl.store(dst_ptr + offs, x, mask=mask)",
    ]


def _gemm_kernel(kernel: Kernel, op: Mma) -> list[str]:
    a = kernel.buffer(op.a)
    b = kernel.buffer(op.b)
    m = a.layout.shape[0] if a and len(a.layout.shape) == 2 else 16
    k = a.layout.shape[1] if a and len(a.layout.shape) == 2 else 16
    n = b.layout.shape[1] if b and len(b.layout.shape) == 2 else 16
    fn = _ident(kernel.name)
    return [
        "@triton.jit",
        f"def {fn}(a_ptr, b_ptr, c_ptr, M, N, K, stride_am, stride_ak, stride_bk, stride_bn, stride_cm, stride_cn, BLOCK_M: tl.constexpr, BLOCK_N: tl.constexpr, BLOCK_K: tl.constexpr):",
        f"    # tile hint from Choreo layouts: M={m} K={k} N={n}",
        "    pid_m = tl.program_id(0)",
        "    pid_n = tl.program_id(1)",
        "    offs_m = pid_m * BLOCK_M + tl.arange(0, BLOCK_M)",
        "    offs_n = pid_n * BLOCK_N + tl.arange(0, BLOCK_N)",
        "    offs_k = tl.arange(0, BLOCK_K)",
        "    a_ptrs = a_ptr + offs_m[:, None] * stride_am + offs_k[None, :] * stride_ak",
        "    b_ptrs = b_ptr + offs_k[:, None] * stride_bk + offs_n[None, :] * stride_bn",
        "    acc = tl.zeros((BLOCK_M, BLOCK_N), dtype=tl.float32)",
        "    for k in range(0, tl.cdiv(K, BLOCK_K)):",
        "        k_remaining = K - k * BLOCK_K",
        "        a = tl.load(a_ptrs, mask=(offs_m[:, None] < M) & (offs_k[None, :] < k_remaining), other=0.0)",
        "        b = tl.load(b_ptrs, mask=(offs_k[:, None] < k_remaining) & (offs_n[None, :] < N), other=0.0)",
        "        acc += tl.dot(a, b)",
        "        a_ptrs += BLOCK_K * stride_ak",
        "        b_ptrs += BLOCK_K * stride_bk",
        "    c_ptrs = c_ptr + offs_m[:, None] * stride_cm + offs_n[None, :] * stride_cn",
        "    tl.store(c_ptrs, acc, mask=(offs_m[:, None] < M) & (offs_n[None, :] < N))",
    ]


def _ident(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in name)
    if not cleaned or cleaned[0].isdigit():
        cleaned = "k_" + cleaned
    return cleaned
