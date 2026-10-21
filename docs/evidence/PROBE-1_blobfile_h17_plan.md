# PROBE-1 Implementation Plan — BLOBFILE Family on h17

**Scope**: Re-probe the MIL dialect on the current SoC (M5, `h17`) using the existing `milc ane fuzz` driver/workflow. Focus on the `blobfile_probe` family as a representative case. Seed: 31337. Total cases: 500.

**Lane**: L-PROBE only. All file paths below are L-PROBE-owned per `OWNERSHIP.md`.

---

## 1. Baseline Reference (h16g)

From `vendor/mil_spec/ANE_FRONTEND_SPEC.md` (upstream's empirical spec, measured on M4/h16g):

| Construct | h16g Verdict | Notes |
|---|---|---|
| `const` + `BLOBFILE` (`@model_path/...`) | **Reject** (`InvalidMILProgram`) | Every spelling rejected; weights need `FileConstants`/`ExternConstants` dict lane |
| `const` + `BLOBFILE` (absolute path) | **Reject** | Same |
| `const` + `BLOBFILE` (relative `weights/weight.bin`) | **Reject** | Same |
| `const` + `BLOBFILE` (`tensor<string,[]>`-wrapped path) | **Reject** | Same |
| Inline `fp16` list consts | **Accept** | Works fine |

The fuzzer's `gen_reject` with `kind == 4` produces the `blobfile_probe` family:
- MIL: conv1x1 with `BLOBFILE` weight at offset 64
- `weights/weight.bin` created with 64-byte header + 16 fp16 values
- `expected: Expected::Reject`
- Note: "BLOBFILE const — rejected on this build"

---

## 2. Reproducible h17 Command

```bash
milc ane fuzz \
  --iters 500 \
  --seed 31337 \
  --arch h17 \
  --compile \
  -o /tmp/probe1_blobfile_h17
```

- `--iters 500` → 500 total cases (mixed families, including blobfile_probe when `id % 6 == 4` in `gen_reject`)
- `--seed 31337` → deterministic xorshift64* sequence
- `--arch h17` → targets the current SoC (M5)
- `--compile` → runs both `ANECValidate` AND `ANECCompile` in the worker (validate-only is faster but compile catches codegen-time rejections)
- `-o /tmp/probe1_blobfile_h17` → corpus root; creates `cases/` and `findings/` subdirs

**Output artifacts** (existing workflow, no new code):
- `/tmp/probe1_blobfile_h17/cases/{NNNNN_blobfile_probe}/model.mil` + `weights/weight.bin`
- `/tmp/probe1_blobfile_h17/cases/{NNNNN_blobfile_probe}/stdout.txt` + `stderr.txt`
- `/tmp/probe1_blobfile_h17/findings/{NNNNN_blobfile_probe_Class::UnexpectedAccept}/...` (if h17 *accepts* blobfile — a validation hole vs h16g)
- `/tmp/probe1_blobfile_h17/fuzz_report.jsonl` — one JSON line per case: `{id, family, expected, class, note}`

---

## 3. L-PROBE File Edits (Minimal)

Only two files need edits to produce the required deliverables. The fuzz driver and worker already exist and work.

### 3.1 `crates/mil_infer/src/fuzz.rs` — Add h17 summary helpers

**Purpose**: Emit a machine-readable verdict matrix and a Markdown diff against the h16g baseline, *after* the fuzz run completes. No behavioral change to generation/execution.

Add a public function (called from a new tiny binary or from the fuzz driver's summary section):

```rust
// In fuzz.rs — new public API
pub struct VerdictMatrix {
    pub arch: String,
    pub seed: u64,
    pub iters: usize,
    pub rows: Vec<VerdictRow>,
}

pub struct VerdictRow {
    pub family: String,
    pub expected: Expected,
    pub class: Class,
    pub note: String,
}

/// Parse fuzz_report.jsonl and produce a VerdictMatrix.
pub fn parse_report(path: &Path) -> Result<VerdictMatrix, std::io::Error> { ... }

/// Emit machine-readable JSON matrix (for SCHED-3 / L-SCHED consumption).
pub fn emit_matrix_json(matrix: &VerdictMatrix, out: &Path) -> Result<(), std::io::Error> { ... }

/// Emit Markdown diff vs h16g baseline (for docs/spec/ane-frontend-h17.md).
pub fn emit_h17_diff_md(matrix: &VerdictMatrix, baseline: &VerdictMatrix, out: &Path) -> Result<(), std::io::Error> { ... }
```

**Baseline construction**: Hard-code the h16g summary from `ANE_FRONTEND_SPEC.md` (the 500-case summary at the bottom of the Fuzzer findings section) into a `VerdictMatrix` constant in `fuzz.rs`, or read it from a checked-in `docs/spec/h16g_baseline.json`. The latter is cleaner for review.

### 3.2 `crates/mil_infer/examples/probe_h17_report.rs` — New binary (L-PROBE-owned)

**Purpose**: One-shot invocation that reads the fuzz run's `fuzz_report.jsonl`, produces the two deliverables, and exits. Keeps the fuzz driver unchanged.

```rust
// probe_h17_report.rs
use mil_infer::fuzz::{parse_report, emit_matrix_json, emit_h17_diff_md, VerdictMatrix};
use std::path::PathBuf;

fn main() {
    let corpus = std::env::args().nth(1).expect("corpus dir");
    let report = PathBuf::from(&corpus).join("fuzz_report.jsonl");
    let matrix = parse_report(&report).expect("parse report");

    // Machine-readable matrix → consumed by L-SCHED
    let matrix_out = PathBuf::from(&corpus).join("verdict_matrix_h17.json");
    emit_matrix_json(&matrix, &matrix_out).expect("write matrix");

    // Load h16g baseline (checked in at docs/spec/h16g_baseline.json)
    let baseline_path = PathBuf::from("docs/spec/h16g_baseline.json");
    let baseline_json = std::fs::read_to_string(&baseline_path).expect("read baseline");
    let baseline: VerdictMatrix = serde_json::from_str(&baseline_json).expect("parse baseline");

    // Markdown diff → docs/spec/ane-frontend-h17.md
    let diff_out = PathBuf::from("docs/spec/ane-frontend-h17.md");
    emit_h17_diff_md(&matrix, &baseline, &diff_out).expect("write diff");

    eprintln!("matrix → {}", matrix_out.display());
    eprintln!("diff   → {}", diff_out.display());
}
```

**Build/run**:
```bash
cargo build --example probe_h17_report --release
./target/release/examples/probe_h17_report /tmp/probe1_blobfile_h17
```

---

## 4. Deliverables

| File | Producer | Content |
|---|---|---|
| `docs/spec/ane-frontend-h17.md` | `probe_h17_report` (via `emit_h17_diff_md`) | Human-readable diff: for each family, h16g class → h17 class. Highlight `blobfile_probe`: if h17 accepts where h16g rejects, that's a validation hole / grammar change. If h17 rejects where h16g rejects, it's stable. |
| `{corpus}/verdict_matrix_h17.json` | `probe_h17_report` (via `emit_matrix_json`) | Machine-readable array of `{family, expected, class, note}` for all 500 cases. Schema matches `VerdictMatrix` above. Used by L-SCHED for cost-model input. |

**Example diff snippet for blobfile_probe**:

```markdown
## BLOBFILE family (h17 vs h16g baseline)

| Case ID | h16g class | h17 class | Verdict |
|---|---|---|---|
| 00004 | RejectOk | RejectOk | Stable (rejected as expected) |
| 00010 | RejectOk | UnexpectedAccept | **VALIDATION HOLE** — h17 accepts BLOBFILE const |
| 00016 | RejectOk | RejectOk | Stable |
| ... | ... | ... | ... |

**Summary**: N/10 blobfile_probe cases changed class. [Details on which spelling(s) now accept.]
```

---

## 5. What This Does NOT Do (Per Constraints)

- ❌ Does **not** invent a new harness — uses existing `milc ane fuzz` + `fuzz-worker` fork isolation
- ❌ Does **not** treat direct-HWX deploy lane as execution — the fuzz worker calls `ANECValidate`/`ANECCompile` only (the `anec` crate's `validate`/`compile` methods). Execution on ANE is `e5rt` lane (PROBE-3 / RUN-3), out of scope.
- ❌ Does **not** modify L-TOOL, L-IR, L-SCHED, L-RUN, L-LINT, L-TEST files
- ❌ Does **not** assume any fact not in source material. Where the fuzzer or spec is silent (e.g., whether h17 *actually* accepts blobfile now), the plan says "measure and record."

---

## 6. Candid Gaps (Source Material Does Not Establish)

1. **Whether `h17` is a valid `TargetArchitecture` string for `ANECValidate`/`ANECCompile` on this machine.**  
   The `ARCHES` array in `anec.rs` lists `h17` (carved from the framework binary), and `anec_probe.rs` shows `ANECUnitValidatorCreate` succeeds for `h17`. But no evidence shows a full `ANECValidate`/`ANECCompile` round-trip on `h17` in this session. The fuzz run will be the first such measurement.

2. **Whether the `FileConstants`/`ExternConstants` dict lane works on h17.**  
   The spec says "schema unprobed." The blobfile_probe family *only* tests embedded `BLOBFILE` — it does not exercise the dict lane. If h17 accepts blobfile, we still won't know if the dict lane works without a separate probe.

3. **Whether `--compile` (i.e., `ANECCompile`) behaves differently from `--validate`-only on h17.**  
   The h16g fuzzer ran with `--compile` and found 0 crashes. The plan uses `--compile` for parity. If compile crashes where validate passes, that's a finding captured in `Class::Crash`.

4. **Whether the 64-byte corpus-style header in `weight_blob` matches what h17's frontend expects.**  
   The header format is inferred from `c64k1.mil` corpus. If h17's parser changed the expected header, blobfile might reject for a *different* reason (header parse error vs "BLOBFILE not supported"). The stderr/stdout capture in each case dir preserves the error message for triage.

---

## 7. Execution Checklist

```bash
# 1. Ensure cargo build is fresh (vendor tree unchanged by TOOL-4 guard)
cargo build --release -p milc

# 2. Run the 500-case fuzz on h17
milc ane fuzz --iters 500 --seed 31337 --arch h17 --compile -o /tmp/probe1_blobfile_h17

# 3. Generate deliverables
cargo build --example probe_h17_report --release
./target/release/examples/probe_h17_report /tmp/probe1_blobfile_h17

# 4. Verify outputs exist
cat docs/spec/ane-frontend-h17.md | head -80
cat /tmp/probe1_blobfile_h17/verdict_matrix_h17.json | jq '.rows[] | select(.family=="blobfile_probe")'
```

---

## 8. Success Criteria

- [ ] `milc ane fuzz` completes 500 iterations on `h17` without driver crash
- [ ] `docs/spec/ane-frontend-h17.md` exists and contains a per-family diff table including `blobfile_probe`
- [ ] `/tmp/probe1_blobfile_h17/verdict_matrix_h17.json` exists, is valid JSON, has 500 rows
- [ ] All `blobfile_probe` cases have preserved artifacts in `cases/` and any findings in `findings/`
- [ ] No edits outside L-PROBE-owned files