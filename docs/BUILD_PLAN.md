# BUILD_PLAN.md — multi-lane plan

Status: living document. Item IDs are stable; use them in commits and PRs.
Owner column = lane. See `docs/lanes/OWNERSHIP.md` for the file contract.

**Ground rule for every item below:** the direct-HWX *deploy* lane is closed at
the OS level (`docs/adr/0002`). Nothing here may depend on it. Anything described
as "on the ANE" means the **`e5rt` lane** (where `aned` compiles the MIL itself)
or the **CoreML lane**, both of which are verified working on this machine.

---

## 0. Where we actually are

Verified this session on the vendored, patched tree:

| Capability | Lane | State |
|---|---|---|
| `.mlpackage` writer accepted by `coremlc` | CoreML | ✅ works |
| Stateful (MLState) package compiles | CoreML | ✅ works — **after our patch 0001** |
| Stateful package runs on `cpu+ane` | CoreML | ✅ 99.42 µs/step median, 3 steps |
| MIL → `ANECValidate`/`ANECCompile` → Mach-O | ANEC | ✅ works |
| MIL → `aned` compiles → execute on ANE | e5rt | ✅ 211 µs/step, numerics correct |
| Emit HWX ourselves and deploy it | HWX | ❌ closed at OS level |
| Perf counters | — | ❌ needs Apple-internal compile switch |

So: **we have a working compute path, a working compiler path, and a working
state path.** What we lack is a *scheduler*, *expressiveness* in the IR, and
*observability*. Those are the plan.

---

## Lane map

| Lane | Scope | Owns |
|---|---|---|
| **L-TOOL** | CLI, packaging, patching, build hygiene | `crates/milc/`, `patches/`, `scripts/` |
| **L-IR** | The validated text IR: expressiveness + validation | `src/ir.rs`, `src/ane_lower.rs`, `tests/ir.rs` |
| **L-SCHED** | Graph scheduling, cost model, placement | `crates/mil_infer/src/graph.rs`, new `crates/mil_sched/` |
| **L-RUN** | e5rt / espresso runtime, decode loop, sharding | `crates/mil_infer/src/{e5rt,espresso,ane_pipeline,ane_decode,shard}.rs` |
| **L-PROBE** | Hardware probing, dialect spec, fuzzing | `crates/mil_infer/src/{anec,fuzz}.rs`, `docs/spec/`, probe binaries |
| **L-LINT** | Placement prediction, plan diffing | `crates/mil_lint/`, `mil_verify::lint_spec` |
| **L-TEST** | Cross-lane test infra, evidence harness | `tests/`, `docs/evidence/` |

Dependency edges (a lane may only *read* what an upstream lane exposes):

```
L-PROBE ──> L-LINT ──> L-SCHED ──> L-RUN
                │           │
                └──> L-IR ──┘
L-TOOL <── (consumes all, owns no internals)
L-TEST ── (may veto any lane; owns no product code)
```

---

## Phase 1 — Make the foundation trustworthy (all lanes, parallel)

### L-TOOL

**TOOL-1 — Patch set + round-trip** ✅ *done*
Four patches, apply cleanly to pristine upstream, verified.
`docs/evidence/0001-write-state-shape.md`, `docs/evidence/0004-milc-run-dispatch.md`.

**TOOL-2 — `milc run` on a compiled `.mlmodelc`**
Currently `milc run x.mlmodelc` looks for `Data/com.apple.CoreML/model.mlmodel`
inside the *compiled* dir and fails. Accept either a package (compile-then-run) or
a prebuilt `.mlmodelc` (run only).
*Accept:* `milc run <pkg>` and `milc run <pkg>.compiled/x.mlmodelc` both work. ✅ **done**
(patch 0005 + `crates/milc/tests/run_cli.rs`; evidence `docs/evidence/0005-milc-run-mlmodelc.md`).
*Blocks:* nothing. *Owner:* L-TOOL. **Effort:** S.

**TOOL-3 — Structured `milc` diagnostics**
Every error currently prints a stage string. Emit machine-readable JSON
(`milc --json check|run|plan`) with `{stage, code, message, path}`, so lanes can
assert on failures in tests instead of grepping stderr.
*Accept:* a failing `milc` invocation under `--json` yields parseable JSON. ✅ **done**
(patch 0006 + 4 run_cli tests; evidence `docs/evidence/0006-milc-json-diagnostics.md`.
Top-level `--json` / `MILC_JSON=1`; success carries latency data; stderr stays human.)
*Owner:* L-TOOL. **Effort:** S. **Needed by:** L-TEST.

**TOOL-4 — Vendored-tree CI guard**
A script that asserts `vendor/mil_spec/` matches "pristine upstream + `patches/`"
byte-for-byte. Prevents silent hand-edits that never became patches.
*Accept:* mutate a vendored file → guard fails naming the file. ✅ **done**
(`scripts/vendor-guard.sh` + `vendor/manifest.sha256` + `tests/vendor-guard.bats.sh`,
evidence `docs/evidence/0005-vendor-guard.md`. First act was catching a stray
`src/ir.rs.orig`.)
*Owner:* L-TOOL. **Effort:** S. **Prevents:** the #1 fork rot.

### L-IR

**IR-1 — `write_state` shape validation** ✅ *done*
Patch 0001. Caught that two upstream fixtures had encoded the bug.

**IR-2 — `slice_update` / incremental state write** ⭐ *highest IR value* — *done (L-IR)* — patch `0007-ir-slice-update`, evidence `docs/evidence/0007-ir-slice-update.md`.
The IR has **no `slice_update`**, so a KV-cache append is inexpressible — the only
legal state write is whole-shape. Every real decode loop needs "write row `pos`".
The `Block` layer already supports it (`ane_lower` rebases `slice_update` for the
ANE dialect), so the IR is the gap, not the encoder.
*Accept:* IR program expressing a KV append at a runtime position, which encodes,
compiles via `coremlc`, and runs correctly against a reference.
*Owner:* L-IR. **Effort:** M. **Depends on:** nothing. **Unblocks:** RUN-3.

**IR-3 — IR → type-shape verification for all state ops** — *done (L-IR)* — patch `0008-ir-state-contract`, evidence `docs/evidence/0008-ir-state-contract.md`.
Generalise IR-1: every op that touches a `state<T>` should validate the full
contract (one `read_state` per state, `write_state` after each `slice_update`,
exact shapes). Mirrors `ANE_FRONTEND_SPEC.md`'s state contract at the IR level so
bad graphs fail at compile time, not inside ANEC/coremlc.
*Accept:* a negative test per contract clause.
*Owner:* L-IR. **Effort:** M. **Depends on:** IR-2.

**IR-4 — `while`/loop and indexed control flow** — *done (L-IR)* — patch `0010-ir-for-loop`, evidence `docs/evidence/0010-ir-for-loop.md`.
Any real decode step needs iteration. Currently the IR is straight-line SSA.
Scope this carefully: prefer *bounded, fully-unrolled* loops (the ANE has no
control flow) over real control flow — the honest answer is "unroll at compile
time", which is what `coyote` does by hand.
*Accept:* a documented, deliberately bounded loop construct with unrolling.
*Owner:* L-IR. **Effort:** L. **Risk:** high — may be descoped to "document that
the IR is straight-line and loops belong in the host".

### L-PROBE

**PROBE-1 — Re-probe the MIL dialect on the current SoC (`h17`)**
All upstream probing was `h16g` (M4). We have an M5. Re-run the validator matrix
and the 500-case fuzzer against `h17` and diff against `ANE_FRONTEND_SPEC.md`.
**This is the highest-value new knowledge available to us** — nobody has published
the `h17` dialect.
*Accept:* a diff document `docs/spec/ane-frontend-h17.md` listing ops that changed
verdict, plus a machine-readable matrix. ✅ **done** — 500 cases, seed 31337.
Family-level behavior identical to h16g (336/160/4/0/0); no verdict changed; first
published h17 matrix. Two verified findings: the spec's laxity count overstates
(3 func-name + 1 fuzzer no-op, fixed in patch 0011), and its "unclosed-paren
`const(` tolerated" claim does NOT reproduce on h17. Artifacts:
`docs/spec/ane-frontend-h17.md` + `ane-frontend-h17-matrix.jsonl` + `h17-findings/`.
*Owner:* L-PROBE. **Effort:** M. **Depends on:** nothing.

**PROBE-2 — Decode the deploy-gate error codes**
`0x170004` (our artifacts) vs `0x130004` (Apple's shipped) vs the un-catchable
ObjC exceptions on `H17`. Even if we cannot fix the gate, understanding it decides
whether ADR-0002 is permanent or version-specific.
*Accept:* an evidence file mapping each code to a cause hypothesis with a
reproduction, and a statement of whether any code path deploys. ✅ **done** —
`docs/evidence/0010-deploy-gate-codes.md` + patch 0012 (probes). **Arch is ruled
out** (h17 compile fails identically to h16g); the gate is **form-specific, not
provenance-specific** (`aned`'s own e5 bundle is also refused). No
externally-presented artifact deploys through `_ANEClient loadModel` on this OS
build; ADR-0002 is version/OS-specific, not arch-specific, and not fixable by
emitting different bytes. e5rt lane unaffected.
*Owner:* L-PROBE. **Effort:** M. **Note:** fork-isolate every probe — ObjC
exceptions abort the process.

**PROBE-3 — Dynamic-shape behaviour matrix**
Upstream measured fixed / EnumeratedShapes / ShapeRange × compute units. Extend to
e5rt and to `h17`, and turn it into an executable table (`mil_sched` input).
*Accept:* `docs/spec/shape-flex-matrix.md` + a test that asserts the table matches
observed behaviour. ✅ **done** — two-lane matrix on h17 (CoreML `loadModel` vs
e5rt `compile_auto`), minimal 1-op add + converted decoder. **h16g→h17 regression:**
ShapeRange on `all`/`ane` went from clean `-14` to a hard crash (SIGSEGV/SIGBUS).
**Lanes disagree on EnumeratedShapes:** CoreML loads+predicts on cpu/ane; e5rt
cannot find `main` in the package at all. **e5rt binds ShapeRange at the default
shape only** — runtime variation needs the unprobed JIT-shapes path. Executable
assertions in `docs/spec/shape-flex-matrix.spec` (passes via evidence-check.sh).
*Owner:* L-PROBE. **Effort:** S–M.

### L-TEST

**TEST-1 — Evidence harness**
Script that runs a work item's evidence commands and captures output verbatim into
`docs/evidence/<item>.md`, so evidence can never drift from the code.
*Accept:* regenerate all existing evidence files; diffs are empty. ✅ **done** —
reframed honestly: prose contains volatile facts (latencies, /tmp paths) by design,
so the harness re-executes a machine-readable `.spec` per item asserting exit codes
and stable claim-substrings instead of re-pasting prose. `scripts/evidence-check.sh`
+ `docs/evidence/*.spec` + `scripts/mk-evidence-artifacts.sh`. 8/8 pass on committed
HEAD; caught three CI-blocking issues on first run (empty patch 0007, stale manifest,
volatile /tmp artifacts). Evidence: `docs/evidence/0008-evidence-harness.md`.
*Owner:* L-TEST. **Effort:** S. **Depends on:** TOOL-3.

**TEST-2 — Hardware-conditional test discipline**
Audit for tests that silently no-op without hardware (upstream's `ops_e2e` returns
`None` when `coremlc` is missing). Replace silent skips with explicit, logged skips
and a `--require-hw` flag that turns a skip into a failure.
*Accept:* CI run without hardware reports N skipped, not N passed. ✅ **done**
(patch 0009: 27 runtime gates across 10 files routed through `mil_compile::hw_gate`
— loud `SKIP:` line by default, hard failure under `MIL_REQUIRE_HW=1`. CI job
`hw-skip-discipline.yml` simulates no-hardware on a macOS runner via a shadowed
`xcrun` and asserts skips fire with zero failures. Linux cannot be used for this —
`mil_infer` does not compile there. Evidence: `docs/evidence/0009-test-hw-gate.md`.)
*Owner:* L-TEST. **Effort:** S.

---

## Phase 2 — The scheduler (the differentiator)

### L-SCHED ⭐ the core new work

The measured truth from upstream: on a sharded SmolLM2-135M, `cpuAndNeuralEngine`
placed **84% of ops on the ANE but only 65% of estimated cost** — i.e. 16% of ops
carried 35% of the work, and the residual is CPU/transfer overhead. Upstream's
`graph.rs` is a rule-based single-stream compiler. A real scheduler attacks that gap.

**SCHED-1 — Cost model** — *blocked (L-SCHED)* — see `docs/evidence/SCHED-1-positive-control.md`.

Inputs we already have: `mil_lint`'s per-op unit verdict, `MLComputePlan`'s real
`preferred`/`cost`, and `milc plan --json`. Output: per-op `(unit, estimated_us,
transfer_bytes)`.
*Accept:* predicted per-op cost within a stated tolerance of measured `MLComputePlan`
cost on a fixed model; disagreement documented rather than hidden.
*Owner:* L-SCHED. **Effort:** M. **Depends on:** L-LINT (read-only), TOOL-3.

> **Blocked on: `MLComputePlan` produces no usable cost on macOS 26.7.1.**
> Measured, not theorised (`SCHED-1-positive-control.md`): two CoreML-authored
> Apple models — `PlanResolutionModel.mlmodelc` (1551 ops) and
> `ASRRankingModel.mlmodelc` (429 ops) — both plan **100% cpu with 0.00
> per-op cost**. So the acceptance metric is unavailable by construction: any
> non-zero predicted cost is infinitely far from a measured 0.00.
>
> **What SCHED-1 did deliver, and this is the point:** the finding itself.
> `milc plan --vs-lint` reports 0/10 agreement against our own corpus
> (`SCHED-1-vs-lint-disagreement.md`), and the natural reading — "`mil_lint`
> mis-predicts" — is **wrong**. The plan side is degenerate, not the lint side.
> Name this before SCHED-2/SCHED-4 build on it, or they will inherit a broken
> oracle without noticing.
>
> **Not blocked:** `mil_lint`'s per-op `Unit` verdicts. Those are unaffected and
> remain SCHED-2's and SCHED-4's placement input. Only the *cost* half of
> SCHED-1 is blocked.
>
> **Unblock condition:** an OS version (or CoreML path) where `MLComputePlan`
> attributes non-zero cost and places ops on the ANE, or an owner decision to
> accept e5rt end-to-end latency per subgraph as the calibration source. The
> latter is available *today* and measurable, but is a genuine precision loss —
> e5rt runs one `execute_sync` per graph, so per-op attribution is not
> recoverable. Decision needed; not silently redefining the item.

**SCHED-2 — Partitioning under the plan-builder limit**
Upstream found the hard ceiling: **CoreML error -14 between 3,164 and 3,284 ops**
(it is op count, not bytes — an int8 variant at 29 MB still fails). `--shard N` is
a blunt workaround. Do better: partition to maximise ANE placement subject to the
op limit, choosing cut points at low-traffic boundaries (minimise hidden-state
crossings), and decide shard count from the model rather than a flag.
*Accept:* a model past the limit is partitioned automatically and runs; compare
placement % against `--shard N` for the same model.
*Owner:* L-SCHED. **Effort:** L. **Depends on:** SCHED-1.

**SCHED-3 — Per-subgraph backend selection (e5rt vs CoreML)**
We have two working execution paths with different characteristics. Route each
subgraph to whichever the cost model prefers — e.g. CoreML for shape-flexible
graphs it alone can plan, e5rt for precompiled fixed-shape ones.
*Accept:* a mixed model runs end-to-end with a recorded per-subgraph backend
decision and a measured latency better than either pure path.
*Owner:* L-SCHED. **Effort:** L. **Depends on:** SCHED-1, L-RUN.

**SCHED-4 — Dispatch-count minimiser**
`mil_lint` already estimates dispatch count, and upstream asserts it is "the number
that decides whether a graph lives or dies on the ANE". Optimise for it directly:
fuse elementwise chains, keep constants resident, avoid layout repacks.
*Accept:* dispatch count strictly reduced on a fixed model with numerics within fp16
tolerance.
*Owner:* L-SCHED. **Effort:** M. **Depends on:** SCHED-1.

---

## Phase 3 — Runtime capability (e5rt lane)

### L-RUN

**RUN-1 — Loader error decoding** — *done (L-RUN)* — patch `0014-run1-loader-errors`, evidence `docs/evidence/RUN-1-loader-errors.md`.
Turn opaque `Program load failure (0x170004)` into structured `AneError` variants
with the code, the failed selector, and a suggested cause. Do it as a proper patch
with tests, not a string tweak.
*Accept:* each observed code maps to a named variant; a table test covers them.
*Owner:* L-RUN. **Effort:** S–M. **Depends on:** PROBE-2.

**RUN-2 — Stateful programs on e5rt with explicit state lifecycle** — *done (L-RUN)* — patch `0013-run2-state-lifecycle`, evidence `docs/evidence/RUN-2-state-lifecycle.md`.
Upstream verified `state<>` params surface as **inout ports, resident across
calls**. Formalise: an explicit state handle API (`new_state`, `reset`, `save`,
`restore`) so KV caches are first-class and testable, rather than implicit.
*Accept:* a 2-layer stateful program runs N steps on e5rt and its state round-trips
through save/restore with bit-identical continuation.
*Owner:* L-RUN. **Effort:* M. **Depends on:** IR-2.

**RUN-3 — Real decode loop against a real checkpoint**
`ane_decode` exists but its receipts need a checkpoint. Get a small model
(Qwen3-0.6B or SmolLM2-135M) through `mil_convert` → shard → e5rt decode, and
record top-1 agreement vs a CPU reference.
*Accept:* ≤N tokens generated, top-1 agrees at all positions, latency recorded.
*Owner:* L-RUN. **Effort:** L. **Depends on:** RUN-2, SCHED-2. **Note:** honest
expectation is correct tokens, not bit-faithful logits (the ANE is approximate —
upstream measured cosine ~0.99).

**RUN-4 — On-chip training on the working lane** ⭐ novel
Upstream demonstrated forward+backward+in-place-SGD through `graph` (MSE
0.076→0.000096 over 16 steps) but on the lane that cannot deploy here. Rebuild that
lowering on **e5rt**, which works. The four routes are known: `emit_avw` (fwd),
`emit_attn_v` (dx), `emit_outer_t` (dW), `emit_add4d` (in-place update).
*Accept:* 2-layer MLP trains on the ANE via e5rt, loss decreases monotonically over
≥20 steps, weights verifiably change in the state buffer.
*Owner:* L-RUN. **Effort:** L. **Depends on:** RUN-2, SCHED-3. **Risk:** medium —
this is the most novel item, and also the most likely to hit undocumented limits.

---

## Phase 4 — Borrowed design from coyote (deliberately last)

**BORROW-1 — `grad`-as-primitive (design adoption, not code)**
Adopt the seed-pre-scaling idea: pre-scale the loss seed by `±lr` so a folded SGD
update is **one packed add**. Reimplement from the description in
`docs/adr/0004-borrowed-design.md`; do not copy `coyote` code (it is MIT, but it is
not vendored and we do not want a second fork).
*Owner:* L-RUN. **Effort:** M. **Depends on:** RUN-4.

**BORROW-2 — Constitutional checking as a library** (only if we need it)
Transitive capability closure, `det`/`stoch`, `sealed` taint. Verified working
upstream. Worth a standalone crate only if we build agent-facing execution;
otherwise document the pattern and stop.
*Owner:* unassigned. **Effort:** L. **Decision gate:** do we need it at all?

---

## Explicitly out of scope

Recorded so nobody spends a lane on them:

| Item | Why not |
|---|---|
| Direct HWX deploy | OS-level gate; Apple's own artifacts fail (`docs/adr/0002`) |
| Perf counters | Requires a compile-time instrumentation switch inside Apple's compiler |
| Dynamic shapes on ANE | Apple's own caveat; upstream measured range-flex only plans on CPU |
| Adding ops the ANEC frontend rejects (`gather`, int/bool tensor math, sub-32 matmul) | The hardware compiler refuses them |
| Forking `coyote` wholesale | 14.9k LOC, zero tests, and its ANE half needs the closed lane |
| Shipping anything private-framework-based as a product | Legal, not technical — see `docs/LEGAL.md` |

---

## Suggested parallelism

Phase 1 is embarrassingly parallel — 6 lanes, no shared files:

```
L-TOOL: TOOL-2, TOOL-3, TOOL-4
L-IR:   IR-2 ──> IR-3 ──> IR-4
L-PROBE:PROBE-1, PROBE-2, PROBE-3
L-TEST: TEST-1, TEST-2
L-LINT: (audit existing rules against PROBE-1 output; no new work yet)
L-SCHED:(read-only: build the cost model against TOOL-3's JSON plan output)
```

Phase 2 starts when **SCHED-1** can consume PROBE-3's matrix and TOOL-3's JSON.
Phase 3 starts when **IR-2** lands (RUN-2 needs it). RUN-4 is the long pole.

**First three things to do, in this order:** `TOOL-4` (protect the fork from rot),
`PROBE-1` (new knowledge, no dependencies), `IR-2` (unblocks the most).
