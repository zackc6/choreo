from choreoir.ast import Barrier, Buffer, Copy, Kernel, Layout, Mma, Partition, Reduce
from choreoir.interp import check_value, simulate, simulate_copy


def test_simulate_copy_identity():
    a = Buffer("A", "gmem", Layout((2, 2), (2, 1)), "f16")
    s = Buffer("S", "smem", Layout((2, 2), (2, 1)), "f16")
    k = Kernel(
        "copy",
        buffers=(a, s),
        partitions=(Partition("load", "load", 1),),
        body=(Copy("c0", "A", "S", "load"),),
    )
    src = [[1.0, 2.0], [3.0, 4.0]]
    assert simulate_copy(k, {"A": src}) == []
    store, fs = simulate(k, {"A": src})
    assert fs == []
    assert store["S"] == src
    assert store["S"] is not src


def test_simulate_copy_gmem_writeback():
    a = Buffer("A", "gmem", Layout((2, 2), (2, 1)), "f16")
    s = Buffer("S", "smem", Layout((2, 2), (2, 1)), "f16")
    b = Buffer("B", "gmem", Layout((2, 2), (2, 1)), "f16")
    k = Kernel(
        "copy",
        buffers=(a, s, b),
        partitions=(Partition("load", "load", 1), Partition("store", "store", 1)),
        body=(
            Copy("c0", "A", "S", "load"),
            Barrier("b0", ("load",), "store"),
            Copy("c1", "S", "B", "store"),
        ),
    )
    src = [[1.0, 2.0], [3.0, 4.0]]
    assert check_value(k, {"A": src}, {"B": src}) == []


def test_simulate_mma_and_value_gate():
    a = Buffer("A", "smem", Layout((2, 2), (2, 1)), "f16")
    b = Buffer("B", "smem", Layout((2, 2), (2, 1)), "f16")
    c = Buffer("C", "regs", Layout((2, 2), (2, 1)), "f32")
    k = Kernel(
        "mma",
        buffers=(a, b, c),
        partitions=(Partition("math", "math", 1),),
        body=(Mma("m0", "A", "B", "C", "math"),),
    )
    tensors = {"A": [[1.0, 2.0], [3.0, 4.0]], "B": [[5.0, 6.0], [7.0, 8.0]]}
    expected = {"C": [[19.0, 22.0], [43.0, 50.0]]}
    assert check_value(k, tensors, expected) == []
    bad = check_value(k, tensors, {"C": [[0.0, 0.0], [0.0, 0.0]]})
    assert any(f.gate == "V" and f.element == (0, 0) for f in bad)


def test_simulate_gemm_with_barrier():
    ag = Buffer("Ag", "gmem", Layout((2, 2), (2, 1)), "f16")
    bg = Buffer("Bg", "gmem", Layout((2, 2), (2, 1)), "f16")
    as_ = Buffer("As", "smem", Layout((2, 2), (2, 1)), "f16")
    bs = Buffer("Bs", "smem", Layout((2, 2), (2, 1)), "f16")
    c = Buffer("C", "regs", Layout((2, 2), (2, 1)), "f32")
    k = Kernel(
        "gemm",
        buffers=(ag, bg, as_, bs, c),
        partitions=(Partition("load", "load", 1), Partition("math", "math", 1)),
        body=(
            Copy("cA", "Ag", "As", "load"),
            Copy("cB", "Bg", "Bs", "load"),
            Barrier("b0", ("load",), "math"),
            Mma("m0", "As", "Bs", "C", "math"),
        ),
    )
    tensors = {"Ag": [[1.0, 2.0], [3.0, 4.0]], "Bg": [[5.0, 6.0], [7.0, 8.0]]}
    assert check_value(k, tensors, {"C": [[19.0, 22.0], [43.0, 50.0]]}) == []


def test_reduce_sum_axis1():
    x = Buffer("X", "regs", Layout((2, 2), (2, 1)), "f32")
    y = Buffer("Y", "regs", Layout((2,), (1,)), "f32")
    k = Kernel(
        "red",
        buffers=(x, y),
        partitions=(Partition("math", "math", 1),),
        body=(Reduce("r0", "X", "Y", 1, "math"),),
    )
    assert check_value(k, {"X": [[1.0, 2.0], [3.0, 4.0]]}, {"Y": [3.0, 7.0]}) == []


def test_mma_accumulate():
    a = Buffer("A", "smem", Layout((1, 1), (1,)), "f16")
    b = Buffer("B", "smem", Layout((1, 1), (1,)), "f16")
    c = Buffer("C", "regs", Layout((1, 1), (1,)), "f32")
    k = Kernel(
        "acc",
        buffers=(a, b, c),
        partitions=(Partition("math", "math", 1),),
        body=(Mma("m0", "A", "B", "C", "math"),),
    )
    store, fs = simulate(k, {"A": [[2.0]], "B": [[3.0]], "C": [[1.0]]})
    assert fs == []
    assert store["C"] == [[7.0]]
