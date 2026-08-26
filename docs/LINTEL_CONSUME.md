# Lintel consume contract (from this tree)

Sibling: [zackc6/lintel](https://github.com/zackc6/lintel). **Read there, do not copy `choreoir` into it.** This file is what that plan repo should treat as current. Lintel year-1 is docs + schemas (no `src/`). This agent cannot push `zackc6/lintel` (`cursor[bot]` 403).

Choreo is the data-plane **compiler object**. Lintel is the control plane. Union is **admit signals**, not languages.

## Commands

```bash
python3 -m choreoir check examples/copy.json
python3 -m choreoir propose examples/copy.json
python3 -m choreoir propose examples/fails/layout_cover.json   # reject.where = L
python3 -m choreoir check examples/fails/value_mismatch.json \
  --tensors examples/fails/value_mismatch.tensors.json \
  --expected examples/fails/value_mismatch.expected.json   # where = V
python3 -m choreoir lower examples/gemm.json -o /tmp/out --emit cubin
python3 -m choreoir pin /tmp/out/pin.json
python3 -m choreoir lower examples/gemm.json -o /tmp/npu --target ascend-a2 --emit npu-bin
```

Year-1 allowlist: `copy`, `gemm_tile` (`Pipeline.depth=3` on gemm). Face `adapter_id`: `choreo.v0`.

Checked-in payloads (source sink; cubin/NPU-bin `pin.json` is produced by `lower --emit`):

- [`examples/copy.proposal.json`](../examples/copy.proposal.json) / [`examples/gemm.proposal.json`](../examples/gemm.proposal.json)
- [`examples/copy.pin.json`](../examples/copy.pin.json) / [`examples/gemm.pin.json`](../examples/gemm.pin.json)
- [`examples/fails/layout_cover.proposal.json`](../examples/fails/layout_cover.proposal.json) — `{where: L}`
- T5-lite `{where}` corpus: [`examples/fails/`](../examples/fails/) — W (`unknown_buffer`, `role_mismatch`, `pipeline_depth`), L (`layout_cover`, `mma_shape`), S (`sync_race`), V (`value_mismatch` + tensors). `choreo propose` runs W/L/S only; V is `--tensors --expected`.

## `%k` (`cache-key.v0`)

`materialize` writes `pin.json`. `cache_key` is the freeze key (additionalProperties false). Kernel AST is the **value at** the key.

| Field | This tree emits | Not |
|---|---|---|
| `adapter_id` | `choreo.v0` | `nvcc.cubin` (that is `sink_id`) |
| `compiler_ver` | `choreoir==0.1.7;nvcc.cubin` or `…;ccec.aicore` | Kernel-only `0.1.7` inside the key |
| `hw_id` | `nvidia.sm_*` / `ascend.davinci`, or `--hw-id` | `Kernel.target` |
| `graph_hash` | `sha256(lintel.graph.unspecified)` unless stamped | hash of Kernel JSON |
| `policy_id` | `lintel.specialize.v0` (handshake slot) | |

`Kernel.target` stays on the AST and as pin **payload** so `lower()` can replay. Admission is `hw_id`. Schema copy: [`schemas/cache-key.v0.schema.json`](../schemas/cache-key.v0.schema.json) (Lintel remains source of truth for field names).

## `{where}` (`adapter-proposal.v0`)

`choreo propose` emits `lintel.adapter_proposal.v0`. On admit error, `reject.{where,hint,finding}` is the CFG edge. `where` ∈ `W|L|S|V` only. `compile_ok` is Lintel's **post-sink** gate (missing `nvcc`/`ccec` here is a W **warning**, not that gate).

Canonical Kernel JSON is lowercase ops (`copy`, `mma`, …). Lintel examples that use PascalCase (`Copy`) are accepted on **read**. This tree also has `reduce` / `yield` and `target` / `compiler_ver` on the Kernel — Choreo is source of truth for Kernel encoding. Schema: [`schemas/adapter-proposal.v0.schema.json`](../schemas/adapter-proposal.v0.schema.json).

## Sinks (not `print_triton`)

| Family | `lower().text` | Device object | Sidecar |
|---|---|---|---|
| NVIDIA | CUDA C++ (`print_cuda`) | official `nvcc -cubin` → ELF cubin | Triton knobs |
| Ascend | CCE (`print_ascendc`) | official `ccec --cce-aicore-only -c` → elf64-hiipu | TileLang |

Sinks consume `Partition`, `Barrier`, `Pipeline.depth`, layout, space, gmem writeback, MMA (CUDA scalar MAC / CCE `vmadd` fallback). Missing toolchain = warning, not a fake binary. **M2 `@triton.v0` knobs are standby** because a year-1 NVIDIA cubin has landed (stand-in path, not the later L5 ISA design).

Lintel YEAR1 “Ascend waits until one NVIDIA cubin” is **satisfied** as a prerequisite. Dual-live *search* is still Lintel's call; this tree **always** lowers to both families.

## Two clocks (T5, not M3)

This repo **does not use GitHub PRs**. Evolution is a **commit on `choreoir` `main`**, then bump `compiler_ver` → new `%k`.

| Clock | Allowed |
|---|---|
| Inside one job | `choreoir` pinned. Fail `{where}` → next Kernel, not a new opcode. |
| Across CI | Recurring `{where}` → Lintel conducts a commit on this `main` → new `%k`. |

Rewriting `check.py` mid-walk is M3. Forbidden here.

## Stale rows in Lintel `docs/CHOREO.md` “Blocked on choreo”

| Lintel row (as of lintel `fda2db2`) | This tree now |
|---|---|
| `print_triton` is a stencil; no cubin | NVIDIA ELF cubin via `nvcc`; Triton is sidecar |
| MMA V not a year-1 gate | V for `Copy` / `Mma` / `Reduce` (`choreo check --tensors --expected`) |
| Pipeline.depth not consumed | CUDA C++ and CCE consume depth |
| JSON serde unpublished | `choreoir.jsonio`; lowercase ops canonical |
| Z3 / thread CEX | Still v2. Not year-1 |

Also stale: “one NVIDIA binary first” as a *Choreo* gap; “Triton-first sink”; “choreo PR” as the evolve path; `compiler_ver` examples `choreoir==0.1.0;triton==3.3.0+cu128`. Prefer `choreoir==0.1.7;nvcc.cubin`.

Files on the Lintel side that should absorb this (when write access exists): `docs/CHOREO.md`, `docs/DATA_PLANE.md`, `docs/ADAPTERS.md`, `docs/YEAR1.md`, `docs/SURVEY_MATCH.md`, `docs/LINTEL_IR.md`, `examples/admit-record.json` `compiler_ver` / `adapter_id`, adapter-proposal op enum.

## Never in this tree

Freeze, land, revert, reject-as-SKU, serving \(F\), ADG walk, MCP, `%w`. Those stay Lintel objects. Emitting `cache_key` and `reject.where` is not owning them.
