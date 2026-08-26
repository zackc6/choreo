from __future__ import annotations

from dataclasses import dataclass

from .ast import (
    Barrier,
    Copy,
    Kernel,
    Layout,
    Mma,
    Pipeline,
    Reduce,
    Yield,
    flatten_ops,
)


@dataclass(frozen=True)
class Finding:
    gate: str  # W | L | S | V
    severity: str  # error | warning
    node: str
    msg: str
    partition: str | None = None
    thread: int | None = None
    element: tuple[int, ...] | None = None

    def as_dict(self) -> dict:
        return {
            "where": self.gate,  # W|L|S|V — Lintel CFG edge; same value as gate
            "gate": self.gate,
            "severity": self.severity,
            "node": self.node,
            "partition": self.partition,
            "thread": self.thread,
            "element": list(self.element) if self.element is not None else None,
            "msg": self.msg,
        }


def check(kernel: Kernel) -> list[Finding]:
    """Admit W → L → S. Value-sim (V) is opt-in via interp.simulate / interp.check_value."""
    out: list[Finding] = []
    out.extend(_wellformed(kernel))
    if any(f.severity == "error" and f.gate == "W" for f in out):
        return out
    out.extend(_layout(kernel))
    out.extend(_sync(kernel))
    return out


def _wellformed(k: Kernel) -> list[Finding]:
    f: list[Finding] = []
    if not k.name:
        f.append(Finding("W", "error", "kernel", "kernel name empty"))
    names = [b.name for b in k.buffers]
    if len(names) != len(set(names)):
        f.append(Finding("W", "error", "buffers", "duplicate buffer name"))
    pnames = [p.name for p in k.partitions]
    if len(pnames) != len(set(pnames)):
        f.append(Finding("W", "error", "partitions", "duplicate partition name"))
    for p in k.partitions:
        if p.width < 1:
            f.append(
                Finding("W", "error", f"partition.{p.name}", "width must be >= 1", partition=p.name)
            )

    used_bufs: set[str] = set()
    used_parts: set[str] = set()
    seen_ids: set[str] = set()

    for i, op in enumerate(flatten_ops(k.body)):
        node = getattr(op, "id", f"op.{i}")
        if isinstance(node, str) and node in seen_ids:
            f.append(Finding("W", "error", node, "duplicate op id"))
        if isinstance(node, str):
            seen_ids.add(node)

        if isinstance(op, (Copy, Mma, Reduce)):
            if k.partition(op.partition) is None:
                f.append(
                    Finding(
                        "W",
                        "error",
                        node,
                        f"unknown partition {op.partition!r}",
                        partition=op.partition,
                    )
                )
            else:
                used_parts.add(op.partition)

        if isinstance(op, Copy):
            for buf in (op.src, op.dst):
                used_bufs.add(buf)
                if k.buffer(buf) is None:
                    f.append(Finding("W", "error", node, f"unknown buffer {buf!r}"))
            f.extend(_role_space_copy(k, op))
        elif isinstance(op, Mma):
            for buf in (op.a, op.b, op.c):
                used_bufs.add(buf)
                if k.buffer(buf) is None:
                    f.append(Finding("W", "error", node, f"unknown buffer {buf!r}"))
            f.extend(_role_space_math(k, op.partition, node, "mma"))
        elif isinstance(op, Reduce):
            for buf in (op.src, op.dst):
                used_bufs.add(buf)
                if k.buffer(buf) is None:
                    f.append(Finding("W", "error", node, f"unknown buffer {buf!r}"))
            f.extend(_role_space_math(k, op.partition, node, "reduce"))
        elif isinstance(op, Barrier):
            if k.partition(op.arrive) is None:
                f.append(Finding("W", "error", node, f"unknown arrive partition {op.arrive!r}"))
            else:
                used_parts.add(op.arrive)
            for w in op.wait_for:
                if k.partition(w) is None:
                    f.append(Finding("W", "error", node, f"unknown wait_for partition {w!r}"))
                else:
                    used_parts.add(w)
        elif isinstance(op, Pipeline) and op.depth < 1:
            f.append(Finding("W", "error", node, "pipeline depth must be >= 1"))
        elif isinstance(op, Yield):
            for buf in op.values:
                used_bufs.add(buf)
                if k.buffer(buf) is None:
                    f.append(Finding("W", "error", node, f"unknown buffer {buf!r}"))

    for b in k.buffers:
        if b.name not in used_bufs:
            f.append(Finding("W", "error", f"buffer.{b.name}", "buffer never used"))
    for p in k.partitions:
        if p.name not in used_parts:
            f.append(
                Finding("W", "error", f"partition.{p.name}", "partition never used", partition=p.name)
            )
    return f


def _role_space_copy(k: Kernel, op: Copy) -> list[Finding]:
    """Copy gmem→onchip wants load; onchip→gmem wants store. generic is the escape."""
    part = k.partition(op.partition)
    src, dst = k.buffer(op.src), k.buffer(op.dst)
    if part is None or src is None or dst is None or part.role == "generic":
        return []
    if src.space == "gmem" and dst.space != "gmem" and part.role != "load":
        return [
            Finding(
                "W",
                "error",
                op.id,
                f"copy {src.space}->{dst.space} wants load role, got {part.role}",
                partition=op.partition,
            )
        ]
    if dst.space == "gmem" and src.space != "gmem" and part.role != "store":
        return [
            Finding(
                "W",
                "error",
                op.id,
                f"copy {src.space}->{dst.space} wants store role, got {part.role}",
                partition=op.partition,
            )
        ]
    return []


def _role_space_math(k: Kernel, partition: str, node: str, kind: str) -> list[Finding]:
    part = k.partition(partition)
    if part is None or part.role in ("math", "generic"):
        return []
    return [
        Finding(
            "W",
            "error",
            node,
            f"{kind} wants math role, got {part.role}",
            partition=partition,
        )
    ]


def _layout_ok(layout: Layout) -> str | None:
    if len(layout.shape) != len(layout.stride):
        return "shape/stride rank mismatch"
    if any(d < 1 for d in layout.shape) or any(s < 1 for s in layout.stride):
        return "shape/stride must be positive"
    if layout.span() < layout.numel():
        return "stride does not cover shape"
    return None


def _layout(k: Kernel) -> list[Finding]:
    f: list[Finding] = []
    for b in k.buffers:
        err = _layout_ok(b.layout)
        if err:
            f.append(
                Finding(
                    "L",
                    "error",
                    f"buffer.{b.name}",
                    err,
                    element=tuple(max(d - 1, 0) for d in b.layout.shape)
                    if b.layout.shape and err == "stride does not cover shape"
                    else ((0,) * len(b.layout.shape) if b.layout.shape else None),
                )
            )
    for op in flatten_ops(k.body):
        if isinstance(op, Copy):
            src, dst = k.buffer(op.src), k.buffer(op.dst)
            if src and dst and src.layout.shape != dst.layout.shape:
                f.append(
                    Finding(
                        "L",
                        "error",
                        op.id,
                        f"copy shape {src.layout.shape} -> {dst.layout.shape}",
                        element=tuple(max(d - 1, 0) for d in src.layout.shape),
                    )
                )
            if src and dst and src.dtype != dst.dtype:
                f.append(
                    Finding(
                        "L",
                        "error",
                        op.id,
                        f"copy dtype {src.dtype} -> {dst.dtype}",
                        element=tuple(max(d - 1, 0) for d in src.layout.shape)
                        if src.layout.shape
                        else None,
                    )
                )
        elif isinstance(op, Mma):
            a, b, c = k.buffer(op.a), k.buffer(op.b), k.buffer(op.c)
            if a and b and c:
                if len(a.layout.shape) != 2 or len(b.layout.shape) != 2 or len(c.layout.shape) != 2:
                    f.append(
                        Finding(
                            "L",
                            "error",
                            op.id,
                            "mma buffers must be rank-2",
                            element=(0, 0),
                        )
                    )
                elif a.layout.shape[1] != b.layout.shape[0] or c.layout.shape != (
                    a.layout.shape[0],
                    b.layout.shape[1],
                ):
                    f.append(
                        Finding(
                            "L",
                            "error",
                            op.id,
                            "mma shape mismatch (A MxK, B KxN, C MxN)",
                            element=tuple(max(d - 1, 0) for d in c.layout.shape)
                            if len(c.layout.shape) == 2
                            else (0, 0),
                        )
                    )
        elif isinstance(op, Reduce):
            src, dst = k.buffer(op.src), k.buffer(op.dst)
            if src and dst:
                if op.axis < 0 or op.axis >= len(src.layout.shape):
                    f.append(
                        Finding(
                            "L",
                            "error",
                            op.id,
                            f"reduce axis {op.axis} out of rank {len(src.layout.shape)}",
                            element=(op.axis,),
                        )
                    )
                else:
                    expected = tuple(d for i, d in enumerate(src.layout.shape) if i != op.axis)
                    if dst.layout.shape != expected:
                        f.append(
                            Finding(
                                "L",
                                "error",
                                op.id,
                                f"reduce dst shape {dst.layout.shape} != {expected}",
                                element=(0,) * len(dst.layout.shape),
                            )
                        )
    return f


def _sync(k: Kernel) -> list[Finding]:
    """Cross-partition data ops must be named in some Barrier.wait_for before a consumer arrives."""
    f: list[Finding] = []
    producers: dict[str, str] = {}  # buffer -> last writer partition
    satisfied: set[tuple[str, str]] = set()  # (writer_part, arriver)

    def note_write(buf: str, part: str) -> None:
        producers[buf] = part

    def require_visible(buf: str, part: str, node: str, kind: str) -> None:
        src_part = producers.get(buf)
        if src_part and src_part != part and (src_part, part) not in satisfied:
            f.append(
                Finding(
                    "S",
                    "error",
                    node,
                    f"{kind} reads {buf} from partition {src_part} without barrier",
                    partition=part,
                    thread=0,  # first lane of arriver; year-1 has no work-partition
                )
            )

    for op in flatten_ops(k.body):
        if isinstance(op, Copy):
            require_visible(op.src, op.partition, op.id, "copy")
            note_write(op.dst, op.partition)
        elif isinstance(op, Mma):
            for buf in (op.a, op.b, op.c):
                require_visible(buf, op.partition, op.id, "mma")
            note_write(op.c, op.partition)
        elif isinstance(op, Reduce):
            require_visible(op.src, op.partition, op.id, "reduce")
            note_write(op.dst, op.partition)
        elif isinstance(op, Barrier):
            for w in op.wait_for:
                satisfied.add((w, op.arrive))
    return f
