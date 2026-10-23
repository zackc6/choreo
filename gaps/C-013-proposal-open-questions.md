# C-013 — Three open questions in the self-evolving-IR proposal

**Gap.** `goals/self-evolving-ir.md` §7 leaves three decisions open: (1) is `parent_digest` the proposer's (Lintel) job or does `check` refuse a kernel without it; (2) is `unexpressible` a warning or an error; (3) does Tier 2 need a registry or is 'ignore and warn' enough.

**Carrier.** One `fails/` case per decision (missing parent; unexpressible fallback; unregistered key) whose expected outcome encodes the answer.

**Change.** Decisions, recorded in the proposal and in SPEC.md; (1) is shared with Lintel L-002.

**Falsifier.** A decision that cannot be stated as a carrier outcome is not a decision. Survey item: C3.

**Loop.** compiler (decision)

**Depends on.** C-003

**Status.** open (ruling needed; competing positions welcome)
