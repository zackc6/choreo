from __future__ import annotations

from .ast import Copy, Kernel
from .check import Finding


def simulate_copy(kernel: Kernel, tensors: dict[str, list]) -> list[Finding]:
    """V-gate for Copy-only kernels. Nested-list CPU sim; not a GPU oracle."""
    findings: list[Finding] = []
    store: dict[str, list] = {k: v for k, v in tensors.items()}
    bufs = {b.name: b for b in kernel.buffers}

    for op in kernel.body:
        if not isinstance(op, Copy):
            findings.append(
                Finding("V", "error", getattr(op, "id", "?"), "simulate_copy only handles Copy ops")
            )
            return findings
        src = store.get(op.src)
        if src is None:
            findings.append(Finding("V", "error", op.id, f"missing tensor for {op.src}"))
            continue
        src_b = bufs[op.src]
        if _nested_shape(src) != src_b.layout.shape:
            findings.append(
                Finding(
                    "V",
                    "error",
                    op.id,
                    f"src tensor shape {_nested_shape(src)} != {src_b.layout.shape}",
                )
            )
            continue
        store[op.dst] = _copy_nested(src)
    return findings


def _nested_shape(x: object) -> tuple[int, ...]:
    if not isinstance(x, list):
        return ()
    if not x:
        return (0,)
    return (len(x),) + _nested_shape(x[0])


def _copy_nested(x: object) -> object:
    if not isinstance(x, list):
        return x
    return [_copy_nested(y) for y in x]
