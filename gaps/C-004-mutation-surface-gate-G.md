# C-004 — Whole-Kernel replacement vs typed transform trace is undecided

**Gap.** Choreo is D1 (agent re-emits the whole Kernel). D2 (typed transform ops over a stable payload) is the Halide / MetaSchedule / MLIR-Transform line. The choice decides what `mutation` *is* and where rejects land. (`goals/self-evolving-ir.md` §1.1c; gate G.)

**Carrier.** The §1.1c experiment: four arms (whole-Kernel, transform trace, knob-only structured search, autotuned Triton/Gluon) on the regression pair plus holdout, matched budgets; report valid-candidate rate, reject-acted-on rate, best result with `measured` label, cost, holdout transfer.

**Change.** Not a commit: a recorded decision. If (2) matches (1) with higher valid rate, the surface becomes the trace and §3.2 `mutation` is the trace; if (3) matches both, the schedule tier is not earning its cost at this corpus size.

**Falsifier.** (1) no better than (2) on both valid rate and best result shows the current D1 position wrong. On a two-kernel corpus 'inconclusive' is a recorded outcome. Survey §5.2 step 3 (compare representations on the same tasks).

**Loop.** compiler (decision)

**Depends on.** C-003, C-009, C-010

**Status.** blocked (needs holdout C-010 and a device for the `measured: true` arm; may run correctness-only and say so)
