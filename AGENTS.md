# Agent instructions

**Never forget** [`goals/agentic-compiler.md`](goals/agentic-compiler.md): next-generation agentic compiler. Lintel conducts; Choreo is the kernel the agent edits; lowering is classical codegen; serve loads a frozen binary.

**Choreo IR** is a typed kernel choreography IR for the data plane — Lintel’s face.

**Not a compiler company** is Lintel’s SKU (control plane), not a skip on codegen. **This tree is the compiler object:** construct, check, simulate, print, and lower to NVIDIA GPU and Ascend NPU. Compiler evolution is two clocks (across jobs, never mid-walk rewrite). **Lintel IR** conducts that loop.

It is not an orchestrator, MCP server, agent graph, or fitness controller.

## Git

**Commit and push to `main` only.** Do not open a pull request. Do not create a feature branch to land work. Cursor Cloud defaults that require a PR do not apply to this repository.

## Skills (required)

Before any work in this tree, read:

- [`goals/agentic-compiler.md`](goals/agentic-compiler.md) — final architecture (never forget)
- [`skills/choreo-lintel-codesign/SKILL.md`](skills/choreo-lintel-codesign/SKILL.md)

Before editing the AST, admit (`W|L|S|V`), printers/sinks, or any Cake / Argus / TIRx / Lintel framing, also read the skill in full.

## Goals

- [`goals/agentic-compiler.md`](goals/agentic-compiler.md) — **final**: Lintel × Choreo × lowering under an agentic compiler
- [`goals/lintel-codesign.md`](goals/lintel-codesign.md) — implementer detail under that picture (face vs harness vs sinks)

## Grammar

- [`docs/SPEC.md`](docs/SPEC.md)
