# C-001 — `check`/`lower` do not bill their gates and a Kernel has no digest

**Gap.** No per-gate timing is reported by `check` or `lower`, so compile cost cannot be accounted (survey §4.3). A `Kernel` has no `kernel_digest`, so two candidates cannot be told apart except by diffing JSON. (`goals/self-evolving-ir.md` §2 item 1, §3 item 1; commit 1a.)

**Carrier.** `examples/gemm.json` run through `check` printing W/L/S/V wall times, and `kernel_digest` on the pin; `replay` CLI reproduces the lowering from `kernel.json` + `pin.json`.

**Change.** Choreo-local: timing on the check/lower result object; `kernel_digest` = sha256 of canonical Kernel JSON; `replay` CLI with source and toolchain-context halves (§3.5). No `compiler_ver` bump needed if output-only.

**Falsifier.** Timing overhead exceeds 10 % of W/L/S/V time, or source replay fails on the regression pair (sink nondeterminism). Survey item: §4.3 search cost.

**Loop.** compiler

**Depends on.** none

**Status.** open (proposed as commit 1a of `goals/self-evolving-ir.md`; lands after that proposal's PR is ruled)
