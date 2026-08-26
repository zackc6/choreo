"""NVIDIA CUDA C++ sink — the cubin-bound path. Walks Copy/Barrier/Mma/Pipeline/Reduce."""

from __future__ import annotations

from .ast import Barrier, Buffer, Copy, Kernel, Mma, Partition, Pipeline, Reduce, Yield
from .knobs import ScheduleFacts, facts_from_kernel, ident, launch_nthreads, partition_nthreads

# Stand-in C types so nvcc can assemble a cubin without a full toolkit / cuda_fp16.h.
# Real Choreo dtype is kept in comments. Not the designed L5 ISA.
_C_DTYPE = {"f16": "float", "bf16": "float", "f32": "float", "f8": "unsigned char"}


def print_cuda(kernel: Kernel, facts: ScheduleFacts | None = None) -> str:
    """Emit CUDA C++ that consumes the Choreo schedule.

    smem → __shared__, Copy → gmem↔onchip index loops, Barrier → __syncthreads,
    Pipeline.depth → staged shared arrays (attrs.num_stages is the Triton sidecar
    and does not unstage this reservation), Partition.width → __launch_bounds__
    and thread-strided loops (width warps × 32), Mma → scalar MAC plus named ISA
    (mma.sync / wgmma.mma_async / tcgen05.mma) from Kernel.target, Reduce →
    nested sum over axis.
    nvcc -cubin turns this into a cubin when the toolchain is present.
    Required launch is <<<1, launch_nthreads>>> (recorded on pin.json ``launch``,
    not in cache_key).
    """
    facts = facts or facts_from_kernel(kernel)
    fn = ident(kernel.name)
    launch = launch_nthreads(facts)
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
        f"// launch: <<<1, {launch}>>>  (__launch_bounds__ from summed partition widths)",
        "// spaces: gmem→global, smem→__shared__, tmem→TMEM (sm100), regs→registers",
        "// dtypes lowered as float/uchar stand-in so nvcc needs no cuda_fp16.h (not L5 ISA)",
        "",
        f'extern "C" __global__ void __launch_bounds__({launch}) {fn}({args}) {{',
    ]
    for b in kernel.buffers:
        if b.space == "gmem":
            continue
        lines.append(f"  {_decl_onchip(b, facts)}")
    for b in kernel.buffers:
        if b.space == "regs":
            lines.extend(_zero_regs(b, "  ", facts))
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
        if facts.pipeline_depth > 1:
            return (
                f"__shared__ {ty} {buf.name}{dims}[{facts.pipeline_depth}];"
                f"  // pipeline depth={facts.pipeline_depth}{note}"
            )
        return f"__shared__ {ty} {buf.name}{dims};{note}"
    if buf.space == "tmem":
        return f"// tmem {buf.name}{dims}  ({facts.isa} TMEM); not allocated in this fallback"
    return f"{ty} {buf.name}{dims};  // regs{note}"


def _zero_regs(buf: Buffer, indent: str, facts: ScheduleFacts) -> list[str]:
    names = [f"z{d}" for d in range(len(buf.layout.shape))]
    nt = launch_nthreads(facts)
    numel = buf.layout.numel()
    lines: list[str] = [
        f"{indent}// zero {buf.name}",
        f"{indent}for (int _z = (int)threadIdx.x; _z < {numel}; _z += {nt}) {{",
    ]
    lines.extend(_unravel(buf.layout.shape, "_z", indent + "  ", names))
    idx = "".join(f"[{nm}]" for nm in names) if names else ""
    lines.append(f"{indent}  {buf.name}{idx} = 0;")
    lines.append(f"{indent}}}")
    return lines


def _walk(ops: tuple[object, ...] | list[object]) -> list[object]:
    out: list[object] = []
    for op in ops:
        out.append(op)
        if isinstance(op, Pipeline):
            out.extend(_walk(op.body))
    return out


def _nthreads(part: Partition | None) -> int:
    return partition_nthreads(part.width if part is not None else 1)


def _unravel(shape: tuple[int, ...], lin: str, indent: str, names: list[str]) -> list[str]:
    """Decode a linear index into C-order coordinates (last dim fastest)."""
    if not names:
        return []
    lines: list[str] = []
    rest = lin
    for d, nm in enumerate(names):
        inner = 1
        for s in shape[d + 1 :]:
            inner *= s
        if d == len(names) - 1:
            lines.append(f"{indent}int {nm} = {rest};")
        else:
            lines.append(f"{indent}int {nm} = {rest} / {inner};")
            rest = f"({rest} % {inner})"
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
            lines.extend(_emit_reduce(op, indent, kernel, facts))
        elif isinstance(op, Yield):
            lines.append(f"{indent}// yield {op.id}: {','.join(op.values)}")
    return lines


def _buf_ref(buf: Buffer, names: list[str], facts: ScheduleFacts) -> str:
    if buf.space == "gmem":
        lin = " + ".join(f"{nm} * {s}" for nm, s in zip(names, buf.layout.stride)) or "0"
        return f"{buf.name}[{lin}]"
    idx = "".join(f"[{nm}]" for nm in names)
    stage = "[_stage]" if facts.pipeline_depth > 1 and buf.space == "smem" else ""
    return f"{buf.name}{idx}{stage}"


def _emit_copy(op: Copy, indent: str, kernel: Kernel, facts: ScheduleFacts) -> list[str]:
    src, dst = kernel.buffer(op.src), kernel.buffer(op.dst)
    if src is None or dst is None:
        return [f"{indent}// copy {op.id} missing buffer"]
    part = kernel.partition(op.partition)
    nt = _nthreads(part)
    role = part.role if part else "?"
    width = part.width if part else 1
    shape = dst.layout.shape
    names = [f"i{d}" for d in range(len(shape))]
    numel = dst.layout.numel()
    body = f"{_buf_ref(dst, names, facts)} = {_buf_ref(src, names, facts)};"
    lines = [
        f"{indent}// copy {op.id} {op.src}({src.space})->{op.dst}({dst.space}) "
        f"@{op.partition} role={role} width={width} threads={nt}",
        f"{indent}for (int _i = (int)threadIdx.x; _i < {numel}; _i += {nt}) {{",
    ]
    lines.extend(_unravel(shape, "_i", indent + "  ", names))
    lines.append(f"{indent}  {body}")
    lines.append(f"{indent}}}")
    return lines


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
    nt = _nthreads(part)
    width = part.width if part else 1
    mn = m * n
    return [
        f"{indent}// mma {op.id} {op.c} += {op.a}@{op.b}  isa={facts.isa} "
        f"@{op.partition} role={role} width={width} threads={nt}",
        f"{indent}for (int _t = (int)threadIdx.x; _t < {mn}; _t += {nt}) {{",
        f"{indent}  int i = _t / {n};",
        f"{indent}  int j = _t % {n};",
        f"{indent}  float acc = 0.f;",
        f"{indent}  for (int kk = 0; kk < {k}; ++kk) {{",
        f"{indent}    acc += (float){a_ref} * (float){b_ref};",
        f"{indent}  }}",
        f"{indent}  {c_ref} += acc;  // {facts.isa} fallback MAC; tensor-core path is {facts.isa}",
        f"{indent}}}",
    ]


def _emit_reduce(op: Reduce, indent: str, kernel: Kernel, facts: ScheduleFacts) -> list[str]:
    src, dst = kernel.buffer(op.src), kernel.buffer(op.dst)
    part = kernel.partition(op.partition)
    role = part.role if part else "?"
    if src is None or dst is None:
        return [f"{indent}// reduce {op.id} missing buffer"]
    nt = _nthreads(part)
    width = part.width if part else 1
    dst_names = [f"rz{d}" for d in range(len(dst.layout.shape))]
    src_names = [f"rs{d}" for d in range(len(src.layout.shape))]
    axis = op.axis
    lines = [
        f"{indent}// reduce {op.id} {op.src}-axis{op.axis}->{op.dst} "
        f"@{op.partition} role={role} width={width} threads={nt}"
    ]
    dst_n = dst.layout.numel()
    ax_name = src_names[axis] if axis < len(src_names) else "rax"
    ax_n = src.layout.shape[axis] if axis < len(src.layout.shape) else 1
    src_from_dst = _src_index_names(src, axis, dst_names, src_names)
    lines.append(f"{indent}for (int _z = (int)threadIdx.x; _z < {dst_n}; _z += {nt}) {{")
    lines.extend(_unravel(dst.layout.shape, "_z", indent + "  ", dst_names))
    lines.append(f"{indent}  {_buf_ref(dst, dst_names, facts)} = 0.f;")
    lines.append(f"{indent}  for (int {ax_name} = 0; {ax_name} < {ax_n}; ++{ax_name}) {{")
    lines.append(
        f"{indent}    {_buf_ref(dst, dst_names, facts)} += "
        f"(float){_buf_ref(src, src_from_dst, facts)};"
    )
    lines.append(f"{indent}  }}")
    lines.append(f"{indent}}}")
    return lines


def _src_index_names(
    src: Buffer, axis: int, dst_names: list[str], src_names: list[str]
) -> list[str]:
    """Src index names: dst coords with the reduced axis reinserted."""
    out: list[str] = []
    di = 0
    for d in range(len(src.layout.shape)):
        if d == axis:
            out.append(src_names[d] if d < len(src_names) else "rax")
        else:
            out.append(dst_names[di] if di < len(dst_names) else src_names[d])
            di += 1
    return out
