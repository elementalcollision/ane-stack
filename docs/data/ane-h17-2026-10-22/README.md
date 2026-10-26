# ANE resource budgets on h17 — datapoints (2026-10-22)

Raw and structured datapoints behind `docs/spec/ane-port-limits-h17.md` (the
writeup), `docs/spec/ane-port-limits-h17.html` (the visual companion) and
`docs/spec/ane-port-limits-h17.spec` (the executable assertions). Use this
directory to cite, plot or re-analyse the measurements. Use the spec to
re-derive them.

| | |
|---|---|
| Host | Apple M5 Max (Mac17,7, `h17`), macOS 26.7.1 (25G241) |
| Compiler | `zin_ane_compiler v9.510.0` (HWX `LC_IDENT`); coremlc 3600.25.1 |
| h16g (M4) rows | **cross-compiled on the M5 host**; nothing was run on M4 silicon |
| Tool | `vendor/mil_spec/target/release/milc ane validate \| compile \| run` on generated `program(1.3)` MIL |
| Collected | 2026-10-22, by Haiku 5.5 and Sonnet 5.5 runner agents orchestrated by Opus 5.5; decisive points re-run by the orchestrator |

## How much to trust each file

1. **`spec_datapoints.json` is the authoritative list.** It holds every
   assertion the spec makes (124 probes, 274 assertions), exported by
   `scripts/spec_to_json.py`. CI fails if it drifts from the spec. Each entry is
   re-run on hardware by
   `./scripts/evidence-check.sh --require-all docs/spec/ane-port-limits-h17.spec`.
2. **`measurements/` holds the runners' raw logs.** They are the evidence for the
   laws, including many points the spec does not assert. Rows were recorded as
   observed: they include failed or abandoned probes (`err`, `OTHER:…` classes),
   and some come from generators that were not committed. Treat any single row as
   a datapoint, not a law. The laws, with their domain and confidence, are in the
   writeup.
3. **`laws/` and `reviews/` hold model-written analysis.** That covers law
   statements, review findings, skeptic verdicts and claim classifications. They
   are useful as an audit trail, but where they disagree with the writeup, the
   writeup wins: it records which findings were refuted or narrowed.

   These round-one laws in `laws/remeasure_round1.json` were later **superseded**:

   | round-one law | replaced by |
   |---|---|
   | `state-fp16-only` | the state-dtype law; see `measurements/state_dtype_runs.jsonl` |
   | `STATE-RUN-SIZE-256` and `L-IO-STATE-SIZE-EXEC` | the 16 KiB page rule |
   | "a program with no plain input is rejected" | a flat-literal generator artifact; with `fill` or a nested literal, 54 states compile and run |
   | "dim1 = 1 emits no copy records" | dim1 = 1 emits `0x926x` records |
   | the computed-source part of `R9344-*` | tentative only |

## Files

### `spec_datapoints.json`
`{source, source_sha256, probes, assertions, requires[], items[]}`. Each item is
`{index, section: {n, title} | null, comment, run, wants: [{kind, value}]}`.
- `run` is the exact shell command, run from the repo root.
- `wants` are the expectations. An item passes only if every want holds.
  `want_rc` is the exit-code check, and a run's success is never judged from text
  alone.
- Item 0 is an informational provenance probe (`section: null`).

Sections follow the
writeup: 1 execution cap, 2 frontend cap, 3 states cost ports, 4 BAR pool,
5 binding records and trailers, 6 copy records, 7 state execution, 8 h16g
vs h17.

### `measurements/io_runs.jsonl` (3,908 rows)
The io-budget runner's call log: the runner's own 3,886 calls, plus 22 rows tagged
`s6` that were appended afterwards (states as ports).
- Fields: `op` (`run` / `validate` / `compile`), `mil` (generated file name; the
  numbers in it are the generator arguments), `rc` (milc exit code), `cls`,
  `tag` (sweep batch), `t` (unix time), `arch`.
- `cls` values:

  | value | meaning |
  |---|---|
  | `PASS` | run ok |
  | `EXEC` | execute_sync `status=0x2` |
  | `OK` | validate/compile ok |
  | `FE:MaxLiveInLiveOutExceeded` | frontend cap |
  | `OTHER:…` | anything else |

- Generators: `gen_live_ports_I_O` = `scripts/gen_live_ports.py I O` (all inputs
  live); `gen_mix_ports_I_O` = dead inputs beyond O. Other prefixes are runner
  variants (dead-op inputs, widened ports, states as ports) described in
  `laws/remeasure_round1.json`, unit `io-budgets`. `gen_dead_ports_*` is
  `generators/gen_dead_ports.py`, and `lp_*` are widened `gen_live_ports.py` ports.
- Five `OTHER:` labels were truncated error strings that ended in a path; the
  scrub replaced that path fragment with `<wd>`.

### `measurements/io_heldout.tsv`
Round-two held-out io checks. The 8 columns are tab-separated, without a header:

| column | content |
|---|---|
| 1 | label |
| 2 | op |
| 3 | arch |
| 4 | `pred=…` (prediction made before running) |
| 5 | `obs=…` |
| 6 | `MATCH` / `**CONTRADICTED**` |
| 7 | raw decisive output (two runs separated by `\|`) |
| 8 | free-text note (often empty) |

The predictions were made against the *first draft* of the rewritten writeup. All
11 `**CONTRADICTED**` rows are reflected in the current writeup:
- dead-read and write-only states don't compile on the run path
- unreferenced states are free at execution
- a returned input is not an execution port
- returned inputs are counted at the frontend
- stateful zero-output programs validate and compile
- one fp32-port program fails to run (fp32 ports are listed as unmeasured)
- `run_mix_200_100` (dead inputs pruned): 100 live inputs + 100 outputs = 200
  fails at execution, as §2 says for 128–255 live ports

### `measurements/state_compiles.jsonl` (2,281 rows)
The state-cap runner's per-program census: 2,163 compiles, 92 validates and 26 runs.
Rows are runs of a program, not distinct programs.
- Identity: `name`, `action` (`compile` / `validate` / `run`), `arch`, `gen`, `rc`,
  `status` (ANECCompile status; absent on `run` rows), `err`.
- `gen` generators:

  | `gen` value | where it lives |
  |---|---|
  | `scripts/gen_states.py` | `scripts/` in this repo |
  | `scripts/gen_states_shape.py` (1,471 rows) | retired; preserved as `generators/gen_states_shape.py`. It equals `scripts/gen_states_nd.py N d0 d1 1 1 in out add`, except at in = 0, where the retired script emits a flat literal that the frontend rejects |
  | `<wd>/re/state/gen_{g,seq,kern,mixshape,conv,dt}.py` | `generators/` |
- Compile metrics: `dram` (ModelMaxDramUsage), `file` (macho bytes), `cpusub`
  (Mach-O cpusubtype: 9 for h17, 7 for h16g).
- Layout: `nsegs` (LC_SEGMENT_64), `n_fvmlib`, `n_data` and `n_const` (section
  counts), the `seg_*` segment details, and `n_lc_thread` / `n_lc40`
  (load-command counts).
- Record counts: one key per tag (`9344`, `934a`, `9442`, `9361`, `9365`, …), from
  a raw u16 scan of `__text`.
- Run results: `step0`, `tail`.

### `measurements/bar_heldout.jsonl` (342 rows)
Round-two BAR-pool held-out checks. 13 rows are failed generator invocations, which
carry only `label` and `err`. Generator paths `<wd>/rv/bar/gen_lut.py` are
`generators/gen_lut.py`.
- `batch` = the source run file.
- Fields: `label`, `arch`, `gen`, `compile_rc` / `compile_ok`, `bar_fail` (output
  contained `unable to allocate free BAR`), `layout` (`hwx_layout.py` line),
  `slots` (`decode_slot_ordinals.py` line), the `0x9344` / `0x934a` / `0x9442`
  counts, `run_rc` / `run_pass`, `pred9344` and `pred_fvmlib` (predictions),
  `compile_tail` / `run_tail` (last output lines), `err`, and `note`.
- The `c1_in*_out*_…` rows of batch `run1` are the 8-cell matrix (plain input,
  plain output, updates exposed) behind `N_max = 55 − [any output] − [any plain
  input]`.

### `measurements/copy_record_sweep.json` (564 keys)
- Key `"dim0,dim1"`. Each entry is one state `[dim0,dim1,1,1]`, with an add-chain
  update source, 1 input and 1 output, on h17.
- Value: `[tag, hex]`, the first copy-record tag found and 0x90 bytes from it;
  `["FAIL", message]` if the compile failed. `["none"]` means no tag from the
  **0x93xx** set was found. The six dim1 = 1 keys are `none` only because their
  records are `0x926x`, which this sweep did not scan (the spec asserts them).
- Open item: `"1000,4096"` (an 8 MB state) reads 500 in the dim0 field. The
  stride and other words still hold there.
- dim0 ∈ {2,3,4,8,64,1000}; dim1 is 1..80 plus selected values up to 4096.

### `measurements/copy_form_grid.json` (320 keys)
- Key `"N,in,out"`, for N states of `[7,11,1,1]` with an add-chain source, on h17.
- Value: the SHORT (`S`) / LONG (`L`) layout of each state-out record, in file
  order. It is the data behind "no closed form for computed sources".

### `measurements/trailer_census_h17.json`, `trailer_census_h16g.json`
- One row per point of the ancillary grid: 126 points, of which 123 compiled. The
  3 `gh` rows with a `fail` field were rejected.
- `n<tag>`: raw u16 counts in `__text`. `t<tag>`: members of parsed block
  trailers.
- `nblocks`, `text` (bytes), section counts, `file`.
- `kind`/`args` give the generator: `gs` = `gen_states.py (N, in, out)`, `nu` = its
  noupd variant, `gh` = add-chain states `[4,4]` (`gen_states_nd.py N 4 4 1 1 in out`).
- 45 + 36 + 45 points.
- Expect `n<tag>` ≠ `t<tag>` for `0x934a` and `0x1341` in `gh` rows with in ≥ 5. A
  multi-input add chain emits records that the trailer parser does not attribute
  to a trailer. This is open (see the writeup, §5).

### `measurements/page_rule_fuzz.json`
Round-two random-shape checks of the state-execution page rule:
`batches.<name>[] = {shape, pred, obs[2], hit, flip, tail}`.
- 320 shapes, each run twice (640 runs). Recomputing the rule from each shape
  matches both observations in 320/320.
- `predictions` holds the copy runner's 18 decoder predictions (tag, stride,
  state-out, reads), which are not scored here.

### `measurements/state_dtype_runs.jsonl` (44 rows)
Re-measured by the orchestrator with the repo's `scripts/gen_state_dtype.py`; every
case was run twice.
- Fields: `dtype`, `states`, `plain_input`, `rep`, `gen`, `compile_rc`, `compile`
  (decisive line), `run_rc`, `run`.
- fp16, int16, int8, uint8 and bool: 53 states compile and run and 54 fail
  (`free BAR`); without a plain input, 54 run and 55 fail.
- fp32 and int32 states are rejected at N = 1.

### `generators/`
Runner-local generators that produced rows above but are not in `scripts/`:
- `gen_states_shape.py`, retired from `scripts/`
- `gen_g.py`, `gen_seq.py`, `gen_kern.py`, `gen_mixshape.py`, `gen_conv.py` and
  `gen_dt.py`, used by the state-cap runner (`gen_dt.py` is a superseded dtype
  design)
- `gen_dead_ports.py` (io runner)
- `gen_lut.py` (BAR held-out runner)
- `gen_dtype_v2.py` (round-two dtype)

They are standalone (stdlib only) and reproduce their MIL byte for byte. Run them
from the repo root like the scripts in `scripts/`.

### `laws/remeasure_round1.json`
The four hardware runners and two audit runners of the re-measurement. Each has
`laws[] {id, statement, domain, confidence, replaces_old_claim, measurements,
counterexamples_checked}`, plus `open_questions` and `notes`.

### `reviews/`
| file | contents |
|---|---|
| `review_round0_findings.json` | the original handoff review: 9 runners, 131 raw findings, with claims checked |
| `review_round0_skeptic_votes.json` | 2 independent skeptic verdicts per voted finding (34 ids); C9–C13, C15 and C21 were the hardware findings, which the orchestrator re-ran on hardware instead |
| `reevaluation_round2.json` | held-out and audit runners on the first rewrite, plus skeptic votes (74 of 75 findings voted; one nit was not); this is where the nine second-pass errors were caught |
| `ori_page_claims.json` | all 91 claims of the old `ori` page v1–v3, classified, with the 8 open ones measured |
| `companion_page_final_pass.json` | the final cross-check of the visual companion (150 claims) and the hardware breaker (479 measurements) |

## Scrubbing

Every string was rewritten before commit:

| original | replaced with |
|---|---|
| session scratch paths | `<wd>` |
| repository paths | `<repo>` |
| the home directory | `~` |
| session and `ori` paths | `<session>`, `<ori-store>` |
| tailnet addresses | `<tailnet-ip>` |
| a host name | `<macos27-host>` |
| the remote login name | `<user>` |
| email addresses | `<email>` |

Also replaced: `<home>` (other home-directory paths) and `<wd>` (uppercase
`<WD>` variants), and "a local tool on PATH" for one tool path. Kept as-is:
- the owner's name: "dave" as the lane owner, and the git author name, which are
  already public in `docs/lanes/OWNERSHIP.md` and the commit metadata
- the fixed `/tmp/pl_*` names that the spec's own commands use
- the upstream author handle `savageAZfck`

No measurement value was changed; the only label change is noted under
`io_runs.jsonl`. Generated MIL files and compiled `.macho` files are not included.
The generators in `scripts/` and `generators/` reproduce them byte for byte.

## Re-derive

```sh
cd vendor/mil_spec && cargo build --release -p milc && cd ../..
./scripts/evidence-check.sh --require-all docs/spec/ane-port-limits-h17.spec
python3 scripts/spec_to_json.py --check docs/data/ane-h17-2026-10-22/spec_datapoints.json
```
