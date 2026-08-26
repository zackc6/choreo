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
Kernel      = { name, target, compiler_ver, params, buffers, partitions, body, attrs }
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

v1 implements W fully (including role/space: gmem→onchip wants `load`, onchip→gmem wants `store`, MMA/Reduce want `math`; `generic` is the escape), L for static shapes, S for barrier pairing (localized to arriving `partition` + `thread=0` first lane), V for `Copy`, `Mma`, and `Reduce` on CPU (`choreo check --tensors --expected` runs W→L→S then V). SMT (Argus Z3) is v2: same finding schema, heavier solver.

These gates are **T2-color signals**, not serving oracles (T6). Passing V does not mean SGLang A/B.

## 5. Lowering

This compiler object **always** lowers to NVIDIA GPU and Ascend NPU. `lower(kernel)` is refused if `check` has `severity=error` or `target` is missing. **L5 ISA (cubin / NPU bin) is later design.** Year-1 printers are the stand-in and must consume the schedule. Agents do not mutate PTX.

| Family | `Kernel.target` | Sink | Consumes |
|---|---|---|---|
| CPU interpreter | (any) | `simulate` | Copy / Mma / Reduce values |
| NVIDIA GPU (M2 sidecar) | `cuda`, `cuda-sm*` | Triton (`print_triton`) | layouts → `BLOCK_*`, partitions → `num_warps`, `Pipeline.depth` → `num_stages`, `Barrier` → `tl.debug_barrier`. Kill switch if cubin never lands. |
| NVIDIA GPU (cubin-bound stand-in) | `cuda`, `cuda-sm*` | CUDA C++ (`print_cuda`); `nvcc` when present | smem → `__shared__`, Copy → gmem↔onchip loops, Barrier → `__syncthreads`, Pipeline → staged smem, Mma ISA *name* from target. `lower().text` is this source. Not the designed cubin ISA. |
| Ascend NPU (sidecar) | `ascend*` | TileLang (`print_ascend`) | GM args + spaces → GM/L1/L0C/UB, `T.copy` / `T.gemm` / `T.pipe_barrier` / `T.Pipelined`. Not the NPU-bin path. |
| Ascend NPU (NPU-bin-bound stand-in) | `ascend*` | CCE (`print_ascendc`); `ccec` when present | gmem → `__gm__`, Copy → `copy_gm_to_ubuf` / `copy_ubuf_to_gm` (burst from layout), Barrier → `pipe_barrier`, Pipeline → staged loop, Mma → `cube.mmad` name + M/N/K loops + UB `vmadd` fallback. `lower().text` is this source. UB stand-in for onchip (like CUDA `float` for dtypes). Not the designed NPU ISA. |

`materialize(kernel, out_dir, emit='cubin'|'npu-bin')` writes the cubin/NPU-bin-bound stand-in (`.cu` / `.cce`) plus the Triton / TileLang sidecars, and tries official `nvcc` / `ccec` when present. Success writes a real ELF cubin or elf64-hiipu NPU object and pins `artifact_sha256` next to `source_sha256` in `pin.json` (`cache-key.v0` + sink payload) for Lintel `%k`. Missing toolchain is a warning finding, not a fake binary. Year-1 SLA names: `copy`, `gemm_tile` — both write results back to gmem (load / math / store partitions). Do not glue NVIDIA and Ascend spaces into one enum. Do not treat homemade PTX/Davinci as the L5 design.

Choreo **storage layout** is an explicit contract for admit and for the sinks (cheap `shape × stride`). Work partitioning lives in `Partition` + `Layout`.

## 6. JSON finding schema

```json
{
  "where": "W|L|S|V",
  "gate": "W|L|S|V",
  "severity": "error|warning",
  "node": "op.3",
  "partition": "load0",
  "thread": null,
  "element": [0, 1],
  "msg": "smem layout stride does not cover K"
}
```

`compiler_ver` on the Kernel JSON is the **choreoir** pin; it is not mutated inside one admit/lower walk. Lintel `%k` (`cache-key.v0`) names **both** that pin and the sink: `choreoir==0.1.6;nvcc.cubin`. `materialize` writes `pin.json` (`Lowered.as_k()`):

```json
{
  "schema_version": "choreo-pin.v1",
  "cache_key": {
    "schema_version": "cache-key.v0",
    "graph_hash": "sha256:…",
    "hw_id": "nvidia.sm_80",
    "compiler_ver": "choreoir==0.1.6;nvcc.cubin",
    "adapter_id": "choreo.v0",
    "policy_id": "lintel.specialize.v0"
  },
  "kernel": "gemm_tile",
  "family": "cuda",
  "isa": "mma.sync",
  "arch": "sm_80",
  "target": "cuda",
  "sink_id": "nvcc.cubin",
  "artifact_kind": "cubin",
  "artifact_sha256": "…",
  "source_sha256": "…"
}
```

`cache_key` is the freeze key (additionalProperties false). **Not in the key:** `model_id`, `enum_id`, `Kernel.target`. Year-1 has no L2 graph: default `graph_hash` is `sha256(lintel.graph.unspecified)`, not a hash of the Kernel JSON; Lintel overwrites it at freeze (`--graph-hash` / `attrs.graph_hash`). `hw_id` is derived from family/arch (`nvidia.sm_*` / `ascend.davinci`) or stamped (`--hw-id`); admission is that id, not `target`. `adapter_id` is the L4 **face** (`choreo.v0`). `sink_id` is the device compiler (`nvcc.cubin` / `ccec.aicore` / `cuda.cxx` / `ascendc.cce`) and is also the suffix of `cache_key.compiler_ver`. That is the **payload** Lintel freezes. This tree does not freeze, land, revert, or serve \(F\). Handshake schema: [`schemas/cache-key.v0.schema.json`](../schemas/cache-key.v0.schema.json) (Lintel is source of truth).

Kernel JSON (construct / inspect / mutate) is defined by `choreoir.jsonio.kernel_to_dict`. Canonical op tags are `"op": "copy"|"mma"|"reduce"|"barrier"|"pipeline"|"yield"`. Lintel examples that use PascalCase (`Copy`) are accepted on **read**. `choreo propose` emits `lintel.adapter_proposal.v0`: face `adapter_id=choreo.v0`, Kernel JSON as the payload, `gates: [W,L,S,V]`. On admit error, `reject.{where,hint,finding}` is the CFG edge Lintel copies (`where` is W|L|S|V only — `compile_ok` is Lintel's post-sink gate). Handshake: [`schemas/adapter-proposal.v0.schema.json`](../schemas/adapter-proposal.v0.schema.json). This tree does not walk that CFG.

## 7. Out of spec

Event Tensor / persistent megakernels, cluster launch, power/energy objectives, artifact hashing for CI replay, agent-search rungs. Those attach *above* or *beside* this IR (L6, L7, T3, control plane).
