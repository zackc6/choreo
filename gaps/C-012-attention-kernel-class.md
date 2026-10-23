# C-012 — The Acme attention kernel is a tile choreography, not an attention kernel

**Gap.** Lintel's PoC kernel (`examples/poc/acme_attn_prefill.choreo.json`) is Q/Kt Copy → barrier → MMA into Acc; there is no online softmax, no running max, no second GEMM, so the schedule cannot state a FlashAttention-class kernel — the class the DeepInfer showcase needs.

**Carrier.** `examples/attn.json`: two-GEMM tile loop with a `Reduce` for row-max/row-sum between them; `fails/attn_sync.json` for the barrier between the reductions.

**Change.** To be found by the carrier: whether `Reduce` + `Pipeline` + roles can express online softmax, or a new sort is needed (a Tier-0 change — spec bump).

**Falsifier.** The kernel needs free-form scalar code between ops (then the schedule level is the wrong cell for this class, survey §1.1 of the proposal). Choreo falsifier #1.

**Loop.** compiler (coverage)

**Depends on.** C-008

**Status.** open
