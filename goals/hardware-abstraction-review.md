# Hardware abstraction and bounded optimization review

Date: 2026-11-03. Status: maintainer-requested discussion record and review criteria;
not an adopted replacement architecture, an implemented feature, or performance evidence.
Read under [the early architecture](agentic-compiler.md). Cross-kernel dependencies,
application placement, budgets, acceptance and deployment remain Lintel responsibilities.

## Questions this record preserves

Can a kernel representation preserve peak-performance opportunities across different
programming models while reducing the cost of agent search? Can compiler evolution turn
expensive discoveries into reusable analyses, transforms and implementations so that later
workloads reach a commercial performance threshold within a bounded budget?
Neither question is answered by expressiveness alone or by naming a compiler framework.

## 1. Expressibility is not optimization support

Distinguish four levels for tensor/tile programming and future hardware features:

| Level | Required evidence |
|---|---|
| Encodable | Loops, pointer arithmetic or intrinsics can execute the operation. |
| First-class | Shape, placement, ownership, participating resources, effects and completion conditions are inspectable without reconstructing them from lowered code. |
| Analyzable and transformable | Legality checks and concrete transformations exploit the preserved abstraction before lowering destroys it. |
| Efficiently searchable | Legal actions, constraints, diagnostics and compilation reuse reduce time and resources to a measured performance threshold. |

First-class does not require a dedicated AST node: a call with explicit semantic contracts
and analysis/transform support may qualify. Merely retaining a named tile operation does
not establish useful optimizations. Candidate optimizations include layout propagation,
redundant-copy elimination, fusion/retile and placement/pipeline decisions; their legality
and numerical effects must be established, not assumed.

Support known recurring patterns explicitly. Allow new hardware features to enter through
controlled target-specific representations, then consider promotion to reusable abstractions
when repeated use justifies it. This is a proposed evolution discipline, not a promise that
a fixed core predicts every future programming model.

## 2. Common abstractions must not impose a lowest-common-denominator ceiling

A shared core may describe computation, dependencies and data lifetime without limiting the
whole representation to operations natively common to every device. Preserve target-specific
memory, ownership, collective participation, visibility and completion semantics. Do not
rename GPU shared memory and NPU scratchpads to a generic on-chip space and claim portability.
An analysis that cannot interpret an extension must conservatively refuse a transformation
or delegate to an appropriate target analysis.

This manages fragmentation; it does not remove backend engineering. Target support,
source portability and performance portability are distinct claims. Sharing syntax or an
IR infrastructure proves none of the latter two.

## 3. MLIR is an implementation option, not the abstraction design

MLIR supplies extensible infrastructure; choosing it does not supply the appropriate tile,
layout, dependency, scheduling or optimization model. A custom MLIR dialect is still a
custom IR. Conversely, a custom IR does not inherently require custom infrastructure.
Compare concrete designs: existing MLIR dialects/transforms plus backend support, direct
TIRx use/extensions, and Choreo's own representation. Neither MLIR nor an independent
infrastructure is selected by this discussion. Infrastructure replacement needs its own
engineering justification.

## 4. TIRx is a substantive baseline and possible substrate

TIRx exposes execution scope, storage layouts and target-owned tile lowering while keeping
much orchestration explicit in native-style source. Backends own namespaces, instruction
contracts, lowering additions and code generation. CUDA and Trainium do not become the same
programming model by sharing this substrate. The author's evaluation describes manual kernel
porting; multi-target support is not automatic model conversion.

Current documentation and the June launch description differ in dispatch granularity: the
launch discusses instruction-family selection, while newer CUDA documentation exposes exact
instruction selection. Pin a revision before comparing functionality or compile cost.
Do not assume the older broad dispatch description applies to every current tile API.

The author's selected B200 and Trainium1 evaluations are evidence that tuned TIRx kernels
can be competitive, not evidence of autonomous optimization, universal peak performance or
bounded time-to-performance. CPU code generation in TVM does not establish equally mature
CPU tile support in the frontier TIRx stack. Trainium evidence is not Ascend evidence.

## 5. Cross-programming-model optimization is a concrete research question

| Decision | CPU examples | GPU examples | NPU examples |
|---|---|---|---|
| Work mapping | Core tasks, SIMD | Blocks, warps, lanes | Cores and specialized engines |
| Data reuse | Cache blocking, packing | Shared memory, registers | Explicit scratchpads and operand buffers |
| Overlap | Prefetch, software pipeline | Async copies, specialized roles | DMA/compute-engine pipelines |
| Coordination | Task/thread synchronization | Collectives, barriers, async completion | Engine/event dependencies |

These are illustrative patterns, not universal properties of every CPU/GPU/NPU.
A generic worker abstraction must not erase their differences. A candidate common level
represents the scheduling problem and unresolved decisions; target models define legal
realizations. The present CPU interpreter is a validation tool, not a production CPU backend.
Adding CPU support is not authorized or implemented by this record.

Choreo may need first-class intra-kernel mapping, placement, lifetime and async-dependency
representations so transformations can change pipeline stages, roles and waits together.
That is a plausible reason for an additional representation even if TIRx can encode the final
result. Absolute impossibility of encoding in TIRx is not a prerequisite: the relevant gap
may be analysis cost, transformation locality, diagnostics or bounded search efficiency.
But these remain hypotheses until compared with direct TIRx use/extensions. They do not
justify rebuilding all infrastructure or moving Lintel's cross-kernel graph into Kernel.

## 6. Diagnose the gap before evolving the compiler

1. Obtain a stronger native/reference realization and record its scope and assumptions.
2. Ask whether the current representation can faithfully encode it.
3. If it can, manually supply the schedule and inspect the lowered implementation.
4. Separate representation limits, search failures, lowering defects and measurement noise.
5. Open a concrete gap with a carrier and falsifier; do not add vocabulary merely because a
   search failed. Proposed richer abstractions must demonstrate effects in checks/transforms
   and lowering, not only syntax.

A new target-specific construct need not have a meaningful realization on every target.
This observation does not override the current dual-sink policy: changing admission,
capability checks or sink requirements requires a separate reviewed owner-repository proposal.
No silent unsupported mapping or generic fallback may be called peak-performance support.

## 7. Self-evolution and commercial optimization budgets

Keep three loops separate: application search under a pinned compiler, compiler/IR evolution
in a separately validated version, and controller improvement under its own experiment.
No optimizer LLM on the serving hot path. Reuse accepted artifacts, parameterized schedule
families and applicability conditions; do not restart open-ended discovery on every compile.
Storing a winning kernel is caching, not proof of generalized compiler evolution.

Record time-to-first-usable separately from time-to-target-performance. Account for proposal,
compilation, rejected candidates, validation, device measurement, final revalidation, CPU/GPU
resources and model cost. Parallel wall-time reductions do not erase resource expenditure.
Optimization only pays back if expected deployment savings exceed those costs before the
workload, hardware or toolchain changes. Lintel owns budgets, stopping and deployment;
Choreo changes must report their contribution without importing those responsibilities.

Commercial performance means a declared threshold against a strong available baseline under
an explicit numerical/workload contract, not theoretical peak or an eager-only speedup.
Any illustrative threshold or time budget is a proposal until measured and agreed.

## 8. Required review checklist for future changes

For each representation, check, transform, sink, target or architecture change, record each
item as addressed, not applicable (with reason), or unresolved. Link evidence and gaps.
This is a documentation review requirement, not a new runtime gate or test suite.

- [ ] Name the loop, owner, affected falsifier and compatibility/version consequences.
- [ ] State whether the change improves encoding, first-class semantics, analysis/transforms,
      or search efficiency; explain the observable effect.
- [ ] Preserve target-specific execution/memory/synchronization semantics and state capability
      limits; distinguish target support from source/performance portability.
- [ ] Explain when decisions remain unresolved and when lowering commits them; identify which
      optimizations operate before that information is lost.
- [ ] Compare existing MLIR-based designs, direct TIRx/extensions and simpler backend interfaces
      where relevant; do not dismiss them using framework names or encoding impossibility alone.
- [ ] Diagnose representation versus search versus lowering limitations with a concrete carrier.
- [ ] State compiler/search/validation costs, reuse assumptions and stopping ownership; do not
      claim bounded commercial optimization from successful code generation.
- [ ] Separate real-device results from proxies, kernel from application gains, tuned kernels
      from autonomous discovery, and CPU simulation from production CPU support.
- [ ] For performance/search claims, compare best-so-far curves under matched wall-time AND
      resource budgets, including failures, strong non-agentic tuning, direct backend access,
      held-out workloads and end-to-end impact. Avoid adding principle-test suites at this stage.
- [ ] State what would falsify the added abstraction's value and whether it should be extended,
      reduced, replaced or removed if the simpler interface performs as well.

## Sources and evidence boundaries

Primary sources inspected on 2026-11-03; live documentation may change. Pin source revisions
and benchmark environments in any experiment. This record does not update survey verdicts
or forecast confidence; the survey remains the referee.

- [TIRx launch, 2026-06-22](https://tvm.apache.org/2026/06/22/tirx): native orchestration,
  layout/scope/dispatch, intrinsic-to-tile evolution.
- [TIRx current overview](https://tvm.apache.org/docs/tirx/overview.html) and
  [backend internals](https://tvm.apache.org/docs/tirx/arch/backends.html): backend ownership
  and current instruction-lowering boundary.
- [TIRx author evaluation, 2026-10-20](https://www.cs.cmu.edu/~csd-phd-blog/2026/tirx/):
  selected tuned-kernel results, manual porting and limitations; not independently reproduced here.
- [MLIR Transform dialect](https://mlir.llvm.org/docs/Dialects/Transform/): transform/payload
  separation and extensibility, not an automatic optimal scheduler.
- [Exo 2](https://arxiv.org/abs/2411.07211): externally extensible scheduling operations.
- [MetaSchedule](https://arxiv.org/abs/2205.13603): extensible search spaces and learned search;
  a necessary non-agentic comparator, not a claimed Choreo capability.
- [KernelBench, ICML 2025](https://proceedings.mlr.press/v267/ouyang25a.html) and
  [AutoKernel, 2026 preprint](https://arxiv.org/abs/2603.21331): feedback-driven kernel search
  evidence with different dates/baselines; neither establishes our cross-target budget claim.

## Adoption boundary

This record adds review criteria only. It does not change the closed AST, W/L/S/V, artifact
schemas, compiler_ver, existing target/sink requirements, or Lintel contracts. It does not
resolve the separate self-evolving-IR proposal or gate G. Future implementation increments
still require the repository's gap/carrier/falsifier protocol and maintainer review.
