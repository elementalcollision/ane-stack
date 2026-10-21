# Evidence — patch 0007: `slice_update` IR op (work item `IR-2`)

Lane: `L-IR` (claimed in `docs/lanes/OWNERSHIP.md`).
Work item: `IR-2` — `slice_update` / incremental state write ⭐ *highest IR value*.
Patch: `patches/0007-ir-slice-update.patch`.

## What was wrong

`mil_spec::ir` had **no `slice_update`**, so an incremental KV-cache append
("write row `pos` of a state") was inexpressible. The only legal state write
was whole-state (`write_state` with update == state shape). `ane_lower`'s
stripe-splitting pass consumes `slice_update` chains over `read_state`
values, but the IR could never produce them — IR-2 blocked RUN-2 (stateful
e5rt programs) and unblocks little until it lands.

## Fix

Three additive changes:

1. `vendor/mil_spec/src/lib.rs` — `Block::slice_update` emits a MIL
   `slice_update(x, begin=const, end=const, update)` op with const begin/end
   vectors and output carrying `x`'s shape.

2. `vendor/mil_spec/src/ir.rs` — IR form
   `su = slice_update(x, begin=[..], end=[..], update=name)` with full
   validation:
   - `x` must be a declared `state` (looked up in `self.states`, like
     `write_state`).
   - begin/end must match rank.
   - every range must be in-bounds and non-empty (`b < e`).
   - the update's shape must equal the *region* shape (end − begin per dim),
     not the whole state.
   Output type = state dtype/shape.

3. `vendor/mil_spec/tests/ir.rs` — 5 new tests:
   - `slice_update_whole_state_write` — begin..end == full dims is legal.
   - `slice_update_region_write` — incremental stripe write is legal.
   - `slice_update_begin_end_must_match_rank`.
   - `slice_update_update_shape_must_match_region`.
   - `slice_update_range_invalid_is_rejected`.

## Test delta

`cargo test --test ir` → 22 passed, 0 failed (was 17 passed).
`cargo test --lib` → 12 passed.
`cargo test --test ane_lower` → 2 passed (unchanged — this IR addition is
consumed by `ane_lower`, not changed by it).

## Confidence

- Validation mirrors `write_state`'s existing contract (state written whole,
  shape-checked).
- Region-shape rule is the actual ANE stripe contract: an update writes into
  begin..end, so its extent must equal that region.
- Full suite green on patched tree.

## Notes

- `src/lib.rs` is shared/contested (`docs/lanes/OWNERSHIP.md`), but this is a
  purely additive method — no existing signatures changed.
- `src/ir.rs` and `tests/ir.rs` are L-IR owned; no other lane's files touched.
- No hardware needed — IR validation is compile-time only.
- The `gate0` example fails to build on this tree due to a pre-existing
  `CompileCfg` field mismatch (missing `profiling`) — untouched by this patch,
  not part of IR-2's scope.
