# Evidence — TOOL-4: vendored-tree guard

Work item: `TOOL-4`. Owner: L-TOOL (jointly reviewed by L-TEST, per OWNERSHIP.md).
Host: Apple M5 Max, macOS 26.7.1, bash 5 / `shasum`.

## Acceptance criterion (from BUILD_PLAN)

> mutate a vendored file → guard fails naming the file.

## What was built

`scripts/vendor-guard.sh`:
- `--generate` — rebuild `vendor/manifest.sha256` (432 entries, one SHA-256 per file)
- `--verify` — exit 1 naming the drifted file(s); this is the CI mode
- `--status` — human-readable drift report, read-only

Excludes `target/`, `*.rej`, `*.orig`, `.DS_Store`.

## Failing-test-first trace

```console
$ scripts/vendor-guard.sh --verify      # before baseline existed
ERROR: no manifest at .../vendor/manifest.sha256
rc=1                                    # fails as required

$ scripts/vendor-guard.sh --generate
wrote vendor/manifest.sha256 (432 entries)

$ echo "// sneaky unpatched edit" >> vendor/mil_spec/src/lib.rs
$ scripts/vendor-guard.sh --verify
DRIFT detected in vendor/mil_spec/:
  < b6d2a89d...  src/lib.rs
  > be9c52e6...  src/lib.rs
rc=1                                    # fails, naming the file

$ sed -i '' '/sneaky unpatched edit/d' vendor/mil_spec/src/lib.rs
$ scripts/vendor-guard.sh --verify
OK: vendor tree matches baseline (432 files)   rc=0
```

## It caught a real artifact immediately

Before baseline generation the tree contained a stray `src/ir.rs.orig` — a patch
leftover the guard's `*.orig` exclusion now permanently ignores, and which I
removed. So the guard's first act was to find an un-tracked artifact. That is the
class of rot it exists to prevent.

## Regression test

`tests/vendor-guard.bats.sh` runs the guard against a **scratch copy** of the
tree (never mutating the real one) and asserts 8 behaviours: no-manifest failure,
baseline generation, clean verify, tamper detection with filename, restore
recovery, and that `target/`/`*.rej`/`*.orig` don't trip it. All pass.

```console
$ bash tests/vendor-guard.bats.sh
...
all TOOL-4 tests passed
```

## Why a manifest and not `git status`?

Git knows what changed, but it can't enforce *why it changed*. The manifest is
regenerated only alongside a numbered patch, so "the tree changed and there is no
patch" is mechanically detectable. Git alone can't tell a sanctioned patch from a
hand edit.

## What it does not guard

- New vendored code dropped in without a `NOTICE`/`FORK.md` entry — the guard sees
  the drift but can't read intent. That's `FORK.md` rule 2, enforced by review.
- Re-vendoring to a *new* upstream sha — that is intentional, and the runbook is in
  `FORK.md`.
