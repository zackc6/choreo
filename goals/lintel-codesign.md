# Goal: Choreo × Lintel co-design

Status: active. Durable product cut for this tree.
Skill (how to implement it): [`skills/choreo-lintel-codesign/SKILL.md`](../skills/choreo-lintel-codesign/SKILL.md).

## One line

**Yes** as a typed L4 face for Lintel. **No** as a compiler *company* (SKU). **Yes** as a compiler *object* that must lower to NVIDIA GPU and Ascend NPU. **No** as Cake + Argus + TIRx glued into one dialect.

## Objective

Co-design Choreo and Lintel as two objects:

- **Choreo** (this repo) is the **data plane**: a closed Kernel AST, localized admit, classical lowering. Kind 1: a program.
- **Lintel** (other repo) is the **control plane**: workload contract, admit freeze, land / revert / reject, serving \(F\). Kind 4: a workflow. Kind 3: the freeze record.

Mixing those kinds is how a control-plane company accidentally becomes a kernel language.

## Not a compiler company vs this compiler object

**Not a compiler company** = Lintel’s product is the control plane (vendor-neutral admit / freeze / \(F\)), not selling Cake, TIRx, or a TVM distro. Do not demo “we compiled Choreo.”

**This tree is the compiler object** = Choreo is the IR you construct, check, simulate, print, and **always lower to NVIDIA GPU and Ascend NPU**. Sinks are classical. That lowering was missing; it is in-scope forever.

**Compiler evolution** happens *to* this object (gates, sinks, rare spec bumps on `main`). **Lintel IR** is the control-plane IR that conducts the loop (classify fail, corpus-gate, land / revert / reject). Choreo does not self-expand at search time.

## Cake’s three pieces (arXiv:2608.12629 §1–4)

Only one is a Lintel object.

| Cake piece | Object | Owner |
|---|---|---|
| (1) Typed IR the agent edits | A program | **Choreo** (face). Lintel *carries* it. |
| (2) Lowering that derives barrier addresses, phase bits, TMEM offsets, descriptors, warp identity, then emits a device binary | A compiler / sink | **This tree** must lower to NV GPU and Ascend NPU (source today). Cubin/NPU bin = device toolchain, not Lintel. |
| (3) Evolving harness: recurring fail → verifier / primitive / cost cal / tactic, corpus-gated, agents write compiler under human merge gates | A workflow | **Lintel** — but only the control-plane slice of Cake’s “harness.” |

Cake’s word *harness* is a bundle. Split it:

**Lintel owns:** generate → filter → oracle → route evidence → merge gate; freeze / `%k`; serving \(F\) as land criterion.

**Lintel does not own:** new IR primitives (Choreo spec bump) or new lowering rules (sink). If kind 4 rewrites kind 1 because a fail recurred, it is no longer a Lintel object.

## What “compiler evolution” means

Choreo **undergoes** compiler evolution; Lintel **conducts** it.

- **Undergo:** commits to `choreoir` on `main` (deeper `check`, sinks that consume the schedule, rare spec bumps). After the commit, `check` and lowering are still total, classical functions. No LLM in that path. This repo does not use GitHub pull requests.
- **Conduct:** Lintel sees `{where}` / sanitizer / miss vs \(F\), classifies (repair candidate vs new gate vs cost cal vs spec-bump / sink-pin), corpus-tests, land / revert / reject.

Choreo does not notice a recurring fail and add a keyword. The agent does not mutate the dialect at runtime (mlirAgent negative: Gemini 2.5 Pro is below identity on MLIR rewrite).

Year-1 evolution is **gates + sinks**, not vocabulary. `Pipeline.depth=3` becoming 3-stage codegen is compiler evolution. Copying Cake’s `role` is not.

New op / space / role: spec bump, and only when a sink consumes it **and** a check admits it the same day. Syntax without effects makes the IR less analyzable (Cake).

A two-kernel SLA is a weak corpus. Harness changes stay rarer than kernel allowlist edits or gates overfit.

## Union is of admit signals, not languages

Cake hides layout; Argus makes layout algebra the spec. Averaging those into one GPU IR is forbidden.

Choreo’s third cell: cheap `shape × stride` so `{where: L}` can fire. No Z3, no CuTe work-partition. The Finding schema may look Argus-shaped (`thread` / `element`); the oracles must actually fill `{where}`. Do not ship Cake keywords + Argus JSON keys + TIRx printer comments as a fake union.

W / L / S / V are **T2-color signals**, not serving oracles. `check() == []` is not serving \(F\).

## Lowering (v0.1: source sinks, required families)

A compiler object here has to (1) take warp/core roles, barriers, pipeline depth, layouts, and memory spaces as **inputs to codegen**, (2) pick a **named** target family (NVIDIA GPU vs Ascend NPU), (3) emit source the device toolchain can compile. Cubin / NPU bin still need that toolchain.

`choreoir.lower` is admit-gated. `Kernel.target` is required (`cuda` / `cuda-sm*` / `ascend*`). Year-1 allowlist: `copy`, `gemm_tile`.

- NVIDIA: Triton source; knobs from the AST; `tl.debug_barrier` from `Barrier`; `tl.range(..., num_stages=)` from `Pipeline.depth`.
- Ascend: TileLang-Ascend source; spaces mapped GM/L1/L0C/UB; `T.copy` / `T.gemm` / `T.pipe_barrier` / `T.Pipelined`.

## Targets: GPU and Ascend NPU

Do both as **required sinks** on this compiler object. Do not unify them in the AST.

v0.1 `Space = gmem|smem|tmem|regs` and `Role = load|math|store` with warp `width` is NVIDIA-shaped. Ascend is Cube / Vector / Scalar, GM / L1 / UB / L0A / L0B / L0C, MTE queues. Spaces and roles are **target-indexed**. Same Finding schema. Not one `onchip` enum.

```text
Lintel     workload contract, admit, F, freeze, evidence → gate | cal | tactic
Choreo     closed JSON AST + target field; cheap shape×stride; {where}
Sinks      not live faces
  gpu    → cubin    @tirx.v0 / Triton / CUTLASS
  ascend → NPU bin  @tilelang.ascend / Ascend C
```

`@cake.v0` is the same *door* as `@tirx.v0` if Cake opens. Do not become “open Cake.” Vendor DSLs (Gluon / TLX / TileLang / CUDA Tile IR) are sinks to print *into*, not second live faces.

Sequence: one kernel, one target, real binary, harness learns from real fails; then the second target. Two printers and no \(F\) is the compiler-company trap.

Cake is NVIDIA-only. “Better than Cake on Ascend” is vacuous. The Ascend bar is TileLang-Ascend / Ascend C.

## Year-1 cardinality and M2

SLA allowlists two complete kernels. Payload is a program (kind 1); the *deal* is kind 2. Do not grow the dialect to look like a language company.

**M2 kill switch:** if there is still no cubin sink, flip to `@triton.v0` knobs rather than sell “we compiled Choreo.” Kind 2 has stronger near-term evidence for weak models (µCUTLASS, ACF, `num_warps`). If kind 2 wins the SKU, this mutation surface **shrinks to knobs** — the AST does not stay the brochure with knobs taped on.

## Success criteria

1. README / spec / skill never describe Choreo as Cake ∪ Argus ∪ TIRx as languages.
2. Admit findings are localized `{where: W|L|S|V}` and are the only agent feedback from this tree.
3. `lower()` to NVIDIA and to Ascend consumes `Partition`, `Barrier`, `Pipeline.depth`, layout, and space; CLI `print` is admit-gated.
4. Lintel (other repo) is the only place land / revert / reject / freeze / \(F\) live.
5. GPU and Ascend are two sinks, not one averaged dialect.
6. Compiler-evolution **commits on `main`** are proposed from Lintel evidence and never from in-process dialect rewrite. No GitHub PR on this repo.
7. Agents land this tree by pushing `main` directly (see the skill’s Git section).

## Non-goals (this tree)

- Control plane: MCP, budget/stop, serving \(F\), agent DAGs, Lintel IR.
- A new execution ISA. Do not replace `opt` / Inductor / Triton / CANN as the device compiler.
- SMT layout (Argus `oracle`) as a year-1 compiler.
- Helion / KernelEvolve / TritorX productize — out of year-1 SKU.
- Claiming Cake’s 1.144× Flash-KMeans or 2.05× KDA from `role` alone.

## Falsifiers

- Agents editing raw CUDA / PTX / Triton beat Choreo on correctness × speed under a matched token budget (reverses Cake’s clean-start).
- Layout / sync admit cannot localize to (point, thread, element).
- A production stack ships peak + serving SLOs with no distinct kernel DSL (collapses the L4 bet).
- “We compiled Choreo” is the demo and there is still no cubin / NPU bin.
- Lintel-driven commits add Choreo keywords without a sink that lowers them.
