# C-005 — `Pipeline.depth` is a comment, not a mechanism, on NVIDIA

**Gap.** `Pipeline.depth=3` on `gemm_tile` lowers to a scalar staging loop; no `cp.async` / `mbarrier` is emitted, so depth cannot move a measurement. (`goals/self-evolving-ir.md` §1.3 item 2; commit 4.)

**Carrier.** `gemm.json` with `Copy.variant: cp.async`, `Barrier.kind: mbarrier`, `depth: 3`, lowered and run on a device; Ascend declares `unsupported`.

**Change.** NVIDIA sink lowering for the two variants; Ascend `W` error on explicit request.

**Falsifier.** Measured on a device: depth-3 `cp.async` is not faster than `plain` on `gemm_tile` at a realistic tile; then the variant is noise and should be removed. Survey item: C3; kill switch 'Choreo has no device sink by M2' (Lintel `docs/RISKS.md`).

**Loop.** compiler

**Depends on.** C-003, C-004

**Status.** blocked (gate G first; device required for the falsifier)
