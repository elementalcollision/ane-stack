# PATCHES.md — our diff against upstream mil_spec

Upstream: `mil_spec@20f097fb34969cd577342a4d7996fbf5464998c8` (v0.4.2)

Status: `open` (carried) · `proposed` (PR sent) · `upstreamed` (droppable) · `wontfix`

| # | Patch | Fixes | Status |
|---|---|---|---|
| 0001 | `ir-write-state-shape` | `mil_spec::ir` validated dtype only for `write_state`; a value whose shape ≠ the state's passed validation and produced a package `coremlc` rejected | open |
| 0002 | `ir-stateful-fixtures` | `tests/ir.rs::stateful_roundtrip` **encoded bug 0001 as correct behaviour**; corrected to a legal whole-state write + new regression test | open |
| 0003 | `mil-verify-stateful-fixture` | conformance case `stateful-kv` encoded the same bug; corrected | open |
| 0004 | `milc-run-shard-dispatch` | `milc run` sent **every** `.mlpackage` to the shard loader (case-insensitive `manifest.json` vs `Manifest.json`), so `milc run <pkg>` never worked on a plain package | open |
| 0005 | `milc-run-mlmodelc` | `milc run <x.mlmodelc>` failed with `model.mlmodel: No such file` — compiled artifacts carry the spec as `model.mil` text, not protobuf. Detect the `.mlmodelc` and parse its `func main` signature instead | open |
| 0006 | `milc-json-diagnostics` | no machine-readable failures — agents grepped stderr. Top-level `--json` / `MILC_JSON=1` emits a `{ok, command, ...}` envelope with `{stage, code, message, path}` errors for `check`/`run`/`plan` | open |
| 0007 | `ir-slice-update` | `mil_spec::ir` had no `slice_update`; an incremental KV-cache write was inexpressible. Adds `Block::slice_update` + IR form with full validation (region-shape rule, rank/bounds checks). Unblocks `RUN-2` (stateful e5rt). | open |
| 0008 | `ir-state-contract` | `mil_spec::ir` had no state-level contract checks. Adds per-state read/slice_update/write counters validated in `finish()`: one read_state per state, write_state after each slice_update (counts match). Mirrors ANE_FRONTEND_SPEC.md's state contract at the IR level. | open |
| 0009 | `test-hw-gate` | hardware-gated tests early-`return`ed on missing hardware, so cargo reported them PASSED with no work done (27 sites across 10 files). Routes every gate through `mil_compile::hw_gate`: loud `SKIP:` line by default, hard failure under `MIL_REQUIRE_HW=1`, plus `count_hw_skips` for a CI summary | open |
| 0010 | `ir-for-loop` | `mil_spec::ir` was straight-line SSA with no iteration construct. Adds bounded `for i in a..b {` fully unrolled at compile time: loop var substituted per iteration, LHS names suffixed with `_<iter>`. Matches the ANE's no-control-flow capability. | open |
| 0011 | `fuzz-noop-splice` | `gen_mutation`'s `const()→const(` splice silently no-ops when the base has no `const()` wrapper (ew_chain), producing a valid program misreported as an UnexpectedAccept. Falls back to a guaranteed-hit keyword. Found by PROBE-1 | open |

All eleven patches apply cleanly to pristine upstream (`patch -p1 --dry-run`
verified) and are applied in order by `scripts/apply-patches.sh`.

**Note on 0008:** the original file used repo-root-relative paths
(`a/vendor/mil_spec/...`), which `apply-patches.sh` (vendor-relative, `-p1`)
could not apply. Relabelled to the vendor-relative convention; content
unchanged, verified byte-identical to committed HEAD.

**Note on 0010:** same header-only defect as 0007 (no diff hunks). Body
reconstructed from the committed tree, byte-identical to HEAD; content is
L-IR's IR-4 work, unchanged.

## Evidence

- 0001/0002/0003: `docs/evidence/0001-write-state-shape.md`
- 0004: `docs/evidence/0004-milc-run-dispatch.md`
- 0005: `docs/evidence/0005-milc-run-mlmodelc.md`
- 0006: `docs/evidence/0006-milc-json-diagnostics.md`
- 0007: `docs/evidence/0007-ir-slice-update.md`
- 0008: `docs/evidence/0008-ir-state-contract.md` (L-IR)
- 0009: `docs/evidence/0009-test-hw-gate.md`
- 0010: `docs/evidence/0010-ir-for-loop.md` (L-IR)
- 0011: `docs/spec/ane-frontend-h17.md` (PROBE-1 findings)
- 0009: `docs/evidence/0009-test-hw-gate.md`
- 0010: `docs/evidence/0010-ir-for-loop.md`

## Test delta

Upstream baseline for `-p mil_spec -p mil_lint -p mil_passes -p mil_verify`:
all green. After patches: **all green, +2 tests** (`write_state_shape_mismatch_rejected`,
`run_compiled_mlmodelc_directly`). `run_cli.rs` additionally carries the TOOL-3
JSON-envelope assertions (4 tests).
The two fixture corrections change *what* two existing tests assert (they now
assert a legal program) — deliberately, because the previous assertion was the bug.

## Not fixing (upstream debt we inherit)

- The HWX deploy lane is closed at the OS level (Apple's own artifacts fail too).
  See `docs/adr/0002-deploy-lane-closed.md`. Not a code bug.
- Perf-counter instrumentation needs a compile-time switch inside Apple's compiler.
- `units_e2e` timing assertions are `#[ignore]`d and suspect (see `patches/0005` note).
