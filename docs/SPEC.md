# Choreo IR spec (v0.1)

Status: draft. Data-plane object only. No agent protocol in this file.

Co-design with Lintel: [`goals/lintel-codesign.md`](../goals/lintel-codesign.md). Implementer SOP: [`skills/choreo-lintel-codesign/SKILL.md`](../skills/choreo-lintel-codesign/SKILL.md).

## 1. Design rules

1. **One band.** Choreo is an L4 kernel IR. It does not represent framework graphs, MLIR pass pipelines, CUDA Graphs, or agent DAGs.
2. **Structured, not textual.** The source of truth is the AST. Pretty-printers exist for humans; agents must not round-trip through dumped Triton/CUDA as the mutation API.
3. **Enumerate mutations.** Ops, memory spaces, partition roles, and barrier kinds are closed enums in v1. New hardware enters as new op/intrinsic variants (TIRx: intrinsics first), not free SSA.
4. **Admit before codegen.** `check(kernel) -> list[Finding]` is total. Codegen is refused if any finding has `severity=error`.
5. **Localized findings.** Each error names a node id. Layout/sync errors may also name `thread` and `element` (Argus-shaped). No “see stderr.”
6. **Lowering is classical.** Interpreter and printers are deterministic functions of the AST. They are not LLM calls.

## 2. Core sorts

```text
Kernel      = { name, target, params, buffers, partitions, body, attrs }
Param       = { name, dtype, shape }            # shape may contain symbols
Buffer      = { name, space, layout, dtype }
Layout      = { shape, stride }                 # CuTe-style pair; v1: static ints
Partition   = { name, role, width }             # width = warps or threads
Op          = Copy | Mma | Reduce | Barrier | Pipeline | Yield
Space       = gmem | smem | tmem | regs
Role        = load | math | store | generic
```

`body` is a straight-line list of ops plus structured `Pipeline` regions. v1 has **no** unstructured CFG. LLM4IR’s CFG-edge failure is treated as a language bug to avoid, not a benchmark to dump into the prompt.

## 3. What the LLM may emit (when a later agent exists)

Allowed:

- Create/replace a `Kernel` AST (or a JSON encoding of it).
- Edit enumerated fields: `target`, tile sizes, partition widths, pipeline depth, layout strides, which `Copy`/`Mma` variant.

Forbidden (in this IR, forever):

- Embed raw PTX/CUDA/Triton strings as the program.
- Emit pass lists, MCP tool calls, or serving-level A/B policy.
- Invent new memory spaces or roles without a spec bump.

## 4. Admit pipeline (W → L → S → V)

| Gate | Question | Failure shape |
|---|---|---|
| **W** wellformed | Types, ranks, every buffer used, every partition named, no unknown ops | `{node, msg}` |
| **L** layout | `size(layout) == numel(buffer)`; copy src/dst layouts compose; MMA fragments match dtype | `{node, element?, msg}` |
| **S** sync | Every cross-partition `Copy`/`Mma` has a dominating `Barrier`; no cyclic wait | `{node, partition?, msg}` |
| **V** value-sim | Interpreter on a tiny concrete shape matches a reference `numpy` kernel | `{node, index?, expected, got}` |

v1 implements W fully, L for static shapes, S for barrier pairing, V for `Copy`, `Mma`, and `Reduce` on CPU. SMT (Argus Z3) is v2: same finding schema, heavier solver.

These gates are **T2-color signals**, not serving oracles (T6). Passing V does not mean SGLang A/B.

## 5. Lowering

This compiler object **always** lowers to NVIDIA GPU and Ascend NPU. `lower(kernel)` is refused if `check` has `severity=error` or `target` is missing.

| Family | `Kernel.target` | Sink | Consumes |
|---|---|---|---|
| CPU interpreter | (any) | `simulate` | Copy / Mma / Reduce values |
| NVIDIA GPU (M2 source) | `cuda`, `cuda-sm*` | Triton (`print_triton`) | layouts → `BLOCK_*`, partitions → `num_warps`, `Pipeline.depth` → `num_stages`, `Barrier` → `tl.debug_barrier` |
| NVIDIA GPU (cubin path) | `cuda`, `cuda-sm*` | CUDA C++ (`print_cuda`) + `nvcc -cubin` | smem → `__shared__`, Copy → gmem loads, Barrier → `__syncthreads`, Pipeline → staged smem, Mma ISA from target (`mma.sync` / `wgmma` / `tcgen05`) |
| Ascend NPU | `ascend*` | TileLang (`print_ascend`) + CANN when present | spaces → GM/L1/L0C/UB, `T.copy` / `T.gemm` / `T.pipe_barrier` / `T.Pipelined` |

`materialize(kernel, out_dir, emit='cubin'|'npu-bin')` writes source and tries the device toolchain. Missing `nvcc` / TileLang is a warning finding, not a fake binary. Year-1 SLA names: `copy`, `gemm_tile`. Do not glue NVIDIA and Ascend spaces into one enum.

Choreo **storage layout** is an explicit contract for admit and for the sinks (cheap `shape × stride`). Work partitioning lives in `Partition` + `Layout`.

## 6. JSON finding schema

```json
{
  "gate": "W|L|S|V",
  "severity": "error|warning",
  "node": "op.3",
  "partition": "load0",
  "thread": null,
  "element": [0, 1],
  "msg": "smem layout stride does not cover K"
}
```

This is the only feedback surface intended for a future agent. Not a control-plane API: it is compiler diagnostics.

Kernel JSON (construct / inspect / mutate) is defined by `choreoir.jsonio.kernel_to_dict`. Ops are tagged with `"op": "copy"|"mma"|"reduce"|"barrier"|"pipeline"|"yield"`.

## 7. Out of spec

Event Tensor / persistent megakernels, cluster launch, power/energy objectives, artifact hashing for CI replay, agent-search rungs. Those attach *above* or *beside* this IR (L6, L7, T3, control plane).
