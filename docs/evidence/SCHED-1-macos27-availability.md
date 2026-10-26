# Evidence — SCHED-1: can macOS 27.x be tested on this machine?

Lane: `L-SCHED`.
Work item: `SCHED-1` (blocked) — calibration-source question.
Host: Apple M5 (h17), macOS 26.7.1 (25G241).

**Question asked:** is the `MLComputePlan` limitation (every op on CPU at 0.00
cost) a macOS 26.x issue, or is it ameliorated in 27.x?

**Answer: not answerable on this machine, and the reason is a structural fact
about how Apple ships simulators — not "we didn't look hard enough".**

> **SUPERSEDED as to the conclusion (2026-10-21):** a macOS 27.0 box became
> available (host B, a second Mac on the owner's private network: M4 Pro),
> so the hypothesis *was* tested. Result in `SCHED-1-macos27-result.md`: the
> placement problem persists on 27.0, but cost attribution is fixed there. This
> file's reasoning about the simulator runtime remains correct — it still
> explains why no 27.x planner existed locally — but the "not answerable" claim
> no longer stands.

---

## 1. What is on disk

| Runtime | CoreML.framework has a binary? | ANE frameworks? |
|---|---|---|
| **macOS 26.7.1 (host)** | yes — in the dyld shared cache, 98 `MLComputePlan` exports | full: `AppleNeuralEngine`, `ANECompiler`, `Espresso`, `ANEServices`, `ParavirtualizedANE` |
| **iOS 26.5 simruntime** | **yes — a real `CoreML` binary** | not checked |
| **iOS 27.0 simruntime** | **no.** Only `Info.plist` + `_CodeSignature` + `CoreMLModelSecurityService.xpc` | `Espresso` (metallib only, no binary), `NeuralNetworks`; **no `ANECompiler`** |

## 2. Why that settles it

The iOS 27 simulator runtime ships **no CoreML executable**, so there is no
27.x `MLComputePlan` implementation on this machine to test against. The iOS 26.5
runtime does ship one — which proves the iOS 27 omission is deliberate
relocation (CoreML moved out of the framework, presumably into a service or the
shared cache), not a truncated download.

Crucially: **the Apple models that produced the 100%-cpu result came from the
iOS 27.0 runtime tree, but were planned by the *host* `MLComputePlan`.** `milc`
`dlopen`s `/System/Library/Frameworks/CoreML.framework/CoreML`
(`crates/mil_infer/src/lib.rs:521`) — the macOS 26.7.1 implementation. So that
result already measures 26.x behaviour, and it does so on 27-era *models*:

> A model from the iOS 27 era, planned by macOS 26.7.1's `MLComputePlan`,
> places 1551 ops on cpu with 0.00 cost.

That is the closest thing to a 27-vs-26 comparison available here, and it says
26.x's planner cpu-ifies a 27-era model. It does **not** say whether 27.x's own
planner behaves better.

## 3. What is *not* established

- Whether macOS 27.x's `MLComputePlan` places ops on the ANE. **Unknown.**
- Whether the ANE stack itself changed in 27. The sim runtime lacks
  `ANECompiler` entirely, which is consistent with ANE work being
  host-only — but absence in a simruntime is expected for private ANE
  frameworks and is therefore weak evidence either way.

This file exists so nobody re-derives "we can't test 27" from scratch, and so
the *reason* is not mistaken for "nobody checked".

## 4. What would settle it

1. **Run the same corpus on real macOS 27.x hardware.** One command:
   `milc plan --vs-lint` against `examples/sched_corpus.rs` output. If any
   package plans off-cpu, 27.x ameliorates it and the SCHED-1 block should be
   revisited. Requires a 27.x machine — not available here.
2. **Install the macOS 27 SDK/runroot**, if Apple ships one with the matching
   `CoreML`, and point `lib.rs:521` at it. Not attempted here: no such runroot
   is present and guessing at a path is worse than recording the gap.
3. **Inspect the host 26.7.1 planner's decision path** for why a plannable
   model cpu-ifies. Local, available now, and independent of 27 — but it is
   reverse-engineering private API, which is a different kind of work than
   SCHED-1 and probably not worth it while e5rt gives real hardware timings.

## 5. Consequence for SCHED-1

Unchanged: still blocked on this host. This file adds a *third* unblock path
to the one already recorded in `BUILD_PLAN.md`:

> a macOS 27.x machine where `MLComputePlan` attributes non-zero cost and
> places ops on the ANE

and makes explicit that it cannot be checked from here. The e5rt-latency
option remains available today, at the precision cost already documented.

## 6. Cross-lane notes

- Touched only this evidence file. No vendor change, no patch, no manifest drift.
- Relevant to `PROBE-2` (deploy gate): that gate is also an OS-version-specific
  `_ANEClient` behaviour, and the same "cannot test 27 here" constraint applies.
  Worth one sentence in that evidence file rather than a separate investigation.
