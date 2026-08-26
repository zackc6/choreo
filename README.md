# Choreo IR

Typed **kernel choreography IR** for the data plane — Lintel’s L4 face, not a compiler company.

This tree is the compiler object: an IR you can construct, check, simulate, and print. It is **not** an orchestrator, MCP server, agent graph, or fitness-\(F\) controller. Lintel (control plane: admit freeze, land / revert / reject, serving \(F\)) lives in a different repo.

Co-design: [`goals/lintel-codesign.md`](goals/lintel-codesign.md). Implementer SOP: [`skills/choreo-lintel-codesign/SKILL.md`](skills/choreo-lintel-codesign/SKILL.md).

Upstream sketch: [zackc6/choreo](https://github.com/zackc6/choreo).

## Survey lean this implements

The living AI-compiler survey’s **LLM-oriented IR** is the agent-visible *face* of an existing data-plane band — **not** a new L-llm band, **not** dumped LLVM/MLIR, **not** an IR of agent workflows (T10).

| Survey family | This repo |
|---|---|
| Fluency IR (paste `.ll` / Triton text) | Out of scope — LLM4IR: syntax ≠ CFG/exec |
| Summary / fingerprint | Optional later view over this AST, not the source of truth |
| Intent / action (pass lists, hints) | Out of v1 — that is advisory *on* a compiler, not a kernel IR |
| **Typed agent-facing IR** | **In scope** — closed Choreo AST; union of **admit signals** (W/L/S/V), not Cake ∪ Argus ∪ TIRx as one dialect |
| Translation glue | Out of scope |
| Control-plane substrate (Auto / FlowCompile / AgentFlow) | **Forbidden here** |

**Home band: L4 (kernel DSL).** That is where kernel agents already train and search (C4). Do not replace StableHLO (L2) or MLIR (L3). Do not invent Event Tensor–class megakernel IR (L6) in v1.

**Hybrid split (invariant).** This IR is what a searcher may *mutate*. Classical passes own legality, lowering, and measure. LLM output must not silently define executable behavior.

## Why “next” is a face + control plane, not a language union

Cake, Argus, and TIRx are evidence for **admit mechanisms** (typed schedule, localized `{where}`, cheap pre-device filter), not a license to glue those languages into one dialect. Cake hides layout; Argus makes layout algebra the spec. Choreo picks a third cell: cheap `shape × stride` so `{where: L}` can fire. No year-1 Z3. No CuTe work-partition.

Lintel owns Cake’s *harness loop* (arXiv:2608.12629 §3–4). Choreo is the typed IR the agent edits. Lowering is a named sink (GPU cubin, Ascend NPU bin), not `print_triton`. See [`goals/lintel-codesign.md`](goals/lintel-codesign.md).

| Piece | Cake (NVIDIA/CMU) | Argus (CausalFlow et al.) | TIRx (TVM) | Choreo v0.1 |
|---|---|---|---|---|
| Typed schedule (roles, barriers, tiers) | Yes; **no** layout algebra | Implicit in the tile DSL | Orchestration in source | **Yes** (closed AST) |
| Layout algebra + compile-time discharge | No | Yes (tags + SMT, thread/element CEX) | Storage contract, not CuTe work-partition | Cheap `shape×stride` only; SMT not in year-1 |
| FFI construct / inspect / mutate | Harness (not public) | Pythonic DSL | TVM FFI | **Yes** (Python AST is the FFI; JSON too) |
| Pre-GPU admit | Safety / conformance / schedule gates | Layout SMT | Wellformed / sync / race / value-sim | **W/L/S/V signals** (not serving \(F\)) |
| Lowering | CUDA/PTX (cubin) | AMD ISA | CUDA C++/PTX | CPU interpreter + Triton **sketch** (not a compiler) |
| Public tree | No | No | TVM | This repo |

Vendor DSLs (TileLang, Gluon, TLX, CuTe DSL, FlyDSL, ThunderKittens) are **sinks** this IR may lower *into*. They are not the LLM-oriented face. `@tirx.v0` / `@cake.v0` / `@tilelang.ascend` are optional doors, not a second live face.

## Non-goals (explicit)

- Control plane: multi-agent loops, MCP, budget/stop, serving \(F\), workflow compile.
- One IR that is both portable HLO and peak kernel DSL (§5.1.1: do not unify those).
- Fluency dumps of LLVM, MLIR, Triton, or PTX as the mutation language.
- Claiming library-class TFLOPS or serving A/B in v1 (C2 stays open until oracles exist).
- Replacing `opt` / Inductor / Triton as the execution compiler.

## v1 deliverable

A **checkable IR**, not a kernel-agent product.

1. **AST** — kernel, buffers, layouts, partitions (roles), ops (`Copy`, `Mma`, `Reduce`, `Barrier`, `Pipeline`, `Yield`).
2. **Admit W/L/S/V** — wellformed, layout legality, sync/race, tiny-tile value sim — returning *localized* findings (program point, optional thread/element), not scraped compiler stdout.
3. **CPU interpreter** — so admit does not require a GPU (TIRx-style sim).
4. **One printer** — Triton sketches for copy and GEMM-tile kernels.

v2 (still data plane): plugin lowers to Gluon/TLX/TileLang/HIP; optional Z3 on layout tags.
v3 (other repo): an agent that mutates Choreo IR and consumes finding JSON.

## Run

Python 3.11+.

```bash
python3 -m pip install -e '.[dev]'
python3 -m pytest -q
```

Admit / simulate / print from JSON (see `examples/`):

```bash
python3 -m choreoir check examples/copy.json
python3 -m choreoir sim examples/gemm.json \
  --tensors examples/gemm.tensors.json \
  --expected examples/gemm.expected.json
python3 -m choreoir print examples/gemm.json
```

Or from Python:

```python
from choreoir import Buffer, Copy, Kernel, Layout, Partition, check

k = Kernel(
    "copy",
    buffers=(
        Buffer("A", "gmem", Layout((8, 8), (8, 1)), "f16"),
        Buffer("S", "smem", Layout((8, 8), (8, 1)), "f16"),
    ),
    partitions=(Partition("load", "load", 4),),
    body=(Copy("c0", "A", "S", "load"),),
)
assert check(k) == []
```

Findings are JSON-serializable (`Finding.as_dict`) so a later agent can consume them without scraping stdout.

## Falsifiers

- Under a matched token budget, agents editing raw CUDA/PTX/Triton beat agents editing Choreo on correctness × speed (reverses Cake’s clean-start result).
- Layout/sync admit cannot localize failures to (point, thread, element) — Argus’s reason to exist.
- A production stack ships peak + serving SLOs with no distinct kernel DSL (would collapse the L4 bet).

## Cite (primaries, not this survey)

- Cake — arXiv:2608.12629
- Argus — arXiv:2604.18616
- TIRx — https://tvm.apache.org/2026/06/22/tirx
- LLM4IR — ICML 2025, arXiv:2502.06854
- TileLang / Gluon / TLX / CuTe DSL / FlyDSL — L4 sinks, not this IR

## Layout

```text
choreoir/     Python AST + checkers + interpreter + Triton printer + JSON FFI
examples/     copy and GEMM-tile kernels as JSON
tests/        wellformed / layout / sync / sim / printer / CLI
docs/SPEC.md  grammar and admit rules
goals/        co-design goals (Lintel control plane / Choreo data plane)
skills/       implementer SOP for that cut
AGENTS.md     which skill to read before editing
```
