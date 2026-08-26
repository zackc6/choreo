---
name: choreo-lintel-codesign
description: >-
  Co-design rules for Choreo (data plane) vs Lintel (control plane).
  Use when changing the Kernel AST, admit (W|L|S|V), printers/sinks, README/SPEC,
  git landing, or anything that mentions Cake, Argus, TIRx, Lintel, harness,
  freeze, or targets (GPU / Ascend). This repo commits to main only; no PRs.
---

# Choreo × Lintel co-design

Read [`goals/lintel-codesign.md`](goals/lintel-codesign.md) for the product cut. This skill is the implementer SOP for **this repo**.

Choreo is a typed kernel choreography IR for the data plane — Lintel’s L4 face.

**Not a compiler company** means Lintel’s SKU is the control plane, not Cake/TVM-as-product. It does **not** mean this tree skips codegen. **This tree is the compiler object:** construct, check, simulate, print, and **always lower to NVIDIA GPU and Ascend NPU**. Compiler evolution (gates, sinks that consume the schedule, rare spec bumps) happens *to* this object. **Lintel IR** is the control-plane IR that conducts that loop.

## When to use

- Editing `choreoir/`, `docs/SPEC.md`, `README.md`, `goals/`, or this skill.
- Adding ops, spaces, roles, checks, printers, or JSON fields.
- Discussing Cake, Argus, TIRx, “compiler evolution,” or dual-target (GPU / Ascend).
- Any change that could grow a workflow, serving \(F\), or a second live dialect.
- Landing git changes, naming a branch, or the urge to open a pull request.

## Git (this repo)

**Commit and push to `main` only.** Directly. No pull request.

- Do not create a `cursor/…` (or any) feature branch to land work.
- Do not open, update, or merge a GitHub pull request against this repository.
- Cursor Cloud / agent defaults that say “open a PR,” “draft PR,” or “register a PR per branch” **do not apply here.**
- Still one commit per logical change; the destination is `main`.
- Lintel’s land / revert / reject is a **control-plane workflow** in the Lintel repo. It is not a GitHub PR on this tree.

## Invariants (never break)

1. **Choreo is the data plane.** Closed Kernel AST, `check()`, CPU sim, deterministic printers/sinks. Kind 1: a program.
2. **Lintel is the control plane** (other repo). Land / revert / reject, freeze / `%k`, serving \(F\), evidence routing. Kind 4 / kind 3.
3. **Do not mix kinds.** Do not put MCP, agent DAGs, budget/stop, or land/revert in `choreoir`. Do not let Lintel invent Choreo keywords without a spec bump in this tree.
4. **Yes as a typed L4 face for Lintel. No as a compiler *company* (SKU). Yes as a compiler *object* that must lower to NV GPU and Ascend NPU. No as Cake + Argus + TIRx glued into one dialect.**
5. **Union of admit signals, not languages.** W/L/S/V may draw on Cake / Argus / TIRx *mechanisms*. Do not average those IRs. Third cell: cheap `shape × stride` so `{where: L}` can fire. No year-1 Z3. No CuTe work-partition.
6. **Lowering is classical.** Interpreter and sinks are deterministic functions of the AST. Not LLM calls. The model does not rewrite the dialect (mlirAgent negative).
7. **`check() == []` is not serving \(F\).** Findings are T2-color compiler diagnostics. \(F\) lives in Lintel.

## Cake split (who owns what)

From arXiv:2608.12629 §1–4, three pieces; **only (3) is a Lintel object**:

| Piece | This repo may contain | Lintel may contain |
|---|---|---|
| (1) Typed IR | Yes — Choreo AST / JSON | Carry the program; do not fork a second face |
| (2) Lowering | Sinks that consume the schedule; or pin `@tirx.v0` / `@tilelang.ascend` | No ISA, no cubin compiler |
| (3) Evolving harness | No workflow. Choreo *undergoes* commits on `main` | *Conducts* the loop: classify fail, corpus-gate, land/revert, freeze |

**Compiler evolution:** Choreo is the artifact that changes (commits to `choreoir` on `main`). Lintel is the process that decides those commits should exist. Choreo does not self-expand when a fail recurs.

Year-1: evolve **gates + sinks**, not vocabulary.

- Allowed without spec bump: deeper W/L/S/V, cost estimate as a pure function, sinks that actually consume `Barrier` / `Pipeline.depth` / layout / space / partition.
- Spec bump required: new op, space, role, or memory enum. Same day: a check that admits it **and** a sink that lowers it. Syntax without effects is forbidden.
- Never here: serving \(F\), freeze, land/revert, “agents write the compiler” as a runtime feature.

## Lowering (required: NVIDIA GPU and Ascend NPU)

This compiler object **always** lowers to both families. Missing that is a bug, not a non-goal.

`choreoir.lower` is admit-gated (`check` errors refuse codegen). Named `Kernel.target` selects the family (`cuda` / `cuda-sm*` → NVIDIA Triton; `ascend*` → TileLang-Ascend). Year-1 SLA allowlists `copy` and `gemm_tile`.

The sinks **must consume** partition widths, `Pipeline.depth`, layouts (`BLOCK_*`), `Barrier`, and memory spaces as codegen inputs — not comments-only. Today:

- **NVIDIA:** Triton source. `num_warps` from partitions, `num_stages` on `tl.range` from `Pipeline.depth`, `BLOCK_*` from layout, `tl.debug_barrier()` from `Barrier`. Not cubin; not WGMMA vs `tcgen05`.
- **Ascend:** TileLang-Ascend source. `gmem→GM`, `smem→L1`, `tmem→L0C`, `regs→UB` (mma C → L0C). `Copy`→`T.copy`, `Mma`→`T.gemm` in `T.Scope("C")`, `Barrier`→`T.pipe_barrier`, `Pipeline.depth`→`T.Pipelined(..., num_stages=)`. Not an NPU bin; CANN is not in the pin.

Do not unify NVIDIA smem and Ascend L1 into one `onchip` enum. Do not add a second live face. Device toolchains stay sinks we print *into*.

`print_triton` without `lower()` is a helper; CLI `print` goes through `lower()`. The demo that fails the product test is still “we compiled Choreo.”

## Dual target (GPU and Ascend)

Two SKUs, two sinks, **one** Finding schema. Not one averaged dialect. Lowering to **both** is required of this tree.

- v0.1 `gmem|smem|tmem|regs` stay NVIDIA names in the AST. The Ascend sink maps them (GM / L1 / L0C / UB). Do not rename `smem` → L1 in the AST and call it portable.
- `Kernel.target` is required for `lower()` (`cuda-sm100`, `ascend-a2`, …).
- Gluon / TLX / CUDA Tile IR remain extra sinks to print *into*, not second live faces.

## Year-1 cardinality and M2

Allowlist two complete kernels. Payload is kind 1; the deal is kind 2. Do not grow ops to look like Cake IR.

If there is still no cubin / NPU bin, **M2** on the GPU sink is `@triton.v0` knobs (`num_warps`, `BLOCK_*`, `num_stages`) derived from the AST. That does not retire the Ascend sink. If kind 2 wins the GPU SKU, the NVIDIA mutation surface can shrink to knobs; Ascend lowering remains required.

## Implementation checklist

When changing this repo, ask:

- [ ] Will this land as a commit on `main` (no PR, no feature branch)?
- [ ] Does this add control-plane behavior? If yes, stop — belongs in Lintel.
- [ ] Does this glue Cake + Argus + TIRx *languages* (layout algebra + hidden layout + TVM in the pin)? If yes, stop.
- [ ] Does a new AST node have a check **and** a sink that consumes it?
- [ ] Does NVIDIA *and* Ascend `lower()` still consume the new schedule fields?
- [ ] Are GPU and Ascend still separate spaces/roles (no unified `onchip`)?
- [ ] Are findings still `{gate, node, where?}` with no scraped stdout as the agent API?

## Do not

- Open a pull request or land via a side branch on this repo. Push `main`.
- Sell `role` as Cake’s numbers (1.144× / 2.05×). Those need a cubin sink + evolving harness.
- Add Z3, CuTe work-partition, or a second year-1 compiler.
- Put TVM in the pin just to wrap TIRx; `@tirx.v0` is an optional door for TVM-native partners.
- Treat Helion / KernelEvolve / TritorX / generic coding agents as year-1 faces (no W/L/S/`%k`).
- Run mlirAgent-style “rewrite the dialect” experiments as the mutation API.

## Pointers

- Goal: [`goals/lintel-codesign.md`](goals/lintel-codesign.md)
- Grammar / admit: [`docs/SPEC.md`](docs/SPEC.md)
- AST / check / printer: `choreoir/`
- Cake: arXiv:2608.12629
- Argus: arXiv:2604.18616
- TIRx: https://tvm.apache.org/2026/06/22/tirx
