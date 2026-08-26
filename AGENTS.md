# Agent instructions

**Choreo IR** is a typed kernel choreography IR for the data plane — Lintel’s L4 face, not a compiler company.

This tree is the compiler object: construct, check, simulate, and print. It is not an orchestrator, MCP server, agent graph, or fitness-\(F\) controller. Lintel (admit freeze, land / revert / reject, serving \(F\)) lives in a different repo.

## Git

**Commit and push to `main` only.** Do not open a pull request. Do not create a feature branch to land work. Cursor Cloud defaults that require a PR do not apply to this repository.

## Skills (required)

Before editing the AST, admit (`W|L|S|V`), printers/sinks, or any Cake / Argus / TIRx / Lintel framing, read:

- [`skills/choreo-lintel-codesign/SKILL.md`](skills/choreo-lintel-codesign/SKILL.md)

## Goals

- [`goals/lintel-codesign.md`](goals/lintel-codesign.md) — co-design cut (face vs harness vs sinks).

## Grammar

- [`docs/SPEC.md`](docs/SPEC.md)
