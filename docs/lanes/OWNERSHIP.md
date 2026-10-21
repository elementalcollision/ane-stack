# OWNERSHIP.md — file-level lane contract

**Rule: if a path is not yours, read it and open a `request:` item. Do not edit it.**
This is what keeps parallel agent work from colliding.

## Claimed lanes

Lanes currently in flight. Add yourself here before starting work; do not start
on an unclaimed lane without claiming it.

| Lane | Agent | Since | Active items |
|---|---|---|---|
| **L-TOOL** | dave (initiator) | 2026-10-21 | TOOL-4 (guard) → TOOL-2 → TOOL-3 |

Unclaimed: **L-IR · L-SCHED · L-RUN · L-PROBE · L-LINT · L-TEST**
(L-TEST has veto authority over every lane's tests regardless of claim status.)

## L-TOOL — CLI, packaging, build hygiene

```
crates/milc/src/main.rs
scripts/**
patches/**
PATCHES.md
FORK.md
NOTICE
```
*May read:* everything. *Owns no library internals.*
**Note:** TOOL-4 (the vendored-tree guard) is *written* by L-TOOL but *reviewed*
by L-TEST, because it is the mechanism that enforces every other lane's
patch discipline. Ownership stays with L-TOOL; correctness is jointly held.

## L-IR — validated text IR

```
src/ir.rs
src/ane_lower.rs
tests/ir.rs
src/proto.rs            (shared with L-TOOL for field numbers — announce changes)
```
*Exposes to others:* `mil_spec::ir::{compile, Program, IrError}`.
*Does not touch:* `crates/mil_infer/`.

## L-SCHED — graph scheduling and placement

```
crates/mil_infer/src/graph.rs
crates/mil_sched/**            (new crate)
```
*Exposes:* `mil_sched::{CostModel, Plan, partition}`.
*Depends on (read-only):* `mil_lint`, `mil_infer::hwx` emitters (signatures only).

## L-RUN — runtime and execution

```
crates/mil_infer/src/e5rt.rs
crates/mil_infer/src/espresso.rs
crates/mil_infer/src/ane_pipeline.rs
crates/mil_infer/src/ane_decode.rs
crates/mil_infer/src/shard.rs
crates/mil_infer/examples/probe_*.rs     (probe binaries, shared with L-PROBE)
```
*Exposes:* `e5rt::{Program, DeviceMask}`, `espresso::EspressoProgram`, `Decoder`.
*Note:* all FFI — see ENGINEERING.md §3.5.

## L-PROBE — hardware probing and dialect spec

```
crates/mil_infer/src/anec.rs
crates/mil_infer/src/fuzz.rs
crates/mil_infer/examples/probe_*.rs
docs/spec/**
```
*Produces:* `docs/spec/ane-frontend-*.md`, machine-readable op matrices.
*Owns the `ANE_FRONTEND_SPEC.md` extension document; does not edit upstream's copy
in `vendor/` — writes alongside it in `docs/spec/`.*

## L-LINT — placement prediction

```
crates/mil_lint/**
crates/mil_verify/src/lib.rs     (lint_spec + the conformance battery)
```
*Note:* we already patched this file (patch 0003). Announce any further change.

## L-TEST — test infrastructure

```
tests/**
docs/evidence/**
docs/ENGINEERING.md
```
*May run any lane's tests. Owns no product code.* Has veto on merges that weaken
a test without a documented reason (ENGINEERING.md §3.1).

## Shared / contested — requires an ADR to change

| File | Why contested |
|---|---|
| `src/lib.rs` (mil_spec core) | `Block` API is consumed by every lane |
| `crates/mil_infer/src/hwx.rs` | 8.8k LOC; only L-SCHED and L-PROBE read it |
| `crates/mil_verify/src/{golden,lib}.rs` | conformance is a cross-lane contract |
| `Cargo.toml` (workspace) | adding a crate affects everyone |

## Escalation

If two lanes genuinely need the same file, the resolution is **not** "take turns
carefully". It is: extract the shared piece into a small module with a written
interface, and give that module one owner. File a note in the lane doc.
