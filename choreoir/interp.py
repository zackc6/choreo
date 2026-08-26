from __future__ import annotations

from .ast import Barrier, Copy, Kernel, Mma, Pipeline, Reduce, Yield, flatten_ops
from .check import Finding


def simulate(kernel: Kernel, tensors: dict[str, list]) -> tuple[dict[str, object], list[Finding]]:
    """CPU interpreter for Copy / Mma / Reduce. Barriers and pipelines do not change values."""
    findings: list[Finding] = []
    store: dict[str, object] = {k: _copy_nested(v) for k, v in tensors.items()}
    bufs = {b.name: b for b in kernel.buffers}

    for op in flatten_ops(kernel.body):
        if isinstance(op, Barrier | Yield | Pipeline):
            continue
        if isinstance(op, Copy):
            src = store.get(op.src)
            if src is None:
                findings.append(Finding("V", "error", op.id, f"missing tensor for {op.src}"))
                continue
            src_b = bufs.get(op.src)
            if src_b is None:
                findings.append(Finding("V", "error", op.id, f"unknown buffer {op.src}"))
                continue
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
        elif isinstance(op, Mma):
            a, b = store.get(op.a), store.get(op.b)
            if a is None or b is None:
                missing = op.a if a is None else op.b
                findings.append(Finding("V", "error", op.id, f"missing tensor for {missing}"))
                continue
            try:
                prod = _matmul(a, b)
            except ValueError as e:
                findings.append(Finding("V", "error", op.id, str(e)))
                continue
            acc = store.get(op.c)
            store[op.c] = _add_nested(prod, acc) if acc is not None else prod
        elif isinstance(op, Reduce):
            src = store.get(op.src)
            if src is None:
                findings.append(Finding("V", "error", op.id, f"missing tensor for {op.src}"))
                continue
            try:
                store[op.dst] = _reduce_sum(src, op.axis)
            except (TypeError, IndexError, ValueError) as e:
                findings.append(Finding("V", "error", op.id, str(e)))
        else:
            findings.append(
                Finding("V", "error", getattr(op, "id", "?"), f"unsupported op {type(op).__name__}")
            )
            return store, findings
    return store, findings


def simulate_copy(kernel: Kernel, tensors: dict[str, list]) -> list[Finding]:
    """V-gate for Copy-only kernels. Nested-list CPU sim; not a GPU oracle."""
    _, findings = simulate(kernel, tensors)
    for op in flatten_ops(kernel.body):
        if not isinstance(op, Copy | Barrier | Pipeline | Yield):
            return [
                Finding("V", "error", getattr(op, "id", "?"), "simulate_copy only handles Copy ops")
            ]
    return findings


def check_value(
    kernel: Kernel,
    tensors: dict[str, list],
    expected: dict[str, list],
    *,
    eps: float = 1e-3,
) -> list[Finding]:
    """Compare interpreter results to a reference (tiny-tile V gate)."""
    store, findings = simulate(kernel, tensors)
    if findings:
        return findings
    for name, want in expected.items():
        got = store.get(name)
        if got is None:
            findings.append(Finding("V", "error", name, f"missing result tensor {name}"))
            continue
        mismatch = _first_mismatch(got, want, (), eps)
        if mismatch is not None:
            idx, g, w = mismatch
            findings.append(
                Finding(
                    "V",
                    "error",
                    name,
                    f"expected {w} got {g}",
                    element=idx or None,
                )
            )
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


def _matmul(a: object, b: object) -> list:
    if not (isinstance(a, list) and a and isinstance(a[0], list)):
        raise ValueError("mma A must be rank-2")
    if not (isinstance(b, list) and b and isinstance(b[0], list)):
        raise ValueError("mma B must be rank-2")
    m, k = len(a), len(a[0])
    k2, n = len(b), len(b[0])
    if k != k2:
        raise ValueError(f"mma inner dim {k} != {k2}")
    out = []
    for i in range(m):
        row = []
        for j in range(n):
            s = 0.0
            for t in range(k):
                s += float(a[i][t]) * float(b[t][j])
            row.append(s)
        out.append(row)
    return out


def _add_nested(a: object, b: object) -> object:
    if not isinstance(a, list):
        return float(a) + float(b)  # type: ignore[arg-type]
    return [_add_nested(x, y) for x, y in zip(a, b, strict=True)]


def _reduce_sum(x: object, axis: int) -> object:
    shape = _nested_shape(x)
    if axis < 0 or axis >= len(shape):
        raise ValueError(f"reduce axis {axis} out of rank {len(shape)}")
    if axis == 0:
        acc = _copy_nested(x[0])  # type: ignore[index]
        for row in x[1:]:  # type: ignore[index]
            acc = _add_nested(acc, row)
        return acc
    return [_reduce_sum(row, axis - 1) for row in x]  # type: ignore[union-attr]


def _first_mismatch(
    got: object, want: object, idx: tuple[int, ...], eps: float
) -> tuple[tuple[int, ...], object, object] | None:
    if isinstance(got, list) and isinstance(want, list):
        if len(got) != len(want):
            return idx, f"len {len(got)}", f"len {len(want)}"
        for i, (g, w) in enumerate(zip(got, want, strict=True)):
            m = _first_mismatch(g, w, idx + (i,), eps)
            if m is not None:
                return m
        return None
    try:
        if abs(float(got) - float(want)) <= eps:  # type: ignore[arg-type]
            return None
    except (TypeError, ValueError):
        pass
    if got == want:
        return None
    return idx, got, want
