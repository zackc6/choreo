"""Ascend CCE sink — the NPU-bin-bound path. Walks Copy/Barrier/Mma/Pipeline.

Official `ccec --cce-aicore-only -c` turns this into an elf64-hiipu relocatable
when the toolchain is present. Not a homemade Davinci object. Not L5 ISA.
Onchip buffers are UB pointer stand-ins (like CUDA mapping every dtype to float):
this `ccec` object accepts GM↔UB copies and UB vector ops, not L1/cube mad.
Copy/Barrier/Pipeline/Mma/Reduce still consume the schedule. Cube mad is later L5.
TileLang is the sidecar.
"""

from __future__ import annotations

from .ast import Barrier, Buffer, Copy, Kernel, Mma, Pipeline, Reduce, Yield
from .knobs import ScheduleFacts, facts_from_kernel, ident

# Stand-in C type so ccec can assemble without half/bfloat headers. Real dtype
# is kept in comments. Burst lengths use this width (32B units).
_C_DTYPE = "float"
_ELEM_BYTES = 4
_ALIGN = 256


def print_ascendc(kernel: Kernel, facts: ScheduleFacts | None = None) -> str:
    """Emit CCE that consumes the Choreo schedule.

    gmem → __gm__, Copy → copy_gm_to_ubuf / copy_ubuf_to_gm (burst from layout),
    Barrier → pipe_barrier(PIPE_ALL), Pipeline.depth → staged loop **and**
    staged UB span for smem (CUDA stages ``__shared__[depth]``),
    Partition.width → ``block_idx < width`` (year-1 launch is one aicore so
    core 0 always runs), Mma → named cube.mmad plus M/N/K loops and a UB
    ``vmadd`` fallback indexed by layout stride (cube mad is later L5 /
    cube-capable arch), Reduce → nested loops over ``axis`` plus UB
    ``vector_dup`` / ``vadd`` (scalar ``+=`` is not an aicore op).
    """
    facts = facts or facts_from_kernel(kernel)
    fn = ident(kernel.name)
    gmem = [b for b in kernel.buffers if b.space == "gmem"]
    args = ", ".join(
        f"const __gm__ {_C_DTYPE}* {b.name} /* {b.dtype} */"
        if _is_readonly(b, kernel)
        else f"__gm__ {_C_DTYPE}* {b.name} /* {b.dtype} */"
        for b in gmem
    )
    if not args:
        args = "void"
    bases = _onchip_bases(kernel, facts)
    lines = [
        f"// Choreo IR → Ascend NPU-bin path  |  kernel {kernel.name!r}  target={kernel.target!r}",
        f"// isa={facts.isa} arch={facts.arch} num_warps={facts.num_warps} num_stages={facts.num_stages}",
        "// partition width → block_idx predicate (core 0 always participates when width>=1)",
        "// Pipeline.depth → staged UB span for smem (CUDA stages __shared__[depth])",
        "// spaces: gmem→__gm__, smem→L1 (UB stand-in), tmem/mma C→L0C (UB stand-in), else UB",
        "// dtypes lowered as float stand-in so ccec needs no half headers (not L5 ISA)",
        "",
        f'extern "C" __global__ __aicore__ void {fn}({args}) {{',
    ]
    for b in kernel.buffers:
        if b.space == "gmem":
            continue
        base = bases[b.name]
        label = _space_label(b, kernel)
        stage_note = ""
        if facts.num_stages > 1 and b.space == "smem":
            stage_note = f"  pipeline stages={facts.num_stages} span={_stage_span_elems(b)}"
        lines.append(
            f"  __ubuf__ {_C_DTYPE}* {b.name} = (__ubuf__ {_C_DTYPE}*){base};"
            f"  // Choreo space={b.space} → {label} stand-in UB base {base}"
            f"  dtype={b.dtype} numel={b.layout.numel()}{stage_note}"
        )
    lines.extend(_emit_ops(kernel.body, "  ", kernel, facts, bases))
    lines.append("}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _is_readonly(buf: Buffer, kernel: Kernel) -> bool:
    for op in _walk(kernel.body):
        if isinstance(op, Copy) and op.dst == buf.name:
            return False
        if isinstance(op, Mma) and op.c == buf.name:
            return False
        if isinstance(op, Reduce) and op.dst == buf.name:
            return False
    return True


def _align_bytes(nbytes: int) -> int:
    return ((nbytes + _ALIGN - 1) // _ALIGN) * _ALIGN


def _stage_span_elems(buf: Buffer) -> int:
    """Elements in one pipeline stage slot (256B-aligned)."""
    nbytes = max(buf.layout.numel() * _ELEM_BYTES, 32)
    return _align_bytes(nbytes) // _ELEM_BYTES


def _onchip_bases(kernel: Kernel, facts: ScheduleFacts) -> dict[str, int]:
    bases: dict[str, int] = {}
    off = 0
    stages = max(facts.num_stages, 1)
    for buf in kernel.buffers:
        if buf.space == "gmem":
            continue
        bases[buf.name] = off
        nbytes = max(buf.layout.numel() * _ELEM_BYTES, 32)
        aligned = _align_bytes(nbytes)
        if buf.space == "smem" and stages > 1:
            off += aligned * stages
        else:
            off += aligned
    return bases


def _ub_ptr(name: str, kernel: Kernel, facts: ScheduleFacts) -> str:
    """smem pointer, staged by ``_stage`` when Pipeline.depth > 1. Matches CUDA."""
    buf = kernel.buffer(name)
    if buf is None:
        return name
    if facts.num_stages > 1 and buf.space == "smem":
        return f"({name} + _stage * {_stage_span_elems(buf)})"
    return name


def _ub_at(name: str, kernel: Kernel, facts: ScheduleFacts, off: str) -> str:
    """UB pointer plus a layout offset (Mma/Reduce). ``off==0`` is the base."""
    base = _ub_ptr(name, kernel, facts)
    if off == "0":
        return base
    return f"({base} + {off})"


def _space_label(buf: Buffer, kernel: Kernel) -> str:
    if buf.space == "gmem":
        return "GM"
    mma_cs = {op.c for op in _walk(kernel.body) if isinstance(op, Mma)}
    if buf.name in mma_cs or buf.space == "tmem":
        return "L0C"
    if buf.space == "smem":
        return "L1"
    return "UB"


def _walk(ops: tuple[object, ...] | list[object]) -> list[object]:
    out: list[object] = []
    for op in ops:
        out.append(op)
        if isinstance(op, Pipeline):
            out.extend(_walk(op.body))
    return out


def _len_burst(buf: Buffer) -> int:
    nbytes = buf.layout.numel() * _ELEM_BYTES
    return max(1, (nbytes + 31) // 32)


def _wrap_width(inner: list[str], part_name: str, kernel: Kernel, indent: str) -> list[str]:
    part = kernel.partition(part_name)
    w = part.width if part else 1
    return [
        f"{indent}if (block_idx < {w}) {{  // partition {part_name} width={w}",
        *inner,
        f"{indent}}}",
    ]


def _emit_ops(
    ops: tuple[object, ...] | list[object],
    indent: str,
    kernel: Kernel,
    facts: ScheduleFacts,
    bases: dict[str, int],
) -> list[str]:
    lines: list[str] = []
    for op in ops:
        if isinstance(op, Pipeline):
            lines.append(f"{indent}// pipeline {op.id} depth={op.depth}")
            lines.append(f"{indent}for (int _stage = 0; _stage < {op.depth}; ++_stage) {{")
            lines.extend(_emit_ops(op.body, indent + "  ", kernel, facts, bases))
            lines.append(f"{indent}}}")
        elif isinstance(op, Copy):
            lines.extend(
                _wrap_width(
                    _emit_copy(op, indent + "  ", kernel, facts), op.partition, kernel, indent
                )
            )
        elif isinstance(op, Barrier):
            waits = ",".join(op.wait_for)
            part = kernel.partition(op.arrive)
            role = part.role if part else "?"
            lines.append(
                f"{indent}pipe_barrier(PIPE_ALL);  // {op.id} wait {waits} "
                f"arrive {op.arrive} role={role}"
            )
        elif isinstance(op, Mma):
            lines.extend(_wrap_width(_emit_mma(op, indent + "  ", kernel, facts), op.partition, kernel, indent))
        elif isinstance(op, Reduce):
            lines.extend(
                _wrap_width(
                    _emit_reduce(op, indent + "  ", kernel, facts), op.partition, kernel, indent
                )
            )
        elif isinstance(op, Yield):
            lines.append(f"{indent}// yield {op.id}: {','.join(op.values)}")
    return lines


def _emit_copy(op: Copy, indent: str, kernel: Kernel, facts: ScheduleFacts) -> list[str]:
    src, dst = kernel.buffer(op.src), kernel.buffer(op.dst)
    if src is None or dst is None:
        return [f"{indent}// copy {op.id} missing buffer"]
    part = kernel.partition(op.partition)
    role = part.role if part else "?"
    src_sp = _space_label(src, kernel)
    dst_sp = _space_label(dst, kernel)
    burst = _len_burst(dst)
    src_p = _ub_ptr(op.src, kernel, facts)
    dst_p = _ub_ptr(op.dst, kernel, facts)
    note = (
        f"{indent}// copy {op.id} {op.src}({src.space}/{src_sp})->"
        f"{op.dst}({dst.space}/{dst_sp}) @{op.partition} role={role} "
        f"nBurst=1 lenBurst={burst} (32B)"
    )
    src_g = src.space == "gmem"
    dst_g = dst.space == "gmem"
    if src_g and not dst_g:
        call = (
            f"{indent}copy_gm_to_ubuf((__ubuf__ void*){dst_p}, (__gm__ void*){src.name}, "
            f"0, 1, {burst}, 0, 0);"
        )
    elif dst_g and not src_g:
        call = (
            f"{indent}copy_ubuf_to_gm((__gm__ void*){dst.name}, (__ubuf__ void*){src_p}, "
            f"0, 1, {burst}, 0, 0);"
        )
    elif not src_g and not dst_g:
        call = (
            f"{indent}copy_ubuf_to_ubuf((__ubuf__ void*){dst_p}, (__ubuf__ void*){src_p}, "
            f"0, 1, {burst}, 0, 0);"
        )
    else:
        return [note, f"{indent}// gmem→gmem copy not lowered in v0.1 cce sink"]
    return [note, call]


def _emit_mma(op: Mma, indent: str, kernel: Kernel, facts: ScheduleFacts) -> list[str]:
    a, b, c = kernel.buffer(op.a), kernel.buffer(op.b), kernel.buffer(op.c)
    part = kernel.partition(op.partition)
    role = part.role if part else "?"
    if not (a and b and c) or len(a.layout.shape) != 2:
        return [f"{indent}// mma {op.id} shape error"]
    m, k = a.layout.shape
    n = b.layout.shape[1] if len(b.layout.shape) == 2 else 1
    a_sp = _space_label(a, kernel)
    b_sp = _space_label(b, kernel)
    c_sp = _space_label(c, kernel)
    a_off = _lin(a, ["i", "kk"])
    b_off = _lin(b, ["kk", "j"])
    c_off = _lin(c, ["i", "j"])
    return [
        f"{indent}// mma {op.id} {op.c} += {op.a}@{op.b}  isa={facts.isa} "
        f"M={m} K={k} N={n} @{op.partition} role={role} "
        f"{a_sp}@{b_sp}->{c_sp}",
        f"{indent}// cube mad needs later L5 / cube-capable arch; UB vmadd fallback",
        f"{indent}// layout stride → element address (CUDA scalar MAC does the same)",
        f"{indent}for (int i = 0; i < {m}; ++i) {{",
        f"{indent}  for (int j = 0; j < {n}; ++j) {{",
        f"{indent}    for (int kk = 0; kk < {k}; ++kk) {{",
        f"{indent}      vmadd({_ub_at(op.c, kernel, facts, c_off)}, "
        f"{_ub_at(op.a, kernel, facts, a_off)}, "
        f"{_ub_at(op.b, kernel, facts, b_off)}, 1);",
        f"{indent}    }}",
        f"{indent}  }}",
        f"{indent}}}",
    ]


def _lin(buf: Buffer, names: list[str]) -> str:
    parts: list[str] = []
    for nm, s in zip(names, buf.layout.stride):
        parts.append(nm if s == 1 else f"{nm} * {s}")
    return " + ".join(parts) or "0"


def _cce_loops(names: list[str], extents: tuple[int, ...], indent: str, body: str) -> list[str]:
    if not names:
        return [f"{indent}{body}"]
    lines: list[str] = []
    for d, (n, nm) in enumerate(zip(extents, names)):
        lines.append(f"{indent}{'  ' * d}for (int {nm} = 0; {nm} < {n}; ++{nm}) {{")
    lines.append(f"{indent}{'  ' * len(names)}{body}")
    for d in range(len(names) - 1, -1, -1):
        lines.append(f"{indent}{'  ' * d}}}")
    return lines


def _emit_reduce(op: Reduce, indent: str, kernel: Kernel, facts: ScheduleFacts) -> list[str]:
    src, dst = kernel.buffer(op.src), kernel.buffer(op.dst)
    part = kernel.partition(op.partition)
    role = part.role if part else "?"
    if src is None or dst is None:
        return [f"{indent}// reduce {op.id} missing buffer"]
    src_names = [f"rs{d}" for d in range(len(src.layout.shape))]
    dst_from_src = [src_names[d] for d in range(len(src.layout.shape)) if d != op.axis]
    dst_off = _lin(dst, dst_from_src)
    src_off = _lin(src, src_names)
    src_p = _ub_ptr(op.src, kernel, facts)
    dst_p = _ub_ptr(op.dst, kernel, facts)
    lines = [
        f"{indent}// reduce {op.id} {op.src}-axis{op.axis}->{op.dst} @{op.partition} role={role}",
        f"{indent}// aicore forbids scalar +=; UB vector_dup/vadd fallback (not L5 ISA)",
        f"{indent}vector_dup({dst_p}, 0.f, 1);",
    ]
    lines.extend(
        _cce_loops(
            src_names,
            src.layout.shape,
            indent,
            f"vadd({dst_p} + {dst_off}, {dst_p} + {dst_off}, {src_p} + {src_off}, 1);",
        )
    )
    return lines
