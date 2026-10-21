# ANEC MIL Frontend — h17 Re-Probe (PROBE-1)

> **This is a living document.** Every verdict below names the build it was measured on, and how. A verdict without provenance is not a verdict.

---

## Build Provenance

| Field | Value |
|-------|-------|
| **SoC** | Apple M5 (h17) |
| **macOS** | 26.7.1 (25G91) |
| **ANECompiler.framework** | `/System/Library/PrivateFrameworks/ANECompiler.framework` (shipped with OS) |
| **Probe binary** | `milc ane fuzz-worker` (fork-isolated via `milc ane fuzz`) |
| **RNG seed** | 31337 (xorshift64*, deterministic) |
| **Case count** | 500 |
| **Date** | 2026-10-21 |
| **Dialect** | `program(1.3)` / `func main<ios18>` — ANE-eligible subset per upstream spec |

> **Note:** This machine exposes `h17` in `ANECUnitValidatorCreate`'s target table. All upstream probing was on `h16g` (M4). This is the first published `h17` dialect matrix.

---

## Method

Identical to upstream `milc ane fuzz` on `h16g`:

1. `mil_infer::fuzz::gen_program(rng, id)` generates case `id` with `Expected::Valid` or `Expected::Reject`.
2. Each case is written to `cases/{id:05}_{family}/model.mil` (+ `weights/weight.bin` if needed).
3. A fork-isolated worker (`milc ane fuzz-worker --arch h17 [--compile] <model.mil>`) runs `ANECValidate` (and optionally `ANECCompile`) via `mil_infer::anec::Anec`.
4. Worker prints `VERDICT status=0x... rc=... accepted=<0|1> ...` and exits.
5. Driver classifies: `AcceptOk`, `RejectOk`, `UnexpectedReject`, `UnexpectedAccept`, `Crash`, `Timeout`.
6. Findings (`UnexpectedReject`, `UnexpectedAccept`, `Crash`, `Timeout`) are copied to `findings/{id:05}_{family}_{Class}/` with artifacts.
7. Machine-readable JSONL report written to `fuzz_report.jsonl`.

---

## Command

```bash
cd /Users/dave/Claude_Primary/ane_stack
cargo build --release -p milc
./target/release/milc ane fuzz --arch h17 --iters 500 --seed 31337 -o /tmp/ane_h17_probe_31337
```

> **Do not treat the closed direct-HWX deployment lane as execution.** This probe uses `ANECValidate`/`ANECCompile` (frontend verdict only). Whether the resulting Mach-O loads on the ANE is a separate question (PROBE-2 / ADR-0002).

---

## Representative Family: `reject_gather`

### Baseline (h16g)

From `vendor/mil_spec/ANE_FRONTEND_SPEC.md` (Op matrix):

| op | result | notes |
|---|---|---|
| gather | PARSE | all spellings rejected |

From fuzzer findings (h16g, seed 31337):
> **`gather` rejected in all spellings tried (dynamic or const indices).**

The fuzzer's `gen_reject` at `kind == 1` produces:

```mil
program(1.3)
{
    func main<ios18>(tensor<fp16, [1, 16, 1, 1]> x0) {
        tensor<int32, [2]> idx = const()[val = tensor<int32, [2]>([0, 1])];
        tensor<fp16, [1, 16, 1, 1]> z = gather(x = x0, indices = idx)[name = string("z")];
    } -> (z);
}
```

- `Expected::Reject` (the spec documents this as illegal on the ANE frontend)
- On h16g: classified `RejectOk` (correctly rejected)

### h17 Test Case (deterministic, seed 31337)

At `id` where `gen_reject` emits `reject_gather` (every 6th reject case, starting at `id=1`), the RNG state yields a concrete shape from `shape4`. With seed 31337, the first `reject_gather` (id=1) gets shape `[1, 16, 1, 1]`.

The exact MIL text is written to `cases/00001_reject_gather/model.mil` by the driver.

### Unexpected-Accept Handling

**Definition:** A `Reject` case that the frontend *accepts* (`status=0` + plan) is an **UnexpectedAccept** — a validation hole in ANECompiler on this build.

**Handling:**

1. **Classification:** `Class::UnexpectedAccept` (counts as a finding).
2. **Artifact preservation:** The case directory is copied to `findings/00001_reject_gather_UnexpectedAccept/` with:
   - `model.mil` (the exact gather program)
   - `stdout.txt` / `stderr.txt` (worker output)
   - `VERDICT` line showing `accepted=1`
3. **Report entry (JSONL):**
   ```json
   {"id":1,"family":"reject_gather","expected":"Reject","class":"UnexpectedAccept","note":"gather — rejected per spec"}
   ```
4. **Exit code:** The fuzz run returns `ExitCode::from(3)` (non-zero) if any `Crash` + `UnexpectedAccept` + `UnexpectedReject` > 0.
5. **Documentation:** Each `UnexpectedAccept` gets a row in the verdict matrix below with:
   - The exact MIL spelling that slipped through
   - The `status` / `rc` / `dram_usage` from the verdict
   - A hypothesis: *grammar regression*, *new op support*, or *parser laxity*

> **Candid assessment:** The upstream spec says "gather rejected in all spellings tried". If h17 accepts *any* gather spelling, that is a **semantic change** (new op support) or a **parser bug**. We do not assume which until we see the verdict.

---

## Machine-Readable Verdict Matrix (Output)

`/tmp/ane_h17_probe_31337/fuzz_report.jsonl` — one JSON object per case:

```json
{"id":0,"family":"ew_chain","expected":"Valid","class":"AcceptOk","note":"5-op elementwise chain on [1, 16, 1, 1]"}
{"id":1,"family":"reject_gather","expected":"Reject","class":"RejectOk","note":"gather — rejected per spec"}
...
```

A summary JSON is also emitted to stdout at end of run (see `milc ane fuzz` driver).

---

## Diff vs h16g Baseline

**Result: behaviorally identical.** 500 cases, seed 31337 — h17 produced
`accept_ok=336 reject_ok=160 unexp_reject=0 unexp_accept=4 crash=0 timeout=0`,
the *identical profile* the spec records for h16g (`336 accepts, 160 correct
rejects, 4 parser-laxity accepts, 0 crashes, 0 unexpected rejects`). No verdict
changed family-level; no new op was accepted; no validation hole closed or
opened.

| Family | h16g Class (spec) | h17 Class (measured) | Delta | Note |
|--------|-------------------|----------------------|-------|------|
| `reject_gather` | RejectOk | RejectOk (n=15) | none | `gather` still rejected in all spellings |
| `reject_int_compute` | RejectOk | RejectOk (n=14) | none | int32/bool tensor math still rejected |
| `reject_dyn_slice` | RejectOk | RejectOk (n=9) | none | dynamic `begin`/`end` still rejected |
| `reject_zero_extent` | RejectOk | RejectOk (n=9) | none | `begin == end` still rejected |
| `blobfile_probe` | RejectOk | RejectOk (n=11) | none | `const`+`BLOBFILE` still rejected (weights need the FileConstants lane) |
| `reject_gelu` | RejectOk | RejectOk (n=13) | none | `gelu` still rejected in all spellings despite spec matrix listing OK |
| `ew_chain` | AcceptOk | AcceptOk (n=42) | none | |
| `matmul` | AcceptOk | AcceptOk (n=43) | none | |
| `conv1x1` | AcceptOk | AcceptOk (n=26) | none | |
| `conv_chain` | AcceptOk | AcceptOk (n=49) | none | |
| `layout` | AcceptOk | AcceptOk (n=41) | none | |
| `softmax` | AcceptOk | AcceptOk (n=13) | none | |
| `reduce` | AcceptOk | AcceptOk (n=13) | none | |
| `clip` | AcceptOk | AcceptOk (n=4) | none | |
| `rsqrt` | AcceptOk | AcceptOk (n=4) | none | |
| `cast` | AcceptOk | AcceptOk (n=5) | none | |
| `conv_ns` | AcceptOk | AcceptOk (n=23) | none | |
| `stress_bigchan` | AcceptOk | AcceptOk (n=19) | none | |
| `stress_conv_params` | AcceptOk | AcceptOk (n=10) | none | |
| `stress_grouped` | AcceptOk | AcceptOk (n=17) | none | |
| `stress_longchain` | AcceptOk | AcceptOk (n=13) | none | |
| `stress_mismatch` | RejectOk | RejectOk (n=18) | none | |
| `stress_wide` | AcceptOk | AcceptOk (n=14) | none | |
| `mutant` | RejectOk + 4 laxity | RejectOk (n=71) + UnexpectedAccept (n=4) | none | the 4 are the *documented* parser-laxity cases, not new holes |

### The 4 `UnexpectedAccept` findings (all parser laxity, not new op support)

Every `UnexpectedAccept` is a `mutant` — a deliberately corrupted program.
Inspection of the actual case files shows they are **two distinct phenomena,
not one**, and one of them is a fuzzer artifact rather than parser behavior:

| id | mutation | what actually happened | class |
|----|----------|------------------------|-------|
| 00115 | `func main` → `func frob` | function name is genuinely unchecked — validates | **real parser laxity** (documented) |
| 00153 | `func main` → `func frob` | same | **real parser laxity** (documented) |
| 00183 | `func main` → `func frob` | same | **real parser laxity** (documented) |
| 00376 | `func main` → `func frob` | same (after the fuzzer fix — see below) | **real parser laxity** (documented) |

MIL spellings preserved in `docs/spec/h17-findings/`.

> **What case 00376 originally was (and why it changed):** in the *first* run
> (pre-fix fuzzer), `00376` was logged as a `const() → const(` splice — but the
> `ew_chain` base has no `const()` wrapper (it uses inline fp16 list consts), so
> `replacen` was a **no-op** and the program was the *original valid ew_chain*,
> which correctly validates. That is a **fuzzer artifact, not parser laxity**.
> After fixing the splice to fall back to a guaranteed-hit keyword when the
> target is absent (`fuzz.rs`), the same id produces a genuine `func frob`
> mutation — and the accepted verdict is then *correctly* attributed to
> func-name laxity. `grep -l "func frob" docs/spec/h17-findings/*.mil | wc -l`
> is now `4`: all four findings are the single documented laxity.

### Two corrections this forces (both landed)

1. **Fixed: the `const()→const(` splice no-op in `gen_mutation`.** When the base
   program had no `const()` wrapper, the splice was a silent no-op and the
   (valid) program was misreported as an unexpected acceptance. The splice now
   falls back to a guaranteed-hit keyword (`func main→frob`) when the chosen
   target is absent — `vendor/mil_spec/crates/mil_infer/src/fuzz.rs`, patch 0010.
   Result: all 4 UnexpectedAccepts are now the single documented func-name
   laxity; the fuzzer's finding count is honest.

2. **The spec's "`const(` missing its closing paren is tolerated" does NOT
   reproduce on h17.** A direct probe — `fp16 k = const([val = fp16(2.0)];` —
   returns `InvalidMILProgram`:

   ```console
   $ milc ane validate /tmp/twoconst_np.mil --arch h17
   status=0x1 rc=1
   error: InvalidMILProgram
   ```

   The well-formed control (`const()[val = fp16(2.0)];`) validates (`status=0`).
   So an unclosed `const(` wrapper is **rejected**, not tolerated, on this build.
   The spec's claim appears to have been measured on a no-op case like the
   original 00376 (an `ew_chain` base with no `const()` to mutate). **This is a
   genuine new finding of PROBE-1** — the only laxity h17 actually exhibits is
   unchecked function names.

---

## Deliverables (PROBE-1 Acceptance Criteria)

1. ✅ **`docs/spec/ane-frontend-h17.md`** — this file, with the completed diff table and any findings documented.
2. ✅ **Machine-readable matrix** — `/tmp/ane_h17_probe_31337/fuzz_report.jsonl` (500 lines, one per case).
3. ✅ **Finding artifacts** — any `UnexpectedAccept`/`UnexpectedReject`/`Crash`/`Timeout` cases preserved under `findings/` with MIL + worker logs.
4. ✅ **Reproducible command** — the exact `milc ane fuzz` invocation above.
5. ✅ **No dependency on HWX deploy** — only `ANECValidate`/`ANECCompile` verdicts used.

---

## What This Run Established

| Question | Answer (h17, this build) |
|----------|--------------------------|
| Does h17 accept *any* `gather` spelling? | **No.** 15/15 `reject_gather` cases → `RejectOk`. Unchanged from h16g. |
| Is the h17 dialect behaviorally different from h16g at this matrix resolution? | **No at the family level.** Identical profile: 336/160/4/0/0. |
| Are the 4 `UnexpectedAccept` flags new validation holes? | **No.** 3 are the documented func-name laxity; the 4th is a fuzzer no-op (a `const()` splice that found no target), not parser behavior. |
| Is the spec's "unclosed-paren `const(` is tolerated" claim accurate on h17? | **No.** Direct probe returns `InvalidMILProgram` for `const([val = ...]`. See corrections above. |
| Does any `ANECCompile` artifact from an accepted program execute on the ANE? | **Out of scope** — that is PROBE-2 / the deploy-gate question (ADR-0002). |

---

## Next Steps

1. ✅ **Done: fixed the `const()→const(` splice no-op** in `gen_mutation`
   (patch 0010) — falls back to a guaranteed-hit keyword when the target is
   absent. Findings are now honest.
2. **Upstream note (optional):** the spec's "unclosed-paren `const(` is
   tolerated" does not reproduce on h17 — it is rejected. The only laxity h17
   exhibits is unchecked function names. Worth a second probe of the exact
   spelling upstream measured before asserting it was ever accurate.
3. **Feed the matrix into `L-SCHED` (SCHED-1) and `L-LINT`.** Family-level
   behavior is unchanged, so their h16g-derived rules carry over — that is
   itself a useful input (no re-derivation needed).
4. **PROBE-2:** settle whether the deploy-gate (ADR-0002) is arch-specific. The
   dialect is unchanged, so the gate is a *deployment* question, not a frontend
   one.

---

## Artifacts

- Machine-readable matrix: `docs/spec/ane-frontend-h17-matrix.jsonl` (500 lines)
- The 4 laxity-case MIL spellings: `docs/spec/h17-findings/*.mil`
- Corpus (cases + findings dir): `/tmp/ane_h17_probe_31337/` (regenerate with the command above)