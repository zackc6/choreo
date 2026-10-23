# C-009 — Not every example carries its tested boundary

**Gap.** `goals/self-evolving-ir.md` §1.1b corollary: the ATen-shaped contract (`params` + `Yield` + `tensors`/`expected`) is what the regression pair should be tested against, `copy` and `gemm` have the `tensors`/`expected` pair; of the nine `fails/` cases only `value_mismatch` does, so eight rejects are never checked against a boundary and a future carrier has no rule to follow.

**Carrier.** Every `examples/*.json` and every `fails/*.json` that reaches V has a `*.tensors.json` / `*.expected.json`.

**Change.** Tier-0 hygiene; no `compiler_ver` bump.

**Falsifier.** A kernel whose boundary cannot be stated at a tiny shape (then V cannot gate it and the kernel must say so).

**Loop.** compiler (hygiene)

**Depends on.** none

**Status.** open
