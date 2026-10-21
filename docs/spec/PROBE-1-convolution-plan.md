# PROBE-1: Convolution Family — h17 Dialect Re-probe Implementation Plan

**Owner:** L-PROBE  
**Status:** Planning  
**Scope:** Re-run the convolution fuzzer matrix against `h17` (M5/ANE17), diff against the `h16g` baseline, produce both `docs/spec/ane-frontend-h17.md` and a machine-readable verdict matrix.

---

## 1. Why this family

The fuzzer generates several convolution sub-families that exercise distinct frontend paths:

| Family | What it probes | Distinguishing dimensions |
|--------|----------------|---------------------------|
| `conv1x1` | Square 1×1 kernels, cin=cout, inline weights | Baseline acceptance |
| `conv_ns` | Non-square cin≠cout 1×1 kernels | Channel-change acceptance |
| `conv_chain` | Two 1×1 convs in sequence | Multi-op interaction, weight reuse |
| `stress_conv_params` | Aggressive stride/dilation/pad (valid) | Spatial transform semantics |
| `stress_grouped` | groups > 1 (depthwise-ish) | Grouped convolution support |
| `stress_mismatch` | cin vs weight cin mismatch | Semantic rejection (must reject cleanly) |

These 6 families cover the full contract surface the ANE frontend exposes for `conv`.

---

## 2. Files L-PROBE owns / may edit

| File | Role |
|------|------|
| `vendor/mil_spec/crates/mil_infer/src/fuzz.rs` | Generator — add targeted convolution sampling, keep seed stable |
| `vendor/mil_spec/crates/milc/src/main.rs` | Driver — already accepts `--arch h17`, `--seed`, `--iters` |
| `docs/spec/ane-frontend-h17.md` | **Output** — human-readable diff document (to create) |
| `docs/spec/ane-frontend-h17.jsonl` | **Output** — machine-readable verdict matrix (to create) |

**No other files.** The existing `milc ane fuzz` / `milc ane fuzz-worker` workflow is the harness.

---

## 3. Reproducible h17 command

```bash
# From repo root (where vendor/mil_spec is the crate root)
cd vendor/mil_spec

# 500 cases, seed 31337, h17 target, validate + compile
cargo run --bin milc -- ane fuzz \
  --arch h17 \
  --seed 31337 \
  --iters 500 \
  --compile \
  -o /tmp/milc_fuzz_h17_conv
```

This invokes the **exact** driver in `main.rs:cmd_ane` → `mode == "fuzz"` path, which:
- Creates `cases/` and `findings/` under the output dir
- Fork-isolates each case via `fuzz-worker` (30s timeout, crash → corpus artifact)
- Emits `fuzz_report.jsonl` with one line per case: `{id, family, expected, class, note}`
- Prints a summary table of `accept_ok / reject_ok / unexp_reject / unexp_accept / crash / timeout`

---

## 4. Selecting convolution cases from the 500

The fuzzer's `gen_program` cycles families deterministically from the seed. With seed 31337 and 500 iterations, the convolution families appear at predictable indices (determined by the `match id % 6` in `gen_program` and the 25% stress probability).

**Do not hand-filter.** Instead, post-process the JSONL report:

```bash
# Extract only convolution families
jq 'select(.family | startswith("conv") or startswith("stress_conv") or startswith("stress_grouped") or startswith("stress_mismatch"))' \
  /tmp/milc_fuzz_h17_conv/fuzz_report.jsonl \
  > /tmp/conv_h17.jsonl
```

This yields the exact subset without modifying the generator.

---

## 5. Comparison against h16g baseline

The h16g baseline is already documented in `vendor/mil_spec/ANE_FRONTEND_SPEC.md` (the "Op matrix" and "Fuzzer findings" sections). Key assertions to verify on h17:

| Probe | h16g verdict | Question for h17 |
|-------|--------------|------------------|
| `conv1x1` (inline weights, valid pad, stride=1) | OK | Still OK? |
| `conv_ns` (cin≠cout) | OK | Still OK? |
| `conv_chain` (2× conv) | OK | Still OK? |
| `stress_conv_params` (stride=2, dil=2, pad>0) | OK | Still OK? |
| `stress_grouped` (groups=2,4) | OK | Still OK? |
| `stress_mismatch` (cin≠weight cin) | Reject | Still Reject (cleanly)? |
| `blobfile_probe` (conv with BLOBFILE const) | Reject | Still Reject? |
| `gelu` (often appears fused in conv chains) | Reject | Still Reject? |

The diff document will record **any verdict that changed** (including new crashes or timeouts).

---

## 6. Artifacts to produce

### 6.1 `docs/spec/ane-frontend-h17.md`

Structure:

```markdown
# ANE MIL Frontend — Empirical Spec (h17 / M5)

Measured on: macOS 26.7.1, Apple M5 Max, ANECompiler.framework build XXXX
Probe command: `milc ane fuzz --arch h17 --seed 31337 --iters 500 --compile`
Date: YYYY-MM-DD

## Convolution family diff vs h16g baseline

| Family | h16g | h17 | Δ | Note |
|--------|------|-----|---|------|
| conv1x1 | AcceptOk | AcceptOk | — | 42 cases |
| conv_ns | AcceptOk | AcceptOk | — | 18 cases |
| conv_chain | AcceptOk | AcceptOk | — | 12 cases |
| stress_conv_params | AcceptOk | AcceptOk | — | 15 cases |
| stress_grouped | AcceptOk | AcceptOk | — | 8 cases |
| stress_mismatch | RejectOk | RejectOk | — | 6 cases (clean semantic reject) |
| blobfile_probe | RejectOk | RejectOk | — | 4 cases |
| ... | | | | |

## Changed verdicts (if any)

> **None** — all convolution families behave identically to h16g.

OR

> ### `stress_grouped` (groups=4)
> - h16g: AcceptOk
> - h17: UnexpectedReject (rc=22, "grouped conv not supported for groups > 2")
> - 2/8 cases affected
> - Finding artifacts in `findings/0042_stress_grouped_UnexpectedReject/`

## New crashes / timeouts (if any)

> **None** — 0 crashes, 0 timeouts across all 500 cases.

## Full h17 op matrix (convolution subset)

| op / variant | h17 verdict | note |
|--------------|-------------|------|
| conv (1x1, inline weights, valid, s=1, d=1, g=1) | OK | |
| conv (1x1, cin!=cout) | OK | |
| conv (stride=2) | OK | |
| conv (dilation=2) | OK | |
| conv (pad=1, valid) | OK | |
| conv (pad=2, valid) | OK | |
| conv (groups=2) | OK | |
| conv (groups=4) | OK | |
| conv (cin vs weight cin mismatch) | PARSE | clean semantic reject |
| conv (BLOBFILE weights) | PARSE | rejected; needs FileConstants lane |
```

### 6.2 `docs/spec/ane-frontend-h17.jsonl` (machine-readable)

One line per convolution case from the 500-case run:

```jsonl
{"id": 2, "family": "conv1x1", "expected": "Valid", "class": "AcceptOk", "note": "conv1x1 8->8 w=1 inline", "arch": "h17", "seed": 31337}
{"id": 8, "family": "conv_ns", "expected": "Valid", "class": "AcceptOk", "note": "conv1x1 4->16 w=2 inline", "arch": "h17", "seed": 31337}
{"id": 14, "family": "conv_chain", "expected": "Valid", "class": "AcceptOk", "note": "2-conv chain c0=8 w=1 inline", "arch": "h17", "seed": 31337}
{"id": 31, "family": "stress_conv_params", "expected": "Valid", "class": "AcceptOk", "note": "conv stride=2 dil=1 pad=1 w=4->2", "arch": "h17", "seed": 31337}
{"id": 47, "family": "stress_grouped", "expected": "Valid", "class": "AcceptOk", "note": "grouped conv groups=2 8->8", "arch": "h17", "seed": 31337}
{"id": 89, "family": "stress_mismatch", "expected": "Reject", "class": "RejectOk", "note": "conv cin=4 vs weight cin=8", "arch": "h17", "seed": 31337}
...
```

Schema: `{id, family, expected, class, note, arch, seed}` — same as the fuzz report, filtered and annotated with `arch` and `seed` for traceability.

---

## 7. Preservation of per-case verdicts and findings

The existing driver **already does this**:

- Every case → `cases/NNNNN_family/` with `model.mil`, optional `weights/weight.bin`, `stdout.txt`, `stderr.txt`
- Findings (any `class != AcceptOk && class != RejectOk`) → `findings/NNNNN_family_Class/` with same artifacts + `stderr.txt`
- Report line written to `fuzz_report.jsonl` immediately after classification

**No changes needed.** The plan simply runs the existing workflow and post-processes its outputs.

---

## 8. What we do NOT do (per ADR-0002)

- ❌ Do not attempt to deploy any compiled artifact (`.macho`, `.hwx`) via `_ANEClient loadModel`
- ❌ Do not treat the HWX emitter as an execution path
- ✅ `ANECValidate` / `ANECCompile` → verdict only (status, rc, errors, `ModelMaxDramUsage`, artifact path)
- ✅ The `--compile` flag in the command above exercises `ANECCompile` (not just `Validate`) — this is the compiler probe, not deployment

---

## 9. Gaps / unknowns (candor)

| Gap | Impact | Mitigation |
|-----|--------|------------|
| The exact `ANECompiler.framework` build number on this M5 is not yet recorded | Provenance for the h17 spec | Capture `md5 /System/Library/PrivateFrameworks/ANECompiler.framework/ANECompiler` in the run log |
| `stress_conv_params` computes output spatial dim with `ow = (w + 2*pad - dil*(1-1) - 1)/stride + 1` — assumes kernel=1 | If kernel>1 ever generated, formula is wrong | Current generator only emits 1×1 kernels for conv; documented in `note` |
| `blobfile_probe` uses `conv_prelude` (valid pad, stride=1, dilation=1, groups=1) — may not test all BLOBFILE spellings | Limited coverage of weight-loading paths | Acceptable; the probe's purpose is "does *any* BLOBFILE spelling work now?" |
| The fuzzer's `shape4()` only produces a fixed candidate set — may miss edge shapes (e.g., 3×3 kernels, large spatial) | Coverage gap | Documented limitation; `stress_wide` and `stress_bigchan` cover some extremes but not conv-specific |

---

## 10. Acceptance criteria

1. ✅ Command in §3 runs to completion (exit 0 or 3 — 3 means findings exist, which is valid)
2. ✅ `docs/spec/ane-frontend-h17.md` exists with the structure in §6.1
3. ✅ `docs/spec/ane-frontend-h17.jsonl` exists with schema in §6.2
4. ✅ Both artifacts reference the exact command, seed, arch, and date
5. ✅ No manual case selection — convolution subset derived by post-filtering the JSONL
6. ✅ Finding artifacts preserved under the run's `findings/` directory
7. ✅ Diff against h16g baseline is explicit (table with Δ column)

---

## 11. Estimated effort

- **Run time:** ~15–20 min (500 cases × ~2–3s each, fork overhead)
- **Post-processing:** ~5 min (jq filtering, markdown generation)
- **Total:** S (small) — the harness exists; this is a targeted invocation + documentation