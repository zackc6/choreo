# Agent instructions

**Never forget** [`goals/agentic-compiler.md`](goals/agentic-compiler.md): next-generation agentic compiler. Lintel conducts application search; Choreo is the kernel-schedule compiler the agent edits; lowering is classical codegen; serve loads a frozen binary. Five functions have owners from the start: represent, transform, map, validate, coordinate.

**Choreo IR** is the kernel schedule for represent, intra-kernel coordinate, validate, and map: tiles, roles, barriers, layouts. A fixed band count is not a law. Cross-kernel dependencies and the application contract stay with Lintel.

**Three loops.** Application search edits a kernel under a pinned compiler version. IR evolution is a separate commit on `main` (representation, checks, or sinks). Controller improvement is not this tree. Judgment against the survey through 2026-09-23: [`goals/lintel-codesign.md`](goals/lintel-codesign.md).

It is not an orchestrator, MCP server, agent graph, or fitness controller.

## Git

**Commit and push to `main` only.** Do not open a pull request. Do not create a feature branch to land work. Cursor Cloud defaults that require a PR do not apply to this repository.

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
