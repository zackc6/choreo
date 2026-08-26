from choreoir.ast import Buffer, Copy, Kernel, Layout, Mma, Partition, Pipeline
from choreoir.print_triton import print_triton


def test_print_copy_contains_load_store():
    k = Kernel(
        "copy",
        buffers=(
            Buffer("A", "gmem", Layout((8, 8), (8, 1)), "f16"),
            Buffer("S", "smem", Layout((8, 8), (8, 1)), "f16"),
        ),
        partitions=(Partition("load", "load", 4),),
        body=(Copy("c0", "A", "S", "load"),),
    )
    text = print_triton(k)
    assert "@triton.jit" in text
    assert "tl.load" in text
    assert "tl.store" in text
    assert "copy c0" in text


def test_print_gemm_contains_dot():
    k = Kernel(
        "gemm_tile",
        buffers=(
            Buffer("A", "smem", Layout((8, 4), (4, 1)), "f16"),
            Buffer("B", "smem", Layout((4, 8), (8, 1)), "f16"),
            Buffer("C", "regs", Layout((8, 8), (8, 1)), "f32"),
        ),
        partitions=(Partition("math", "math", 4),),
        body=(Mma("m0", "A", "B", "C", "math"),),
    )
    text = print_triton(k)
    assert "tl.dot" in text
    assert "BLOCK_M: tl.constexpr = 8" in text
    assert "mma m0" in text


def test_print_triton_walks_pipeline_body():
    k = Kernel(
        "copy",
        target="cuda",
        buffers=(
            Buffer("A", "gmem", Layout((8, 8), (8, 1)), "f16"),
            Buffer("S", "smem", Layout((8, 8), (8, 1)), "f16"),
        ),
        partitions=(Partition("load", "load", 4),),
        body=(Pipeline("p0", 3, (Copy("c0", "A", "S", "load"),)),),
    )
    text = print_triton(k)
    assert "for _stage in tl.range(0, 3, num_stages=3):  # p0" in text
    assert "tl.load" in text
    assert "copy c0" in text
