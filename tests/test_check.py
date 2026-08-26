from choreoir.ast import Barrier, Buffer, Copy, Kernel, Layout, Mma, Param, Partition
from choreoir.check import check


def _bufs():
    a = Buffer("A", "gmem", Layout((8, 8), (8, 1)), "f16")
    s = Buffer("S", "smem", Layout((8, 8), (8, 1)), "f16")
    return a, s


def test_copy_kernel_ok():
    a, s = _bufs()
    k = Kernel(
        "copy",
        params=(Param("A", "f16", (8, 8)),),
        buffers=(a, s),
        partitions=(Partition("load", "load", 4),),
        body=(Copy("c0", "A", "S", "load"),),
    )
    assert check(k) == []


def test_unknown_buffer_is_wellformed_error():
    a, s = _bufs()
    k = Kernel(
        "bad",
        buffers=(a, s),
        partitions=(Partition("load", "load", 4),),
        body=(Copy("c0", "A", "missing", "load"),),
    )
    fs = check(k)
    assert any(f.gate == "W" and "missing" in f.msg for f in fs)


def test_layout_rank_mismatch():
    a = Buffer("A", "gmem", Layout((8, 8), (8, 1)), "f16")
    s = Buffer("S", "smem", Layout((4, 4), (4, 1)), "f16")
    k = Kernel(
        "bad",
        buffers=(a, s),
        partitions=(Partition("load", "load", 4),),
        body=(Copy("c0", "A", "S", "load"),),
    )
    fs = check(k)
    assert any(f.gate == "L" for f in fs)


def test_cross_partition_copy_needs_barrier():
    a = Buffer("A", "gmem", Layout((8, 8), (8, 1)), "f16")
    s = Buffer("S", "smem", Layout((8, 8), (8, 1)), "f16")
    c = Buffer("C", "regs", Layout((8, 8), (8, 1)), "f16")
    k = Kernel(
        "race",
        buffers=(a, s, c),
        partitions=(
            Partition("load", "load", 4),
            Partition("math", "math", 4),
        ),
        body=(
            Copy("c0", "A", "S", "load"),
            Copy("c1", "S", "C", "math"),  # no barrier
        ),
    )
    fs = check(k)
    assert any(f.gate == "S" for f in fs)

    k2 = Kernel(
        "ok",
        buffers=(a, s, c),
        partitions=(
            Partition("load", "load", 4),
            Partition("math", "math", 4),
        ),
        body=(
            Copy("c0", "A", "S", "load"),
            Barrier("b0", wait_for=("load",), arrive="math"),
            Copy("c1", "S", "C", "math"),
        ),
    )
    assert not any(f.gate == "S" for f in check(k2))


def test_mma_shapes():
    a = Buffer("A", "smem", Layout((8, 4), (4, 1)), "f16")
    b = Buffer("B", "smem", Layout((4, 8), (8, 1)), "f16")
    c = Buffer("C", "regs", Layout((8, 8), (8, 1)), "f32")
    k = Kernel(
        "mma",
        buffers=(a, b, c),
        partitions=(Partition("math", "math", 4),),
        body=(Mma("m0", "A", "B", "C", "math"),),
    )
    assert not any(f.gate == "L" for f in check(k))
