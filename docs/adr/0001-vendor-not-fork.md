# ADR 0001 — Vendor mil_spec, don't fork druid

**Status:** accepted (2026-10-21)

## Context

We want ANE capability beyond what `coremltools` offers: static placement
prediction, better scheduling, stateful graphs, and eventually on-chip training.
Two upstream repos provide most of the machinery: `mil_spec` (toolchain, 66.7k LOC)
and `coyote` (language, 14.9k LOC). Both MIT/Apache-2.0, © Adam Clark.

Options considered:

1. Depend on `mil_spec` via git (how `coyote` does it).
2. Vendor upstream at a pinned sha and carry a patch set.
3. Fork wholesale; rebrand and diverge.
4. Clean-room reimplement.

## Decision

**Vendor at a pinned sha with a small, numbered patch set (option 2).**

## Rationale

- **Depend (1)** cannot work: we need four bug fixes that block basic use
  (`milc run <pkg>` was entirely broken by a case-sensitivity bug). A git
  dependency we cannot patch is a dead end.
- **Fork wholesale (3)** buys nothing but maintenance. The upstream history is a
  single commit; there is no maintainer velocity to diverge from, and ~80k LOC of
  undocumented-hardware code is not something to own casually.
- **Clean-room (4)** is 6–18 months for parity on a target that
  `coremltools` already covers, and would inherit the same OS-level deploy wall.
- **Vendoring (2)** keeps the diff reviewable, keeps builds reproducible if
  upstream disappears, and makes re-vendoring a mechanical operation
  (`FORK.md` documents it).

## Consequences

- We own the patch set and must keep it applying (`scripts/apply-patches.sh --check`).
- Attribution is a hard requirement: `NOTICE`, `FORK.md`, in-file `FORK(ane-stack)`
  comments. Apache-2.0 §4(b) requires change notices on modified files.
- We must prefer upstreaming; patches accepted upstream become droppable.
- `coyote` is **not** vendored — design only, recorded in ADR-0004.
