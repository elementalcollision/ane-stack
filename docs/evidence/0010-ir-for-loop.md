# Evidence — patch 0010: bounded `for` loops fully unrolled (work item `IR-4`)

Lane: `L-IR` (claimed in `docs/lanes/OWNERSHIP.md`).
Work item: `IR-4` — `while`/loop and indexed control flow.
Patch: `patches/0010-ir-for-loop.patch`.

## What was wrong

`mil_spec::ir` was straight-line SSA with no iteration construct. Any real
decode step needs iteration, but the ANE has no control flow — so loops
belong at compile time.

## Fix

Purely additive, in L-IR-owned files only (`src/ir.rs`, `tests/ir.rs`):

1. `vendor/mil_spec/src/ir.rs` — `unroll_loops()` pre-pass runs before
   compilation. It detects `for i in a..b { ... }` (brace-depth body
   collection handles nesting), then for each iteration:
   - substitutes the loop var `i` with its concrete value,
   - suffixes every LHS-defined name with `_<iter>` to avoid collisions.
   
   Bounds must be integer literals; empty ranges are rejected; only bounded,
   fully-unrolled loops — no real control flow, matching the ANE's
   capabilities.

2. `vendor/mil_spec/tests/ir.rs` — 4 new tests:
   - `for_loop_unrolls` — N iterations emit N mul ops, output names last iter.
   - `for_loop_var_substituted` — loop var const substituted per iteration.
   - `for_loop_empty_range_rejected` — empty range errors.
   - `for_loop_output_refs_last_iteration` — output can reference last iter.

## Test delta

`cargo test --test ir` → 29 passed, 0 failed (was 25 after IR-3).
`cargo test --lib` → 12 passed.
`cargo test --test ane_lower` → 2 passed (unchanged).

## Confidence

- Unrolling is a pure source transform before the existing validated
  compile path, so all IR-1/IR-2/IR-3 checks still apply per iteration.
- Name suffixing prevents cross-iteration collisions.
- No hardware needed — IR is compile-time only.
- `src/lib.rs` (contested/shared) untouched.

## Notes

- The `gate0` example fails to build on this tree due to a pre-existing
  `CompileCfg` field mismatch (missing `profiling`) — untouched by this patch,
  not part of IR-4's scope.
