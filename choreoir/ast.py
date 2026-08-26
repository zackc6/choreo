from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Space = Literal["gmem", "smem", "tmem", "regs"]
Role = Literal["load", "math", "store", "generic"]
Dtype = Literal["f16", "bf16", "f32", "f8"]


@dataclass(frozen=True)
class Layout:
    """Shape × stride. v1: static positive ints (CuTe-style pair, no algebra library)."""

    shape: tuple[int, ...]
    stride: tuple[int, ...]

    def numel(self) -> int:
        n = 1
        for s in self.shape:
            n *= s
        return n

    def span(self) -> int:
        """Minimum storage elements implied by the last touched coordinate."""
        return 1 + sum((d - 1) * s for d, s in zip(self.shape, self.stride, strict=True))


@dataclass(frozen=True)
class Param:
    name: str
    dtype: Dtype
    shape: tuple[int, ...]


@dataclass(frozen=True)
class Buffer:
    name: str
    space: Space
    layout: Layout
    dtype: Dtype


@dataclass(frozen=True)
class Partition:
    name: str
    role: Role
    width: int  # warps in v1


@dataclass(frozen=True)
class Copy:
    id: str
    src: str
    dst: str
    partition: str


@dataclass(frozen=True)
class Mma:
    id: str
    a: str
    b: str
    c: str
    partition: str


@dataclass(frozen=True)
class Reduce:
    id: str
    src: str
    dst: str
    axis: int
    partition: str


@dataclass(frozen=True)
class Barrier:
    id: str
    wait_for: tuple[str, ...]  # partition names that must complete
    arrive: str  # partition that waits


@dataclass(frozen=True)
class Pipeline:
    id: str
    depth: int
    body: tuple[object, ...]


@dataclass(frozen=True)
class Yield:
    id: str
    values: tuple[str, ...]


Op = Copy | Mma | Reduce | Barrier | Pipeline | Yield


@dataclass
class Kernel:
    name: str
    params: tuple[Param, ...] = ()
    buffers: tuple[Buffer, ...] = ()
    partitions: tuple[Partition, ...] = ()
    body: tuple[Op, ...] = ()
    attrs: dict[str, str] = field(default_factory=dict)
    target: str = ""  # cuda | cuda-sm90 | cuda-sm100 | ascend-a2 | ...
    compiler_ver: str = "0.1.8"  # choreoir pin; not mutated inside one walk. %k combines this with the sink.

    def buffer(self, name: str) -> Buffer | None:
        return next((b for b in self.buffers if b.name == name), None)

    def partition(self, name: str) -> Partition | None:
        return next((p for p in self.partitions if p.name == name), None)


def flatten_ops(ops: tuple[object, ...] | list[object]) -> list[object]:
    """Straight-line view: Pipeline regions are inlined for admit/interp."""
    out: list[object] = []
    for op in ops:
        out.append(op)
        if isinstance(op, Pipeline):
            out.extend(flatten_ops(op.body))
    return out
