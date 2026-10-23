# C-007 — Every candidate pays the full toolchain

**Gap.** No stage cache exists; toolchain runs once per candidate even when the lowered text is unchanged. (`goals/self-evolving-ir.md` §2 item 2; commit 6.)

**Carrier.** A 100-candidate walk from the bench replayed with caches keyed by full context; hit rate reported on the measure event.

**Change.** Stage caches for check / lower / toolchain keyed by content + toolchain context, not by `%k`.

**Falsifier.** Hit rate < 20 % over a 100-candidate walk; caching is then complexity without payback. Survey §4.3.

**Loop.** compiler

**Depends on.** C-001

**Status.** open
