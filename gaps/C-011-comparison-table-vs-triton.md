# C-011 — Falsifiers #1 and #3 are not testable

**Gap.** `README.md` falsifier #1 (raw CUDA/PTX/Triton matches or beats this representation under a matched budget) and #3 (a simpler interface gets the same attainable performance and validation) have no table to land in: no kernel in `examples/` has a raw-Triton twin on the same task.

**Carrier.** `comparison/<kernel>.md` per regression kernel: Choreo schedule vs raw Triton (the sidecar printer's output is *not* the baseline; a hand-written Triton kernel is), admit outcome, lowering outcome, latency with denominator and `measured` label.

**Change.** Triton-only baseline first (cheapest; the sidecar exists); hand CUDA and CCE per sink family later. Numbers come only from the bench's measurement job once a device exists; until then rows say `measured: false`.

**Falsifier.** This is the table the README falsifiers fire in. Survey item: §5.2 step 3; survey falsification discipline §5.3.

**Loop.** compiler (evidence)

**Depends on.** C-009

**Status.** open
