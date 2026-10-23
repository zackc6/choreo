# Instructions for coding agents (ChatGPT/Codex, Claude, Cursor)

This file is the briefing for any agent working in this repository. Read it fully before editing. It is one of four repositories maintained together. The ownership rules below are shared by all four; the **IR-increment loop** below is shared by the two IR repositories (lintel, choreo), while the survey and agentic-compiler keep their own working rules.

## What this repository is

**Never forget** [`goals/agentic-compiler.md`](goals/agentic-compiler.md): next-generation agentic compiler. Lintel conducts application search; Choreo is the kernel-schedule compiler the agent edits; lowering is classical codegen; serve loads a frozen binary. Five functions have owners from the start: represent, transform, map, validate, coordinate.

**Choreo IR** is the kernel schedule for represent, intra-kernel coordinate, validate, and map: tiles, roles, barriers, layouts. A fixed band count is not a law. Cross-kernel dependencies and the application contract stay with Lintel.

**Three loops.** Application search edits a kernel under a pinned compiler version. IR evolution is a separate commit on `main` (representation, checks, or sinks). Controller improvement is not this tree. Judgment against the survey through 2026-09-23: [`goals/lintel-codesign.md`](goals/lintel-codesign.md).

It is not an orchestrator, MCP server, agent graph, or fitness controller.

## Skills (required)

Before any work in this tree, read:

- [`goals/agentic-compiler.md`](goals/agentic-compiler.md) — early architecture and function coverage (never forget)
- [`skills/choreo-lintel-codesign/SKILL.md`](skills/choreo-lintel-codesign/SKILL.md)

Before editing the AST, admit (`W|L|S|V`), printers/sinks, or any Cake / Argus / TIRx / Lintel framing, also read the skill in full.

## Goals

- [`goals/agentic-compiler.md`](goals/agentic-compiler.md) — early architecture: Lintel × Choreo × lowering, five functions, three loops
- [`goals/lintel-codesign.md`](goals/lintel-codesign.md) — function-coverage judgment, plus implementer detail

## Grammar

- [`docs/SPEC.md`](docs/SPEC.md)

### In one line

**Choreo IR** is the kernel-schedule compiler the agent edits: closed typed AST, W/L/S/V admit, CPU interpreter, CUDA C++ / CCE sinks with `nvcc` / `ccec`. It owns the Kernel encoding, the admit findings, and the artifact kinds.

**This repo owns:** Kernel encoding, admit gates and their localized findings, sinks, `compiler_ver`.

**This repo does not own:** schema field names (Lintel owns those); application search, budgets, and serving (Lintel's design, agentic-compiler's walk); the thesis and forecasts (the survey).

## Validation gate (must pass on the branch before an increment is argued)

```bash
python3 -m pip install -q -e '.[dev]' && python3 -m pytest -q
```

`python3 -m pytest -q` passes (cubin tests may skip without `nvcc`; the public CI on `main` requires them). A representation, check, or sink change is an **IR-evolution commit** and must bump `compiler_ver` (new `%k`) and keep the previous allowlist passing.

## What an increment must say (the verdict comes first)

Every increment entry in the Review thread leads with its gap id and: which of the three loops the change belongs to (application search must not rewrite `check.py`; IR evolution bumps `compiler_ver`); which falsifier in the README it bears on; whether `docs/LINTEL_CONSUME.md` and the handshake test still match Lintel's pin. A list of files changed without these is not an increment.

## The four repositories, and who owns what

| Repo | Role | Owns |
|---|---|---|
| [ai-compiler-survey](https://github.com/zackc6/ai-compiler-survey) | Referee. The thesis, evidence, and dated forecasts. | Whether the thesis still holds; what the evidence means. |
| [lintel](https://github.com/zackc6/lintel) | Control plane: written contract + design. | Schema field names, the three loops, kill switches. |
| [choreo](https://github.com/zackc6/choreo) | Data plane: kernel-schedule compiler. | Kernel encoding, admit findings, sinks, `compiler_ver`. |
| [agentic-compiler](https://github.com/zackc6/agentic-compiler) | Where the two run together. | The walk, the case corpus, drift report, performance table. |

The same two agents (Claude and ChatGPT/Codex) maintain all four. In the two IR repositories the rule is the **IR-increment loop** below; in every repository the maintainer (Zack) approves every merge and decides ties. Each agent's daily check covers all four `STATUS.md` files, not just the one it last edited.

Cross-repo rules:

1. **The survey is the referee, not an advocate.** Thesis and forecast changes happen only in the survey repo. An increment here that rests on a survey claim names the section. If work here produces evidence that bears on the thesis (a falsifier fired, a measured number), open a row in the **survey's** `STATUS.md` rather than arguing it here.
2. **A contract change starts in the owner repo.** Field names → Lintel. Kernel encoding, artifact kinds, `compiler_ver` → Choreo. It lands there by this protocol, then reaches agentic-compiler as a submodule-bump batch that updates `docs/DRIFT.md` and the drift tests in the same commit. Nobody edits a submodule's files from agentic-compiler.
3. **Three loops stay apart.** Application search (the walk) never edits the compiler; a compiler change is an IR-evolution commit on Choreo `main` with a `compiler_ver` bump; a controller change is a `policy_id` promotion with its own holdout. Say which loop an increment belongs to.
4. **Numbers keep their denominators.** A correctness-only result is not a speedup; a kernel speedup is not an application gain; a proxy labelled `measured: false` is not performance. Same evidence discipline as the survey.

## The IR-increment loop (how the two agents work together in the two IR repos)

Lintel (control-plane IR) and Choreo (data-plane IR) are **IR-design repositories**. They solve different problems and must progress independently, so the unit of work here is not a "batch" but an **increment**, and the backlog is `gaps/` (format and sources: `gaps/README.md`). The survey and agentic-compiler keep their own protocols; the cross-repo rules above are unchanged. Maintainer's rules, 23 October 2026.

1. **An increment is: gap → IR change → carrier → falsifier.** It opens only when all four are in the branch. The gate (see "Validation gate") is a precondition to opening the thread, not a subject of it. Debate is allowed on the **Falsifier** and the **Change**; the gap and the carrier are facts.
2. **IR-design stage.** Until both IRs are decided, examples and tests are **illustrative carriers**, not a correctness contract: the gate asks "do schemas validate, do examples parse, does the carrier admit/reject as its gap says" — nothing more. Do not add principle-test suites or carrier generators yet (`gaps/README.md`, "Deferred on purpose"). Do not argue about validation evidence in the thread: the workflow attaches the gate run to the branch, and the maintainer sees it on the pull request; a missing citation of a run URL is not an objection.
3. **Parallel gaps, one owner each.** The **Open gaps** table at the top of `STATUS.md` holds **up to three gaps in flight per repo**, one row per gap: `gap id, agent, branch, started, status`. Claim a row before editing. One agent owns an increment; the other reviews it. If a gap file says `mode: compete`, both agents may put an increment on their own branch for the same gap and the thread compares the two against the falsifier. Gaps that do not share files proceed in parallel; schemas are versioned (`v1` beside `v0`) and the AST is closed, so they rarely conflict.
4. **Branch and thread.** An increment lives on `claude/<gap-id>-<date>` or `chatgpt/<gap-id>-<date>`. Thread entries go in the Review thread in `STATUS.md`, newest first, headed `**<YYYY-MM-DD HH:MM UTC> — <Agent> [<gap id>]**` (ChatGPT headings must contain "ChatGPT" so the push detector fires). An entry says: which loop; which falsifier; agree / object per point naming file and line; what you will do next. **At most two rounds per side per increment.** At the cap, stop and hand the increment to the maintainer; do not post a third round.
5. **The maintainer approves every merge.** When both agents have written "agree" on every open point, or the round cap is reached, the author opens a **pull request** from the branch to `main` (title = increment summary; body = the four parts of the increment, the gate run on the head SHA, the thread entries, the agreement record or the open points for the maintainer to rule on) and requests the maintainer's review. Nothing merges without that approval; there is no auto-land, no tie-break rule, and no deadline that lands an increment on its own. After approval: squash to one commit (what changed, the gap id, the loop, the review rounds), write a **MERGE SUMMARY** entry at the top of the Review thread (alignment with the owner contracts and the survey first, then the change, then the agreement record, then the commit hash; email recorded as pending, never sent), update the gap's **Status** to `closed (<commit>)` or `falsified (<commit>)`, clear the Open-gaps row, delete the branch and verify with `git ls-remote --heads origin`.
6. **What may go to `main` directly:** Review-thread entries, Open-gaps rows, new gap files (backlog, not design), and pure fact fixes (a wrong number, a broken link, a failing build fixed). Nothing else.
7. **Sign commits** with your agent name (`Co-Authored-By: Claude` / `Co-Authored-By: ChatGPT`).
8. **Event-driven debate.** `.github/workflows/claude-reply.yml` runs Claude (`anthropics/claude-code-action/base-action@v1`, secret `ANTHROPIC_API_KEY`) when a push to `main` adds a ChatGPT-headed Review-thread entry or on a `chatgpt_replied` dispatch. `.github/workflows/codex-review.yml` runs a read-only Codex review (`openai/codex-action@v1`, secret `OPENAI_API_KEY`) when a `claude/*` branch is created or pushed, on manual dispatch, or on a `claude_replied` dispatch; it posts to `STATUS.md` and dispatches Claude. The round cap is **two** per side per increment; the loop stops when the branch is merged or deleted, a reply fails to publish, or the cap is reached. A workflow run is never approval.
9. **PRs are for the maintainer, not for the debate.** The two agents argue in the thread, not in PR comments. `main` is the only long-lived ref.
10. **Cross-repo coupling is one-directional.** The bench (agentic-compiler) files gaps here; it never designs. A contract change lands here versioned, then reaches the bench as a submodule-bump batch on the bench's own cadence. Lintel and Choreo never wait on each other inside a one-version compatibility window: the consumer adopts `vN+1` before the owner publishes `vN+2`.
11. **Progress is counted in gaps**, not in merges: the MERGE SUMMARY records gap opened → increment opened → merged, and the weekly check reports gaps closed and gaps falsified per repo.

## What not to do

- Do not edit the other agent's stylistic choices; object in the thread, fix only facts, broken links, or failing builds.
- Do not change a contract field, a Kernel encoding, or `compiler_ver` outside the owner repo.
- Do not call a proxy a measurement, or a correctness result a speedup.
- Do not merge because a workflow passed. Green CI is a precondition, not agreement.
- Do not argue validation evidence in the thread; the gate run is on the branch and the maintainer sees it on the PR.
- Do not open an increment without a gap file, or a second increment on a gap that is not `mode: compete`.
- Do not build carrier generators or principle-test suites before both IRs are decided.
