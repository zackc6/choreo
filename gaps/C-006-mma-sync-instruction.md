# C-006 — `Mma` lowers to a scalar MAC

**Gap.** `Mma` is a scalar multiply-accumulate in the CUDA sink; no tensor-core instruction is emitted, so GEMM-tile numbers cannot be compared with cuBLAS at all. (`goals/self-evolving-ir.md` §1.3 item 3; commit 5.)

**Carrier.** `gemm.json` with `Mma.variant: mma.sync` lowered to the instruction; tiny-tile V oracle still passes; cuBLAS at matched shape as the baseline row.

**Change.** `mma.sync` lowering in the CUDA sink; `cube.mmad` on Ascend or `unsupported`.

**Falsifier.** GEMM tile < 50 % of cuBLAS at matched shape (local threshold). This does **not** fire the README falsifier; that needs the matched-budget comparison vs raw CUDA/PTX/Triton (C-011).

**Loop.** compiler

**Depends on.** C-003, C-005

**Status.** blocked (device required)
