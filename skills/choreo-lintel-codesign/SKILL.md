---
name: choreo-lintel-codesign
description: >-
  Co-design rules for Choreo (data plane) vs Lintel (control plane).
  Use when changing the Kernel AST, admit (W|L|S|V), printers/sinks, README/SPEC,
  or anything that mentions Cake, Argus, TIRx, Lintel, harness, freeze, or targets
  (GPU / Ascend).
---

# Choreo × Lintel co-design

Read [`goals/lintel-codesign.md`](../../goals/lintel-codesign.md) for the product cut. This skill is the implementer SOP for **this repo**.

## When to use

- Editing `choreoir/`, `docs/SPEC.md`, `README.md`, `goals/`, or this skill.
- Adding ops, spaces, roles, checks, printers, or JSON fields.
- Discussing Cake, Argus, TIRx, “compiler evolution,” or dual-target (GPU / Ascend).
- Any change that could grow a workflow, serving \(F\), or a second live dialect.

## Invariants (never break)

1. **Choreo is the data plane.** Closed Kernel AST, `check()`, CPU sim, deterministic printers/sinks. Kind 1: a program.
2. **Lintel is the control plane** (other repo). Land / revert / reject, freeze / `%k`, serving \(F\), evidence routing. Kind 4 / kind 3.
3. **Do not mix kinds.** Do not put MCP, agent DAGs, budget/stop, or land/revert in `choreoir`. Do not let Lintel invent Choreo keywords without a spec bump in this tree.
4. **Yes as a typed L4 face for Lintel. No as a compiler company. No as Cake + Argus + TIRx glued into one dialect.**
5. **Union of admit signals, not languages.** W/L/S/V may draw on Cake / Argus / TIRx *mechanisms*. Do not average those IRs. Third cell: cheap `shape × stride` so `{where: L}` can fire. No year-1 Z3. No CuTe work-partition.
6. **Lowering is classical.** Interpreter and sinks are deterministic functions of the AST. Not LLM calls. The model does not rewrite the dialect (mlirAgent negative).
7. **`check() == []` is not serving \(F\).** Findings are T2-color compiler diagnostics. \(F\) lives in Lintel.

## Cake split (who owns what)

From arXiv:2608.12629 §1–4, three pieces; **only (3) is a Lintel object**:

| Piece | This repo may contain | Lintel may contain |
|---|---|---|
| (1) Typed IR | Yes — Choreo AST / JSON | Carry the program; do not fork a second face |
| (2) Lowering | Sinks that consume the schedule; or pin `@tirx.v0` / `@tilelang.ascend` | No ISA, no cubin compiler |
| (3) Evolving harness | No workflow. Choreo *undergoes* PRs | *Conducts* the loop: classify fail, corpus-gate, merge, freeze |

**Compiler evolution:** Choreo is the artifact that changes (`choreoir` PRs). Lintel is the process that lands them. Choreo does not self-expand when a fail recurs.

Year-1: evolve **gates + sinks**, not vocabulary.

- Allowed without spec bump: deeper W/L/S/V, cost estimate as a pure function, sinks that actually consume `Barrier` / `Pipeline.depth` / layout / space / partition.
- Spec bump required: new op, space, role, or memory enum. Same day: a check that admits it **and** a sink that lowers it. Syntax without effects is forbidden.
- Never here: serving \(F\), freeze, land/revert, “agents write the compiler” as a runtime feature.

## Lowering honesty

Do not describe `choreoir.print_triton` as a compiler. Today it takes the first `Copy` or `Mma`, emits a generic `@triton.jit`, and writes roles / barriers / pipeline depth / spaces as comments. `BLOCK_M` is not filled from the AST. There is no named target.

A real sink must:

1. Take roles, barriers, pipeline depth, layouts, and memory spaces as **inputs to codegen**.
2. Pick real instructions for a **named** target (e.g. WGMMA vs `tcgen05`; MTE vs Cube).
3. Emit a cubin or NPU bin you can measure.

Refuse codegen (or label the output a sketch) if `check()` has `severity=error`. The CLI `print` path must not pretend admit passed if it did not run `check`.

In-tree falsifier: `examples/gemm.json` already has Copy → Barrier → Mma. A compiler would emit producer-consumer code. Do not wait on `choreo.attn.d3.w4` to admit the stencil.

The demo that fails the product test is still “we compiled Choreo.”

## Dual target (GPU and Ascend)

Two SKUs, two sinks, **one** Finding schema. Not one averaged dialect.

- v0.1 `gmem|smem|tmem|regs` and warp `load|math|store` are NVIDIA-shaped. Do not rename `smem` → L1 and call it portable.
- Spaces / roles are **target-indexed** once a `target` field exists (`cuda-sm100`, `ascend-a2`, …).
- GPU sink: `@tirx.v0` (or Triton / CUTLASS). Ascend sink: `@tilelang.ascend` / Ascend C. `@cake.v0` is a door if they open — wrap, do not become open Cake.
- Gluon / TLX / TileLang / CUDA Tile IR are sinks to print *into*, not second live faces.
- Sequence: one kernel, one target, real binary, then the second target. Do not add a second stencil printer as “Ascend support.”

## Year-1 cardinality and M2

Allowlist two complete kernels. Payload is kind 1; the deal is kind 2. Do not grow ops to look like Cake IR.

If there is still no cubin / NPU bin, **M2 kill switch:** `@triton.v0` knobs. If kind 2 wins the SKU, this mutation surface shrinks to knobs. Do not keep the AST as a brochure with knobs taped on.

## Implementation checklist

When changing this repo, ask:

- [ ] Does this add control-plane behavior? If yes, stop — belongs in Lintel.
- [ ] Does this glue Cake + Argus + TIRx *languages* (layout algebra + hidden layout + TVM in the pin)? If yes, stop.
- [ ] Does a new AST node have a check **and** a sink that consumes it?
- [ ] Is `print_triton` still described as a sketch unless it consumes the schedule?
- [ ] Are GPU and Ascend still separate spaces/roles (no unified `onchip`)?
- [ ] Are findings still `{gate, node, where?}` with no scraped stdout as the agent API?

## Do not

- Sell `role` as Cake’s numbers (1.144× / 2.05×). Those need a cubin sink + evolving harness.
- Add Z3, CuTe work-partition, or a second year-1 compiler.
- Put TVM in the pin just to wrap TIRx; `@tirx.v0` is an optional door for TVM-native partners.
- Treat Helion / KernelEvolve / TritorX / generic coding agents as year-1 faces (no W/L/S/`%k`).
- Run mlirAgent-style “rewrite the dialect” experiments as the mutation API.

## Pointers

- Goal: `goals/lintel-codesign.md`
- Grammar / admit: `docs/SPEC.md`
- AST / check / printer: `choreoir/`
- Cake: arXiv:2608.12629
- Argus: arXiv:2604.18616
- TIRx: https://tvm.apache.org/2026/06/22/tirx
