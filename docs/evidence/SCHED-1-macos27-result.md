# Evidence — SCHED-1: macOS 27.0 tested against macOS 26.7.1

Lane: `L-SCHED`.
Work item: `SCHED-1` (blocked) — calibration-source question.
Status: **the hypothesis is tested. Answer: macOS 27 does NOT fix the placement
problem, but it DOES fix the cost attribution. SCHED-1's block lifts partially.**

Supersedes the "cannot be tested" constraint in
`SCHED-1-macos27-availability.md` — that document recorded the gap *as of not
having a 27.x box*; one became available, so it is now superseded rather than
deleted (the reasoning about the simulator runtime is still correct and still
explains why no 27.x planner could be found locally).

---

## 1. Hosts

| | Host | OS | HW |
|---|---|---|---|
| **A** | local (`daves-m5-macbook-pro`) | macOS **26.7.1** (25G241) | Apple M5 (h17) |
| **B** | `davids-mac-mini` (tailnet `100.127.197.66`) | macOS **27.0** (26A428) | Apple M4 Pro |

Same `milc` binary on both (copied, arm64 Mach-O, no rebuild) — so any
difference is the OS, not the build. `dyld_info` confirms 98 `MLComputePlan`
exports and the full ANE stack (`AppleNeuralEngine`, `ANECompiler`, `Espresso`,
`ANEServices`) on both. B's ANE is present (`ioreg` hits).

## 2. The corpus result — placement is unchanged

Same six corpus packages, same command, `--units ane --vs-lint`:

| package | macOS 26.7.1 | macOS 27.0 |
|---|---|---|
| `elemwise` | 0/1 (mul → cpu) | 0/1 (mul → cpu) |
| `big_elemwise` | 0/4 | 0/4 |
| `softmax` | 0/1 | 0/1 |
| `stateful` | 0/2 | 0/2 |
| `cast_chain` | 0/2 | 0/2 |
| **Total** | **0/10** | **0/10** |

Identical. And B refuses Apple's own model too: `hybrid_model.mlmodelc` plans
**cpu 20/20 (100%)** on 27.0, matching A's 100%-cpu result for
`PlanResolutionModel` (1551 ops) and `ASRRankingModel` (429 ops).

> **`MLComputePlan` places nothing on the ANE on either OS version, for our
> graphs or Apple's. This is not a 26.x regression and it is not fixed in 27.x.**

Patch 0016's warning fires on both hosts, which is the self-check: it detects
exactly this condition.

## 3. The real finding — cost attribution *did* change

Raw `MLComputePlan` cost for the same `big_elemwise.mlpackage`:

| | macOS 26.7.1 | macOS 27.0 |
|---|---|---|
| per-op cost | **`2.5e-1` — one flat value for every op** | **`1.802030851236606e-1` (add) and `3.1979691487633943e-1` (mul)** |

On 26.7.1 every op in every corpus package returned the same `0.25`, and Apple's
models returned `0.00`. On 27.0 costs are **differentiated per op type and
non-zero**, and Apple's `hybrid_model` returns a spread of small non-zero values
(`1.07e-8` … `1.16e-5`) instead of `0.00`. Reproduced identically over three
consecutive runs, so it is not jitter.

This is the half of SCHED-1 that was blocked. On 26.7.1 the accept criterion was
unachievable because there was literally no variance to calibrate against — any
prediction sat at infinite distance from a flat `0.25`. On 27.0 there *is*
variance: `add` costs less than `mul` here, consistently.

## 4. What this means for SCHED-1

**Placement (the `unit` half): still unusable.** `preferred` is `cpu` for
everything on both hosts, so `MLComputePlan` remains worthless as an oracle for
"will CoreML put this on the ANE". This is why `--vs-lint`'s agreement number
stays meaningless, and why patch 0016's warning should stay.

**Cost (the `estimated_us` half): usable on 27.x.** Differentiated, non-zero,
reproducible. SCHED-1's acceptance criterion can be met on B.

So SCHED-1 unblocks **as a cost model only**, on macOS 27.x, and it should be
explicit that the placement half of the model is *not* calibrated by it — it is
either inherited from `mil_lint`'s `Unit` verdicts or left unvalidated.

## 5. What this does NOT settle

- **Whether 27.x plans onto the ANE for *large* graphs.** All corpus packages
  are tiny (1–4096 elements). Apple's own 1551-op model also stayed on CPU, so
  size does not appear to be the trigger — but a genuinely large ML-Program has
  not been tried on 27.x. Worth one run before claiming the placement half is
  permanently dead.
- **Cross-arch comparability.** A is M5/h17, B is M4 Pro. The `0.25` flat cost
  on A vs differentiated on B *could* be an SoC difference rather than an OS
  one. This needs the same OS on both, or two hosts on the same OS, to separate.
  Recorded as an open confound, not resolved — it is the obvious next
  measurement if SCHED-1 gets re-prioritised.
- **e5rt on B.** Not run; B has no Rust toolchain and ANE presence is asserted
  via `ioreg`, not by executing. So no claim about 27.x's e5rt lane.

## 6. Method notes

- No toolchain was installed on B. The existing `target/release/milc` was
  `scp`'d and `chmod +x`'d, and it runs — `milc plan` `dlopen`s CoreML at
  runtime, so no rebuild was needed. Cheaper and less invasive than rustup on
  someone else's machine.
- Blob-backed corpus entries (`conv1x1`, `rmsnorm`, `matmul_chain`) were omitted
  here as on A, for the same reason (`coremlc` refuses `@model_path/weights`
  references). Both hosts therefore measured 6 package names, 10 comparable ops.
- Access was `davidgraham@100.127.197.66` over the tailnet. Keys on the local
  Mac that do *not* work there are recorded in the git history of this session,
  so nobody re-tries them.

## 7. Cross-lane notes

- Touched only this evidence file. No vendor change, no patch, no manifest drift.
- `SCHED-1-macos27-availability.md` should be read as "why we could not test it
  locally", superseded as to the conclusion by this file.
- **PROBE-2 / ADR-0002:** the deploy gate is the other `_ANEClient` OS-version
  question. B has `ANECompiler` and the full stack and macOS 27.0 — it is now
  the natural place to re-run `deploy_probe`/`dp3`, which is a much bigger
  question than whether 26.x-specific. Not attempted here (would need a build on
  B); flagged rather than actioned.
