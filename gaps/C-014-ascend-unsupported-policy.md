# C-014 — Ascend coverage in public CI is skip, not unsupported

**Gap.** `ccec` is not a public redist, so NPU-bin tests skip on GitHub. A skip is indistinguishable from 'this schedule cannot be lowered on Ascend'. The `unsupported` finding (C-003) needs a CI policy: which outcomes are recorded as findings and which as environment skips.

**Carrier.** CI summary that separates `unsupported` findings (from the sink, reproducible anywhere) from environment skips (no `ccec`).

**Change.** `scripts/ci_annotate.py` reports the two classes separately; a sink-level `unsupported` never depends on the toolchain being present.

**Falsifier.** A schedule reported `unsupported` on Ascend that lowers fine once `ccec` is present. Survey item: C4.

**Loop.** compiler (evidence discipline)

**Depends on.** C-003

**Status.** open
