# Evidence — SCHED-1: characterising the `--vs-lint` disagreement

Lane: `L-SCHED` (claimed 2026-10-21).
Work item: `SCHED-1` — cost model. This is its *prerequisite*: the acceptance
criterion says "disagreement documented rather than hidden", and a model
calibrated on an undiagnosed disagreement is unfalsifiable. So the model is not
built yet.

Host: Apple M5 (h17), macOS 26.7.1. All runs via `milc plan ... --vs-lint`.

> **Settled since by `SCHED-1-positive-control.md`:** the 0/10 result below is
> **not** evidence that `mil_lint` is wrong. Two CoreML-authored Apple models
> also plan 100% cpu with 0.00 cost, so the plan side of this comparison is
> degenerate on this host. Read this file for the corpus and the method; read
> the positive-control file for the conclusion. Patch `0016` now warns at the
> point where this number is printed.

---

## 1. Corpus

Built by `examples/sched_corpus.rs` (L-SCHED, at the workspace root rather than
in `vendor/`, since it is our own tooling and not an upstream patch):

| package | shape | why included |
|---|---|---|
| `elemwise` | fp16 `[1,64,1,1]` mul | easy positive case |
| `big_elemwise` | fp16 `[1,4096,1,1]`, 4 ops | large enough that CoreML *should* prefer the ANE |
| `softmax` | fp16 `[1,8,64]` | the reduction class PROBE-1 flagged as a family |
| `stateful` | fp16 `[1,8,64,64]` state | RUN-2's path |
| `cast_chain` | fp16→fp32→fp16 | dtype-flip class |
| `int32_const` | int32 const | pins what the integer rule fires on |
| `conv1x1`, `rmsnorm`, `matmul_chain` | blob-backed | **did not build** — see §4 |

Three packages failed to build because `@model_path/weights/*.bin` blobs are
referenced but not supplied; `coremlc` refuses the package outright. Excluded
rather than fabricated a blob, so the corpus remains honest: 6 packages with
verdicts, not 9 with 3 silenced.

## 2. Result — the disagreement is total, not per-class

| package | agree/total | disagreements |
|---|---|---|
| `elemwise` | **0/1** | `mul` lint ane → plan cpu |
| `softmax` | **0/1** | `softmax` lint ane → plan cpu |
| `stateful` | **0/2** | `read_state`, `add` lint ane → plan cpu |
| `cast_chain` | **0/2** | 2× `cast` lint ane → plan cpu |
| `big_elemwise` | **0/4** | 2× `mul`, 2× `add` lint ane → plan cpu |
| `int32_const` | — | 0 comparable ops (`const` exempt) |
| Total | **0/10** | every comparable op, both `--units ane` and `--units all` |

Every disagreement is the **same direction**: lint says `ane`, plan says `cpu`.

## 3. What this is *not*

It would be easy to conclude "`mil_lint` is broken". Three checks say that
conclusion is premature, and all three were run rather than reasoned about:

**a. The plan is real and correctly read.** `--json` shows non-`None`
`preferred`, a `supported` list including `"ane"`, and non-zero `cost` (0.25 per
op). `walk_ops` uses the genuine CoreML selectors
(`computeDeviceUsageForMLProgramOperation:`,
`estimatedCostOfMLProgramOperation:`). The plan is not an empty or misread
object.

**b. The lint/plan *mapping* is not the artefact.** `dev_of()` maps
`Unit::Cpu → Device::Cpu`, and `classify_op` really does emit `Unit::Cpu`
(`"integer op"` among other rules), so lint can represent `cpu` and the
comparison is honest. Hypothesis rejected.

**c. Size is not the cause.** `big_elemwise` at 4096 elements still plans `cpu`.
The "tiny graphs are never planned onto the ANE" explanation does not survive.

## 4. The leading hypothesis

`coremlc`-compiled packages from our own IR are **compiling to a form CoreML's
planner keeps entirely on CPU**. This is consistent with what the rest of the
project already knows rather than contradicting it:

- `docs/evidence/0001-write-state-shape.md` shows our positive control
  (`compile_ir_fixed` → `milc run --units ane`) reporting **99.42 µs/step**,
  which is real ANE work. But that goes through `milc run`, not
  `MLComputePlan`.
- `BUILD_PLAN.md §0` records the e5rt lane as "MIL → `aned` compiles → execute
  on ANE ✅ 211 µs/step". Both *working* paths bypass `MLComputePlan`.

So the hypothesis is that **`MLComputePlan`'s planner is simply not placing our
IR-compiled graphs on the ANE at all** — which would make the lint/plan
agreement number meaningless as a *lint* quality metric, because the plan itself
is the thing that is wrong.

**This is a hypothesis, not a finding.** It is not settled here because settling
it needs the positive control: does `MLComputePlan` place a known-good,
CoreML-authored (not ours) model onto the ANE on this machine? If it does, our
IR output is the problem. If it also puts *that* on CPU, `MLComputePlan` on this
OS build is not a usable calibration source and SCHED-1 must use e5rt timing
instead — which would be a scope change, not a bug.

## 5. Proposed next step (the actual decision point)

**Obtain a CoreML-authored positive control and run `--vs-lint` against it.**
One command, decisive either way. This is the only step that can separate "our
IR compiles badly" from "`MLComputePlan` is not usable here", and SCHED-1's
calibration source depends entirely on the answer.

Options for the control, cheapest first:
1. A `coremltools`-produced `.mlpackage` — none may be present; check.
2. A model in `mil_convert`'s test fixtures — likely present, check first.
3. `mil_machines::write_memory_package` output — ours, so not an independent
   control.

## 6. What SCHED-1 has and has not gained

**Gained:** a reproducible, 10-op measurement showing the comparison is 0%, a
ruled-out hypothesis (the mapping), a ruled-out explanation (size), and a
corpus generator that will be reused to measure any change.

**Not gained:** a cost model. Nothing here is calibrated. No `mil_sched` code
exists, and per ADR-0003 none should until there is something to put in it.

## 7. Cross-lane notes

- Touched only L-SCHED files: `examples/sched_corpus.rs`,
  `examples/Cargo.toml`, this evidence file. No `vendor/` change, so no patch
  and no manifest drift.
- `examples/` at the workspace root is currently unowned by any lane
  (`OWNERSHIP.md` covers `scripts/`, `patches/`, the vendored crates, and
  `docs/` — but not a root `examples/`). L-SCHED is adding a file there, so:
  **request to L-TOOL** — either claim `examples/**` or extend L-SCHED's block
  to include it, so two lanes do not both add examples there.
- `--vs-lint` lives in `crates/milc/` (L-TOOL). No change made to it.
