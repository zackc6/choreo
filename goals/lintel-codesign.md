# Goal: Choreo × Lintel co-design

Status: active. Durable product cut for this tree.
Skill (how to implement it): [`skills/choreo-lintel-codesign/SKILL.md`](../skills/choreo-lintel-codesign/SKILL.md).

## One line

**Yes** as a typed L4 face for Lintel. **No** as a compiler *company* (SKU). **Yes** as a compiler *object* that must lower to NVIDIA GPU and Ascend NPU. **No** as Cake + Argus + TIRx glued into one dialect.

Year-1 is **Horizon A, job (a), M1-lite**: one e2e controller (Lintel) searches **only L4** (Choreo), admits on L6 \(F\), classical lower/admit stay. It is **not** Horizon B (joint search across L1–L7, four jobs, compiled control plane). Not a new L-band. Not “agents are the compiler” (M3 / C6-A).

## Objective

Co-design Choreo and Lintel as two objects:

- **Choreo** (this repo) is the **data plane**: a closed Kernel AST, localized admit, classical lowering. Kind 1: a program. The only year-1 *search* surface.
- **Lintel** (other repo) is the **control plane**: workload contract, admit freeze, land / revert / reject, serving \(F\). Kind 4: a workflow. Kind 3: the freeze record.

Mixing those kinds is how a control-plane company accidentally becomes a kernel language.

## Survey placement (direction vs stack)

Match the survey’s predicted **direction** (Horizon A, soft merge M1, hybrid C6-B). Do not claim the predicted **stack**.

| Survey claim | This codesign | Year-1 |
|---|---|---|
| Agents = control plane; compilers = data plane | Lintel walks the job; `choreoir.check` + sink are L4 tools | Yes |
| **M1** one controller over band *tools* | Lintel is the controller; Choreo+sink are tools; serve is `lookup(%k)` | Yes, narrow |
| **M3** agents *are* the compiler | Out. Kill C6-A | Refuse |
| **T1+T2+T3** typed face + `{where}` + freeze | Kernel AST + findings + Lintel `%k` | SKU shape; `%k` is Lintel |
| **T6** serving \(F\), not microbench | Lintel law; not evidence in this tree | Law, not yet numbers |
| **T5** compiler evolves from recurring fails | Two clocks (below). Cake flavor, not TritorX ISA RFC | T5-lite |
| **C3-B** constrain the action space | Two allowlisted kernels | Yes |
| **C4** multi-DSL | One *face*; Triton-first *sink*; later `adapter_id` | Partial |
| **C5** freeze-before-serve | Specialize vs serve; no LLM on serve | Lintel |
| Joint L1–L7 policy, L7 place, jobs (b)(c)(d) | Out | Intentional miss |

Year-1 Lintel×Choreo is M1 **cut to one search band**:

```text
 F (tokens/s × parity × $/compile)     Lintel, not this repo
        │
   Lintel IR  ← e2e controller
        │
   L1  fingerprint / Amdahl triage     searched?  NO (cut only)
   L2  graph_hash in %k                searched?  NO
   L3  Inductor/MLIR pinned            searched?  NO
   L4  Choreo Kernel AST               searched?  YES (only live surface)
   L5  cubin / NPU bin via sink        searched?  NO — classical; path assumed, designed later
   L6  serving A/B + freeze            searched?  NO — this is the *oracle*
   L7  place                           out
```

C4 is an L4 *sink* fight, not a Lintel-IR fight. A second DSL is a new adapter / `%k`, not a second live face. `{where}` JSON from this tree is a **CFG edge in Lintel**, not a `reject` enum. Do not put that CFG in `choreoir`.

## Later: L1–L7 without growing this dialect

**Choreo does not become the IR for all bands.** Graph, cluster, MLIR, and Inductor are **other legality/lower surfaces**. Soft merge unifies the *controller* (Lintel + \(F\)), not the execution substrate. One Kernel AST that is also FX/HLO/MLIR/place is survey §5.1.1 (do not unify portable graph and peak kernel DSL) and the C4 trap (IR only we compile).

| Band | Later extension | Not Choreo |
|---|---|---|
| **L1** capture / cut | Lintel `triage` / fingerprint / skip cold regions | No Torch rewrite, no FX dialect in this AST |
| **L2** portable graph | `graph_hash` in `%k`; optional *other* face (StableHLO) as a tool | No fusion/graph ops on `Kernel` |
| **L3** mid-IR | Pin Inductor/MLIR in `compiler_ver`; admit stays classical | No mlirAgent-style rewrite; no MLIR dumped into Choreo |
| **L4** kernel DSL | This tree. T5: gates + sinks + rare spec bumps | Does not become the SKU |
| **L5** ISA | Designed later as a *sink* | No PTX mutation; no ISA company |
| **L6** serving | Lintel \(F\) + freeze; load the binary | No Event Tensor megakernel IR here |
| **L7** place / cluster | Lintel gate if ever | No cluster IR in `choreoir` |

Horizon B, if it happens, is **Lintel proposing at more bands** (same `{where}`-shaped admit, rolled into \(F\)), each band keeping its own compiler. A second typed face for graphs would be a **new package**, not new Choreo opcodes. Year-1 stays L4-only search.

## Not a compiler company vs this compiler object

**Not a compiler company** = Lintel’s product is the control plane (vendor-neutral admit / freeze / \(F\)), not selling Cake, TIRx, or a TVM distro. Do not demo “we compiled Choreo.”

**This tree is the compiler object** = Choreo is the IR you construct, check, simulate, print, and **always lower to NVIDIA GPU and Ascend NPU**. Sinks are classical.

**L5 is assumed, not designed in this increment.** Year-1 printers (Triton knobs, TileLang-Ascend, CUDA C++ walk) are a stand-in that must **consume the schedule**. The cubin / NPU-bin ISA path is a later design. Do not invent PTX/SASS/Davinci here as the SKU, and do not treat “we assembled a cubin” as the product test.

## Cake’s three pieces (arXiv:2608.12629 §1–4)

Only one is a Lintel object.

| Cake piece | Object | Owner |
|---|---|---|
| (1) Typed IR the agent edits | A program | **Choreo** (face). Lintel *carries* it. |
| (2) Lowering that emits a device binary | A compiler / sink | **This tree** (classical). Path assumed; ISA designed later. Not Lintel. |
| (3) Evolving harness | A workflow | **Lintel** — control-plane slice only |

**Lintel owns:** generate → filter → oracle → route evidence → merge gate; freeze / `%k`; serving \(F\) as land criterion.

**Lintel does not own:** new IR primitives (Choreo spec bump) or new lowering rules (sink). If kind 4 rewrites kind 1 because a fail recurred, it is no longer a Lintel object.

## Two clocks (T5 without M3)

“Choreo evolves during compilation, not a fixed dialect” matches survey **T5 (Cake flavor)** only with **two clocks**. If “evolve” means `check` rewrites itself **inside one specialize walk**, that is **M3** and is forbidden.

| Clock | What is allowed | Survey reading |
|---|---|---|
| **Inside one job / ADG walk** | `choreoir` **pinned** (Lintel `%k` / `compiler_ver`). `check` / sink are ordinary functions. Agent fills allowlisted Kernels. Fail `{where: L}` → next kernel, **not** a new opcode. | Hybrid C6-B. Cake *using* a harness, not rewriting it mid-step. |
| **Across CI / overnight specialize** | Recurring `{where}` → Lintel conducts a **commit on `main`** (this repo does not use GitHub PRs) → bump `compiler_ver` → **new `%k`**, must re-land. Next walk uses a different compiler on the same region. | **T5**. Compiler is not fixed. Replay still holds. |

Gray zone that stays T5, not M3: extra Finding rules / cost cal loaded from a **versioned bundle** whose hash is in `%k`. `check` stays a pure function. No LLM in `check`. Year-1 still routes that through git on `main` (safer replay; slower than Cake’s in-job harness).

Until the Undergo loop has a real fail corpus, “not fixed” is a **process claim**. Two allowlisted kernels plus `examples/fails/` (localized `{where}`) are the year-1 T5-lite corpus.

## Union is of admit signals, not languages

Cake hides layout; Argus makes layout algebra the spec. Averaging those into one GPU IR is forbidden.

Choreo’s third cell: cheap `shape × stride` so `{where: L}` can fire. No Z3, no CuTe work-partition. The Finding schema may look Argus-shaped (`thread` / `element`); the oracles must actually fill `{where}`. Do not ship Cake keywords + Argus JSON keys + TIRx printer comments as a fake union.

W / L / S / V are **T2-color signals**, not serving oracles. `check() == []` is not serving \(F\).

## Lowering (assumed path; ISA designed later)

A compiler object here has to (1) take warp/core roles, barriers, pipeline depth, layouts, and memory spaces as **inputs to codegen**, (2) pick a **named** target family (NVIDIA GPU vs Ascend NPU), (3) lower classically. **L5 is not a search surface.** Agents do not mutate PTX/SASS/Davinci.

`choreoir.lower` is admit-gated. `Kernel.target` is required (`cuda` / `cuda-sm*` / `ascend*`). Year-1 allowlist: `copy`, `gemm_tile`.

**Stand-in (today, not the L5 design):** NVIDIA CUDA C++ walk is `lower().text` (cubin-bound); Triton knobs are the M2 sidecar. Ascend TileLang-Ascend with GM args. Printers must consume `Partition`, `Barrier`, `Pipeline.depth`, layout, space, and gmem writeback. `materialize(..., emit='cubin'|'npu-bin')` may try a device toolchain when present; missing toolchain is a warning, not a fake binary.

**Later design:** the actual cubin / NPU-bin path (how schedule becomes loadable GPU/NPU objects). Until that lands, M2 `@triton.v0` knobs are the GPU stand-in, not a secret second SKU.

Do not unify NVIDIA smem and Ascend L1 into one `onchip` enum.

## Targets: GPU and Ascend NPU

Do both as **required sink families**. Do not unify them in the AST. Spaces and roles stay **target-indexed**. Same Finding schema.

```text
Lintel     workload contract, admit, F, freeze, evidence → gate | cal | tactic
Choreo     closed JSON AST + target field; cheap shape×stride; {where}
Sinks      not live faces; L5 designed later
  gpu    → cubin    (stand-in: Triton / CUDA C++)
  ascend → NPU bin  (stand-in: TileLang-Ascend)
```

Vendor DSLs are sinks to print *into*, not second live faces. Two printers and no \(F\) is the compiler-company trap. \(F\) lives in Lintel.

Cake is NVIDIA-only. “Better than Cake on Ascend” is vacuous. The Ascend bar is TileLang-Ascend / Ascend C.

## Year-1 cardinality and M2

SLA allowlists two complete kernels. Payload is a program (kind 1); the *deal* is kind 2. Do not grow the dialect to look like a language company.

**M2 kill switch:** if the designed cubin sink never lands, flip to `@triton.v0` knobs rather than sell “we compiled Choreo.” Kind 2 has stronger near-term evidence for weak models. If kind 2 wins the SKU, this mutation surface **shrinks to knobs**.

## Success criteria

1. README / spec / skill never describe Choreo as Cake ∪ Argus ∪ TIRx as languages.
2. Admit findings are localized `{where: W|L|S|V}` and are the only agent feedback from this tree.
3. `lower()` to NVIDIA and to Ascend consumes `Partition`, `Barrier`, `Pipeline.depth`, layout, and space; CLI `print` is admit-gated. L5 ISA is later design.
4. Lintel (other repo) is the only place land / revert / reject / freeze / \(F\) live.
5. GPU and Ascend are two sinks, not one averaged dialect.
6. Compiler-evolution **commits on `main`** are proposed from Lintel evidence and never from in-process dialect rewrite (two clocks). No GitHub PR on this repo.
7. Agents land this tree by pushing `main` directly (see the skill’s Git section).
8. Docs never describe mid-walk self-modify of `check` / the dialect as “evolve during compilation.”

## Non-goals (this tree)

- Control plane: MCP, budget/stop, serving \(F\), agent DAGs, Lintel IR, `%k` / `%w`.
- Joint search over L2/L3/L6/L7. Year-1 does not propose fusion or place. Later, Lintel may *talk to* those bands; Choreo still does not *become* them.
- A new execution ISA. Do not replace `opt` / Inductor / Triton / CANN as the device compiler. Do not design L5 in lieu of the later cubin/NPU path.
- SMT layout (Argus `oracle`) as a year-1 compiler.
- Helion / KernelEvolve / TritorX productize — out of year-1 SKU.
- Claiming Cake’s 1.144× Flash-KMeans or 2.05× KDA from `role` alone.
- Calling this slice “the e2e-optimal-seeking architecture.”

## Falsifiers

- Agents editing raw CUDA / PTX / Triton beat Choreo on correctness × speed under a matched token budget (reverses Cake’s clean-start).
- Layout / sync admit cannot localize to (point, thread, element).
- A production stack ships peak + serving SLOs with no distinct kernel DSL (collapses the L4 bet).
- “We compiled Choreo” is the demo (compiler-company SKU).
- Lintel-driven commits add Choreo keywords without a sink that lowers them.
- `check.py` or the dialect is rewritten **inside** one specialize walk (M3).
