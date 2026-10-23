# C-003 — No enumerated way to reach `cp.async` / `wgmma` / `mmad`

**Gap.** The AST has no `Copy.variant`, `Mma.variant` or `Barrier.kind`; an unregistered `attrs` key reaches `int(raw)` in `knobs.py` and raises an unlocalized `ValueError`. A legal schedule a sink cannot express is lowered silently. (`goals/self-evolving-ir.md` §1.2, §3.4; commit 3.)

**Carrier.** `examples/gemm.json` with `Mma.variant: plain` (today's behaviour) unchanged; `examples/fails/unknown_knob.json` with an ill-typed `num_stages` → `W` error naming the key; `Mma.variant: wgmma` on `ascend-a2` → `W` error at `m0`.

**Change.** Tier-1 enums with today's behaviour as `plain`; knob registry (name, type, range, consuming sink); `unexpressible` finding; pass-through metadata rows for Lintel pin keys so the handshake admits unchanged. `compiler_ver` bump.

**Falsifier.** The bench's walk cannot run unchanged against the bumped pin (consume contract broke). Survey item: C3 (widen enums behind admit).

**Loop.** compiler

**Depends on.** C-001

**Status.** open
