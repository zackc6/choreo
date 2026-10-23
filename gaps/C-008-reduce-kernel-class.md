# C-008 — `Reduce` has no carrier kernel

**Gap.** The AST has a `Reduce` op and the admit checks cover it, but `examples/` holds only `copy` and `gemm`; no reduce kernel is lowered by either sink, so the regression pair exercises three of six ops.

**Carrier.** `examples/reduce.json` (row-sum over a tile with `role` split load/reduce) plus `fails/reduce_role.json`; tensors/expected pair for V.

**Change.** Possibly none to the AST; the gap is whether `Reduce` as specified can be scheduled, checked and lowered on both families.

**Falsifier.** `Reduce` cannot express a tree reduction without a new op, or the Ascend sink cannot lower it. Choreo falsifier #3 (a simpler interface gets the same validation).

**Loop.** compiler (coverage)

**Depends on.** none

**Status.** open
