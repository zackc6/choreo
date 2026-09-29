---
name: choreo-lintel-codesign
description: >-
  Co-design rules for the starting architecture: Lintel (control), Choreo
  (kernel-schedule compiler), classical lowering. Three loops stay apart:
  application search, IR evolution, controller improvement. Use when changing
  the Kernel AST, admit (W|L|S|V), printers/sinks, README/SPEC, git landing,
  or anything that mentions Cake, Ave, Argus, TIRx, Lintel, harness, freeze,
  or targets (GPU / Ascend). This repo commits to main only; no PRs.
---

# Choreo × Lintel co-design

**Never forget** [`goals/agentic-compiler.md`](goals/agentic-compiler.md) — the starting architecture. This skill is the implementer SOP for **this repo**. Detail: [`goals/lintel-codesign.md`](goals/lintel-codesign.md).

Choreo is the kernel-schedule compiler in this repo: the program the agent edits, the checks, and classical lowering to NVIDIA GPU and Ascend NPU.

**Three loops, kept apart.** Application search edits a `Kernel` under a pinned `compiler_ver`. IR evolution is a separate commit on `main` that may change the representation, a check, or a sink, then bumps `compiler_ver`. Controller improvement (how Lintel decides) is not this tree. Revised against [zackc6/ai-compiler-survey](https://github.com/zackc6/ai-compiler-survey) through 2026-09-23. Judgment: [`goals/lintel-codesign.md`](goals/lintel-codesign.md).

## When to use

- Any change that could forget or overwrite [`goals/agentic-compiler.md`](goals/agentic-compiler.md).
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

0. **Starting architecture.** Lintel conducts application search; Choreo is the kernel compiler the agent edits; lowering is classical; serve loads a frozen binary. Picture: [`goals/agentic-compiler.md`](goals/agentic-compiler.md). Do not treat that picture as proof that every compiler must keep the split.
1. **Choreo is the kernel-schedule compiler.** Closed Kernel AST for the pinned version, `check()`, CPU sim, deterministic printers/sinks.
2. **Lintel is the control plane** (other repo). Land / revert / reject, freeze / `%k`, application score, evidence routing.
3. **Do not mix loops.** Do not put MCP, agent DAGs, budget/stop, land/revert, or controller self-improvement in `choreoir`. Do not let an application search invent Choreo keywords.
4. **Yes as this compiler object, lowering to NV GPU and Ascend NPU. No as the control plane. No as Cake + Ave + TIRx glued into one dialect.** Ave was Argus before 14 September 2026.
5. **Union of admit signals, not languages.** W/L/S/V may draw on Cake / Ave / TIRx *mechanisms*. Do not average those IRs. Third cell: cheap `shape × stride` so `{where: L}` can fire. No year-1 Z3. No CuTe work-partition.
6. **Lowering is classical.** Interpreter and sinks are deterministic functions of the AST. Not LLM calls. The model does not rewrite the dialect during a search. Device ISA is later design. Year-1 printers are the stand-in and must still consume the schedule.
7. **`check() == []` is not the application score.** Findings are compiler diagnostics. The score lives in Lintel.
8. **Three loops.** Application search: `choreoir` pinned, fail `{where}` → next Kernel. IR evolution: a commit on `main`, bump `compiler_ver`, new `%k`, previous allowlist still passes. Controller improvement: not this tree. Rewriting `check` during one search is forbidden.

## Who owns which change

Cake (arXiv:2608.12629) bundled a typed IR, lowering, and an evolving harness. The 23 September 2026 survey splits the harness into compiler evolution and controller improvement.

| Change | This repo | Lintel |
|---|---|---|
| Kernel program | Yes — Choreo AST / JSON | Carries it; does not fork a second face |
| Checks and lowering | Yes — deterministic; official `nvcc` / `ccec` when present; ISA later | No cubin compiler |
| IR evolution | Undergoes the commit on `main` | Decides the promotion from evidence; corpus-gates it |
| Controller improvement | No | Own experiment, compiler held fixed |
| Freeze / application score | No | Yes |

A recurring `{where}` opens an IR-evolution proposal. It does not add an opcode inside the search that saw the reject.

- Allowed without a spec bump: deeper W/L/S/V, a pure cost estimate, sinks that consume `Barrier` / `Pipeline.depth` / layout / space / partition / gmem writeback.
- Spec bump, same change: a new op, space, role, or memory enum, a check that admits it, and both sink families lowering it. The existing `copy` / `gemm_tile` kernels still pass. Syntax without effects is forbidden.
- Never here: application score, freeze, land/revert, controller self-improvement, rewriting `check` inside one search.

## Lowering (required families; L5 ISA later)

This compiler object **always** lowers to both families. The **path is assumed**; the cubin / NPU-bin **ISA is designed later**. Do not invent PTX/SASS/Davinci as the SKU.

`choreoir.lower` is admit-gated (`check` errors refuse codegen). Named `Kernel.target` selects the family (`cuda` / `cuda-sm*` → NVIDIA; `ascend*` → Ascend). Year-1 SLA allowlists `copy` and `gemm_tile`.

Stand-in printers **must consume** partition widths, `Pipeline.depth`, layouts (`BLOCK_*`), `Barrier`, memory spaces, and gmem writeback — not comments-only:

- **NVIDIA cubin-bound stand-in:** CUDA C++ walk (`print_cuda`) is `lower().text`. `Partition.width` becomes `__launch_bounds__(summed widths×32)` and thread-strided Copy/Mma/Reduce (`threadIdx.x`, stride `width×32`). `attrs.num_warps` is the Triton sidecar and must not shrink that block. `Pipeline.depth` stages `__shared__[depth]`; `attrs.num_stages` is the Triton sidecar and must not unstage that reservation. `materialize(..., emit='cubin')` runs official `nvcc -cubin` when present (discovers `~/.local/cuda-nvcc`, `CUDA_HOME`, `CHOREO_NVCC`); otherwise a warning and `.cu` only. Manifest pins `artifact_sha256` of the ELF. `pin.json` `launch` records `<<<grid, block>>>` (`block = partition_warps×32`); it is payload, not a cache-key field.
- **NVIDIA M2 sidecar:** Triton knobs (`print_triton`, written as `*.triton.py`), including a `{name}_launch` helper that passes `num_warps` / `num_stages`. Standby kill if the cubin path is withdrawn.
- **Ascend NPU-bin-bound stand-in:** CCE walk (`print_ascendc`) is `lower().text`. Copy/Barrier/Pipeline/Mma/Reduce consume the schedule (Copy nested over shape **indexed by layout stride**, matching CUDA Copy; `vmadd` fallback for MMA **indexed by layout stride**, matching CUDA scalar MAC; `vector_dup`/`vadd` for Reduce; cube mad is later L5). `Pipeline.depth` stages smem UB (`name + _stage * span`, reservation × depth) the way CUDA stages `__shared__[depth]`; `attrs.num_stages` must not unstage that reservation. `Partition.width` is `block_idx < width` (year-1 one aicore: core 0 always runs). `materialize(..., emit='npu-bin')` runs official `ccec --cce-aicore-only -c` when present (discovers `~/.local/ascend/pkg/bisheng_compiler`, `CCE_HOME`, `CHOREO_CCEC`); otherwise a warning and `.cce` only. Manifest pins `artifact_sha256` of the elf64-hiipu ELF. Not a homemade Davinci object.
- **Ascend sidecar:** TileLang-Ascend (`print_ascend`, written as `*.npu.py`). `T.Kernel(num_warps)`. Parallel to Triton; not what `npu-bin` compiles.

Do not unify NVIDIA smem and Ascend L1 into one `onchip` enum. Do not add a second live face. Do not mutate PTX. Device toolchains stay sinks we print *into*.

`print_triton` without `lower()` is a helper; CLI `print` goes through `lower()`. The demo that fails the product test is still “we compiled Choreo.”

`pin.json` is the Lintel handshake, not a freeze. `cache_key` matches `cache-key.v0`: face `adapter_id` is `choreo.v0`; `sink_id` (`nvcc.cubin` / `ccec.aicore` / …) is payload and the suffix of `compiler_ver`; `Kernel.target` is not a key field; default `graph_hash` is `sha256(lintel.graph.unspecified)` so Lintel can overwrite the L2 digest. `cache_key_digest` is sha256 of canonical JSON of the key (sorted keys, no whitespace) and is the lookup address, not a key field. `choreo pin path/to/pin.json` validates the key, the digest if present, and `launch` on `choreo-pin.v1` payloads. `choreo consume-check PATH` checks a Lintel tree against the year-1 consume contract (no `src/`, two SLA slots, cubin freeze + `artifact.launch`, session Finding JSON as a sibling of `reject`). `choreo propose` emits `lintel.adapter_proposal.v0`; `reject.where` is the CFG edge (`W|L|S|V`). Do not put freeze / land / revert / serving \(F\) / MCP in `choreoir`. The Lintel repo is the control-plane tree (docs + schemas in year-1); this agent does not land commits there.

## Dual target (GPU and Ascend)

Two SKUs, two sinks, **one** Finding schema. Not one averaged dialect. Lowering to **both** is required of this tree.

- v0.1 `gmem|smem|tmem|regs` stay NVIDIA names in the AST. The Ascend sink maps them (GM / L1 / L0C / UB). Do not rename `smem` → L1 in the AST and call it portable.
- `Kernel.target` is required for `lower()` (`cuda-sm100`, `ascend-a2`, …).
- Gluon / TLX / CUDA Tile IR remain extra sinks to print *into*, not second live faces.

## Year-1 cardinality and M2

Allowlist two complete kernels (gmem writeback via `store`). That cardinality is the current experiment. Do not grow ops to resemble a language product. A promoted op still needs a check and both sinks, and these two kernels still pass.

Until the later cubin / NPU-bin ISA design lands, `@triton.v0` knobs stay a standby sidecar. Year-1 NVIDIA cubin via official `nvcc` already exists for the allowlist; do not flip the product to knobs while that ELF path holds.

## Implementation checklist

When changing this repo, ask:

- [ ] Will this land as a commit on `main` (no PR, no feature branch)?
- [ ] Does this add control-plane or controller-improvement behavior? If yes, stop — belongs in Lintel.
- [ ] Does this glue Cake + Ave + TIRx *languages* (layout algebra + hidden layout + TVM in the pin)? If yes, stop.
- [ ] Does a new AST node have a check **and** both sink families consuming it, with `copy` / `gemm_tile` still passing?
- [ ] Does NVIDIA *and* Ascend `lower()` still consume the new schedule fields?
- [ ] Is this inventing the device ISA (PTX, SASS, Davinci) instead of waiting for the later lowering design? If yes, stop.
- [ ] Could this rewrite `check` or add an opcode inside one application search? If yes, stop.
- [ ] Does this stuff a graph, MLIR pipeline, or placement dialect into `Kernel`? If yes, stop — that is another representation.
- [ ] Does this freeze “search only the kernel, forever” or a fixed band count as architecture? If yes, stop — kernel schedule is the starting scope.
- [ ] Are GPU and Ascend still separate spaces/roles (no unified `onchip`)?
- [ ] Are findings still `{where, gate, node, ...}` with no scraped stdout as the agent API?
- [ ] Does `materialize` write `pin.json` (`as_k`) whose `cache_key` is Lintel `cache-key.v0` (`adapter_id=choreo.v0`, no `Kernel.target` in the key, `compiler_ver` names choreoir **and** the sink, `graph_hash` is not a Kernel hash), without this tree freezing?
- [ ] Does `choreo propose` emit `adapter-proposal.v0` with `{where: W|L|S|V}` as a CFG edge (not `compile_ok`, not freeze)?
- [ ] Does `choreo consume-check` stay a handshake checker (no freeze / land / \(F\) in this tree)?

## Do not

- Open a pull request or land via a side branch on this repo. Push `main`.
- Sell `role` as Cake’s numbers (1.144× / 2.05×). Those need a cubin sink + evolving harness.
- Add Z3, CuTe work-partition, or a second year-1 compiler.
- Put TVM in the pin just to wrap TIRx; `@tirx.v0` is an optional door for TVM-native partners.
- Treat Helion / KernelEvolve / TritorX / generic coding agents as year-1 faces (no W/L/S/`%k`).
- Grow `Kernel` into FX / HLO / MLIR / Inductor / cluster / Event Tensor. A wider scope is a promoted version or another representation, decided outside an application search.
- Run dialect-rewrite experiments as the mutation API inside one search.
- Rewrite `check` or add opcodes inside one application search.
- Call `examples/fails/` evidence that the compiler evolved. That directory localizes rejects for the application search.
- Record a Lintel prompt or workflow edit as a Choreo `compiler_ver` bump.

## Pointers

- Starting architecture: [`goals/agentic-compiler.md`](goals/agentic-compiler.md)
- Judgment and detail: [`goals/lintel-codesign.md`](goals/lintel-codesign.md)
- Lintel consume contract: [`docs/LINTEL_CONSUME.md`](docs/LINTEL_CONSUME.md)
- Grammar / admit: [`docs/SPEC.md`](docs/SPEC.md)
- AST / check / printer: `choreoir/`
- Cake: arXiv:2608.12629
- Ave (previously Argus): arXiv:2604.18616
- TIRx: https://tvm.apache.org/2026/06/22/tirx
