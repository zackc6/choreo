# Choreo IR spec (v0.1)

Status: draft. Data-plane object only. No agent protocol in this file.

Co-design with Lintel: [`goals/lintel-codesign.md`](../goals/lintel-codesign.md). What Lintel should consume: [`LINTEL_CONSUME.md`](LINTEL_CONSUME.md). Implementer SOP: [`skills/choreo-lintel-codesign/SKILL.md`](../skills/choreo-lintel-codesign/SKILL.md).

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
| **W** wellformed | Types, ranks, every buffer used, every partition named, no unknown ops, `Pipeline.body` nonempty | `{node, msg}` |
| **L** layout | `size(layout) == numel(buffer)`; copy src/dst layouts compose; MMA fragments match dtype | `{node, element?, msg}` |
| **S** sync | Every cross-partition `Copy`/`Mma` has a dominating `Barrier`; no cyclic wait | `{node, partition?, msg}` |
| **V** value-sim | Interpreter on a tiny concrete shape matches a reference `numpy` kernel | `{node, index?, expected, got}` |

v1 implements W fully (including role/space: gmem→onchip wants `load`, onchip→gmem wants `store`, MMA/Reduce want `math`; `generic` is the escape; `Pipeline.body` must be the staged region — empty body is a W error), L for static shapes, S for barrier pairing (localized to arriving `partition` + `thread=0` first lane), V for `Copy`, `Mma`, and `Reduce` on CPU (`choreo check --tensors --expected` runs W→L→S then V). SMT (Argus Z3) is v2: same finding schema, heavier solver.

These gates are **T2-color signals**, not serving oracles (T6). Passing V does not mean SGLang A/B.

## 5. Lowering

This compiler object **always** lowers to NVIDIA GPU and Ascend NPU. `lower(kernel)` is refused if `check` has `severity=error` or `target` is missing. **Designed L5 ISA is later.** Year-1 stand-in printers consume the schedule and, when `nvcc` / `ccec` are present, emit official ELF cubin / NPU-bin objects. Agents do not mutate PTX.

| Family | `Kernel.target` | Sink | Consumes |
|---|---|---|---|
| CPU interpreter | (any) | `simulate` | Copy / Mma / Reduce values |
| NVIDIA GPU (M2 sidecar) | `cuda`, `cuda-sm*` | Triton (`print_triton`) | Walks Copy / Barrier / Pipeline / Mma / Reduce. layouts → `BLOCK_*`, partitions → `num_warps`, `Pipeline.depth` → `tl.range(..., num_stages=depth)`, `Barrier` → `tl.debug_barrier`. Standby M2 kill if the cubin path is withdrawn. |
| NVIDIA GPU (cubin-bound stand-in) | `cuda`, `cuda-sm*` | CUDA C++ (`print_cuda`); `nvcc` when present | smem → `__shared__`, Copy → thread-strided gmem↔onchip loops, Barrier → `__syncthreads`, Pipeline → staged smem, `Partition.width` → `__launch_bounds__` + stride (`width×32`), Mma ISA *name* from target, Reduce → per-thread dst sum. `lower().text` is this source. Not the designed cubin ISA. |
| Ascend NPU (sidecar) | `ascend*` | TileLang (`print_ascend`) | GM args + spaces → GM/L1/L0C/UB, `T.copy` / `T.gemm` / `T.pipe_barrier` / `T.Pipelined` / `T.reduce_sum`, `T.Kernel(num_warps)`. Not the NPU-bin path. |
| Ascend NPU (NPU-bin-bound stand-in) | `ascend*` | CCE (`print_ascendc`); `ccec` when present | gmem → `__gm__`, Copy → `copy_gm_to_ubuf` / `copy_ubuf_to_gm` (burst from layout), Barrier → `pipe_barrier`, Pipeline → staged loop **and** staged UB span for smem (CUDA stages `__shared__[depth]`), `Partition.width` → `block_idx < width` (year-1 one aicore: core 0 always runs), Mma → `cube.mmad` name + M/N/K loops + UB `vmadd` fallback **indexed by layout stride** (CUDA scalar MAC does the same; cube mad is later L5), Reduce → nested loops + UB `vector_dup`/`vadd` (scalar `+=` is not an aicore op). `lower().text` is this source. UB stand-in for onchip (like CUDA `float` for dtypes). Not the designed NPU ISA. |

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

`compiler_ver` on the Kernel JSON is the **choreoir** pin; it is not mutated inside one admit/lower walk. Lintel `%k` (`cache-key.v0`) names **both** that pin and the sink: `choreoir==0.1.11;nvcc.cubin`. `materialize` writes `pin.json` (`Lowered.as_k()`):

```json
{
  "schema_version": "choreo-pin.v1",
  "cache_key": {
    "schema_version": "cache-key.v0",
    "graph_hash": "sha256:…",
    "hw_id": "nvidia.sm_80",
    "compiler_ver": "choreoir==0.1.11;nvcc.cubin",
    "adapter_id": "choreo.v0",
    "policy_id": "lintel.specialize.v0"
  },
  "cache_key_digest": "sha256:…",
  "kernel": "gemm_tile",
  "family": "cuda",
  "isa": "mma.sync",
  "arch": "sm_80",
  "target": "cuda",
  "sink_id": "nvcc.cubin",
  "artifact_kind": "cubin",
  "artifact_sha256": "…",
  "source_sha256": "…",
  "launch": {"grid": 1, "block": 384, "num_warps": 12, "num_stages": 3}
}
```

`cache_key` is the freeze key (additionalProperties false). `cache_key_digest` is `sha256` of that object's canonical JSON (sorted keys, no whitespace) and is the lookup address — not a sixth key field. **Not in the key:** `model_id`, `enum_id`, `Kernel.target`, `launch`. Year-1 has no L2 graph: default `graph_hash` is `sha256(lintel.graph.unspecified)`, not a hash of the Kernel JSON; Lintel overwrites it at freeze (`--graph-hash` / `attrs.graph_hash`). `hw_id` is derived from family/arch (`nvidia.sm_*` / `ascend.davinci`) or stamped (`--hw-id`); admission is that id, not `target`. `adapter_id` is the L4 **face** (`choreo.v0`). `sink_id` is the device compiler (`nvcc.cubin` / `ccec.aicore` / `cuda.cxx` / `ascendc.cce`) and is also the suffix of `cache_key.compiler_ver`. `launch` is how Q1 `lookup(%k)` runs the cubin (CUDA `<<<grid, block>>>` from partition widths; Ascend year-1 one aicore). That is the **payload** Lintel freezes. This tree does not freeze, land, revert, or serve \(F\). `choreo consume-check PATH` checks a Lintel checkout against that contract. Handshake schema: [`schemas/cache-key.v0.schema.json`](../schemas/cache-key.v0.schema.json) (Lintel is source of truth).

Kernel JSON (construct / inspect / mutate) is defined by `choreoir.jsonio.kernel_to_dict`. Canonical op tags are `"op": "copy"|"mma"|"reduce"|"barrier"|"pipeline"|"yield"`. Lintel examples that use PascalCase (`Copy`) are accepted on **read**. `choreo propose` emits `lintel.adapter_proposal.v0`: face `adapter_id=choreo.v0`, Kernel JSON as the payload, `gates: [W,L,S,V]`. On admit error, `reject.{where,hint,finding}` is the CFG edge Lintel copies (`where` is W|L|S|V only — `compile_ok` is Lintel's post-sink gate). V is folded in only when `--tensors` and `--expected` are set; Kernel-only propose walks W/L/S. Handshake: [`schemas/adapter-proposal.v0.schema.json`](../schemas/adapter-proposal.v0.schema.json). This tree does not walk that CFG.

## 7. Out of spec

Event Tensor / persistent megakernels, cluster launch, power/energy objectives, artifact hashing for CI replay, agent-search rungs. Those attach *above* or *beside* this IR (L6, L7, T3, control plane).
