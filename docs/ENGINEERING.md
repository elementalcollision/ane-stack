# ENGINEERING.md — conventions for multi-lane, multi-agent work

This repo is small but touches undocumented hardware. The failure mode of
parallel agent work here is not slowness — it is **two lanes editing the same
file, or one lane "fixing" a test another lane depends on**. These rules exist
to make that impossible rather than unlikely.

## 1. The invariant

> **A lane owns files, not features.** A feature that spans two lanes is split
> into two work items with an interface contract between them, and the contract
> is written down before either starts.

Ownership lives in `docs/lanes/OWNERSHIP.md`. If a file is not listed as yours,
you do not edit it. Need a change there? Open a `request:` item against the
owning lane instead of editing.

## 2. Definition of done (every work item)

1. **A failing test first.** No behaviour change without a test that fails before
   the change and passes after. For hardware-dependent paths where a test cannot
   run in CI, the *evidence file* takes its place — but the test must still exist
   and must run when the hardware is present.
2. **Evidence recorded** in `docs/evidence/<item>.md`: the command, the output,
   and what it proves / does not prove. Copy the real output; never paraphrase it.
3. **`cargo test --workspace` green** (on the patched tree).
4. **Patches isolated** — if the change is against `vendor/mil_spec/`, it is a
   numbered patch in `patches/`, an entry in `PATCHES.md`, and re-applies cleanly
   to pristine upstream (`apply-patches.sh --check`).
5. **No unlicensed surprise** — no new upstream code vendored without a `NOTICE`
   and `FORK.md` entry.

## 3. Rules that prevent the classic failures

### 3.1 Never "fix" a test to make it pass

Three upstream tests **encoded bugs as correct behaviour** (see `PATCHES.md`
0002/0003). Those were corrected deliberately, with a comment explaining why and
a new test asserting the correct rejection. That is the only sanctioned reason to
change an existing test, and it requires:

- a one-line comment in the test saying what was wrong and the upstream sha,
- a new test that would have caught the original bug.

If you are tempted to weaken an assertion, the assertion is probably right.

### 3.2 Don't trust the READMEs — trust the evidence files

Upstream claims that did not survive contact with hardware: on-chip execution via
the HWX lane, `--cpu` fallback for non-organism programs, the `rope` builtin.
Every claim we carry forward must have an evidence file. See
`docs/adr/0002-deploy-lane-closed.md` for the biggest one.

### 3.3 Hardware claims need hardware

Anything asserting ANE behaviour must be run on Apple Silicon. Mark such tests
`#[ignore]` with a reason, and make the *reason string* the runbook:

```rust
#[test]
#[ignore = "ANE: needs Apple Silicon + xcrun coremlc"]
fn ...() { ... }
```

A test that silently no-ops when hardware is absent is a lie in the suite. Prefer
`return` + eprintln skip over silent pass, and note in the evidence file whether
it actually ran.

### 3.4 Never block on the closed lane

`docs/adr/0002` records that the direct-HWX deploy path is closed at the OS level.
**No lane may make forward progress depend on it.** If a work item needs it, that
item is descoped to "generate and verify bytes", not "execute".

### 3.5 Unsafe and FFI

`mil_spec`, `mil_convert`, `mil_lint` are `#![forbid(unsafe_code)]` upstream — keep
it. `mil_infer`'s FFI modules (`espresso`, `e5rt`, `anec`) are inherently unsafe;
any change there needs:

- a comment naming the exact ABI recovered empirically, with how it was recovered,
- a `Result` boundary so a bad call cannot abort the process (upstream learned this
  the hard way — malformed CFDicts historically crashed the process),
- a probe example under `crates/mil_infer/examples/` that can be run in isolation.

**ObjC exceptions are not catchable from Rust.** Any call that can raise must be
fork-isolated in a probe first. Precedent: probing Apple's shipped `.H17` bundles
aborts the process with `fatal runtime error: Rust cannot catch foreign exceptions`.

## 4. Commit hygiene

- Conventional-ish prefix: `lane/<name>: <what>` e.g. `lane/ir: reject shape-mismatched write_state`.
- Body: what failed before, what the fix is, how it was verified.
- Reference the work item ID from `docs/BUILD_PLAN.md` (`IR-2`, `SCHED-1`, …).
- One concern per commit. Patches to `vendor/` are separate commits from our own code.

## 5. Reporting

Status is tracked in `docs/BUILD_PLAN.md` against item IDs. An item is
`todo` / `wip` / `blocked` / `done`, and `blocked` **must** name what it is
blocked on. "Blocked on hardware" is legitimate; "blocked on unclear" is not —
convert it into a question to a human.
