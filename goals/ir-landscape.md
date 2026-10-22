# IR and DSL landscape — what exists, and what the agent-friendly ones changed

Status: **companion to [`self-evolving-ir.md`](self-evolving-ir.md), for debate** (same branch).
Requested by the maintainer on 22 October 2026: survey the state-of-the-art IRs and DSLs,
and the recent agent-friendly ones, before fixing Choreo's design — not limited to the
systems the earlier goals cite.

Evidence rule: every row names its source. Sources marked **(survey)** are digests in
[ai-compiler-survey/reference/publications](https://github.com/zackc6/ai-compiler-survey/tree/main/reference/publications)
and carry that repo's evidence tier; numbers are quoted from those digests. Sources marked
**(new, not yet in the survey)** were read for this document and are candidates for a survey
batch; they are not survey-verified. Systems with no citation are described from general
knowledge without numbers, and nothing below rests on them.

## 1. The axis, with the systems on it

Same axis as `self-evolving-ir.md` §1.1, now populated. "Agent sees" is what the mutation
surface exposes; "compiler owns" is what it hides.

| Cell | Systems | Agent sees | Compiler owns | Admit before device? |
|---|---|---|---|---|
| **A. ISA / post-compile** | PTX, SASS, AMDGPU asm — AsmEvo (survey, A) | everything | nothing | no; AsmEvo gates timing on equivalence to the original binary |
| **B. Template / layout-algebra libraries** | CUTLASS + CuTe DSL (survey, B), ThunderKittens (survey, B), FlyDSL (survey, B), CuTeGen as the agent on CuTe (survey) | layouts as algebra, warp roles, pipelines, as C++/Python | instruction selection | type/layout errors at compile time; no schedule-level check |
| **C. Tile languages, compiler picks the schedule** | Triton; cuTile / CUDA Tile (survey, A eval); Pallas → Mosaic (survey, B); Helion (survey, B); TileLang (survey, B) | blocked dataflow, tile sizes, a few knobs | layouts, pipelining, warp roles (TileLang infers layouts; Helion autotunes) | compiler errors; no localized schedule diagnostics |
| **C′. Tile languages with an explicit lower face** | Gluon (survey, B), TLX (survey, B), TileLang overrides, Triton Tile-IR backend (survey, B) | + explicit layouts, warp-group roles, barriers | lowering only | same as C |
| **D. Schedule-level IRs with typed decisions** | TensorIR / MetaSchedule (survey), TIRx (survey, B), Cake (survey, A), Ave/Argus (survey, A), Halide and Exo-style scheduling languages, MLIR Transform dialect, Mirage μGraphs (survey, A), **Choreo** | tiles, layouts, roles, sync, pipeline depth, as data | ISA | **yes** — this is the cell's defining property |
| **E. Narrow spec / knob DSLs** | **μCUTLASS** (new), Helion's autotuner config, Triton `num_warps/num_stages`, MetaSchedule search space | a validated grammar of knobs; 10–20 lines | the whole kernel (a library or a compiler generates it) | yes — the spec is validated before emit |
| **F. Operator / graph boundary** | ATen, StableHLO, ONNX, Event Tensor (survey) | op signature and shapes | everything below | only output checks |
| **G. Generic compiler IR as text** | LLVM IR, MLIR text — LLM4IR (survey, A), CIRBench (survey, A), IRCoder, Intent-driven IR (survey) | the whole program as text | — | the compiler's own verifier; no agent-targeted diagnostics |

## 2. What each cell's evidence says about the four goals

Scores are the survey's numbers where they exist; otherwise a qualitative reading, marked.

| Cell | Performance reach / steer | Compile cost per candidate | Traceable | Debuggable | Evidence |
|---|---|---|---|---|---|
| A | full reach; no steering — 0 enumeration. Works as *post-compile polish* when an equivalence oracle exists. | assembler only; correctness only by equivalence run | byte-exact, decision-blind | address faults | AsmEvo (survey, A): classical rebuild + equivalence-gated timing; the original binary is the oracle. |
| B | near-library reach in expert hands; the agent steers through code, not data | full C++ toolchain per candidate | source diff | template errors, famously opaque | CuTeGen (survey): agent on CuTe; cute-dsl digest: "layout algebra; Cake IR is typed schedule with no layout algebra". |
| C | **62–101 % of cuBLAS (Triton, autotuned per GPU)**; cuTile 52–79 % in 22 lines, slower than autotuned Triton on every tested shape; B200 attention cuTile 1.92× Triton but 53 % of FA2 on sm_120 | compiler + autotune; no cheap static reject | source diff + autotuner log | compiler stderr | cutile-evaluation (survey, A); the referee note flags whether cuTile got tile tuning the Triton baseline did not. |
| C′ | restores the decisions C hides when Blackwell-class kernels "broke Triton's promise" | same as C | same | same | triton-gluon, tlx (survey, B): "a lower face instead of abandoning the compiler". |
| D | the decisions that separate 60 % from 90 % are *data*; library-class numbers on B200 are **expert-authored**, no public agent loop yet | static checks in µs–ms before any toolchain | mutations are field edits | **localized**: Ave thread/element counterexamples; Cake typed rejects; TIRx wellformed/sync/race/value-sim | tirx (survey, B), cake (survey, A), argus (survey, A), mirage (survey, A: structured search + verification, no LLM). |
| E | **0.40× → 1.27× geomean over PyTorch for the same model (GPT-5-mini), raw code → μCUTLASS; 1.56× with SOL guidance; 2.07× with GPT-5**, 59 KernelBench problems, one H100 | spec validated, then CUTLASS C++ build | spec diff (10–20 lines) | spec validation errors; SOL integrity check catches >10 %-faster-than-light results | μCUTLASS (new, not yet in survey, arXiv 2603.29010, NVIDIA). Single GPU; SOL reports generated by an LLM; not general. |
| F | reach is whatever is behind the op; steer: none | full toolchain + run per candidate | excellent at the boundary, blobs inside | "element i wrong" | KernelBench-Verified (survey): 0.88× geomean under verified single-turn; 28 % of best kernels raise peak memory. |
| G | negative: **every model's median dynamic speedup on IR rewriting is below `-O3`** (0.66–0.96×); models get CFG edges wrong | compiler verifier | text diff | none targeted | cirbench (survey, A), llm4ir (survey, A). Bounds the "let it write the IR" option. |

Two readings that the table forces, and that `self-evolving-ir.md` must absorb:

1. **The strongest *measured* agent result on this axis is in cell E, not D.** μCUTLASS is a
   170-line EBNF of knobs over a library; the library owns the schedule. Same model, same
   budget, raw code 0.40× → spec 1.27×. Cell D has typed admit and localized rejects but no
   published agent loop with a number (TIRx and Cake numbers are expert-authored). So the
   honest position is: *closed grammar beats free text* is measured; *schedule-level beats
   knob-level* is not. Choreo's Tier-2 knob registry (§1.2 of the proposal) is cell E inside
   cell D, and the first thing to measure is whether Tier 2 alone — knobs over a strong sink —
   gets most of the gain. If it does, the schedule tier is the long tail, and the proposal
   should say so.
2. **Cell C′ is the industry's own answer to "compiler picks the schedule" failing** (Gluon,
   TLX, TileLang overrides). The decisions Choreo makes explicit are the same ones those
   faces added: layouts, warp roles, barriers. That is corroboration of *which* decisions
   matter, from three vendors, independent of any agent claim.

## 3. The agent-friendly IRs of 2025–26: what each actually added

| System | Mechanism added for the agent | What it does not do | Survey tier |
|---|---|---|---|
| **Cake** (NVIDIA/CMU) | typed schedule representation; compiler and harness localize failures; recurring limits feed representation/check changes — the co-design loop | no layout algebra; harness not public | A |
| **Ave / Argus** | data-flow (layout) invariants discharged by SMT; counterexample names thread and element | heavier solver; not a permanent agent/compiler boundary | A |
| **TIRx + TIRx Harness** | intrinsics-first kernel IR; storage contract; execution scope; wellformed/sync/race/value-sim checks; harness with analyses, simulation, references, profiling behind a stable contract | no published agent loop; library numbers expert-authored | B |
| **μCUTLASS + SOL** (new) | narrow validated grammar over CUTLASS; roofline bound used to steer hypotheses, schedule budget, and catch impossible results | not general; one GPU; SOL from an LLM | — |
| **Mirage** | enumerated μGraph mutations + probabilistic equivalence verification, no LLM | not an agent IR; a superoptimizer | A |
| **Helion + LLM autotuning** | high-level DSL; LLM-guided autotuning "from minutes to seconds" at comparable final latency | search-efficiency result, not a runtime gain (survey §4.3) | B |
| **TileLang LSP** | inferred layouts, scopes, dtypes exposed as hover/inlay — the compiler's inference made agent-visible | an IDE face, not an admit gate | B |
| **MLIR `mlir-opt-repl` + MCP server** (RFC) | the pass pipeline as an interactive tool surface | pass-level, not schedule-level | forum |
| **Intent-driven IR** (ICT/CAS) | optimization intent as IR instead of pass-by-pass | early | paper, 2026 |
| **KForge** | cross-platform (NVIDIA / Intel Arc) agent forge across DSLs | measures bring-up, not a representation | A |
| **MetaKernelBench** | cross-DSL skill transfer measured: **−19 % to +29 %**, regressions on 16–45 % of problems in every model | negative transfer is real; distilled knowledge is not language-free | A |
| **AsmEvo** | post-compile assembly edits with equivalence-gated timing | starts where lowering stopped; not a design surface | A |

Three patterns recur across the "friendly" ones, and they are exactly the three things
`self-evolving-ir.md` proposes to make first-class: **a closed grammar the agent fills in**
(Cake, TIRx, μCUTLASS), **a localized reject with a program point or element** (Ave, TIRx,
Cake), and **a cheap bound or simulation before the device** (SOL, TIRx value-sim, Mirage
verification). None of them yet has a published loop where the *representation itself*
evolves from counted rejects — Cake describes the loop; nobody reports it running.

## 4. Systems deliberately not on the axis, and why

- **Mojo / Modular, Hidet, Exo, Luminal, Taichi, Warp**: real DSLs, no survey digest with
  agent-relevant numbers; Exo's user-scheduling with equivalence-preserving rewrites is the
  closest ancestor of "mutations as records" (§3.2 of the proposal) and belongs in a survey
  batch before this doc leans on it.
- **Event Tensor, persistent megakernels, cluster launch**: out of Choreo's spec (§7); they
  are Lintel program-record concerns.
- **Agent harnesses that add memory or workflow but no representation** (KernelSkill,
  Kernel Forge, Xe-Forge, CudaForge, GEAK): they change the controller, not the IR, and are
  the controller loop's evidence, not this document's.

## 5. What this changes in the proposal

1. **Add Tier 2 first, measure it alone.** Reorder §5: the knob registry and `unexpressible`
   finding (row 3) before the lineage stamps (row 1), and add an explicit experiment: the
   enumerated proposer over Tier-2 knobs only versus Tier-1+2, same budget, same sink, on the
   regression pair. μCUTLASS is the prior that says most of the gain may be in E.
2. **Cite C′ as corroboration of the decision set**, not of Choreo: layouts, roles, barriers,
   depth are what Gluon/TLX/TileLang-overrides added when inference failed.
3. **Adopt a SOL-style bound as a gate input.** A roofline lower bound from `Layout` and
   `Mma` shapes costs nothing and gives the walk (a) a stop rule and (b) an integrity check
   on any future device number. It is cell-E evidence that transfers directly.
4. **Keep the schedule tier's burden of proof where the table puts it**: an autotuned
   Triton baseline, not an untuned one (the Claude-Action correction in the thread), and no
   claim that cell D beats E until the Tier-2-only arm has run.

## 6. Candidates for the survey (not edited here)

Sources read for this document that the survey does not digest yet, for a survey batch under
its own protocol: μCUTLASS + SOL guidance (arXiv 2603.29010, NVIDIA, 30 Mar 2026). Checked
and found to add no representation (so not proposed): KernelSkill (arXiv 2603.10085).
Not read, not cited: Xe-Forge (2605.26118), the trace-driven production benchmark
(2607.14541).
