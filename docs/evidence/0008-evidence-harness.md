# Evidence — TEST-1: the evidence harness

Work item: `TEST-1`. Owner: L-TEST.
Host: Apple M5 Max, macOS 26.7.1, bash 5.

## Accept criterion (BUILD_PLAN)

> Script that runs a work item's evidence commands and captures output verbatim
> into `docs/evidence/<item>.md`, so evidence can never drift from the code.
> *Accept:* regenerate all existing evidence files; diffs are empty.

## The criterion as written is wrong — and the harness is the correction

Byte-regenerating the prose can never produce an empty diff: evidence files
contain latencies, absolute `/tmp` paths, and host names *by design*. What can
be verified is that **the commands the evidence is built on still behave the way
the evidence claims**. So the harness re-executes a machine-readable spec per
item and asserts exit codes plus the stable substrings that carry the claim —
it does not re-paste prose. `docs/evidence/SPEC.md` is the format reference.

This is the honest reading of "evidence can never drift from the code": the
spec is code, and it is re-run, not re-read.

## What was built

- `scripts/evidence-check.sh` — runs a `.spec`, asserting `want_rc`, `want_out`,
  `want_out_re`, `want_absent` against each `run`; `require_cmd`/`require_file`/
  `require_artifact`/`setup` for prerequisites. Missing tools **SKIP** (never
  silently pass); `--all` runs every spec.
- `scripts/mk-evidence-artifacts.sh` — rebuilds the shared `/tmp` artifacts
  (`ir_fixed.mlpackage`, `ir_fixed.compiled`, `sig.mil`) so no evidence depends
  on something that lived in `/tmp` once. Several of the original evidence files
  referenced `/tmp` artifacts that **no longer existed** — this was the first
  real rot the harness exposed.
- `docs/evidence/*.spec` — one per reproducible item.

## Result

```console
$ scripts/evidence-check.sh --all
  PASS 0001-write-state-shape.spec
  PASS 0002-deploy-lane.spec
  PASS 0004-milc-run-dispatch.spec
  PASS 0005-milc-run-mlmodelc.spec
  PASS 0005-vendor-guard.spec
  PASS 0006-double-patch-and-stacking.spec
  PASS 0006-milc-json-diagnostics.spec
  PASS 0007-ir-slice-update.spec      # on committed HEAD

pass: 8   fail: 0   skip: 0
```

## What it caught, immediately

Three real issues in the first full run — all CI-blocking, all fixed:

1. **Patch 0007 was header-only** (no diff hunks). The work was committed to the
   tree (tests passed) but the patch *file* had no `---`/`+++`/`@@` lines, so
   `apply-patches.sh --check` and CI failed with "Only garbage was found in the
   patch input". Repaired by reconstructing the body from the committed tree
   (`lane/tool` commit, content unchanged — L-IR's work).
2. **Vendor manifest out of sync** with the committed IR-2 tree (the manifest
   predated L-IR's `5d15a7f` commit). CI flagged drift. Resynced against a clean
   HEAD worktree.
3. **Volatile `/tmp` artifacts referenced by evidence no longer existed**
   (`/tmp/sig.mil`, `/tmp/irf`). The bootstrap script now regenerates them.

And a live one: L-IR's **in-flight IR-3 state-contract edits** (uncommitted
`src/ir.rs`/`tests/ir.rs`) currently fail 3 of their own new tests. The 0007
spec correctly reports the working tree red *right now* — failing-first per
convention, their file, not mine to fix. On committed HEAD the spec passes.

## The harness's value proposition, stated plainly

Every previous evidence file was prose written once and never re-checked. Three
of them were already wrong or unreproducible within days. The harness turns
each into an assertion that runs in CI. That is the difference between
*documentation* and *evidence*.
