# Gaps — the IR-increment backlog

This repository designs an IR. Work on it is an **increment**, and every increment starts
from a **gap**: a concrete case the current representation cannot express, check, decide,
or lower. This directory is the backlog of such gaps. The loop that consumes it is in
`AGENTS.md` ("The IR-increment loop").

The same format is used in `zackc6/lintel` (control-plane IR, ids `L-nnn`) and
`zackc6/choreo` (data-plane IR, ids `C-nnn`).

## One gap, one file

`gaps/<ID>-<slug>.md`, with these sections in this order. Keep each under a screen.

| Section | What goes there |
|---|---|
| **Gap** | The case the IR cannot handle today, stated as a fact about a file or a walk — never as a preference. |
| **Carrier** | The example that will exercise it: an `examples/` file (and for Choreo a `fails/` twin). At the IR-design stage carriers are **illustrative**, not a correctness contract. |
| **Change** | The schema / AST / check / sink change sketched in one paragraph. Versioned, never mutated in place (`v0` stays; `v1` lands beside it). |
| **Falsifier** | What result would show the change did not earn its cost. Tie it to the repo's own falsifier list and name the survey item (`docs/SURVEY_MAP.md` row in Lintel; `goals/lintel-codesign.md` in Choreo). |
| **Loop** | application / compiler / controller — which of the three loops the change belongs to. |
| **Depends on** | Other gap ids, or "none". A gap blocked by a gate (e.g. the controller-development gate) says so. |
| **Status** | `open` · `in flight (<agent>, <branch>)` · `closed (<commit>)` · `falsified (<commit>)` · `blocked (<why>)`. |

Debate is allowed on **Falsifier** and **Change** only. Gap and Carrier are facts; if they
are wrong, fix them as a fact fix.

## Where gaps come from

1. **The bench.** When a walk in `zackc6/agentic-compiler` hits a representation limit (a
   reject that cannot name a program point, a kernel the schedule cannot express, a decision
   the admit record cannot carry, a cache key that collides), the bench files a gap here. The
   bench never designs; it files gaps and produces numbers.
2. **The maintainer.**
3. **An agent's own survey.** Standing rule: IR-design work starts from a survey of existing
   SOTA IRs / DSLs and recent agentic-friendly IRs, not only the systems already cited. One
   survey per gap *class*, recorded once (e.g. `goals/ir-landscape.md`), not per increment.

Filing a gap is a backlog operation, not a design decision: a new gap file may go to `main`
directly, like an Open-batch row. Changing a gap's **Falsifier** or **Change**, or closing it,
travels with the increment's pull request.

## Closing

A merged increment moves its gap's status to `closed (<squash commit>)`. An increment whose
falsifier fired is recorded as `falsified (<commit>)` and stays in the directory: a negative
result is evidence. If it bears on the thesis, it also becomes a source row in the survey's
`STATUS.md` (the survey is the referee).

## Deferred on purpose

Carrier **generators** (a schedule enumerator over the closed AST; session-trace generation
from bench walks) are not built until both IRs are decided. Hand-written carriers until then.
