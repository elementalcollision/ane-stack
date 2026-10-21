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

**Note on 0007:** the original patch file was header-only (no `---`/`+++`/`@@`
hunks), so `apply-patches.sh --check` and CI failed with "Only garbage was
found in the patch input". The patch body was reconstructed from the committed
tree (byte-identical to it); content is L-IR's, unchanged.

All seven patches apply cleanly to pristine upstream (`patch -p1 --dry-run`
verified) and are applied in order by `scripts/apply-patches.sh`.

## Evidence

- 0001/0002/0003: `docs/evidence/0001-write-state-shape.md`
- 0004: `docs/evidence/0004-milc-run-dispatch.md`
- 0005: `docs/evidence/0005-milc-run-mlmodelc.md`
- 0006: `docs/evidence/0006-milc-json-diagnostics.md`
- 0007: `docs/evidence/0007-ir-slice-update.md`

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
