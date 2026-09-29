# Agent instructions

**Never forget** [`goals/agentic-compiler.md`](goals/agentic-compiler.md): next-generation agentic compiler. Lintel conducts application search; Choreo is the kernel-schedule compiler the agent edits; lowering is classical codegen; serve loads a frozen binary.

**Choreo IR** is that kernel schedule: tiles, roles, barriers, layouts. Starting scope, not a fixed band count.

**Three loops.** Application search edits a kernel under a pinned compiler version. IR evolution is a separate commit on `main` (representation, checks, or sinks). Controller improvement is not this tree. Judgment against the survey through 2026-09-23: [`goals/lintel-codesign.md`](goals/lintel-codesign.md).

It is not an orchestrator, MCP server, agent graph, or fitness controller.

## Git

**Commit and push to `main` only.** Do not open a pull request. Do not create a feature branch to land work. Cursor Cloud defaults that require a PR do not apply to this repository.

## Skills (required)

Before any work in this tree, read:

- [`goals/agentic-compiler.md`](goals/agentic-compiler.md) — starting architecture (never forget)
- [`skills/choreo-lintel-codesign/SKILL.md`](skills/choreo-lintel-codesign/SKILL.md)

Before editing the AST, admit (`W|L|S|V`), printers/sinks, or any Cake / Argus / TIRx / Lintel framing, also read the skill in full.

## Goals

- [`goals/agentic-compiler.md`](goals/agentic-compiler.md) — starting architecture: Lintel × Choreo × lowering, three loops
- [`goals/lintel-codesign.md`](goals/lintel-codesign.md) — scope and IR-evolution judgment, plus implementer detail

## Grammar

- [`docs/SPEC.md`](docs/SPEC.md)

## Cursor Cloud specific instructions

Python 3.12 and g++ are on the default image. Install is `python3 -m pip install --user -e '.[dev]'`, then `CHOREO_FETCH_NVCC=1` so `ensure_nvcc()` places official nvcc 12.8 in `~/.local/cuda-nvcc`. `~/.local/bin` is not on `PATH`; use `python3 -m pytest` and `python3 -m choreoir`.

Match CI with `CHOREO_REQUIRE_NVCC=1 python3 -m pytest -q`. `ccec` is not a public redistributable, so Ascend NPU-bin tests skip. A working product check is `python3 -m choreoir check examples/copy.json`, `sim` on `examples/gemm.json` with its tensor fixtures, and `lower examples/gemm.json --emit cubin` (ELF cubin).
