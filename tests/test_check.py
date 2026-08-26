from choreoir.ast import Barrier, Buffer, Copy, Kernel, Layout, Mma, Param, Partition, Reduce, Yield
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
    shape = [f for f in fs if f.gate == "L" and "copy shape" in f.msg]
    assert shape and shape[0].element == (7, 7)
    assert shape[0].as_dict()["where"] == "L"


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
    race = next(f for f in fs if f.gate == "S")
    assert race.thread == 0
    assert race.partition == "math"
    assert race.as_dict()["where"] == "S"

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
    assert check(k) == []


def test_unused_buffer_is_wellformed_error():
    a, s = _bufs()
    extra = Buffer("U", "regs", Layout((8, 8), (8, 1)), "f16")
    k = Kernel(
        "unused",
        buffers=(a, s, extra),
        partitions=(Partition("load", "load", 4),),
        body=(Copy("c0", "A", "S", "load"),),
    )
    fs = check(k)
    assert any(f.gate == "W" and "never used" in f.msg and f.node == "buffer.U" for f in fs)


def test_duplicate_op_id():
    a, s = _bufs()
    k = Kernel(
        "dup",
        buffers=(a, s),
        partitions=(Partition("load", "load", 4),),
        body=(Copy("c0", "A", "S", "load"), Copy("c0", "S", "A", "load")),
    )
    fs = check(k)
    assert any("duplicate op id" in f.msg for f in fs)


def test_reduce_layout_and_unused_axis():
    src = Buffer("X", "regs", Layout((4, 2), (2, 1)), "f32")
    dst = Buffer("Y", "regs", Layout((4,), (1,)), "f32")
    k = Kernel(
        "red",
        buffers=(src, dst),
        partitions=(Partition("math", "math", 1),),
        body=(Reduce("r0", "X", "Y", 1, "math"), Yield("y0", ("Y",))),
    )
    assert check(k) == []

    bad = Kernel(
        "red_bad",
        buffers=(src, Buffer("Z", "regs", Layout((2,), (1,)), "f32")),
        partitions=(Partition("math", "math", 1),),
        body=(Reduce("r0", "X", "Z", 1, "math"),),
    )
    fs = check(bad)
    assert any(f.gate == "L" and "dst shape" in f.msg for f in fs)


def test_finding_schema_keys():
    a, s = _bufs()
    k = Kernel(
        "bad",
        buffers=(a, s),
        partitions=(Partition("load", "load", 4),),
        body=(Copy("c0", "A", "missing", "load"),),
    )
    d = check(k)[0].as_dict()
    assert set(d) == {
        "where",
        "gate",
        "severity",
        "node",
        "partition",
        "thread",
        "element",
        "msg",
    }
    assert d["where"] == d["gate"] == "W"


def test_layout_span_localizes_last_element():
    a = Buffer("A", "gmem", Layout((8, 8), (1, 1)), "f16")
    s = Buffer("S", "smem", Layout((8, 8), (1, 1)), "f16")
    k = Kernel(
        "copy",
        buffers=(a, s),
        partitions=(Partition("load", "load", 1),),
        body=(Copy("c0", "A", "S", "load"),),
    )
    fs = check(k)
    cover = [f for f in fs if f.gate == "L" and "cover" in f.msg]
    assert cover
    assert cover[0].element == (7, 7)


def test_role_space_writeback_wants_store():
    a = Buffer("A", "gmem", Layout((2, 2), (2, 1)), "f16")
    s = Buffer("S", "smem", Layout((2, 2), (2, 1)), "f16")
    b = Buffer("B", "gmem", Layout((2, 2), (2, 1)), "f16")
    k = Kernel(
        "copy",
        buffers=(a, s, b),
        partitions=(
            Partition("load", "load", 1),
            Partition("math", "math", 1),
        ),
        body=(
            Copy("c0", "A", "S", "load"),
            Barrier("b0", wait_for=("load",), arrive="math"),
            Copy("c1", "S", "B", "math"),
        ),
    )
    fs = check(k)
    role = [f for f in fs if f.gate == "W" and "store role" in f.msg]
    assert role and role[0].node == "c1"
    assert role[0].partition == "math"
