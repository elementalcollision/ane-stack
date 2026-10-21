# PROBE-1: Dynamic-Slice-Reject Family — h17 Re-Probe Plan

**Lane:** L-PROBE  
**Target:** `docs/spec/ane-frontend-h17.md` + machine-readable verdict matrix  
**Baseline:** `vendor/mil_spec/ANE_FRONTEND_SPEC.md` (h16g, M4)  
**Seed:** 31337  
**Cases:** 500 (deterministic via xorshift64*)

---

## 1. Scope and Constraints

### What this plan covers
- Re-running the **existing** fuzzer workflow (`milc ane fuzz`) against `h17` instead of `h16g`
- Focus on the **`reject_dyn_slice`** family (dynamic slice bounds) as the representative expected-reject case
- Handling of **`UnexpectedAccept`** verdicts (validation holes) for this family
- Producing two artifacts: a human-readable spec diff (`ane-frontend-h17.md`) and a machine-readable matrix (JSONL/CSV)

### What this plan does NOT cover
- Direct HWX deployment (ADR-0002: closed at OS level — no execution path)
- New harness code — reuse `milc ane fuzz` / `fuzz-worker` exactly as-is
- Changes to `vendor/mil_spec/` — L-PROBE writes only under `docs/spec/`
- Other reject families (`reject_int_compute`, `reject_gather`, `reject_zero_extent`, `blobfile_probe`, `reject_gelu`) — they are probed incidentially but not the focus

### Candid gaps in source material
- The h16g baseline (500-case run, seed 31337) reports **0 crashes, 0 unexpected rejects** for the full matrix, but the per-family breakdown is not published.
- `reject_dyn_slice` specifically: the h16g `ANE_FRONTEND_SPEC.md` states "dynamic begin/end → PARSE: const indices only" but the fuzzer finding "dynamic slice begin — runtime index" is listed as an expected reject. We do not know the exact h16g acceptance rate for this family in isolation.
- No published h17 data exists — this probe *is* the first measurement.

---

## 2. Files L-PROBE May Edit

| File | Purpose | Owner |
|------|---------|-------|
| `docs/spec/ane-frontend-h17.md` | Human-readable spec diff (primary deliverable) | L-PROBE |
| `docs/spec/h17-verdict-matrix.jsonl` | Machine-readable per-case verdicts (primary deliverable) | L-PROBE |
| `docs/spec/h17-fuzz-report.jsonl` | Raw fuzz run log (evidence, append-only) | L-PROBE |
| `docs/evidence/PROBE-1-h17-dynamic-slice.md` | Evidence capture for this specific work item | L-TEST (harness) / L-PROBE (content) |

**No edits to:** `vendor/mil_spec/ANE_FRONTEND_SPEC.md`, `crates/mil_infer/src/fuzz.rs`, `crates/milc/src/main.rs`, any `.rs` files.

---

## 3. Reproducible h17 Command

```bash
# From repo root (where milc binary is built)
cd /Users/dave/Claude_Primary/ane_stack

# 1. Ensure milc is built with the vendored tree
cargo build --release -p milc --manifest-path vendor/mil_spec/Cargo.toml

# 2. Run the 500-case fuzz matrix against h17, seed 31337
#    --compile exercises ANECCompile (not just Validate) for each case
#    Output lands in a timestamped corpus dir; findings auto-saved
MILC_JSON=1 \
./target/release/milc ane fuzz \
  --arch h17 \
  --iters 500 \
  --seed 31337 \
  --compile \
  -o /tmp/milc_fuzz_h17_$(date +%Y%m%d_%H%M%S)
```

**Expected runtime:** ~8–12 minutes (30s timeout/worker × 500 cases, parallelism limited by fork isolation).  
**Exit codes:** 0 = no findings; 3 = findings present (UnexpectedAccept, UnexpectedReject, Crash). Both are valid outcomes.

---

## 4. Workflow — Using Existing Fuzz Infrastructure

### Step 1: Run the fuzz matrix (single command above)
- Driver: `cmd_ane` → `mode == "fuzz"` in `milc/src/main.rs`
- Each case: `gen_program(rng, id)` → writes `model.mil` (+ `weights/weight.bin` if needed)
- Worker: `milc ane fuzz-worker --arch h17 --compile <model.mil>` (fork-isolated)
- Worker prints: `VERDICT status=0x... rc=... accepted=0|1 ERROR ...`
- Driver classifies via `classify(expected, accepted, crashed, timed_out)`
- Findings (non-AcceptOk/RejectOk) copied to `findings_dir/{id}_{family}_{Class}/`
- Raw report: `fuzz_report.jsonl` (one JSON line per case)

### Step 2: Extract `reject_dyn_slice` family rows
```bash
# From the generated report
jq 'select(.family=="reject_dyn_slice")' fuzz_report.jsonl > reject_dyn_slice_h17.jsonl
```

### Step 3: Classify outcomes for the family
| Class | Meaning for `reject_dyn_slice` (expected=Reject) |
|-------|--------------------------------------------------|
| `RejectOk` | h17 correctly rejects dynamic slice bound — **expected** |
| `UnexpectedAccept` | h17 **accepts** a program with runtime `begin`/`end` — **validation hole** (finding) |
| `Crash` | ANECompiler process died (signal/abort) — **compiler bug** (finding) |
| `Timeout` | Worker exceeded 30s — **possible hang** (finding) |
| `UnexpectedReject` | Impossible for expected=Reject (logic) |

### Step 4: Handle `UnexpectedAccept` (the critical handling)
For each `reject_dyn_slice` case classified `UnexpectedAccept`:
1. The finding artifact is already saved: `findings/NNNNN_reject_dyn_slice_UnexpectedAccept/{model.mil, stderr.txt}`
2. **Do not** attempt to execute the accepted MIL — the HWX deploy lane is closed (ADR-0002).
3. Record in the spec diff: "h17 accepts dynamic slice indices (validation hole vs h16g rejection). Artifact: `findings/.../model.mil`."
4. In the machine matrix: mark `verdict: "UnexpectedAccept"`, `note: "h17 accepts dynamic begin/end; h16g rejected"`.

### Step 5: Compare against h16g baseline
- h16g baseline is the **text** in `vendor/mil_spec/ANE_FRONTEND_SPEC.md` (not a re-run).
- For each op/construct in the fuzzer's generator, the h17 run produces an empirical verdict.
- Diff rule: if h17 verdict ≠ h16g text claim → entry in `ane-frontend-h17.md` with "CHANGED" badge.
- If h17 matches h16g → "SAME" (can be implicit or explicit in matrix).
- The matrix must include **every case** (500 rows), not just findings.

---

## 5. Output Artifacts — Specification

### 5.1 `docs/spec/ane-frontend-h17.md` (human-readable)

Structure (mirror upstream's spec sections):

```markdown
# ANEC MIL Frontend — Empirical Spec (h17 / M5)

> Probed via `milc ane fuzz --arch h17 --iters 500 --seed 31337 --compile`
> on macOS 26.x (M5 Max). Fork-isolated workers. Baseline: h16g (M4) in
> `vendor/mil_spec/ANE_FRONTEND_SPEC.md`.

## Summary
- Total cases: 500
- AcceptOk: N
- RejectOk: N
- UnexpectedAccept: N  ← validation holes
- UnexpectedReject: N  ← regressions vs spec
- Crash: N
- Timeout: N

## Op Matrix (h17) — Diff vs h16g

| op / construct | h16g verdict | h17 verdict | status | evidence |
|---|---|---|---|---|
| dynamic slice begin/end | PARSE (reject) | OK (accept) | **CHANGED** | findings/00042_reject_dyn_slice_UnexpectedAccept/model.mil |
| gelu(mode) | PARSE (reject) | OK (accept) | **CHANGED** | findings/00117_reject_gelu_UnexpectedAccept/model.mil |
| ... | ... | ... | ... | ... |

## Dynamic Slice Family Detail (`reject_dyn_slice`)

### h16g baseline
> "begin/end must be const — dynamic/index-computed slices are rejected (InvalidMILProgram)"

### h17 observed
- Cases generated: K (out of 500)
- RejectOk: A
- UnexpectedAccept: B
- Crash/Timeout: C

**If B > 0:** h17 admits dynamic slice indices that h16g rejected. The accepted MIL uses
runtime `tensor<int32, [4]> bgn/end` parameters passed to `slice_by_index`.
This is a **validation hole** — the frontend no longer enforces const indices.
Implication: `NetworkJITShapesPath` path may now be partially wired, or the check
was relaxed. **No execution test performed** (HWX deploy lane closed).

### Example accepted case (if any)
```mil
program(1.3) {
    func main<ios18>(tensor<fp16, [1, 32, 1, 1]> x0,
                     tensor<int32, [4]> bgn,
                     tensor<int32, [4]> end,
                     tensor<int32, [4]> st) {
        tensor<int32, [4]> bm = const()[val = tensor<int32, [4]>([1, 1, 1, 1])];
        tensor<int32, [4]> em = const()[val = tensor<int32, [4]>([1, 1, 1, 1])];
        tensor<int32, [4]> sq = const()[val = tensor<int32, [4]>([0, 0, 0, 0])];
        tensor<fp16, [1, 4, 1, 1]> z = slice_by_index(begin = bgn, end = end, stride = st,
                          begin_mask = bm, end_mask = em, squeeze_mask = sq, x = x0);
    } -> (z);
}
```

## Other Families with Verdict Changes
(One subsection per family where h17 ≠ h16g)

## Methodology
- Generator: `crates/mil_infer/src/fuzz.rs` (xorshift64*, seed 31337)
- Validator: `ANECValidate` + `ANECCompile` via `ANECompiler.framework`
- Architecture: `h17` (from `mil_infer::anec::ARCHES`)
- iOS target: `ios18` (hardcoded in generator)
- Timeout: 30s/worker
- Weights: inline fp16 lists only (BLOBFILE rejected on both h16g/h17)
```

### 5.2 `docs/spec/h17-verdict-matrix.jsonl` (machine-readable)

One line per case (500 lines):

```json
{"id":0,"family":"ew_chain","expected":"Valid","class":"AcceptOk","note":"3-op elementwise chain on [1, 16, 1, 1]","arch":"h17","seed":31337}
{"id":1,"family":"matmul","expected":"Valid","class":"AcceptOk","note":"matmul tx=true ty=false n=8 inline weights","arch":"h17","seed":31337}
{"id":2,"family":"reject_dyn_slice","expected":"Reject","class":"RejectOk","note":"dynamic slice begin — runtime index","arch":"h17","seed":31337}
...
{"id":42,"family":"reject_dyn_slice","expected":"Reject","class":"UnexpectedAccept","note":"dynamic slice begin — runtime index","arch":"h17","seed":31337,"finding_path":"findings/00042_reject_dyn_slice_UnexpectedAccept/model.mil"}
```

Schema (all fields present):
- `id` (int): case index 0..499
- `family` (string): generator family name
- `expected` (string): "Valid" | "Reject"
- `class` (string): "AcceptOk" | "RejectOk" | "UnexpectedAccept" | "UnexpectedReject" | "Crash" | "Timeout"
- `note` (string): generator's descriptor
- `arch` (string): "h17"
- `seed` (int): 31337
- `finding_path` (string, optional): relative path to artifact if `class` is finding

---

## 6. Evidence Capture (for L-TEST / docs/evidence)

The evidence harness (`scripts/evidence-check.sh` / `mk-evidence-artifacts.sh`) should be invoked after the run:

```bash
# Capture the raw report and summary as evidence
./scripts/mk-evidence-artifacts.sh PROBE-1-h17-dynamic-slice \
  --report /tmp/milc_fuzz_h17_*/fuzz_report.jsonl \
  --findings /tmp/milc_fuzz_h17_*/findings \
  --matrix docs/spec/h17-verdict-matrix.jsonl \
  --spec docs/spec/ane-frontend-h17.md
```

This creates `docs/evidence/PROBE-1-h17-dynamic-slice.md` with the command log, summary counts, and links to artifacts.

---

## 7. Acceptance Criteria

| Criterion | Met When |
|-----------|----------|
| h17 fuzz run completes | `milc ane fuzz --arch h17 --iters 500 --seed 31337 --compile` exits 0 or 3 |
| Per-case verdicts preserved | `fuzz_report.jsonl` has 500 lines; `findings/` contains all non-baseline cases |
| `reject_dyn_slice` family analyzed | `ane-frontend-h17.md` has a dedicated subsection with counts and example |
| `UnexpectedAccept` handling documented | Each such case has `finding_path` in matrix; spec diff calls it "validation hole" |
| No HWX execution attempted | Plan never invokes `milc ane run`, `e5rt`, or `EspressoProgram::bench` on accepted rejects |
| Machine matrix produced | `h17-verdict-matrix.jsonl` exists, 500 lines, valid JSONL, all fields present |
| Human spec diff produced | `ane-frontend-h17.md` exists, mirrors upstream structure, every change has evidence link |
| Baseline comparison explicit | Every row in matrix implies h16g vs h17; spec diff table has "CHANGED"/"SAME" |

---

## 8. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| `h17` not in `mil_infer::anec::ARCHES` | Verify `ARCHES` includes `h17` (it does per spec: `h17 h17a h17c h17d h17g h17s h18 h18g h19`). If missing, add to local `ARCHES` in `anec.rs` — **but this is a L-PROBE-owned file** (`crates/mil_infer/src/anec.rs` is L-PROBE per OWNERSHIP.md). |
| Worker timeout too short for h17 | 30s is generous for Validate+Compile; if timeouts spike, re-run with `--iters 100` first to calibrate. |
| ANECompiler.framework not loadable on h17 | `Anec::open()` will fail fast; evidence captures the error. This is a valid "environment" finding. |
| Seed 31337 produces 0 `reject_dyn_slice` cases | Generator: `gen_reject` cycles `id % 6`; at 500 iters, ~83 rejects/6 ≈ 14 `reject_dyn_slice` cases expected. Deterministic. |
| Findings dir permission errors | Use `/tmp/milc_fuzz_h17_<timestamp>` (world-writable). |

---

## 9. Dependencies and Blockers

- **None** — this is the first item in L-PROBE, no upstream lane dependencies.
- **Provides:** h17 dialect truth for L-LINT (placement rules), L-SCHED (cost model), L-IR (dialect boundaries).
- **Consumes:** existing fuzzer, `milc` CLI, `ANECompiler.framework` on M5.

---

## 10. Execution Checklist (for the agent doing the work)

- [ ] Verify `h17` in `crates/mil_infer/src/anec.rs` `ARCHES` array
- [ ] Build `milc` from vendored tree: `cargo build --release -p milc`
- [ ] Run the reproducible command (Section 3)
- [ ] Wait for completion; capture exit code and stdout/stderr
- [ ] Extract `reject_dyn_slice` rows from report
- [ ] Count `UnexpectedAccept` for this family
- [ ] Write `docs/spec/h17-verdict-matrix.jsonl` (transform full report)
- [ ] Write `docs/spec/ane-frontend-h17.md` (template in Section 5.1)
- [ ] Run evidence harness to create `docs/evidence/PROBE-1-h17-dynamic-slice.md`
- [ ] Verify matrix has 500 lines; spec diff has diff table

---

## 11. What Would Constitute a "Finding" for This Family

| Outcome | Interpretation |
|---------|----------------|
| `UnexpectedAccept` count > 0 | **High-value finding**: h17 frontend relaxed the const-index rule for `slice_by_index`. The MIL dialect on M5 admits dynamic slice bounds that M4 rejected. This affects KV-cache append patterns (runtime `pos`). |
| `UnexpectedAccept` count = 0 | **Null result**: h17 still rejects dynamic slices. The h16g rule holds. Document as "SAME". |
| `Crash` count > 0 | **Compiler bug**: ANECompiler crashes on a specific dynamic-slice MIL. Artifact saved for Apple feedback. |
| `Timeout` count > 0 | **Possible hang**: specific slice shape/config causes validator to spin. |

**Candid note:** We cannot know whether an `UnexpectedAccept` program would *execute correctly* on the ANE — the HWX deploy lane is closed. The finding is strictly "frontend validation hole vs h16g baseline." Execution behavior is unknowable without the deploy lane.