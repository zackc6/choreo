"""NVIDIA CUDA C++ sink — the cubin-bound path. Walks Copy/Barrier/Mma/Pipeline."""

from __future__ import annotations

from .ast import Barrier, Buffer, Copy, Kernel, Mma, Pipeline, Reduce, Yield
from .knobs import ScheduleFacts, facts_from_kernel, ident

# Stand-in C types so nvcc can assemble a cubin without a full toolkit / cuda_fp16.h.
# Real Choreo dtype is kept in comments. Not the designed L5 ISA.
_C_DTYPE = {"f16": "float", "bf16": "float", "f32": "float", "f8": "unsigned char"}


def print_cuda(kernel: Kernel, facts: ScheduleFacts | None = None) -> str:
    """Emit CUDA C++ that consumes the Choreo schedule.

    smem → __shared__, Copy → gmem↔onchip index loops, Barrier → __syncthreads,
    Pipeline.depth → staged shared arrays, Mma → scalar MAC plus named ISA
    (mma.sync / wgmma.mma_async / tcgen05.mma) from Kernel.target.
    nvcc -cubin turns this into a cubin when the toolchain is present.
    """
    facts = facts or facts_from_kernel(kernel)
    fn = ident(kernel.name)
    gmem = [b for b in kernel.buffers if b.space == "gmem"]
    args = ", ".join(
        f"const {_C_DTYPE.get(b.dtype, 'float')}* {b.name} /* {b.dtype} */"
        if _is_readonly(b, kernel)
        else f"{_C_DTYPE.get(b.dtype, 'float')}* {b.name} /* {b.dtype} */"
        for b in gmem
    )
    if not args:
        args = "void"
    lines = [
        f"// Choreo IR → NVIDIA cubin path  |  kernel {kernel.name!r}  target={kernel.target!r}",
        f"// isa={facts.isa} arch={facts.arch} num_warps={facts.num_warps} num_stages={facts.num_stages}",
        "// spaces: gmem→global, smem→__shared__, tmem→TMEM (sm100), regs→registers",
        "// dtypes lowered as float/uchar stand-in so nvcc needs no cuda_fp16.h (not L5 ISA)",
        "",
        f'extern "C" __global__ void {fn}({args}) {{',
        f"  // launch: dim3 block({max(facts.num_warps * 32, 32)});",
    ]
    for b in kernel.buffers:
        if b.space == "gmem":
            continue
        lines.append(f"  {_decl_onchip(b, facts)}")
    for b in kernel.buffers:
        if b.space == "regs":
            lines.extend(_zero_regs(b, "  "))
    lines.extend(_emit_ops(kernel.body, "  ", kernel, facts))
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


def _decl_onchip(buf: Buffer, facts: ScheduleFacts) -> str:
    ty = _C_DTYPE.get(buf.dtype, "float")
    dims = "".join(f"[{d}]" for d in buf.layout.shape) or "[1]"
    note = f"  // choreo dtype={buf.dtype}"
    if buf.space == "smem":
        if facts.num_stages > 1:
            return (
                f"__shared__ {ty} {buf.name}{dims}[{facts.num_stages}];"
                f"  // pipeline depth={facts.num_stages}{note}"
            )
        return f"__shared__ {ty} {buf.name}{dims};{note}"
    if buf.space == "tmem":
        return f"// tmem {buf.name}{dims}  ({facts.isa} TMEM); not allocated in this fallback"
    return f"{ty} {buf.name}{dims};  // regs{note}"


def _zero_regs(buf: Buffer, indent: str) -> list[str]:
    names = [f"z{d}" for d in range(len(buf.layout.shape))]
    if not names:
        return [f"{indent}{buf.name} = 0;"]
    lines: list[str] = [f"{indent}// zero {buf.name}"]
    for d, (n, nm) in enumerate(zip(buf.layout.shape, names)):
        lines.append(f"{indent}{'  ' * d}for (int {nm} = 0; {nm} < {n}; ++{nm}) {{")
    idx = "".join(f"[{nm}]" for nm in names)
    lines.append(f"{indent}{'  ' * len(names)}{buf.name}{idx} = 0;")
    for d in range(len(names) - 1, -1, -1):
        lines.append(f"{indent}{'  ' * d}}}")
    return lines


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
            lines.append(f"{indent}#pragma unroll  // {op.id} depth={op.depth}")
            lines.append(f"{indent}for (int _stage = 0; _stage < {op.depth}; ++_stage) {{")
            lines.extend(_emit_ops(op.body, indent + "  ", kernel, facts))
            lines.append(f"{indent}}}")
        elif isinstance(op, Copy):
            lines.extend(_emit_copy(op, indent, kernel, facts))
        elif isinstance(op, Barrier):
            waits = ",".join(op.wait_for)
            part = kernel.partition(op.arrive)
            role = part.role if part else "?"
            lines.append(
                f"{indent}__syncthreads();  // {op.id} wait {waits} arrive {op.arrive} role={role}"
            )
        elif isinstance(op, Mma):
            lines.extend(_emit_mma(op, indent, kernel, facts))
        elif isinstance(op, Reduce):
            lines.append(f"{indent}// reduce {op.id} axis={op.axis} (not lowered in v0.1 cuda sink)")
        elif isinstance(op, Yield):
            lines.append(f"{indent}// yield {op.id}: {','.join(op.values)}")
    return lines


def _buf_ref(buf: Buffer, names: list[str], facts: ScheduleFacts) -> str:
    if buf.space == "gmem":
        lin = " + ".join(f"{nm} * {s}" for nm, s in zip(names, buf.layout.stride)) or "0"
        return f"{buf.name}[{lin}]"
    idx = "".join(f"[{nm}]" for nm in names)
    stage = "[_stage]" if facts.num_stages > 1 and buf.space == "smem" else ""
    return f"{buf.name}{idx}{stage}"


def _index_loops_named(shape: tuple[int, ...], indent: str, body: str) -> list[str]:
    if not shape:
        return [f"{indent}{body}"]
    lines: list[str] = []
    names = [f"i{d}" for d in range(len(shape))]
    for d, (n, nm) in enumerate(zip(shape, names)):
        lines.append(f"{indent}{'  ' * d}for (int {nm} = 0; {nm} < {n}; ++{nm}) {{")
    lines.append(f"{indent}{'  ' * len(shape)}{body}")
    for d in range(len(shape) - 1, -1, -1):
        lines.append(f"{indent}{'  ' * d}}}")
    return lines


def _emit_copy(op: Copy, indent: str, kernel: Kernel, facts: ScheduleFacts) -> list[str]:
    src, dst = kernel.buffer(op.src), kernel.buffer(op.dst)
    if src is None or dst is None:
        return [f"{indent}// copy {op.id} missing buffer"]
    shape = dst.layout.shape
    names = [f"i{d}" for d in range(len(shape))]
    body = f"{_buf_ref(dst, names, facts)} = {_buf_ref(src, names, facts)};"
    part = kernel.partition(op.partition)
    role = part.role if part else "?"
    lines = [
        f"{indent}// copy {op.id} {op.src}({src.space})->{op.dst}({dst.space}) "
        f"@{op.partition} role={role}"
    ]
    return lines + _index_loops_named(shape, indent, body)


def _emit_mma(op: Mma, indent: str, kernel: Kernel, facts: ScheduleFacts) -> list[str]:
    a, b, c = kernel.buffer(op.a), kernel.buffer(op.b), kernel.buffer(op.c)
    if not (a and b and c) or len(a.layout.shape) != 2:
        return [f"{indent}// mma {op.id} shape error"]
    m, k = a.layout.shape
    n = b.layout.shape[1] if len(b.layout.shape) == 2 else 1
    a_ref = _buf_ref(a, ["i", "kk"], facts)
    b_ref = _buf_ref(b, ["kk", "j"], facts)
    c_ref = _buf_ref(c, ["i", "j"], facts)
    part = kernel.partition(op.partition)
    role = part.role if part else "?"
    return [
        f"{indent}// mma {op.id} {op.c} += {op.a}@{op.b}  isa={facts.isa} @{op.partition} role={role}",
        f"{indent}for (int i = 0; i < {m}; ++i) {{",
        f"{indent}  for (int j = 0; j < {n}; ++j) {{",
        f"{indent}    float acc = 0.f;",
        f"{indent}    for (int kk = 0; kk < {k}; ++kk) {{",
        f"{indent}      acc += (float){a_ref} * (float){b_ref};",
        f"{indent}    }}",
        f"{indent}    {c_ref} += acc;  // {facts.isa} fallback MAC; tensor-core path is {facts.isa}",
        f"{indent}  }}",
        f"{indent}}}",
    ]
