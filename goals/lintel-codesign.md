# Goal: Choreo × Lintel co-design

Status: active implementer detail under [`agentic-compiler.md`](agentic-compiler.md). Revised **2026-09-29** against [zackc6/ai-compiler-survey](https://github.com/zackc6/ai-compiler-survey) through **2026-09-23**. Do not let this file overwrite that picture.
Skill: [`skills/choreo-lintel-codesign/SKILL.md`](../skills/choreo-lintel-codesign/SKILL.md).

## Judgment

The August 2026 goals matched an older survey map: one controller, search confined to a kernel “band,” and a single evolution clock. The 23 September 2026 survey revised that map. Two corrections matter here.

**Scope.** A fixed layer count is unproven. Expanding what the compiler may optimize (kernels, communication, memory, runtime) is a separate question from whether an agent should do the search. This tree still starts at a kernel schedule, because that is the evidenced surface and the first implementation sequence. “Search only this band forever” is retired. Widening waits on a measured bottleneck outside the kernel. Stuffing a graph, MLIR, or placement dialect into `Kernel` stays rejected: one representation that is also a portable graph is a bad unification, and several representations may coexist.

**Self-evolving loop in the IR.** The survey now separates three targets. Application search changes the program. Compiler evolution changes analyses, transformations, representations, or backends, and must be judged on workloads that did not motivate the change. Controller improvement changes the decision procedure (instructions, search strategy, orchestration, agent code) and, as of that survey, has no application-level compiler evidence; it is the most expensive loop and a late gated experiment. Storing logs is memory, not either evolution.

The previous “two clocks” note got the pin right and the target wrong. It forbade rewriting `check` inside one search (that still holds: acceptance rules stay fixed during an experiment). It then called every later commit “the compiler evolves,” while also freezing vocabulary so the representation could not evolve. Recurring rejects are the input to IR evolution, not a cue to invent an opcode in the search, and not a cue to edit Lintel’s decision procedure. `examples/fails/` localizes application-search rejects. It is not evidence that this compiler has evolved.

Retired as laws: Horizon A, M1, M3, T5, C6, and L1–L7. They remain historical survey identifiers only.

## One line

**Yes** as the kernel-schedule compiler an agent edits under a pinned version, checked and lowered to NVIDIA GPU and Ascend NPU. **No** as the control plane, and **no** as controller self-improvement. **No** as Cake, Ave, and TIRx glued into one dialect. **No** as a permanent seven-band architecture.

## Three loops

| Loop | What changes | Where it lives | Promotion rule |
|---|---|---|---|
| Application search | The `Kernel` (tiles, roles, depth, layout, spaces) | Lintel proposes; this tree checks and lowers | Compiler version pinned. Reject `{where}` → next kernel. |
| IR evolution | Representation, checks, or sinks | A commit on this `main` | New `compiler_ver`, then a new `%k`. Kernels that did not motivate the change still have to pass. Both sink families consume a new schedule field. |
| Controller improvement | How Lintel decides | Lintel only, and only as its own experiment | Compiler and acceptance rules held fixed. Out of this tree until that experiment exists. |

Inside one application search, `choreoir` is an ordinary function of the AST. No LLM in `check` or `lower`. A versioned bundle of extra findings is still IR evolution: its hash belongs in `%k`, and it does not rewrite itself mid-search.

Year-1 preference inside the IR loop: deepen checks and sinks before adding vocabulary. A new op, space, role, or memory enum is allowed when the representation is the measured limit. Same change: spec bump, a check that admits it, and sinks that lower it. Syntax without effects is rejected.

## Scope of this representation

v0.1 is one kernel: buffers, layouts, partitions, barriers, pipelines, and gmem writeback for `copy` and `gemm_tile`.

| Pressure | Response |
|---|---|
| A reject names a kernel point (`W\|L\|S\|V`) | Next kernel in the application search. |
| The same reject, or an unsinkable schedule, recurs across kernels | Open an IR-evolution change. |
| The profile is dominated by communication, launch, or runtime | A separate representation or a promoted widening. Not new graph ops on `Kernel`. |
| Lintel’s search policy is weak | Controller experiment in the Lintel repo, with this compiler pinned. |

The representation is under test. It earns a permanent place only if a matched comparison (same tasks, feedback, and budget) beats a strong existing interface on attainable performance, search efficiency, or validation. Cake’s clean-start result is one setting and does not settle that comparison. Ave (previously Argus) is evidence for localized data-flow feedback, not a license to copy its language.

## Who owns which object

| Object | Owner |
|---|---|
| Typed kernel the agent edits | **Choreo** |
| Checks and classical lowering | **Choreo** (deterministic). Device ISA design is later; year-1 sinks are the stand-in and must consume the schedule. |
| Which kernel to try, freeze, rollback, application score | **Lintel** |
| When a compiler version is promoted | **Lintel conducts** the decision from evidence. **This repo undergoes** the commit. |
| Decision-procedure changes | **Lintel**, separate experiment. Not a `compiler_ver` bump. |

## Admit signals, not languages

Cake hides layout. Ave makes layout algebra the spec. Averaging those languages is rejected.

Choreo’s layout cell is cheap `shape × stride`, so `{where: L}` can fire. No year-1 Z3. No CuTe work-partition. Findings may name `thread` / `element`. The oracles must actually fill `{where}`.

`W` / `L` / `S` / `V` are compiler diagnostics. `check() == []` is not an application score.

## Lowering

`choreoir.lower` is admit-gated. `Kernel.target` is required (`cuda` / `cuda-sm*` / `ascend*`). Year-1 allowlist: `copy`, `gemm_tile`.

Agents do not mutate PTX, SASS, or Davinci. NVIDIA CUDA C++ (`print_cuda`) is `lower().text` and `nvcc -cubin` when the toolchain is present; Triton knobs are a sidecar. Ascend CCE (`print_ascendc`) is `lower().text` and `ccec` when present; TileLang-Ascend is a sidecar. Printers consume `Partition`, `Barrier`, `Pipeline.depth`, layout, space, and gmem writeback. `materialize` writes `pin.json`: a Lintel `cache-key.v0` payload. This tree does not freeze. Missing toolchain is a warning, not a fake binary.

Do not unify NVIDIA `smem` and Ascend L1 into one `onchip` enum. Vendor DSLs are sinks to print into, not a second live face.

## Year-1 pinned surface

Two complete kernels. That cardinality is the current experiment, not a ceiling on the IR loop. Do not grow the dialect to look like a language product. Do not refuse a promoted construct that both sinks can lower and that the existing kernels still survive.

`@triton.v0` knobs stay a standby sidecar while official `nvcc` cubin exists for the allowlist. They are not the product test.

## Success criteria

1. README, spec, and skill describe three loops and a kernel-schedule starting scope.
2. They do not restore a fixed band count, or call `examples/fails/` proof that the compiler evolved.
3. Admit findings are localized `{where: W|L|S|V}` and are the only application-search feedback from this tree.
4. `lower()` to NVIDIA and to Ascend consumes `Partition`, `Barrier`, `Pipeline.depth`, layout, and space.
5. Land, rollback, freeze, and the application score live in Lintel.
6. An IR-evolution commit bumps `compiler_ver`, keeps both sinks honest, and leaves the previous allowlist passing.
7. A search walk does not rewrite `check` or add an opcode.
8. Agents land this tree by pushing `main` directly. No GitHub pull request on this repo.

## Non-goals (this tree)

- Controller improvement, MCP, budgets, agent graphs, freeze, and the application score.
- A joint search over graph, communication, and placement inside this AST.
- Designing the cubin / NPU-bin ISA in place of the later lowering design.
- SMT layout as a year-1 compiler.
- Treating Helion, KernelEvolve, or TritorX as this face.
- Claiming Cake’s reported speedups from `role` alone.

## Falsifiers

- Under a matched budget and the same feedback, raw CUDA, PTX, or Triton matches or beats this representation on correctness and speed.
- Layout or sync rejects cannot name a program point (and, where relevant, a thread or element).
- A simpler existing interface gets the same attainable performance and validation, so the new representation has not earned its cost.
- An IR-evolution change fixes the motivating kernel and breaks the other allowlisted kernel, and still lands.
- Recurring rejects show the representation cannot express a measured schedule, and no promoted version is proposed.
- A Lintel prompt or workflow edit is recorded as a Choreo `compiler_ver` bump.
- `check` or the dialect changes inside one application search.
- The demo is “we compiled Choreo,” with no application contract in Lintel.
