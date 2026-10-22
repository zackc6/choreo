# Instructions for coding agents (ChatGPT/Codex, Claude, Cursor)

This file is the briefing for any agent working in this repository. Read it fully before editing. It is one of four repositories maintained together under the same protocol; the protocol below is identical in all four, the sections above it are specific to this one.

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

## Validation gate (must pass on the branch before a batch is argued)

```bash
python3 -m pip install -q -e '.[dev]' && python3 -m pytest -q
```

`python3 -m pytest -q` passes (cubin tests may skip without `nvcc`; the public CI on `main` requires them). A representation, check, or sink change is an **IR-evolution commit** and must bump `compiler_ver` (new `%k`) and keep the previous allowlist passing.

## What a batch must say (the verdict comes first)

Every batch entry in the Review thread leads with: which of the three loops the change belongs to (application search must not rewrite `check.py`; IR evolution bumps `compiler_ver`); which falsifier in the README it bears on; whether `docs/LINTEL_CONSUME.md` and the handshake test still match Lintel's pin. A list of files changed without these is not a batch.

## The four repositories, and who owns what

| Repo | Role | Owns |
|---|---|---|
| [ai-compiler-survey](https://github.com/zackc6/ai-compiler-survey) | Referee. The thesis, evidence, and dated forecasts. | Whether the thesis still holds; what the evidence means. |
| [lintel](https://github.com/zackc6/lintel) | Control plane: written contract + design. | Schema field names, the three loops, kill switches. |
| [choreo](https://github.com/zackc6/choreo) | Data plane: kernel-schedule compiler. | Kernel encoding, admit findings, sinks, `compiler_ver`. |
| [agentic-compiler](https://github.com/zackc6/agentic-compiler) | Where the two run together. | The walk, the case corpus, drift report, performance table. |

The same two agents (Claude and ChatGPT/Codex) maintain all four under the same rule: **debate in the Review thread, agree, then squash-merge.** The maintainer (Zack) decides ties. Each agent's daily check covers all four `STATUS.md` files, not just the one it last edited.

Cross-repo rules:

1. **The survey is the referee, not an advocate.** Thesis and forecast changes happen only in the survey repo. A batch here that rests on a survey claim names the section. If work here produces evidence that bears on the thesis (a falsifier fired, a measured number), open a row in the **survey's** `STATUS.md` rather than arguing it here.
2. **A contract change starts in the owner repo.** Field names → Lintel. Kernel encoding, artifact kinds, `compiler_ver` → Choreo. It lands there by this protocol, then reaches agentic-compiler as a submodule-bump batch that updates `docs/DRIFT.md` and the drift tests in the same commit. Nobody edits a submodule's files from agentic-compiler.
3. **Three loops stay apart.** Application search (the walk) never edits the compiler; a compiler change is an IR-evolution commit on Choreo `main` with a `compiler_ver` bump; a controller change is a `policy_id` promotion with its own holdout. Say which loop a batch belongs to.
4. **Numbers keep their denominators.** A correctness-only result is not a speedup; a kernel speedup is not an application gain; a proxy labelled `measured: false` is not performance. Same evidence discipline as the survey.

## How the two agents work together (same as the survey)

1. **Claim before editing.** Add one row to the **Open batch** table at the top of `STATUS.md` (agent, scope, start date, status) and push it, or include it in your batch commit. If the other agent has an open row on overlapping scope, review its pushed work instead of editing the same files.
2. **Talk in the Review thread** in `STATUS.md`, newest entry first, one dated entry per reply, headed `**<YYYY-MM-DD HH:MM UTC> — <Agent>**` (ChatGPT headings must start `**<date> … ChatGPT` so the push detector fires). Each entry: verdict on the other agent's last batch (agree / object, naming file and line), open points, and what you will do next. Mark a point "resolved" with the commit hash. Do not argue in commit messages or in docs.
3. **Debate, then merge.** A content batch goes on a branch `claude/<topic>-<date>` or `chatgpt/<topic>-<date>`, **validated on that branch** (see "Validation gate" above). The author posts its argument in the Review thread on `main`: what changes, which owner-repo contract or survey section it rests on, the verdict items listed under "What a batch must say", and the proposed wording. The other agent replies agree / object per point with reasons. The branch is **squashed into one commit on `main`** (`git merge --squash`, never force-pushed, never a fast-forward or multi-parent merge for content) only after both agents have written "agree" on every disputed point or the maintainer has ruled. Review-thread entries, Open-batch rows, and pure fact fixes (a wrong number, a broken link, a failing build fixed) may go to `main` directly. If the other agent has not replied within two daily checks, ask the maintainer to rule; do not merge unilaterally.
4. **Merge rules.** On agreement: (a) squash with a `git log`-readable message — what changed, which contract or survey section it rests on, the loop it belongs to, the review rounds; (b) write a **"MERGE SUMMARY"** entry at the top of the Review thread (alignment with the survey and the owner contracts first, then changes, then agreement record, then commit hash) so the maintainer's merge-email watch can email it — a GitHub Action cannot send email, so record email as pending, never as sent; (c) delete the merged branch and any draft it superseded, and verify with `git ls-remote --heads origin`. Do not report deletion without checking.
5. **Sign commits** with your agent name (`Co-Authored-By: Claude` / `Co-Authored-By: ChatGPT`).
6. **Event-driven debate.** `.github/workflows/claude-reply.yml` runs Claude (`anthropics/claude-code-action/base-action@v1`, secret `ANTHROPIC_API_KEY`) when a push to `main` adds a ChatGPT-headed Review-thread entry or on a `chatgpt_replied` dispatch. `.github/workflows/codex-review.yml` runs a read-only Codex review (`openai/codex-action@v1`, secret `OPENAI_API_KEY`) when a `claude/*` branch is created or pushed, on manual dispatch, or on a `claude_replied` dispatch; it posts to `STATUS.md` and dispatches Claude. At most three rounds per side per branch; the loop stops when the branch is merged or deleted or a reply fails to publish. A workflow run is never approval: only the agreement procedure above authorizes a merge. Both secrets must be set on this repository for unattended runs.
7. **No PRs.** The debate replaces pull requests. Branches exist only to carry a batch to the thread; `main` is the only long-lived ref.

## What not to do

- Do not edit the other agent's stylistic choices; object in the thread, fix only facts, broken links, or failing builds.
- Do not change a contract field, a Kernel encoding, or `compiler_ver` outside the owner repo.
- Do not call a proxy a measurement, or a correctness result a speedup.
- Do not merge because a workflow passed. Green CI is a precondition, not agreement.
