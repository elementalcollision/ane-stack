# Evidence — TOOL-2 CI failure: double-applied patch 0001, and patch stacking

Work item: `TOOL-2` (patch 0005). Owner: L-TOOL.
This is the incident the vendor guard exists to catch — and it did.

## Symptom

CI on the TOOL-2 commit failed the "patches apply cleanly to pristine upstream"
step:

```
patching file crates/milc/src/main.rs   (0004)
patching file crates/milc/src/main.rs   (0005)
Hunk #1 FAILED at 1514.
1 out of 2 hunks FAILED
```

Patch 0005 was generated against a tree that already had 0004 applied, so its
context assumed 0004 — it would not apply to pristine upstream.

## Root cause — two distinct defects, not one

**(a) Patch 0005 was not stacked.** It was diffed against the working tree
(pristine + 0001..0004), not against pristine. Fix: regenerate against
pristine + 0001..0004 and document the stacking in the patch header.

**(b) The vendored tree had patch 0001 applied twice.** Comparing the stacked
result to the real tree surfaced it:

```
$ grep -c "write_state shape mismatch" vendor/mil_spec/src/ir.rs
2        # should be 1
```

The `FORK(ane-stack)` comment and the shape-check block appeared twice
(lines 814 and 829). The patches themselves were each correct (each applies
exactly once to pristine); the tree had been double-patched during the initial
manual application and never caught, because nothing compared the tree to
"pristine + patches applied once".

## Fix

Rebuilt the tree from pristine + the five patches applied exactly once:

```console
$ grep -c "write_state shape mismatch" vendor/mil_spec/src/ir.rs
1
```

`tests/ir.rs` (17 tests) and `run_cli.rs` still pass; `milc verify` 10/10.

## Second, related issue: our own code under vendor/

`vendor/mil_spec/examples/compile_ir_fixed.rs` was authored by us but placed in
the vendored tree — violating FORK.md's own rule that vendor/ holds upstream +
patches only. Moved to `examples/compile_ir_fixed.rs` (its own tiny crate that
depends on the vendored `mil_spec`), and `FORK.md` now states the rule
explicitly: *nothing we authored goes under `vendor/mil_spec/`.*

## What this proves

- The guard + CI ordering check are working as designed: a drifted tree and a
  non-stacked patch were both caught, in CI, before merge.
- The correct baseline to diff a patch against is **pristine + all
  lower-numbered patches**, never the raw working tree.
- The tree should be **rebuilt from patches** whenever there is any doubt, not
  hand-maintained. `scripts/apply-patches.sh` exists for exactly this.

## Process change (permanent)

After this incident, generating a new patch means:

1. apply all lower-numbered patches to a **fresh pristine clone**,
2. make the change there, run tests,
3. `diff -uN` that tree against its **pre-change** self,
4. write the patch header (including any stacking note),
5. verify the **full** patch list applies in order to pristine,
6. rebuild `vendor/mil_spec/` from pristine + patches,
7. regenerate `vendor/manifest.sha256`, commit patch + manifest together.

`scripts/apply-patches.sh` (rebuild) + `scripts/vendor-guard.sh --verify`
(assert) make steps 6 and 7 mechanical.
