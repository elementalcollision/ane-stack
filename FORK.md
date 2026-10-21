# FORK.md — vendoring record

Required by Apache-2.0 §4(b) (prominent notices of modified files) and by our
own policy of never letting attribution drift.

## Upstream

| Field | Value |
|---|---|
| Project | `mil_spec` |
| URL | https://github.com/savageAZfck/mil_spec |
| Licence | MIT OR Apache-2.0 (this fork elects **MIT**) |
| Copyright | © 2026 Adam Clark |
| Pinned commit | `20f097fb34969cd577342a4d7996fbf5464998c8` |
| Pinned tag-ish | v0.4.2, committed 2026-10-19 |
| Vendored on | 2026-10-21 |
| Location | `vendor/mil_spec/` (git history stripped; this file is the record) |

Upstream history contained a single commit, so no history was lost by
stripping `.git`. If upstream later publishes history, re-vendoring is a
`git clone` + `git checkout <sha>` + `rm -rf .git` + update this table.

## Why vendor rather than depend

`coyote` (the upstream consumer) depends on `mil_infer` via a git URL. We need
to carry patches for bugs that block our work (see `patches/`). Vendoring keeps
the patch set reviewable and makes builds reproducible when upstream moves or
disappears.

## How to re-vendor

```sh
cd vendor && rm -rf mil_spec
git clone https://github.com/savageAZfck/mil_spec.git mil_spec
cd mil_spec && git checkout <new-sha> && rm -rf .git
# then: re-apply every patch in ../patches/ that still applies, and update the
# table above plus PATCHES.md.
```

## Modified files

Every file we change gets an entry here. Convention for the in-file header:

```rust
// FORK(ane-stack): <one-line reason>. Upstream: <sha>.
```

| File | Patch | Status |
|---|---|---|
| _none yet_ | | |

## Rules

1. **Never** edit `vendor/mil_spec/` by hand without adding an entry here and a
   patch file in `patches/`. Reviewers must be able to reconstruct our diff
   against upstream from `patches/` alone.
2. Keep patches minimal and independently testable. One concern per patch.
3. Every patch carries a regression test. A patch without a failing-first test
   is not merged (see `docs/ENGINEERING.md`).
4. Prefer upstreaming. A patch that upstream accepts gets marked `upstreamed`
   in `PATCHES.md` and can eventually be dropped at the next re-vendor.
