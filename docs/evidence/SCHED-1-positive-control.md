# Evidence — SCHED-1: `MLComputePlan` positive control

Lane: `L-SCHED`.
Work item: `SCHED-1` — cost model, calibration-source question.
Status: **settled — `MLComputePlan` is not a usable calibration source on this
host. SCHED-1 must use e5rt timing.**

Host: Apple M5 (h17), macOS 26.7.1 (25G91). Supersedes nothing; resolves the
open question in `SCHED-1-vs-lint-disagreement.md` §4/§5.

---

## 1. The question

`SCHED-1-vs-lint-disagreement.md` measured `milc plan --vs-lint` at **0/10 ops
agreeing**, every disagreement in the same direction (lint `ane` → plan `cpu`).
It ruled out three premature readings but could not separate:

- **H1** — our IR compiles to graphs `MLComputePlan` will not place on the ANE;
- **H2** — `MLComputePlan` will not place *anything* on the ANE here.

The difference is not academic. Under H1 the accept criterion stands: calibrate
against `MLComputePlan`. Under H2 the criterion needs a scope change, because
the proposed ground truth is itself unavailable.

Settling it needs one thing: a **CoreML-authored model we did not build**, run
through the same command.

## 2. The positive control

`coremltools` is not installed (`import coremltools` → ModuleNotFoundError), so
no freshly-converted control. Instead, Apple's own shipped models were used.

Two unrelated CoreML-authored models both produce a plan:

| Model | Ops placed | Placement |
|---|---|---|
| `PlanResolutionModel.mlmodelc` (IntelligenceFlowPlannerRuntime) | 1551 | **cpu 1551 (100%)**, est. cost 100% |
| `ASRRankingModel.mlmodelc` (IntelligenceFlowPlannerRuntime) | 429 | **cpu 429 (100%)**, est. cost 100% |

Per-op `cost` is **0.00** for every op in both. Both also carry the same
`--vs-lint`-shaped failure our own corpus does: a CoreML-authored model, not
ours, planned entirely onto the CPU.

```console
$ ./target/release/milc plan .../PlanResolutionModel.mlmodelc --units ane
plan under CpuAndNeuralEngine: 1551 ops placed (1455 const/no-device ops skipped)
  cpu    1551 ops (100.0%)   est. cost 100.0%
```

## 3. Confounds checked, not assumed

**a. Host vs simulator CoreML.** These models ship in the *iOS simulator*
runtime, which could mean a simulator-specific CoreML is being used.
`milc` resolves `/System/Library/Frameworks/CoreML.framework/CoreML`
(`crates/mil_infer/src/lib.rs:521`) — the **host** framework, macOS 26.7.1.
Checked directly, not inferred.

**b. ANE is genuinely working.** Independent of CoreML entirely:
`MIL_REQUIRE_HW=1 cargo test -p mil_infer --test e5rt` → **9 passed, 0 failed**,
i.e. real ANE execution via e5rt. The hardware and the e5rt path are fine.
`BUILD_PLAN.md §0` records the same two working paths (99.42 µs/step via
`milc run`, 211 µs/step via e5rt).

**c. Not "unsupported model" selectivity.** Several Apple models *do* fail with
`Failed to construct compute plan, model is not supported` (`Recipe.mlmodelc`,
`MapsSuggestionsTransportModePrediction`, `ATXModeWorkingSetupPredictionModel`,
`ExtractedOrderCoreMLMatcherModel`) — so the two that succeed are genuinely
plannable, not trivially erroring.

**d. Not `--units`.** `--units ane` and `--units all` behave identically
(0/10 in the prior evidence file).

## 4. Conclusion

**H2 is confirmed. H1 is not supported.** `MLComputePlan` on this host places
100% of a CoreML-authored model's ops on the CPU with zero estimated cost.
It is not a differentiator between our IR and Apple's — it does not
differentiate at all.

Therefore the 0/10 `--vs-lint` figure is **not evidence that `mil_lint` is
wrong**. It is evidence that the *plan* side of the comparison is degenerate on
this host. Two earlier "ruled out" notes in the prior evidence file stand, and
one is now superseded: size was ruled out as an explanation for *our* corpus,
but the real explanation was never size — it is that the planner never plans
onto the ANE here.

## 5. Consequence for SCHED-1

The accept criterion reads:

> *predicted per-op cost within a stated tolerance of measured `MLComputePlan`
> cost on a fixed model; disagreement documented rather than hidden.*

`MLComputePlan` **cost** is 0.00 for every op, so "within a stated tolerance of
measured MLComputePlan cost" is unachievable by construction — any non-zero
prediction is infinitely far from 0.00. The criterion cannot be met as written,
through no fault of any model.

**Scope change proposed (needs owner decision, recorded not acted on):**
calibrate SCHED-1 against **e5rt measured latency** instead, which is the path
that demonstrably executes on the ANE. Concretely:

- per-op wall time is not available from e5rt (one `execute_sync` for the whole
  graph), so the calibration target becomes **end-to-end latency per subgraph**,
  not per-op;
- that inverts what SCHED-1 produces: instead of predicting a cost you compare
  to CoreML's plan, you predict a latency you verify by running it;
- `mil_lint`'s **unit** verdicts remain usable and valuable — they are
  unaffected by this. Only the *cost* half of SCHED-1 loses its ground truth.

This is a real demotion of SCHED-1's precision, not a technicality: per-op cost
was the acceptance target and it is gone. It is recorded here rather than
silently redefining the item.

## 6. What has *not* changed

- `mil_lint`'s placement predictions are not invalidated by this. Nothing here
  says lint is wrong. The previously-suspected lint bug was a mirage caused by
  comparing against a degenerate plan.
- L-SCHED's corpus (`examples/sched_corpus.rs`) is still useful — it is simply
  a *different* corpus now, one that exercises e5rt.
- ADR-0003 stands; no crate added, still nothing to put in it.

## 7. Cross-lane notes

- Touched only this evidence file. No vendor change, no patch, no manifest drift.
- **Request to L-LINT:** `milc plan --vs-lint` is now known to be a misleading
  diagnostic on macOS 26.7.1 — it will report a low agreement rate for reasons
  that have nothing to do with lint quality. Worth a warning in `milc lint`'s
  docs or in `--vs-lint`'s output, or it will mislead the next reader exactly
  as it briefly misled this one.
- **Request to L-TEST:** an e5rt-latency fixture is the natural replacement
  calibration source; belongs in the existing `crates/mil_infer/tests/e5rt.rs`
  harness (L-RUN), which L-SCHED would read, not edit.
