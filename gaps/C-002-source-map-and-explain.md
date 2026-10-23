# C-002 — An emitted line cannot name its op

**Gap.** Printers comment each block but there is no `source_map.json` from sink output lines back to op ids, so a toolchain diagnostic cannot be mapped to a `node`. (`goals/self-evolving-ir.md` §4; commit 2.)

**Carrier.** Inject 20 toolchain errors into lowered `gemm.json` text; each must map to the right op id. `explain` prints a per-partition timeline; `diff` prints the mutation list between `gemm.json` and a one-field variant.

**Change.** `source_map.json` sidecar emitted by every printer; toolchain diagnostics mapped to `node`; `explain` and `diff` CLIs.

**Falsifier.** Mapped diagnostics wrong for > 1 in 20 injected errors on the regression pair. Choreo falsifier #2 (rejects must name a program point).

**Loop.** compiler

**Depends on.** C-001

**Status.** open
