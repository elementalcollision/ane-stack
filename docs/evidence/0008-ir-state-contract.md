# Evidence — patch 0008: state contract validation (work item `IR-3`)

Lane: `L-IR` (claimed in `docs/lanes/OWNERSHIP.md`).
Work item: `IR-3` — IR → type-shape verification for all state ops.
Patch: `patches/0008-ir-state-contract.patch`.

## What was wrong

`mil_spec::ir` validated per-op shapes (IR-1/IR-2) but never checked the
state-level contract across a whole program, so a bad state graph compiled
fine and failed only inside ANEC/coremlc:

- **Clause 1:** one `read_state` per state — two readers on the same state
  passed validation.
- **Clause 2:** `write_state` after each `slice_update` — a `slice_update`
  with no matching `write_state`, or write count ≠ update count, passed.
- **Clause 3:** exact shapes — already enforced per-op (IR-1/IR-2).

## Fix

Three additive changes, all in L-IR-owned files (no contested files touched):

1. `vendor/mil_spec/src/ir.rs` — `Compiler` tracks three per-state counters
   (`state_reads`, `state_slice_updates`, `state_writes`), incremented when
   `read_state`, `slice_update`, and `write_state` bind.

2. `vendor/mil_spec/src/ir.rs` — `finish()` validates the contract:
   - `reads > 1` → rejected ("at most one read_state per state").
   - `su > 0 && writes != su` → rejected ("N slice_update(s) but M write_state(s)").
   - shapes already enforced per-op.

3. `vendor/mil_spec/tests/ir.rs` — 3 new negative tests (one per contract clause):
   - `state_double_read_rejected`
   - `state_slice_update_without_write_rejected`
   - `state_write_slice_count_mismatch_rejected`

## Test delta

`cargo test --test ir` → 25 passed, 0 failed (was 22 after IR-2).
`cargo test --lib` → 12 passed.
`cargo test --test ane_lower` → 2 passed.

## Confidence

- Each clause maps to a sentence of ANE_FRONTEND_SPEC.md's state contract.
- Negative tests assert on the exact rejection message, so the failure mode is
  pinned, not incidental.
- No hardware needed — IR validation is compile-time only.
- Only L-IR files touched (`src/ir.rs`, `tests/ir.rs`); `src/lib.rs` untouched.

## Notes

- `src/lib.rs` is shared/contested (`docs/lanes/OWNERSHIP.md`), but IR-3 needs
  no encoder change — the contract is enforced entirely at the IR layer.
- The `gate0` example fails to build on this tree due to a pre-existing
  `CompileCfg` field mismatch (missing `profiling`) — untouched by this patch,
  not part of IR-3's scope.
