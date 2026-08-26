# Agent instructions

**Choreo IR** is a typed kernel choreography IR for the data plane — Lintel’s L4 face.

**Not a compiler company** is Lintel’s SKU (control plane), not a skip on codegen. **This tree is the compiler object:** construct, check, simulate, print, and lower to NVIDIA GPU and Ascend NPU. Year-1 is Horizon A / M1-lite (L4-only search). L5 is assumed; ISA designed later. Compiler evolution is two clocks (T5 across jobs, never M3 mid-walk). **Lintel IR** conducts that loop.

It is not an orchestrator, MCP server, agent graph, or fitness-\(F\) controller.

## Git

**Commit and push to `main` only.** Do not open a pull request. Do not create a feature branch to land work. Cursor Cloud defaults that require a PR do not apply to this repository.

## Skills (required)

Before editing the AST, admit (`W|L|S|V`), printers/sinks, or any Cake / Argus / TIRx / Lintel framing, read:

- [`skills/choreo-lintel-codesign/SKILL.md`](skills/choreo-lintel-codesign/SKILL.md)

## Goals

- [`goals/lintel-codesign.md`](goals/lintel-codesign.md) — co-design cut (face vs harness vs sinks).

## Grammar

- [`docs/SPEC.md`](docs/SPEC.md)
