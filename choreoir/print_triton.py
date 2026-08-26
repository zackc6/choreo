from __future__ import annotations

from .ast import Barrier, Buffer, Copy, Kernel, Mma, Pipeline, Reduce, Yield, flatten_ops
from .knobs import ScheduleFacts, facts_from_kernel, ident


def print_triton(kernel: Kernel, facts: ScheduleFacts | None = None) -> str:
    """NVIDIA M2 sidecar (Triton knobs). Deterministic. Not an LLM. Not a cubin.

    Walks Copy / Barrier / Pipeline / Mma like ``print_cuda``. Knobs
    (``BLOCK_*``, ``num_warps``, ``num_stages``) stay the M2 kill switch if
    the cubin path is withdrawn. Does not pick WGMMA vs ``tcgen05``.
    """
    facts = facts or facts_from_kernel(kernel)
    lines: list[str] = [
        f"# Choreo IR → NVIDIA GPU (Triton sidecar)  |  kernel {kernel.name!r}  target={kernel.target or 'cuda'!r}",
        f"# @triton.v0 knobs: {facts.as_dict()}",
        "# Walk consumes schedule: Copy→tl.load/store, Barrier→tl.debug_barrier,",
        "# Pipeline.depth→tl.range(num_stages=depth), Mma→tl.dot, layouts→BLOCK_*,",
        "# partitions→num_warps on the launch helper (M2 knob, not a cubin).",
        "# Not a cubin. Not warp-specialized producer-consumer CUDA.",
    ]
    for p in kernel.partitions:
        lines.append(f"# partition {p.name}: role={p.role} width={p.width}")
    for op in flatten_ops(kernel.body):
        lines.append(f"# {_op_comment(op)}")
    lines += ["", "import triton", "import triton.language as tl", ""]
    lines.extend(_kernel_def(kernel, facts))
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


def _kernel_def(kernel: Kernel, facts: ScheduleFacts) -> list[str]:
    fn = ident(kernel.name)
    gmem = [b for b in kernel.buffers if b.space == "gmem"]
    ptrs = ", ".join(f"{ident(b.name)}_ptr" for b in gmem) or "src_ptr, dst_ptr"
    lines = [
        "@triton.jit",
        (
            f"def {fn}({ptrs}, n, M, N, K, "
            f"BLOCK: tl.constexpr = {facts.block}, "
            f"BLOCK_M: tl.constexpr = {facts.block_m}, "
            f"BLOCK_N: tl.constexpr = {facts.block_n}, "
            f"BLOCK_K: tl.constexpr = {facts.block_k}):"
        ),
        f"    # launch knob num_warps={facts.num_warps} num_stages={facts.num_stages} isa={facts.isa}",
    ]
    if not kernel.body:
        lines.append(f"    # no Copy/Mma in {kernel.name}; nothing to lower")
        return lines
    lines.extend(_emit_ops(kernel.body, "    ", kernel, facts))
    lines.append("")
    lines.append(f"def {fn}_launch({ptrs}, n, M, N, K):")
    lines.append(
        f"    {fn}[(1,)]({ptrs}, n, M, N, K, "
        f"num_warps={facts.num_warps}, num_stages={facts.num_stages})"
    )
    return lines


def _emit_ops(
    ops: tuple[object, ...] | list[object],
    indent: str,
    kernel: Kernel,
    facts: ScheduleFacts,
) -> list[str]:
    lines: list[str] = []
    for op in ops:
        if isinstance(op, Pipeline):
            lines.append(
                f"{indent}for _stage in tl.range(0, {op.depth}, num_stages={op.depth}):  # {op.id}"
            )
            lines.extend(_emit_ops(op.body, indent + "    ", kernel, facts))
        elif isinstance(op, Copy):
            lines.extend(_emit_copy(op, indent, kernel, facts))
        elif isinstance(op, Barrier):
            waits = ",".join(op.wait_for)
            part = kernel.partition(op.arrive)
            role = part.role if part else "?"
            lines.append(
                f"{indent}tl.debug_barrier()  # {op.id} wait {waits} arrive {op.arrive} role={role}"
            )
        elif isinstance(op, Mma):
            lines.extend(_emit_mma(op, indent, kernel, facts))
        elif isinstance(op, Reduce):
            lines.append(
                f"{indent}{ident(op.dst)} = tl.sum({ident(op.src)}, axis={op.axis})  # {op.id} @{op.partition}"
            )
        elif isinstance(op, Yield):
            lines.append(f"{indent}# yield {op.id}: {','.join(op.values)}")
    return lines


def _emit_copy(op: Copy, indent: str, kernel: Kernel, facts: ScheduleFacts) -> list[str]:
    del facts
    src, dst = kernel.buffer(op.src), kernel.buffer(op.dst)
    part = kernel.partition(op.partition)
    role = part.role if part else "?"
    n = dst.layout.numel() if dst else 0
    src_sp = src.space if src else "?"
    dst_sp = dst.space if dst else "?"
    src_ref = _ptr_or_name(op.src, src)
    dst_ref = _ptr_or_name(op.dst, dst)
    return [
        f"{indent}# copy {op.id} {op.src}({src_sp})->{op.dst}({dst_sp}) @{op.partition} role={role} numel={n}",
        f"{indent}offs_{op.id} = tl.arange(0, BLOCK)",
        f"{indent}mask_{op.id} = offs_{op.id} < {n}",
        f"{indent}x_{op.id} = tl.load({src_ref} + offs_{op.id}, mask=mask_{op.id})",
        f"{indent}tl.store({dst_ref} + offs_{op.id}, x_{op.id}, mask=mask_{op.id})",
    ]


def _emit_mma(op: Mma, indent: str, kernel: Kernel, facts: ScheduleFacts) -> list[str]:
    part = kernel.partition(op.partition)
    role = part.role if part else "?"
    a = kernel.buffer(op.a)
    b = kernel.buffer(op.b)
    c = kernel.buffer(op.c)
    a_ptr = _ptr_or_name(op.a, a)
    b_ptr = _ptr_or_name(op.b, b)
    c_ptr = _ptr_or_name(op.c, c)
    stages = facts.num_stages
    return [
        f"{indent}# mma {op.id} {op.c} += {op.a}@{op.b} isa={facts.isa} @{op.partition} role={role}",
        f"{indent}offs_m = tl.arange(0, BLOCK_M)",
        f"{indent}offs_n = tl.arange(0, BLOCK_N)",
        f"{indent}offs_k = tl.arange(0, BLOCK_K)",
        f"{indent}a_ptrs = {a_ptr} + offs_m[:, None] * BLOCK_K + offs_k[None, :]",
        f"{indent}b_ptrs = {b_ptr} + offs_k[:, None] * BLOCK_N + offs_n[None, :]",
        f"{indent}acc = tl.zeros((BLOCK_M, BLOCK_N), dtype=tl.float32)",
        f"{indent}for k in tl.range(0, tl.cdiv(K, BLOCK_K), num_stages={stages}):",
        f"{indent}    k_remaining = K - k * BLOCK_K",
        f"{indent}    a = tl.load(a_ptrs, mask=(offs_k[None, :] < k_remaining), other=0.0)",
        f"{indent}    b = tl.load(b_ptrs, mask=(offs_k[:, None] < k_remaining), other=0.0)",
        f"{indent}    acc += tl.dot(a, b)",
        f"{indent}    a_ptrs += BLOCK_K",
        f"{indent}    b_ptrs += BLOCK_K",
        f"{indent}tl.store({c_ptr} + offs_m[:, None] * BLOCK_N + offs_n[None, :], acc)",
    ]


def _ptr_or_name(name: str, buf: Buffer | None) -> str:
    if buf is not None and buf.space == "gmem":
        return f"{ident(name)}_ptr"
    return ident(name)
