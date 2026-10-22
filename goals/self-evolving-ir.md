# Goal: the self-evolving IR — what the representation must be so the evolution loop can act on it

Status: **proposal for debate** (branch `claude/self-evolving-ir-2026-10-22`). Position under
[`lintel-codesign.md`](lintel-codesign.md) ("IR evolution is a commit on this `main`") and the
survey through 2026-09-23 (§2.4 three targets, §4.3 search cost, §5.2 step 6 "evolve the
compiler selectively; validate against a separate corpus"). It changes no code and no
`compiler_ver`; it says what the next IR-evolution commits should add, in what order, and
what would prove each of them wrong.

The question the maintainer put (22 October 2026): what should the IR be so that it is (1)
**good for performance** — the right abstraction level, and easy for the agent to extend from
inside the feedback loop, (2) **cheap to compile**, (3) **traceable**, (4) **debuggable**?

## One line

Keep a closed core, make extension *enumerated* (variants and knobs, never free form), give
every kernel a lineage, bill every gate, and map every emitted line back to an op id. The
loop then evolves the IR from counted rejects, not from taste.

## 0. What "self-evolving" means here, and what it does not

The representation is edited by three different hands at three different clocks:

| Hand | Clock | Edits | Promotion |
|---|---|---|---|
| Application search (Lintel proposes, Choreo admits) | per candidate | a `Kernel` under a pinned `compiler_ver` | `%k` freeze or `{where}` → next candidate |
| **IR evolution** (this doc) | per commit on `main` | a sort, a variant, a check, a sink | `compiler_ver` bump; regression pair still passes; both sink families consume it |
| Controller improvement | Lintel's experiment | how candidates are chosen | `policy_id`; not this tree |

"Self-evolving" is the middle row *driven by evidence from the first row*: a reject class that
recurs, a schedule the sink cannot express, a measured gap to a vendor library. It is not the
IR rewriting itself during a search (forbidden: `check.py` is fixed inside one walk), and it is
not an LLM inventing opcodes. The survey's own test applies (§2.4): a change counts as
evolution only if the reusable artifact that persists is a compiler change, validated on
kernels that did not motivate it.

## 1. Performance: abstraction level and how the agent extends it

### 1.1 The level

The choice is between three cells, and the evidence base is thin enough that this is a
position, not a result:

| Cell | Example | What the agent can reach | What the agent cannot see | Reject quality |
|---|---|---|---|---|
| Op/graph level | Triton tiles, cuTile | Triton 62–101 % of cuBLAS GEMM on three Blackwell GPUs without source changes, autotuned per GPU; cuTile 52–79 % (CUDA Tile evaluation, arXiv 2604.23466v2; survey evidence register) | layout, warp roles, pipelining decisions made by the backend | compiler diagnostics (line-level, not schedule-level) |
| **Schedule level** (Choreo) | tiles + layouts + roles + barriers + pipeline depth | *hypothesis, not measured here:* the decisions that separate library-level from backend-default kernels — who loads, who computes, how deep the pipeline, which layout | the ISA (inside the sink) | `{where, node, element/thread}` |
| ISA / device-source level | PTX text; CCE source (C-like device source, not itself ISA) | everything | nothing hidden, but the space is unenumerable and most of it is illegal | assembler/compiler diagnostics for syntax and typing; no structured schedule diagnostic; semantic errors surface at run time |

Choreo sits in the middle cell on purpose: it exposes exactly the decisions whose absence
caps Triton-level kernels below the library, and hides the ones whose exposure makes the
search space unenumerable. **This is the claim the survey says we must test, not assume**:
Choreo's README already carries the falsifier (raw CUDA/PTX/Triton matches it under a
matched budget). Nothing in this doc moves that; it says how to make the middle cell *grow*
without sliding into the third.

### 1.1b The extreme cases: the IR *is* the interface

Two ends of the axis deserve a direct answer, because each is a real design people ship.

**(a) The stable, tested boundary as the IR — C ABI / ATen operators.** The representation
is the operator signature (`aten::mm(a, b) -> c`, or a C function with a reference
implementation and a test suite); the agent emits an implementation behind it; "the IR" never
changes because the boundary is frozen and tested. This is KernelBench, DeepSeek's harness
with a fixed op set, and every "LLM writes the kernel for this op" result in the survey.

**(b) The ISA as the IR — PTX / CCE text.** Everything is reachable; nothing is hidden; the
agent edits (or writes) the instruction stream. AsmEvo (survey, 2608.20711) and the
assembly-level KernelEvolve lineage are the evidence.

| Criterion | (a) Boundary as IR (ATen / C) | (b) ISA as IR (PTX / CCE) | Choreo (schedule) |
|---|---|---|---|
| **Performance: reach** | Everything behind the boundary is open — the ceiling is the device, same as (b). | Everything. | The schedule decisions; ISA inside the sink. |
| **Performance: what the agent can *see* and steer** | Nothing structural beyond what the toolchain reports. The implementation is text (CUDA/Triton/Python); feedback is compiler diagnostics, pass/fail, time. KernelBench-Verified (arXiv 2607.16241v1, single-turn, one H200) reports best geomean 0.88× under a TF32 baseline with hidden tests, and 28 % of the best model's correct kernels raise peak memory; the paper attributes most of the drop to baseline precision, so this shows how little a boundary-level pass/fail verdict explains, not that the boundary caused the gap. | Everything, but the space is unenumerable; most mutations are illegal; no schedule-level admit before run. | Tiles, layouts, roles, barriers, depth — enumerated, admit-checked. |
| **Extensible from the loop** | Trivially: add an op signature. But that extends the *contract*, not the optimizer; nothing learned about one op transfers to the next except as text in a prompt. | Trivially: any instruction. Nothing is closed, so nothing is *checked*. | Tier-1 variants with evidence (§1.2). |
| **Compile time** | Full toolchain per candidate; the cheapest reject is a compile error (seconds, line-level). Kernels that compile but are wrong or slow cost a device run. | Assembler only — cheapest toolchain — but semantic correctness is only knowable by running. | Static schedule rejects before any toolchain (target: §2.5; not yet measured). |
| **Traceable** | Excellent at the boundary (input/output, versioned reference, bit-exact tests). Nothing inside: two implementations of `mm` differ as blobs. | Byte-exact by construction, but a diff of two PTX files does not say *what decision* changed. | `kernel_digest`, `parent_digest`, `mutation` (§3). |
| **Debuggable** | Only "wrong output at element i" and "slower". No program point. The LLM4IR failure the SPEC names. | Hardware fault at an address; register pressure; no mapping back to intent. | `{where, node, element/thread}`; source map (§4). |
| **Stable, tested** | **Yes — this is its whole value.** | The ISA is stable per generation; the *programs* are not testable before execution. | Stable at Tier 0; Tier 1 grows under the regression pair. |

**Verdict.** Neither extreme matches the four goals *as the mutation surface*, and for the
same reason from opposite ends: (a) cannot localize or steer because it hides structure
behind a boundary; (b) cannot localize or check because it exposes everything. But (a) is not
wrong — it is **already half of this design**. Choreo's `params` + `Yield` + the
`tensors/expected` V oracle *is* an ATen-style boundary: a frozen, tested input/output
contract. The proposal is therefore to state the split explicitly rather than pick an end:

- **The stable tested boundary is the *contract***. It comes in two layers that must not be
  conflated. Choreo's layer is the kernel's `params` + `Yield` + the tiny-tile V oracle
  (`tensors`/`expected`): an ATen-shaped op name, dtypes, shapes, reference. Lintel's layer is
  the application acceptance contract that a frozen binary must meet. `graph_hash` names
  neither: it is the digest of Lintel's cross-kernel program record
  ([`agentic-compiler.md`](agentic-compiler.md) decision-area table; `choreoir/pin.py`). The
  Choreo layer never changes inside a search and is what the ledger counts rejects against.
  Nothing in §1.2 touches it.
- **The ISA is the *sink's* output**, never an input. Tier-1 variants name mechanisms
  (`cp.async`, `wgmma`, `mmad`); the sink chooses the instruction. If a result ever shows that
  the agent editing PTX beats the schedule at a matched budget (AsmEvo-style, on this
  contract), that is the survey falsifier firing and the schedule tier should shrink, not
  grow a PTX escape hatch.
- **The schedule is the *mutation surface*** between them, and it is the only one of the
  three that can be both enumerated and localized.

A corollary for the test corpus: every `examples/*.json` kernel should be paired with its
boundary (`*.tensors.json` / `*.expected.json`) so the ATen-shaped contract is literally what
the regression pair is tested against — today only some are. That is a Tier-0 hygiene
commit, no `compiler_ver` bump.

### 1.2 Extension from inside the loop: three tiers, two of them closed to the agent

The agent must be able to reach new hardware behavior (TMA, `wgmma`, `tcgen05`, cube
`mmad`, multicast) without the IR becoming text. Proposal: every extensible thing is one of
three tiers, and the tier decides who may add it and what a commit must carry.

| Tier | What | Who adds | What the commit carries | Agent sees it as |
|---|---|---|---|---|
| **0 — core sorts** | `Kernel, Buffer, Layout, Partition, Copy, Mma, Reduce, Barrier, Pipeline, Yield`; spaces; roles | nobody in year 1; a sort change is a spec bump with a migration | spec section, check, both sinks, migration of the regression pair | the grammar |
| **1 — enumerated variants** | `Copy.variant ∈ {plain, cp.async, tma, multicast}`, `Mma.variant ∈ {mma.sync, wgmma, tcgen05, cube.mmad}`, `Barrier.kind ∈ {block, mbarrier, pipe}` | **IR evolution commit**, triggered by evidence (§3.3) | one enum value + its W/L/S rule + a lowering in *each* sink (or an explicit "unsupported on family X" finding) | a closed choice list in `propose`; picking a variant is an ordinary mutation |
| **2 — knobs** | `attrs` entries a sink reads (`num_stages`, swizzle, cluster dims) | registered per sink; unregistered keys are ignored and flagged `W` warning | a registry row: name, type, range, which sink consumes it | a typed knob with a range |

Rules that keep this from becoming a language union:

1. **A variant exists in both families or declares itself unsupported.** An *explicitly
   requested* variant the target cannot provide (`Mma.variant=wgmma` on `ascend-a2`) is a `W`
   **error** with `node=m0`: rejected, never silently lowered to something else. Only
   `variant=plain` (or an unset variant) may be lowered by a documented semantics-preserving
   fallback, and that is the `unexpressible` **warning** of §3.4, whose message names the
   mechanism actually emitted. A warning never implies the requested mechanism ran. Device
   ISA still stays inside the sink; the variant names the *mechanism*, the sink owns the
   instruction.
2. **No free text.** `attrs` values are typed by the registry; an unregistered key is a
   warning the agent can read, never something the sink interprets.
3. **A Tier-1 commit is admitted by the same gates as a kernel.** It ships with a kernel in
   `examples/` that uses it, a fail case in `examples/fails/` that localizes its new check,
   and `copy` / `gemm_tile` unchanged and passing. That is survey §5.2 step 6's "separate
   corpus" made concrete: the regression pair is the held-out set.
4. **The agent proposes variants, never defines them.** The feedback loop's output for the IR
   is a *counted request* (§3.3), not a patch to `ast.py`.

Why not let the agent add ops directly (the "recursive" reading)? Because the survey records
no evidence that a controller-written representation change generalized beyond the kernels
that motivated it, and because the three-loop split is what lets a bad variant be reverted by
`compiler_ver` without touching any frozen `%k`. A variant added inside a search has no
version to revert to.

### 1.3 What performance work this implies, in order

1. Tier-1 `Mma.variant` and `Copy.variant` enums with the current scalar fallbacks registered
   as `plain` — no behavior change, one `compiler_ver` bump, so later variants have a slot.
2. First real variants: `Copy.variant=cp.async` + `Barrier.kind=mbarrier` on NVIDIA, with the
   Ascend side declaring `unsupported` honestly. This is the smallest change that lets
   `Pipeline.depth` mean overlap on a real device.
3. `Mma.variant=mma.sync` lowered to the instruction (today it is a scalar MAC with the
   name on the pin). Until this lands, no GEMM number from this tree may be compared to
   cuBLAS; `agentic-compiler/docs/PERFORMANCE.md` already says so.

## 2. Compilation time: bill every gate, cache every stage, keep solvers out of the loop

The expensive parts of one candidate are, in rising order: W/L/S (microseconds, pure
Python over a straight-line body), V (CPU interpreter on a tiny shape, milliseconds), the
sink printer (milliseconds), the device toolchain (`nvcc`/`ccec`, seconds), and device
timing (seconds, plus queueing). Survey §4.3 says compile time is *search cost* and must be
reported, not hidden. Proposal:

**Ownership note for this section and §3.** Fields on `adapter_proposal` and on session
events are Lintel's (`schemas/adapter-proposal.v0.schema.json` here is a copy with
`additionalProperties: false` and has no `cost` or `mutation` field). Every envelope or event
field below is therefore a **contingent proposal to Lintel**: it starts and lands in Lintel by
this protocol, the walk integration lands in agentic-compiler as a submodule-bump batch, and
Choreo implements its side only after both. Choreo-internal items (caches, CLIs, findings,
`kernel_digest` computed by `check`) need no outside agreement.

1. **Per-gate accounting** *(contingent on Lintel)*. Choreo measures
   `{W_ms, L_ms, S_ms, V_ms, sink_ms, toolchain_ms}` per candidate; proposed to Lintel as a
   `cost` object on the envelope, copied onto the `measure` event next to `search_cost`.
   Nothing is optimized until it is measured.
2. **Stage caches keyed by full context, not by `%k`** *(proposed; none exists today)*. `%k`
   is the *freeze* address and stays `hash(graph, hw, compiler, adapter, policy)`. Inside a
   search, cheaper keys apply, each carrying everything that can change the result:
   - findings: `(kernel_digest, choreoir version / compiler_ver, target)`;
   - V result: `(kernel_digest, tensors_digest, expected_digest, interpreter version)`;
   - binary: `(source_sha256, toolchain path + version, arch, full flag list, include-dir
     digest)` — `lower.py` passes `-arch` and `-I` separately from the source, so
     `source_sha256` alone is not a safe key.
   Hit rates are reported with the cost record. A reject already seen under the same context
   costs nothing the second time.
3. **No SMT in the walk.** Layout stays `shape×stride`; Ave-style Z3 discharge is allowed
   only in the validation of a Tier-1 commit (where seconds are fine), never in `check`. If a
   variant needs a solver to be admitted per kernel, that variant is not ready for Tier 1.
4. **Toolchain only after admit, and at most once per binary cache context.** The first half
   is the current behaviour; the second is *not* — `materialize()` invokes `nvcc`/`ccec` on
   every call. Deduplication arrives with item 2. Write both down as a rule so a future
   "compile early to get better rejects" change has to argue against it.
5. **Target**: W/L/S/V under 50 ms per candidate on the regression pair; toolchain cost
   reported separately. The number is a budget to be checked, not a claim.

## 3. Traceability: lineage, counted rejects, and versioned replay

What exists: every proposal carries the full AST; every reject carries the finding; the pin
carries `compiler_ver`, `sink_id`, `source_sha256`, `artifact_sha256`. What is missing is the
*relationship between candidates* and the *count* that justifies an evolution commit.

1. **`kernel_digest` and `parent_digest` on every Kernel** (`kernel_digest` computable by
   Choreo; `parent_digest` stamped by the proposer, *contingent on Lintel* per the §2 note): sha256 of canonical JSON, and the digest of the candidate this one was derived
   from. The session stream then encodes a tree of mutations, not a list.
2. **`mutation` record on `propose`** *(contingent on Lintel; session-event field)*: the enumerated field edits that produced this kernel
   from its parent (`[{path: "body.p0.depth", from: 2, to: 3}]`). The agent already edits
   only enumerated fields (SPEC §3); writing the edit down costs nothing and makes "which
   knob moved the number" answerable without diffing JSON.
3. **Reject ledger per `(compiler_ver, where, node_class)`.** `node_class` is the op kind plus
   the space pair (`copy gmem→smem`, `mma smem×smem→regs`). The ledger is derived from
   session streams, not stored by this tree; agentic-compiler's walk can emit it. **The
   evolution trigger becomes a number**: a Tier-1 proposal must cite the ledger row (count,
   sessions, kernels) it answers, or the sink-side `unexpressible` finding it removes.
4. **`unexpressible` is a finding, not a comment.** When a sink lowers a legal schedule
   through a documented semantics-preserving fallback (today: scalar MAC loops where the pin
   names `mma.sync` or cube `mmad`, `print_cuda.py` `_emit_mma`), it returns `W` *warning*
   `node=m0, msg="fallback: scalar MAC emitted; mma.sync not used"`. An explicitly requested
   variant the sink cannot emit is the §1.2 rule-1 *error*, not this warning. These warnings
   are the second input to the ledger.
5. **Versioned replay.** `pin.json` + `kernel.json` + the `choreoir` version named in
   `compiler_ver` must reproduce `source_sha256` byte for byte. Add a `replay` CLI that
   asserts it; a failed replay is a sink nondeterminism bug and blocks promotion.

## 4. Debuggability: every emitted line knows its op

What exists: localized findings with `node`, `partition`, `thread`, `element`; V reports the
first mismatching element. What is missing is the path *back* from the sink and the device.

1. **Source map from sink output to op ids.** Printers already comment each block
   (`// copy cA ...`). Make it a machine-readable sidecar `source_map.json`:
   `{line_range → op_id}` for the `.cu`/`.cce`. An `nvcc`/`ccec` diagnostic at line *n*
   becomes a finding at `node=cA`, same shape as W/L/S/V, instead of a stderr dump — which is
   exactly the LLM4IR failure the SPEC says to avoid.
2. **Device failures map the same way.** A launch that faults or a timing run whose output
   mismatches the interpreter is reported as `V` with `node` from the source map and the
   element from the device-side check. (`DeviceMeasurer` in agentic-compiler is the place.)
3. **`explain` printer.** A human and agent-readable timeline per partition: for each stage,
   which partition does what, who waits on whom, which buffers are live. Derived purely from
   the AST; it is how a reviewer reads a kernel without reading CUDA.
4. **Op-level diff.** `choreo diff a.json b.json` reports the `mutation` list of §3.2 for any
   two kernels. The agent's "what did I change" and the reviewer's "what changed" are the
   same artifact.
5. **Counterexamples stay small.** V runs on the tiny shape that produced the reject; the
   finding carries `element`, `expected`, `got`. Never attach a tensor dump.

## 5. Order of commits, and the falsifier for each

Each row is one IR-evolution commit on this `main`, debated in `STATUS.md`, with a
`compiler_ver` bump and the regression pair passing. Nothing here is a year-1 promise. Rows
that touch Lintel's envelope or events (#1's `cost` / `parent_digest` / `mutation`, #6's hit
rates on the measure event) wait for the Lintel batch and the agentic-compiler submodule
bump (§2 ownership note); their Choreo-internal halves may land first.

| # | Commit | Criterion served | What would show it was wrong |
|---|---|---|---|
| 1 | Per-gate `cost` on the envelope; `kernel_digest` / `parent_digest` / `mutation` stamps; `replay` CLI | 2, 3 | Accounting overhead itself exceeds 10 % of W/L/S/V time; or replay fails on the regression pair (sink is nondeterministic today). |
| 2 | `source_map.json` sidecar; toolchain diagnostics mapped to `node`; `explain` and `diff` CLIs | 4 | Mapped diagnostics are wrong for > 1 in 20 injected errors on the regression pair. |
| 3 | Tier-1 enums `Copy.variant`, `Mma.variant`, `Barrier.kind` with today's behavior as `plain`; knob registry; `unexpressible` finding | 1, 3 | Agentic-compiler's walk cannot run unchanged against the bumped pin (the enum broke the consume contract). |
| 4 | `cp.async` + `mbarrier` on NVIDIA; Ascend declares unsupported | 1 | Measured on a device: `Pipeline.depth=3` with `cp.async` is not faster than `plain` on `gemm_tile` at a realistic tile. Then the variant is noise and should be removed. |
| 5 | `mma.sync` as the instruction | 1 | Local implementation threshold: GEMM tile reaches < 50 % of cuBLAS at matched shape; then this lowering has not earned its cost. This does **not** fire the README falsifier, which needs the matched-budget comparison against raw CUDA/PTX/Triton; only that experiment goes to the survey. |
| 6 | Stage caches with hit rates on the measure event | 2 | Hit rate < 20 % over a 100-candidate walk; caching is then complexity without payback. |

The ledger (§3.3) is what decides the order *after* #3: the next variant is the one with the
largest `unexpressible` or `{where}` count, not the most interesting one.

## 6. What this proposal refuses

- An IR the agent extends by emitting new op definitions during a search.
- A textual IR of any kind as the mutation surface, including "just let it write the CUDA".
- One enum that spans NVIDIA and Ascend mechanisms as if they were the same thing; a
  variant names a mechanism, each sink maps it or refuses it.
- SMT or any solver in the per-candidate path.
- Calling any of #1–#6 above "self-improvement". They are compiler versions with evidence
  attached; the survey's controller checkpoint (September 2027) is a different experiment.

## 7. Open questions for the thread

1. Is `parent_digest` the proposer's job (Lintel) or should `check` refuse a kernel without
   one? Position: proposer's job; Choreo stamps `kernel_digest`, Lintel stamps lineage.
2. Should `unexpressible` be a warning (admit, lower with fallback, count it) or an error
   (reject, `{where: X}`)? Position (revised after Codex round 1): split by request. An
   explicitly requested variant the target cannot provide is an error (§1.2 rule 1). An
   unset/`plain` variant lowered by a documented semantics-preserving fallback is a warning
   that names the emitted mechanism (§3.4), because a slow but correct fallback is still a
   frozen artifact; revisit when #4 lands and the fallback is a measured loss.
3. Does Tier 2 need a registry at all, or is "unregistered keys are ignored and warned" enough?
   Position: the registry is what makes a knob *typed* for the proposer; without it the agent
   is back to guessing strings.
