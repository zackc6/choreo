from __future__ import annotations

from .ast import (
    COMPILER_VER,
    Barrier,
    Buffer,
    Copy,
    Kernel,
    Layout,
    Mma,
    Param,
    Partition,
    Pipeline,
    Reduce,
    Yield,
)
from .pin import apply_pin_stamps

PROPOSAL_SCHEMA = "lintel.adapter_proposal.v0"


def kernel_to_dict(k: Kernel) -> dict:
    return {
        "name": k.name,
        "target": k.target,
        "params": [{"name": p.name, "dtype": p.dtype, "shape": list(p.shape)} for p in k.params],
        "buffers": [
            {
                "name": b.name,
                "space": b.space,
                "dtype": b.dtype,
                "layout": {"shape": list(b.layout.shape), "stride": list(b.layout.stride)},
            }
            for b in k.buffers
        ],
        "partitions": [
            {"name": p.name, "role": p.role, "width": p.width} for p in k.partitions
        ],
        "body": [_op_to_dict(op) for op in k.body],
        "attrs": dict(k.attrs),
        "compiler_ver": k.compiler_ver,
    }


def kernel_from_dict(d: dict) -> Kernel:
    return Kernel(
        name=d["name"],
        params=tuple(
            Param(p["name"], p["dtype"], tuple(p["shape"])) for p in d.get("params", [])
        ),
        buffers=tuple(
            Buffer(
                b["name"],
                b["space"],
                Layout(tuple(b["layout"]["shape"]), tuple(b["layout"]["stride"])),
                b["dtype"],
            )
            for b in d.get("buffers", [])
        ),
        partitions=tuple(
            Partition(p["name"], p["role"], int(p["width"])) for p in d.get("partitions", [])
        ),
        body=tuple(_op_from_dict(op) for op in d.get("body", [])),
        attrs=dict(d.get("attrs", {})),
        target=str(d.get("target", "")),
        compiler_ver=str(d.get("compiler_ver", COMPILER_VER)),
    )


def load_kernel_doc(d: dict) -> Kernel:
    """Kernel JSON, or a lintel.adapter_proposal.v0 envelope."""
    if d.get("schema") == PROPOSAL_SCHEMA and isinstance(d.get("kernel"), dict):
        kernel = kernel_from_dict(d["kernel"])
        apply_pin_stamps(
            kernel,
            graph_hash=d.get("graph_hash") if isinstance(d.get("graph_hash"), str) else None,
            hw_id=d.get("hw_id") if isinstance(d.get("hw_id"), str) else None,
        )
        enum_id = d.get("enum_id")
        if isinstance(enum_id, str) and enum_id and "enum_id" not in kernel.attrs:
            kernel.attrs["enum_id"] = enum_id
        return kernel
    return kernel_from_dict(d)


def _op_kind(raw: object) -> str:
    """Canonical lowercase op tag. Lintel examples use PascalCase class names."""
    text = str(raw)
    if not text:
        return text
    return text[0].lower() + text[1:]


def _op_to_dict(op: object) -> dict:
    if isinstance(op, Copy):
        return {"op": "copy", "id": op.id, "src": op.src, "dst": op.dst, "partition": op.partition}
    if isinstance(op, Mma):
        return {
            "op": "mma",
            "id": op.id,
            "a": op.a,
            "b": op.b,
            "c": op.c,
            "partition": op.partition,
        }
    if isinstance(op, Reduce):
        return {
            "op": "reduce",
            "id": op.id,
            "src": op.src,
            "dst": op.dst,
            "axis": op.axis,
            "partition": op.partition,
        }
    if isinstance(op, Barrier):
        return {
            "op": "barrier",
            "id": op.id,
            "wait_for": list(op.wait_for),
            "arrive": op.arrive,
        }
    if isinstance(op, Pipeline):
        return {
            "op": "pipeline",
            "id": op.id,
            "depth": op.depth,
            "body": [_op_to_dict(x) for x in op.body],
        }
    if isinstance(op, Yield):
        return {"op": "yield", "id": op.id, "values": list(op.values)}
    raise TypeError(f"unknown op {type(op)!r}")


def _op_from_dict(d: dict) -> object:
    kind = _op_kind(d["op"])
    if kind == "copy":
        return Copy(d["id"], d["src"], d["dst"], d["partition"])
    if kind == "mma":
        return Mma(d["id"], d["a"], d["b"], d["c"], d["partition"])
    if kind == "reduce":
        return Reduce(d["id"], d["src"], d["dst"], int(d["axis"]), d["partition"])
    if kind == "barrier":
        return Barrier(d["id"], tuple(d["wait_for"]), d["arrive"])
    if kind == "pipeline":
        return Pipeline(d["id"], int(d["depth"]), tuple(_op_from_dict(x) for x in d["body"]))
    if kind == "yield":
        return Yield(d["id"], tuple(d["values"]))
    raise ValueError(f"unknown op {kind!r}")
