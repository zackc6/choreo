# Lintel consume contract (from this tree)

Sibling: [zackc6/lintel](https://github.com/zackc6/lintel). **Read there, do not copy `choreoir` into it.** This file is what that plan repo should treat as current. Lintel year-1 is docs + schemas (no `src/`). This agent cannot push `zackc6/lintel` (`cursor[bot]` 403).

Choreo is the data-plane **compiler object**. Lintel is the control plane. Union is **admit signals**, not languages.

## Commands

```bash
python3 -m choreoir check examples/copy.json
python3 -m choreoir propose examples/copy.json
python3 -m choreoir propose examples/fails/layout_cover.json   # reject.where = L
python3 -m choreoir propose examples/fails/value_mismatch.json \
  --tensors examples/fails/value_mismatch.tensors.json \
  --expected examples/fails/value_mismatch.expected.json   # reject.where = V
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
- [`examples/fails/value_mismatch.proposal.json`](../examples/fails/value_mismatch.proposal.json) — `{where: V}` (needs `--tensors` / `--expected`)
- T5-lite `{where}` corpus: [`examples/fails/`](../examples/fails/) — W (`unknown_buffer`, `role_mismatch`, `pipeline_depth`, `pipeline_empty`), L (`layout_cover`, `mma_shape`), S (`sync_race`), V (`value_mismatch` + tensors). Kernel `compiler_ver` is `0.1.9` (same pin as `copy` / `gemm_tile`; adapter-proposal `compiler_ver` is `choreoir==0.1.9;cuda.cxx`). `choreo propose` always walks W/L/S; V is folded into `reject.where` only when `--tensors` and `--expected` are both set (Kernel-only propose does not invent a V edge). A `Pipeline` with `depth>=1` and empty `body` is `{where: W}` (`pipeline_empty`): the sink stages `body`, so a marker pipeline is syntax without effects. Nest ops like [`examples/gemm.json`](../examples/gemm.json).

## `%k` (`cache-key.v0`)

`materialize` writes `pin.json`. `cache_key` is the freeze key (additionalProperties false). `cache_key_digest` is sha256 of canonical JSON of that key (sorted keys, no whitespace) and is the lookup address, not a key field. Kernel AST is the **value at** the key. The installable package version is `0.1.9`, same as `Kernel.compiler_ver`.

| Field | This tree emits | Not |
|---|---|---|
| `adapter_id` | `choreo.v0` | `nvcc.cubin` (that is `sink_id`) |
| `compiler_ver` | `choreoir==0.1.9;nvcc.cubin` or `…;ccec.aicore` | Kernel-only `0.1.9` inside the key |
| `hw_id` | `nvidia.sm_*` / `ascend.davinci`, or `--hw-id` | `Kernel.target` |
| `graph_hash` | `sha256(lintel.graph.unspecified)` unless stamped | hash of Kernel JSON |
| `policy_id` | `lintel.specialize.v0` (handshake slot) | |
| `cache_key_digest` (pin sibling) | sha256 of canonical `cache_key` JSON | a sixth field *inside* `cache_key` |

`Kernel.target` stays on the AST and as pin **payload** so `lower()` can replay. Admission is `hw_id`. Schema copy: [`schemas/cache-key.v0.schema.json`](../schemas/cache-key.v0.schema.json) (Lintel remains source of truth for field names).

## `{where}` (`adapter-proposal.v0`)

`choreo propose` emits `lintel.adapter_proposal.v0`. On admit error, `reject.{where,hint,finding}` is the CFG edge. `where` ∈ `W|L|S|V` only. V is opt-in (`--tensors` + `--expected`); without those flags the envelope is W/L/S. `compile_ok` is Lintel's **post-sink** gate (missing `nvcc`/`ccec` here is a W **warning**, not that gate). The nested `finding` uses Lintel's shape (`gate`, `severity`, `node`, `msg`, optional `partition` / `thread` / `element`) — it does **not** repeat `where`.

Lintel **copies** that envelope onto the session stream. It does not own the Finding; it stores it:

| Envelope | Finding JSON | Kernel AST |
|---|---|---|
| `adapter-proposal.v0` | nested under `reject.finding` | `kernel` is the full AST |
| `session-event.v0` `propose` / `gate` | payload **sibling** of `reject` (`reject.additionalProperties: false`) | `propose.payload.kernel` is the full AST (`name`/`buffers`/`partitions`/`body`), not a name stub |

Copy rule (Q1 adapter plugin): `finding = reject.finding`; session `reject = {where, hint, reason}`; session `kernel = envelope.kernel`. This tree does not emit session events.

Canonical Kernel JSON is lowercase ops (`copy`, `mma`, …). Lintel examples that use PascalCase (`Copy`) are accepted on **read**. This tree also has `reduce` / `yield` and `target` / `compiler_ver` on the Kernel — Choreo is source of truth for Kernel encoding. Schema: [`schemas/adapter-proposal.v0.schema.json`](../schemas/adapter-proposal.v0.schema.json). Handshake test: [`tests/test_lintel_handshake.py`](../tests/test_lintel_handshake.py).

## Sinks (not `print_triton`)

| Family | `lower().text` | Device object | Sidecar |
|---|---|---|---|
| NVIDIA | CUDA C++ (`print_cuda`) | official `nvcc -cubin` → ELF cubin | Triton knobs |
| Ascend | CCE (`print_ascendc`) | official `ccec --cce-aicore-only -c` → elf64-hiipu | TileLang |

Sinks consume `Partition` (width → CUDA `__launch_bounds__` / thread stride; CCE `block_idx < width`), `Barrier`, `Pipeline.depth`, layout, space, gmem writeback, MMA (CUDA scalar MAC / CCE `vmadd` fallback), and `Reduce` (CUDA per-thread dst sum; CCE `vector_dup`/`vadd` because aicore rejects scalar `+=`). Missing toolchain = warning, not a fake binary. **M2 `@triton.v0` knobs are standby** because a year-1 NVIDIA cubin has landed (stand-in path, not the later L5 ISA design). The Triton sidecar walks `Copy` / `Barrier` / `Pipeline` / `Mma` / `Reduce` (not the first-op stencil); it is still not `lower().text`.

Lintel YEAR1 “Ascend waits until one NVIDIA cubin” is **satisfied** as a prerequisite. Dual-live *search* is still Lintel's call; this tree **always** lowers to both families. Public CI on this `main` fetches official nvcc and fails if cubin tests would skip (`CHOREO_REQUIRE_NVCC=1`). That is not Lintel `compile_ok`. `ccec` is not a public redist; NPU-bin ELF tests skip on GitHub. Two `%k` for the same `copy` Kernel still run there: pin helpers + the land/sibling freeze addresses (`sha256:71f32cff…` / `sha256:67a233d2…`).

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

Also stale on **origin** lintel `fda2db2`: “one NVIDIA binary first” as a *Choreo* gap; “Triton-first sink”; “choreo PR” as the evolve path; `compiler_ver` examples `choreoir==0.1.0;triton==3.3.0+cu128`; PoC CFG slots `choreo.attn.d3.w4` / `d2.w8`. Prefer `choreoir==0.1.9;nvcc.cubin` and year-1 SLA names `copy` / `gemm_tile`. Origin PoC `acme_attn_prefill.choreo.json` still uses a marker `Pipeline` with empty `body` (PascalCase ops, no `target`); live `choreo propose` on that envelope is `{where: W}` at `pipe0`. Year-1 `lower(sla=True)` also rejects those attn names.

A consume absorb is committed locally on lintel `main` but **cannot be pushed** (`cursor[bot]` 403):

- `6fc4513` nested `Pipeline.body`, lowercase ops, `choreoir==0.1.8;nvcc.cubin`, year-1 `examples/choreo/{copy,gemm}.json`, T5 = commit on `choreoir` `main`, CUDA C++ / nvcc as the NVIDIA sink
- `98356bc` drop remaining Triton-as-sink wording
- `d4a0056` year-1 PoC CFG / admit-record slots are `copy` then `gemm_tile`; L-fail is `examples/choreo/layout_cover.proposal.json` (`{where: L, hint: buffer.A}`); attn envelopes moved to `examples/later/`
- `0203863` `cache_key_digest` is sha256 of canonical `cache-key.v0` JSON (was a leftover Triton-era example hash)
- `9436e8f` session log is Choreo `copy` / `gemm_tile` walks (`{where: L}` edge, freeze under `%k`, serving revert) — not Triton knobs
- `4078eba` adapter-fail `propose`/`gate` store Finding JSON; session log walks W (`pipeline_empty`) / L (`layout_cover`) / S (`sync_race`) / V (`value_mismatch`); T5-lite table maps those `{where}` letters to CFG reject vs a commit on this `main`
- `54d1dbd` propose payload kernel is the full AST (name/buffers/partitions/body), not a name stub; session-event schema requires those fields
- `a89e5d4` freeze artifact is nvcc cubin (kind cubin, copy.cubin / gemm_tile.cubin), not a .py; digest is pin.artifact_sha256
- `ae62bae` same copy Kernel on Ascend is a new %k (ccec.aicore / npu-bin); year-1 live search stays NVIDIA
- `beab884` consume rows point at choreo `409180a` public nvcc cubin CI; two copy-kernel `%k` without ccec
- `9971fb1` data-plane PoC notes that choreo public CI fetches nvcc so cubin tests cannot skip
- `c962329` T5 fail envelopes and session-log kernels pin choreoir 0.1.8 (`choreoir==0.1.8;cuda.cxx`)
- `d74f509` Q1 install pin is choreoir 0.1.8 (choreo `43fd20d` package version)
- `e5c8fa0` C4 is one live face (`choreo.v0`); M2 knobs are standby because the nvcc cubin path has landed
- `0f2fea4` C4 kill is “we compiled Choreo” without serving \(F\); cubin already exists
- `1e6dab6` consume choreoir 0.1.9: partition-width sinks (`__launch_bounds__` / thread stride / `block_idx < width`); land `%k` `sha256:71f32cff…` / `sha256:67a233d2…`; freeze cubin digest `07aadb61…`

Land those commits on lintel `origin/main` when write exists. Do not add `src/` or vendor `choreoir`. A throwaway `git am` of that 16-commit series onto origin `fda2db2` applies clean: year-1 slots `copy` / `gemm_tile`, freeze `artifact.kind=cubin` (`choreoir==0.1.9;nvcc.cubin`), 35 session events, no `src/`.

Files on the Lintel side that should absorb this: `docs/CHOREO.md`, `docs/DATA_PLANE.md`, `docs/ADAPTERS.md`, `docs/YEAR1.md`, `docs/SURVEY_MATCH.md`, `docs/LINTEL_IR.md`, `docs/POC.md`, `examples/admit-record.json` `compiler_ver` / `adapter_id` / `enum_id` / `cache_key_digest`, `examples/session-log.jsonl`, `schemas/session-event.v0.schema.json` Finding JSON, `schemas/adapter-proposal.v0.schema.json` op enum, `schemas/admit-record.v0.schema.json` `artifact.kind`, `examples/poc/*.json` / `*.lintel`, `examples/choreo/`, `examples/choreo/fails/`.

## Never in this tree

Freeze, land, revert, reject-as-SKU, serving \(F\), ADG walk, MCP, `%w`. Those stay Lintel objects. Emitting `cache_key`, `cache_key_digest`, and `reject.where` is not owning them.
