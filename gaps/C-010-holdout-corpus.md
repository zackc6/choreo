# C-010 — The regression pair is a compatibility set, not a holdout

**Gap.** Every Tier-1 change is designed against `copy` / `gemm_tile`, so passing them shows nothing broke, not that the change generalizes. Survey §5.2 step 6 needs a separately versioned holdout no proposal cites or tunes on. (`goals/self-evolving-ir.md` §1.2 rule 3.)

**Carrier.** `holdout/` with its own version tag, at least two kernels of classes not in `examples/` (candidates: C-008 reduce, C-012 attention), never referenced from a gap's Change.

**Change.** Directory + rule: a Tier-1 increment reports holdout results but may not edit holdout in the same PR.

**Falsifier.** The holdout is small enough that every proposal passes it trivially (then it is not a holdout). Survey §5.2 step 6.

**Loop.** compiler (evidence discipline)

**Depends on.** C-008

**Status.** open
