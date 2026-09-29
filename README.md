# Choreo IR

Kernel-schedule compiler for an agentic search: a typed program, checks, and classical lowering to NVIDIA GPU and Ascend NPU.

**Three loops stay apart.** Application search edits a `Kernel` under a pinned compiler version and gets a localized reject. IR evolution is a later commit on `main` that may change the representation, a check, or a sink. Controller improvement (how the search decides) is Lintel’s experiment, not this tree. The 23 September 2026 survey is the source of that split: [`goals/lintel-codesign.md`](goals/lintel-codesign.md).

**Starting scope is one kernel schedule** (tiles, roles, barriers, layouts, memory spaces). A fixed stack of bands is not a law. Widen only when a measured bottleneck sits outside the kernel, as a promoted version or a separate representation. Do not put framework graphs, MLIR pipelines, or placement into `Kernel`.

Lintel (other repo) decides what to try, what to ship, and what to roll back. The demo that fails the product test is still “we compiled Choreo,” with no application contract. Device ISA design is later; year-1 sinks must still consume the schedule.

Starting architecture: [`goals/agentic-compiler.md`](goals/agentic-compiler.md). What Lintel should consume: [`docs/LINTEL_CONSUME.md`](docs/LINTEL_CONSUME.md). Implementer SOP: [`skills/choreo-lintel-codesign/SKILL.md`](skills/choreo-lintel-codesign/SKILL.md). Git: commit and push `main` only; no pull requests.

Upstream sketch: [zackc6/choreo](https://github.com/zackc6/choreo). Survey: [zackc6/ai-compiler-survey](https://github.com/zackc6/ai-compiler-survey) through 2026-09-23.

## What this representation is for

The survey’s recommendation is to compare existing languages, structured interfaces, and a proposed representation on the same tasks. Choreo is that proposed kernel-schedule representation. It has not yet earned a permanent place by that comparison.

| Concern | This repo |
|---|---|
| Pasted LLVM, MLIR, or Triton text as the program | Out. Syntax is not the executable form (LLM4IR). |
| Pass lists and hints | Out of v0.1. Those advise some other compiler. |
| **Typed kernel schedule** | **In.** Closed AST. Admit signals `W/L/S/V`, not Cake ∪ Ave ∪ TIRx as one dialect. |
| Agent workflows, MCP, controller self-improvement | Out. Lintel, and only as their own experiment. |
| Graph, communication, runtime placement | Not this AST. A later representation if a profile says the kernel boundary is the limit. |

Application search mutates the AST. Checks and lowering are deterministic. An optimizer model does not define executable behavior, and it does not run on the default serving path.

## Why this is a kernel schedule, not a language union

Cake, Ave (previously Argus), and TIRx are evidence for **admit mechanisms** (typed schedule, localized `{where}`, cheap pre-device filter), not a license to glue those languages into one dialect. Cake hides layout; Ave makes layout algebra the spec. Choreo picks a third cell: cheap `shape × stride` so `{where: L}` can fire. No year-1 Z3. No CuTe work-partition.

Lintel conducts application search and decides when an IR-evolution commit should land. This tree undergoes that commit. Year-1 printers (`print_cuda` / `print_ascendc` cubin- and NPU-bin-bound; `print_triton` / `print_ascend` sidecars) are the stand-in device path and must consume the schedule. The cubin / NPU-bin ISA is designed later. See [`goals/lintel-codesign.md`](goals/lintel-codesign.md).

| Piece | Cake (NVIDIA/CMU) | Ave, previously Argus | TIRx (TVM) | Choreo v0.1 |
|---|---|---|---|---|
| Typed schedule (roles, barriers, tiers) | Yes; **no** layout algebra | Implicit in the tile DSL | Orchestration in source | **Yes** (closed AST) |
| Layout algebra + compile-time discharge | No | Yes (Ave: tags + SMT, thread/element CEX) | Storage contract, not CuTe work-partition | Cheap `shape×stride` only; SMT not in year-1 |
| FFI construct / inspect / mutate | Harness (not public) | Pythonic DSL | TVM FFI | **Yes** (Python AST is the FFI; JSON too) |
| Pre-GPU admit | Safety / conformance / schedule gates | Layout SMT | Wellformed / sync / race / value-sim | **W/L/S/V signals** (not the application score) |
| Lowering | CUDA/PTX (cubin) | AMD ISA | CUDA C++/PTX | **Required families:** NV GPU and Ascend NPU; year-1 stand-in: CUDA C++ + `nvcc`, CCE + `ccec`; Triton/TileLang sidecars; device ISA later |
| Public tree | No | No | TVM | This repo |

Vendor DSLs (TileLang, Gluon, TLX, CuTe DSL, FlyDSL, ThunderKittens) are **sinks** this IR may lower *into*. `@tirx.v0` / `@cake.v0` / `@tilelang.ascend` are optional doors, not a second live representation.

## Non-goals (explicit)

- Control plane and controller self-improvement: multi-agent loops, MCP, budget/stop, application score, workflow compile (Lintel).
- One IR that is both a portable graph and a peak kernel schedule. Wider scope is another representation or a promoted version, not graph opcodes on `Kernel`.
- Fluency dumps of LLVM, MLIR, Triton, or PTX as the mutation language.
- Claiming library-class TFLOPS or an application score from this tree alone.
- Replacing `opt` / Inductor / Triton / CANN as the **device** compiler. This tree **does** lower *into* them.

## v1 deliverable

A **checkable IR**, not a kernel-agent product.

1. **AST** — kernel, buffers, layouts, partitions (roles), ops (`Copy`, `Mma`, `Reduce`, `Barrier`, `Pipeline`, `Yield`).
2. **Admit W/L/S/V** — wellformed, layout legality, sync/race, tiny-tile value sim — returning *localized* findings (program point, optional thread/element), not scraped compiler stdout.
3. **CPU interpreter** — so admit does not require a GPU (TIRx-style sim).
4. **Lower** — admit-gated `lower()` to NVIDIA GPU and Ascend NPU. Year-1 allowlist: `copy`, `gemm_tile` (gmem writeback; gemm has `Pipeline.depth=3`). `lower().text` is CUDA C++ / CCE. Official `nvcc` / `ccec` emit ELF cubin / NPU-bin when present. Triton and TileLang are sidecars. Device ISA design is later. Printers must consume the schedule.

v2 (still this compiler): plugin lowers to Gluon/TLX/TileLang/HIP; optional Z3 on layout tags.
v3 (other repo): an agent that mutates Choreo IR and consumes finding JSON.

## Run

Python 3.11+.

```bash
python3 -m pip install -e '.[dev]'
python3 -m pytest -q
```

Public GitHub Actions fetches official `nvcc` (`CHOREO_FETCH_NVCC=1`) and sets `CHOREO_REQUIRE_NVCC=1` so NVIDIA cubin tests run on `main`. `ccec` is not a public redist; Ascend NPU-bin tests skip there.

Admit / simulate / print from JSON (see `examples/`):

```bash
python3 -m choreoir check examples/copy.json
python3 -m choreoir sim examples/gemm.json \
  --tensors examples/gemm.tensors.json \
  --expected examples/gemm.expected.json
python3 -m choreoir print examples/gemm.json
python3 -m choreoir print examples/gemm.json --target ascend-a2
python3 -m choreoir lower examples/gemm.json -o /tmp/choreo-out --emit cubin
python3 -m choreoir lower examples/gemm.json -o /tmp/choreo-npu --target ascend-a2 --emit npu-bin
python3 -m choreoir pin /tmp/choreo-out/pin.json
python3 -m choreoir consume-check /path/to/lintel
python3 -m choreoir propose examples/copy.json
python3 -m choreoir propose examples/fails/layout_cover.json
python3 -m choreoir propose examples/fails/value_mismatch.json \
  --tensors examples/fails/value_mismatch.tensors.json \
  --expected examples/fails/value_mismatch.expected.json
```

Or from Python:

```python
from choreoir import Buffer, Copy, Kernel, Layout, Partition, check, lower

k = Kernel(
    "copy",
    target="cuda",
    buffers=(
        Buffer("A", "gmem", Layout((8, 8), (8, 1)), "f16"),
        Buffer("S", "smem", Layout((8, 8), (8, 1)), "f16"),
    ),
    partitions=(Partition("load", "load", 4),),
    body=(Copy("c0", "A", "S", "load"),),
)
assert check(k) == []
gpu = lower(k)
assert gpu.family == "cuda" and "__global__" in gpu.text
k.target = "ascend-a2"
npu = lower(k)
assert npu.family == "ascend" and "__aicore__" in npu.text
assert "T.copy" in npu.tilelang_text
```

Findings are JSON-serializable (`Finding.as_dict`) so a later agent can consume them without scraping stdout.

## Falsifiers

- Under a matched budget and the same feedback, raw CUDA, PTX, or Triton matches or beats this representation on correctness and speed.
- Layout or sync rejects cannot name a program point (and, where relevant, a thread or element).
- A simpler existing interface gets the same attainable performance and validation, so this representation has not earned its cost.

## Cite (primaries, not this survey)

- Survey — [zackc6/ai-compiler-survey](https://github.com/zackc6/ai-compiler-survey) through 2026-09-23
- Cake — arXiv:2608.12629
- Ave (previously Argus) — arXiv:2604.18616
- TIRx — https://tvm.apache.org/2026/06/22/tirx
- LLM4IR — ICML 2025, arXiv:2502.06854
- TileLang / Gluon / TLX / CuTe DSL / FlyDSL — sinks to print into, not this IR

## Layout

```text
choreoir/     AST + checkers + interpreter + NV/Ascend sinks + JSON FFI
examples/     copy and GEMM-tile kernels as JSON (gmem writeback); fails/ localized rejects; proposal/pin handshake goldens
tests/        wellformed / layout / sync / sim / printer / CLI
docs/SPEC.md  grammar and admit rules
docs/LINTEL_CONSUME.md  what the Lintel plan repo should treat as current
goals/        starting architecture + scope and IR-evolution judgment
skills/       implementer SOP for that cut
schemas/      Lintel cache-key.v0 handshake copy (Lintel is source of truth)
AGENTS.md     which skill to read before editing
```
