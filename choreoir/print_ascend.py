"""Ascend NPU sink (TileLang-shaped). Deterministic. Not an LLM. Not CANN in the pin."""

from __future__ import annotations

from .ast import Barrier, Buffer, Copy, Kernel, Mma, Pipeline, Reduce, Yield
from .knobs import ScheduleFacts, facts_from_kernel, ident

_DTYPE = {"f16": "float16", "bf16": "bfloat16", "f32": "float32", "f8": "float8"}


def print_ascend(kernel: Kernel, facts: ScheduleFacts | None = None) -> str:
    """Lower Copy/Mma/Barrier/Pipeline onto TileLang-Ascend primitives.

    Space map (target-indexed, not a unified onchip enum):
      gmem→GM, smem→L1, tmem→L0C, regs→UB (mma accumulator → L0C).
    Role map: load→MTE copy, math→Cube gemm.
    Pipeline.depth → T.Pipelined(..., num_stages=depth).
    Barrier → T.pipe_barrier after producer copies.
    Does not emit an NPU bin; does not pin CANN/TileLang.
    """
    facts = facts or facts_from_kernel(kernel)
    fn = ident(kernel.name)
    gmem = [b for b in kernel.buffers if b.space == "gmem"]
    sig = ", ".join(
        f"{b.name}: T.Buffer({list(b.layout.shape)}, {_DTYPE.get(b.dtype, 'float16')!r})"
        for b in gmem
    )
    lines: list[str] = [
        f"# Choreo IR → Ascend NPU (TileLang)  |  kernel {kernel.name!r}  target={kernel.target!r}",
        f"# knobs: {facts.as_dict()}",
        "# space: gmem→GM, smem→L1, tmem→L0C, regs→UB (mma C → L0C)",
        "# role: load→MTE T.copy, math→Cube T.gemm, store→MTE T.copy to GM",
        "# Not an NPU bin. Device compile is CANN/TileLang outside this pin.",
        "",
        "import tilelang.language as T",
        "",
        "@T.prim_func",
        f"def {fn}({sig}):",
        "    with T.Kernel(1, is_npu=True):",
    ]
    for b in kernel.buffers:
        alloc = _alloc_line(b, kernel)
        if alloc:
            lines.append(f"        {alloc}")
    lines.extend(_emit_ops(kernel.body, "        ", kernel, facts))
    return "\n".join(lines) + "\n"


def _alloc_line(buf: Buffer, kernel: Kernel) -> str | None:
    if buf.space == "gmem":
        return None
    shape = list(buf.layout.shape)
    dt = _DTYPE.get(buf.dtype, "float16")
    kind = _npu_alloc(buf, kernel)
    return f"{buf.name} = T.{kind}({shape}, {dt!r})  # Choreo space={buf.space}"


def _npu_alloc(buf: Buffer, kernel: Kernel) -> str:
    mma_cs = {
        op.c
        for op in _walk(kernel.body)
        if isinstance(op, Mma)
    }
    if buf.name in mma_cs or buf.space == "tmem":
        return "alloc_L0C"
    if buf.space == "smem":
        return "alloc_L1"
    return "alloc_ub"


def _space_label(buf: Buffer, kernel: Kernel) -> str:
    if buf.space == "gmem":
        return "GM"
    kind = _npu_alloc(buf, kernel)
    return {"alloc_L0C": "L0C", "alloc_L1": "L1", "alloc_ub": "UB"}.get(kind, buf.space)


def _walk(ops: tuple[object, ...] | list[object]) -> list[object]:
    out: list[object] = []
    for op in ops:
        out.append(op)
        if isinstance(op, Pipeline):
            out.extend(_walk(op.body))
    return out


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
                f"{indent}for _k in T.Pipelined(1, num_stages={op.depth}):  # {op.id}"
            )
            lines.extend(_emit_ops(op.body, indent + "    ", kernel, facts))
        elif isinstance(op, Copy):
            part = kernel.partition(op.partition)
            role = part.role if part else "load"
            src_b, dst_b = kernel.buffer(op.src), kernel.buffer(op.dst)
            src_sp = _space_label(src_b, kernel) if src_b else "?"
            dst_sp = _space_label(dst_b, kernel) if dst_b else "?"
            lines.append(
                f"{indent}T.copy({op.src}, {op.dst})  # {op.id} {src_sp}->{dst_sp} "
                f"MTE @{op.partition} role={role}"
            )
        elif isinstance(op, Mma):
            part = kernel.partition(op.partition)
            role = part.role if part else "math"
            lines.append(f"{indent}with T.Scope('C'):  # Cube @{op.partition} role={role}")
            lines.append(f"{indent}    T.gemm({op.a}, {op.b}, {op.c})  # {op.id}")
        elif isinstance(op, Barrier):
            waits = ",".join(op.wait_for)
            lines.append(
                f"{indent}T.pipe_barrier('PIPE_ALL')  # {op.id} wait {waits} arrive {op.arrive}"
            )
        elif isinstance(op, Reduce):
            lines.append(
                f"{indent}T.reduce_sum({op.src}, {op.dst}, axis={op.axis})  # {op.id}"
            )
        elif isinstance(op, Yield):
            lines.append(f"{indent}# yield {op.id}: {','.join(op.values)}")
    if not any(isinstance(op, Pipeline) for op in ops) and facts.num_stages > 1:
        # depth came from attrs; wrap nothing extra
        pass
    return lines
