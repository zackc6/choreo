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

**Not a compiler company** means Lintel’s SKU is the control plane, not Cake/TVM-as-product. It does **not** mean this tree skips codegen. **This tree is the compiler object:** construct, check, simulate, print, and **always lower to NVIDIA GPU and Ascend NPU**. Year-1 is Horizon A / M1-lite: Lintel searches **only L4**; L5 is classical and **assumed (ISA designed later)**. Compiler evolution is **two clocks** (T5 across jobs, never M3 mid-walk). **Lintel IR** conducts that loop.

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
6. **Lowering is classical.** Interpreter and sinks are deterministic functions of the AST. Not LLM calls. The model does not rewrite the dialect (mlirAgent negative). L5 is not a search surface. Do not design cubin/NPU ISA here until that later design lands; year-1 printers are the stand-in and must still consume the schedule.
7. **`check() == []` is not serving \(F\).** Findings are T2-color compiler diagnostics. \(F\) lives in Lintel.
8. **Two clocks.** Inside one job, `choreoir` is pinned: fail `{where}` → next Kernel, not a new opcode. Across CI, Lintel conducts commits on `main` and a new `%k`. Rewriting `check` during `^try0`→`^try1` is M3 — forbidden.

## Cake split (who owns what)

From arXiv:2608.12629 §1–4, three pieces; **only (3) is a Lintel object**:

| Piece | This repo may contain | Lintel may contain |
|---|---|---|
| (1) Typed IR | Yes — Choreo AST / JSON | Carry the program; do not fork a second face |
| (2) Lowering | Sinks that consume the schedule; or pin `@tirx.v0` / `@tilelang.ascend` | No ISA, no cubin compiler |
| (3) Evolving harness | No workflow. Choreo *undergoes* commits on `main` | *Conducts* the loop: classify fail, corpus-gate, land/revert, freeze |

**Compiler evolution:** Choreo is the artifact that changes (commits to `choreoir` on `main`). Lintel is the process that decides those commits should exist. Choreo does not self-expand when a fail recurs.

Year-1: evolve **gates + sinks**, not vocabulary.

- Allowed without spec bump: deeper W/L/S/V (role/space, `{where}` fill), cost estimate as a pure function, sinks that actually consume `Barrier` / `Pipeline.depth` / layout / space / partition / gmem writeback.
- Spec bump required: new op, space, role, or memory enum. Same day: a check that admits it **and** a sink that lowers it. Syntax without effects is forbidden.
- Never here: serving \(F\), freeze, land/revert, “agents write the compiler” as a runtime feature.

## Lowering (required families; L5 ISA later)

This compiler object **always** lowers to both families. The **path is assumed**; the cubin / NPU-bin **ISA is designed later**. Do not invent PTX/SASS/Davinci as the SKU.

`choreoir.lower` is admit-gated (`check` errors refuse codegen). Named `Kernel.target` selects the family (`cuda` / `cuda-sm*` → NVIDIA; `ascend*` → Ascend). Year-1 SLA allowlists `copy` and `gemm_tile`.

Stand-in printers **must consume** partition widths, `Pipeline.depth`, layouts (`BLOCK_*`), `Barrier`, memory spaces, and gmem writeback — not comments-only:

- **NVIDIA cubin-bound stand-in:** CUDA C++ walk (`print_cuda`) is `lower().text`. `materialize(..., emit='cubin')` runs official `nvcc -cubin` when present (discovers `~/.local/cuda-nvcc`, `CUDA_HOME`, `CHOREO_NVCC`); otherwise a warning and `.cu` only. Manifest pins `artifact_sha256` of the ELF.
- **NVIDIA M2 sidecar:** Triton knobs (`print_triton`, written as `*.triton.py`). Kill switch if the designed cubin never lands.
- **Ascend stand-in:** TileLang-Ascend with GM function args. `emit='npu-bin'` loads the generated prim_func and calls `tilelang.compile` when TileLang **and** CANN/bisheng are present; otherwise a warning and the `.npu.py` only.

Do not unify NVIDIA smem and Ascend L1 into one `onchip` enum. Do not add a second live face. Do not mutate PTX. Device toolchains stay sinks we print *into*.

`print_triton` without `lower()` is a helper; CLI `print` goes through `lower()`. The demo that fails the product test is still “we compiled Choreo.”

## Dual target (GPU and Ascend)

Two SKUs, two sinks, **one** Finding schema. Not one averaged dialect. Lowering to **both** is required of this tree.

- v0.1 `gmem|smem|tmem|regs` stay NVIDIA names in the AST. The Ascend sink maps them (GM / L1 / L0C / UB). Do not rename `smem` → L1 in the AST and call it portable.
- `Kernel.target` is required for `lower()` (`cuda-sm100`, `ascend-a2`, …).
- Gluon / TLX / CUDA Tile IR remain extra sinks to print *into*, not second live faces.

## Year-1 cardinality and M2

Allowlist two complete kernels (gmem writeback via `store`). Payload is kind 1; the deal is kind 2. Do not grow ops to look like Cake IR.

Until the later cubin / NPU-bin design lands, **M2** on the GPU sink is `@triton.v0` knobs (`num_warps`, `BLOCK_*`, `num_stages`) derived from the AST. That is the stand-in, not a secret second SKU. It does not retire the Ascend sink. If kind 2 wins the GPU SKU, the NVIDIA mutation surface **shrinks to knobs**.

## Implementation checklist

When changing this repo, ask:

- [ ] Will this land as a commit on `main` (no PR, no feature branch)?
- [ ] Does this add control-plane behavior? If yes, stop — belongs in Lintel.
- [ ] Does this glue Cake + Argus + TIRx *languages* (layout algebra + hidden layout + TVM in the pin)? If yes, stop.
- [ ] Does a new AST node have a check **and** a sink that consumes it?
- [ ] Does NVIDIA *and* Ascend `lower()` still consume the new schedule fields?
- [ ] Is this inventing L5/ISA (PTX, SASS, Davinci) instead of waiting for the later lowering design? If yes, stop.
- [ ] Could this be read as mid-walk self-modify of `check` (M3)? If yes, stop.
- [ ] Does this grow Choreo into L2/L3/L6/L7 (graph, MLIR, Inductor, cluster, Event Tensor)? If yes, stop — that is a Lintel tool or a *new* face, not this AST.
- [ ] Are GPU and Ascend still separate spaces/roles (no unified `onchip`)?
- [ ] Are findings still `{where, gate, node, ...}` with no scraped stdout as the agent API?

## Do not

- Open a pull request or land via a side branch on this repo. Push `main`.
- Sell `role` as Cake’s numbers (1.144× / 2.05×). Those need a cubin sink + evolving harness.
- Add Z3, CuTe work-partition, or a second year-1 compiler.
- Put TVM in the pin just to wrap TIRx; `@tirx.v0` is an optional door for TVM-native partners.
- Treat Helion / KernelEvolve / TritorX / generic coding agents as year-1 faces (no W/L/S/`%k`).
- Grow Choreo into FX / HLO / MLIR / Inductor / cluster / Event Tensor. Later L1–L7 coverage is Lintel talking to those compilers, or a new face package — not new opcodes here.
- Run mlirAgent-style “rewrite the dialect” experiments as the mutation API.
- Rewrite `check` or add opcodes **inside** one specialize walk. That is M3, not T5.

## Pointers

- Goal: [`goals/lintel-codesign.md`](goals/lintel-codesign.md)
- Grammar / admit: [`docs/SPEC.md`](docs/SPEC.md)
- AST / check / printer: `choreoir/`
- Cake: arXiv:2608.12629
- Argus: arXiv:2604.18616
- TIRx: https://tvm.apache.org/2026/06/22/tirx
