# Goal: Choreo × Lintel co-design

Status: active implementer detail under [`agentic-compiler.md`](agentic-compiler.md). Revised **2026-09-29** against [zackc6/ai-compiler-survey](https://github.com/zackc6/ai-compiler-survey) through **2026-09-23**. Do not let this file overwrite that picture.
Skill: [`skills/choreo-lintel-codesign/SKILL.md`](../skills/choreo-lintel-codesign/SKILL.md).

## Judgment

The August 2026 goals matched an older survey map: one controller, search confined to a kernel “band,” and a single evolution clock. The 23 September 2026 survey revised that map. The 29 September cut in this tree kept the three loops and still organized scope as a kernel slice that would widen when a profile asked, with a year-scoped surface as the design. This revision drops both. Function coverage is the early architecture in [`agentic-compiler.md`](agentic-compiler.md).

**Functions.** The survey keeps five functions and leaves their implementation open: represent computation, transform and optimize, map to hardware, validate, and coordinate execution. This design assigns each an owner and an interface now. Decision areas (workload and graph, representation and transformation, kernel and machine code, runtime and distribution, evaluation and deployment) sit on those interfaces. A fixed layer count stays unproven. Stuffing a graph, an MLIR pipeline, or placement into `Kernel` stays rejected: one representation that is also a portable graph is a bad unification.

**Self-evolving loop in the IR.** The survey separates three targets. Application search changes the program. Compiler evolution changes analyses, transformations, representations, or backends, and must be judged on kernels that did not motivate the change. Controller improvement changes the decision procedure (instructions, search strategy, orchestration, agent code) and, as of that survey, has no application-level compiler evidence. Storing logs is memory, not either evolution.

The previous “two clocks” note got the pin right and the target wrong. It forbade rewriting `check` inside one search (that still holds: acceptance rules stay fixed during an experiment). It then called every later commit “the compiler evolves,” while also freezing vocabulary so the representation could not evolve. Recurring rejects are the input to IR evolution, not a cue to invent an opcode in the search, and not a cue to edit Lintel’s decision procedure. `examples/fails/` localizes application-search rejects. It is not evidence that this compiler has evolved.

Retired as laws: Horizon A, M1, M3, T5, C6, and L1–L7. They remain historical survey identifiers only. A year-scoped allowlist and a profile-triggered widening are retired as architecture as well.

## One line

**Yes** as the kernel-schedule compiler an agent edits under a pinned version, checked and lowered to NVIDIA GPU and Ascend NPU, inside an early architecture that already assigns all five functions. The control plane and controller self-improvement stay in Lintel. Cake, Ave, and TIRx contribute admit mechanisms. The design has no band stack, no year plan, and no function whose owner waits on one application’s profile.

## Three loops

| Loop | What changes | Where it lives | Promotion rule |
|---|---|---|---|
| Application search | The `Kernel` (tiles, roles, depth, layout, spaces) | Lintel proposes; this tree checks and lowers | Compiler version pinned. Reject `{where}` → next kernel. |
| IR evolution | Representation, checks, or sinks | A commit on this `main` | New `compiler_ver`, then a new `%k`. Kernels that did not motivate the change still have to pass. Both sink families consume a new schedule field. |
| Controller improvement | How Lintel decides | Lintel only, and only as its own experiment | Compiler and acceptance rules held fixed. Out of this tree until that experiment exists. |

Inside one application search, `choreoir` is an ordinary function of the AST. No LLM in `check` or `lower`. A versioned bundle of extra findings is still IR evolution: its hash belongs in `%k`, and it does not rewrite itself mid-search.

A new op, space, role, or memory enum is a representation change: spec bump, a check that admits it, and sinks that lower it. Syntax without effects covers no function. Deepening a check is the same loop when a reject cannot name a program point.

## Function coverage in this tree

| Function | This tree | Lintel |
|---|---|---|
| Represent | `Kernel` AST and its JSON encoding | Chooses which kernel to propose; holds the program record `graph_hash` names |
| Transform | Admits a replacement kernel; undergoes an IR-evolution commit | Proposes the kernel; conducts the promotion |
| Map | `lower` to NVIDIA and Ascend; sinks consume the schedule | Selects the artifact to keep |
| Validate | `W\|L\|S\|V` findings | Contract, application score, rollout |
| Coordinate | Partitions, barriers, pipelines, and `launch` | Program record: artifact-id nodes, buffer edges, per-node `hw_id`, digested as `graph_hash` |

`copy` and `gemm_tile` stay the regression pair for a representation change. The consume handshake with today’s Lintel tree still names those two kernels. That pin is a contract with the other repo. It is not the function set.

## Who owns which object

| Object | Owner |
|---|---|
| Typed kernel the agent edits | **Choreo** |
| Checks and classical lowering | **Choreo** (deterministic). Device ISA stays inside the sink. Printers consume the schedule. |
| Contract, which kernel to try, freeze, rollback, application score | **Lintel** |
| Cross-kernel dependencies and placement | **Lintel** program record |
| When a compiler version is promoted | **Lintel conducts** the decision from evidence. **This repo undergoes** the commit. |
| Decision-procedure changes | **Lintel**, separate experiment. Not a `compiler_ver` bump. |

## Admit signals, not languages

Cake hides layout. Ave makes layout algebra the spec. Averaging those languages is rejected.

Choreo’s layout cell is cheap `shape × stride`, so `{where: L}` can fire. SMT layout solving and CuTe work-partition are not this representation’s layout check. Findings may name `thread` / `element`. The oracles must actually fill `{where}`.

`W` / `L` / `S` / `V` are compiler diagnostics. `check() == []` is not an application score.

## Lowering

`choreoir.lower` is admit-gated. `Kernel.target` is required (`cuda` / `cuda-sm*` / `ascend*`). The regression pair is `copy`, `gemm_tile`.

Agents do not mutate PTX, SASS, or Davinci. NVIDIA CUDA C++ (`print_cuda`) is `lower().text` and `nvcc -cubin` when the toolchain is present; Triton knobs are a sidecar. Ascend CCE (`print_ascendc`) is `lower().text` and `ccec` when present; TileLang-Ascend is a sidecar. Printers consume `Partition`, `Barrier`, `Pipeline.depth`, layout, space, and gmem writeback. `materialize` writes `pin.json`: a Lintel `cache-key.v0` payload. This tree does not freeze. Missing toolchain is a warning, not a fake binary.

Do not unify NVIDIA `smem` and Ascend L1 into one `onchip` enum. Vendor DSLs are sinks to print into, not a second live face.

## Success criteria

1. README, spec, and skill describe three loops and the five-function early coverage.
2. They do not restore a fixed band count, a year horizon as scope, a profile as the way a function gets an owner, or `examples/fails/` as proof that the compiler evolved.
3. Admit findings are localized `{where: W|L|S|V}` and are the only application-search feedback from this tree.
4. `lower()` to NVIDIA and to Ascend consumes `Partition`, `Barrier`, `Pipeline.depth`, layout, and space.
5. Land, rollback, freeze, the application score, and cross-kernel placement live in Lintel.
6. An IR-evolution commit bumps `compiler_ver`, keeps both sinks honest, and leaves the regression kernels passing.
7. A search walk does not rewrite `check` or add an opcode.
8. Agents land this tree by pushing `main` directly. No GitHub pull request on this repo.

## Non-goals (this tree)

- Controller improvement, MCP, budgets, agent graphs, freeze, and the application score.
- A joint search encoded as one AST over graph, communication, and placement.
- Designing the cubin / NPU-bin ISA in place of the sink.
- SMT layout as this representation’s layout check.
- Treating Helion, KernelEvolve, or TritorX as this face.
- Claiming Cake’s reported speedups from `role` alone.
- A year-scoped kernel list, or one application’s profile, as the architecture.

## Falsifiers

- Under a matched budget and the same feedback, raw CUDA, PTX, or Triton matches or beats this representation on correctness and speed.
- Layout or sync rejects cannot name a program point (and, where relevant, a thread or element).
- A simpler existing interface gets the same attainable performance and validation, so the new representation has not earned its cost.
- An IR-evolution change fixes the motivating kernel and breaks the other regression kernel, and still lands.
- Recurring rejects show the representation cannot express a schedule the sink must lower, and no promoted version is proposed.
- A Lintel prompt or workflow edit is recorded as a Choreo `compiler_ver` bump.
- `check` or the dialect changes inside one application search.
- The demo is “we compiled Choreo,” with no application contract in Lintel.
- A necessary function has no owner in the early design, or a function appears or disappears because of a calendar slice or one application’s profile.
