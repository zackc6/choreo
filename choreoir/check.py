from __future__ import annotations

from dataclasses import dataclass

from .ast import Barrier, Copy, Kernel, Layout, Mma, Pipeline


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
            "gate": self.gate,
            "severity": self.severity,
            "node": self.node,
            "partition": self.partition,
            "thread": self.thread,
            "element": list(self.element) if self.element is not None else None,
            "msg": self.msg,
        }


def check(kernel: Kernel) -> list[Finding]:
    """Admit W → L → S. Value-sim (V) is opt-in via interp.simulate_*."""
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
    for i, op in enumerate(k.body):
        node = getattr(op, "id", f"op.{i}")
        if isinstance(op, (Copy, Mma)):
            if k.partition(op.partition) is None:
                f.append(
                    Finding("W", "error", node, f"unknown partition {op.partition!r}", partition=op.partition)
                )
        if isinstance(op, Copy):
            for buf in (op.src, op.dst):
                if k.buffer(buf) is None:
                    f.append(Finding("W", "error", node, f"unknown buffer {buf!r}"))
        if isinstance(op, Mma):
            for buf in (op.a, op.b, op.c):
                if k.buffer(buf) is None:
                    f.append(Finding("W", "error", node, f"unknown buffer {buf!r}"))
        if isinstance(op, Barrier):
            if k.partition(op.arrive) is None:
                f.append(Finding("W", "error", node, f"unknown arrive partition {op.arrive!r}"))
            for w in op.wait_for:
                if k.partition(w) is None:
                    f.append(Finding("W", "error", node, f"unknown wait_for partition {w!r}"))
        if isinstance(op, Pipeline) and op.depth < 1:
            f.append(Finding("W", "error", node, "pipeline depth must be >= 1"))
    return f


def _layout_ok(layout: Layout) -> str | None:
    if len(layout.shape) != len(layout.stride):
        return "shape/stride rank mismatch"
    if any(d < 1 for d in layout.shape) or any(s < 1 for s in layout.stride):
        return "shape/stride must be positive"
    span = 1 + sum((d - 1) * s for d, s in zip(layout.shape, layout.stride, strict=True))
    if span < layout.numel():
        return "stride does not cover shape"
    return None


def _layout(k: Kernel) -> list[Finding]:
    f: list[Finding] = []
    for b in k.buffers:
        err = _layout_ok(b.layout)
        if err:
            f.append(Finding("L", "error", f"buffer.{b.name}", err, element=(0,) * len(b.layout.shape)))
    for op in k.body:
        if isinstance(op, Copy):
            src, dst = k.buffer(op.src), k.buffer(op.dst)
            if src and dst and src.layout.shape != dst.layout.shape:
                f.append(
                    Finding(
                        "L",
                        "error",
                        op.id,
                        f"copy shape {src.layout.shape} -> {dst.layout.shape}",
                    )
                )
            if src and dst and src.dtype != dst.dtype:
                f.append(Finding("L", "error", op.id, f"copy dtype {src.dtype} -> {dst.dtype}"))
        if isinstance(op, Mma):
            a, b, c = k.buffer(op.a), k.buffer(op.b), k.buffer(op.c)
            if a and b and c:
                if len(a.layout.shape) != 2 or len(b.layout.shape) != 2 or len(c.layout.shape) != 2:
                    f.append(Finding("L", "error", op.id, "mma buffers must be rank-2"))
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
                        )
                    )
    return f


def _sync(k: Kernel) -> list[Finding]:
    """Cross-partition data ops must be named in some Barrier.wait_for before a consumer arrives."""
    f: list[Finding] = []
    producers: dict[str, str] = {}  # buffer -> last writer partition
    satisfied: set[tuple[str, str]] = set()  # (writer_part, arriver)

    def note_write(buf: str, part: str, node: str) -> None:
        producers[buf] = part

    for op in k.body:
        if isinstance(op, Copy):
            src_part = producers.get(op.src)
            if src_part and src_part != op.partition and (src_part, op.partition) not in satisfied:
                f.append(
                    Finding(
                        "S",
                        "error",
                        op.id,
                        f"copy reads {op.src} from partition {src_part} without barrier",
                        partition=op.partition,
                    )
                )
            note_write(op.dst, op.partition, op.id)
        elif isinstance(op, Mma):
            for buf in (op.a, op.b, op.c):
                src_part = producers.get(buf)
                if src_part and src_part != op.partition and (src_part, op.partition) not in satisfied:
                    f.append(
                        Finding(
                            "S",
                            "error",
                            op.id,
                            f"mma reads {buf} from partition {src_part} without barrier",
                            partition=op.partition,
                        )
                    )
            note_write(op.c, op.partition, op.id)
        elif isinstance(op, Barrier):
            for w in op.wait_for:
                satisfied.add((w, op.arrive))
    return f
