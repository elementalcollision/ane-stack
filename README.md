# ANE Stack

A fork-in-progress of [`mil_spec`](https://github.com/savageAZfck/mil_spec) aimed at
doing more on Apple's Neural Engine than `coremltools` can. **Vendored with
attribution, not rebranded.** See `NOTICE`, `FORK.md`, `docs/LEGAL.md`.

> **Scope honesty, up front.** The direct-HWX deploy lane is **closed at the OS
> level** — Apple's own shipped artifacts fail through the same loader. Everything
> here targets the two lanes that actually work: **CoreML** (public) and **e5rt**
> (`aned` compiles the MIL itself). Read `docs/adr/0002-deploy-lane-closed.md`
> before proposing anything that "emits a binary and runs it".

## Status

| | |
|---|---|
| Upstream | `mil_spec@20f097fb34969cd577342a4d7996fbf5464998c8` (v0.4.2) |
| Vendored | `vendor/mil_spec/` — pristine + `patches/` |
| Patches | 4, all re-applying cleanly to pristine upstream |
| Test state | `cargo test` green; `milc verify` 10/10 |
| Verified running | stateful model on `cpu+ane` (99.42 µs/step); MIL → e5rt on the ANE (211 µs/step) |

## What works today

```sh
cd vendor/mil_spec

# CoreML lane: write a package, compile it, run it on cpu+ane
cargo run --release --example compile_ir_fixed
cargo build --release -p milc
./target/release/milc run /tmp/ir_fixed.mlpackage --units ane --steps 3
#   → 3 steps on cpu+ane: median 99.42µs

# e5rt lane: hand-written MIL, compiled and executed on the ANE with no CoreML
./target/release/milc ane run model.mil --steps 3
```

## Layout

```
NOTICE                  attribution (paste into product about-screens)
FORK.md                 what we vendored, from which sha, how to re-vendor
PATCHES.md              our diff against upstream, itemised
patches/                numbered diffs, apply to pristine upstream
scripts/apply-patches.sh
vendor/mil_spec/        upstream @ pinned sha (+ patches applied)
docs/
  BUILD_PLAN.md         ⭐ the plan: items, lanes, dependencies, out-of-scope
  ENGINEERING.md        conventions for multi-lane / multi-agent work
  LEGAL.md              what the licences do and do not cover
  lanes/OWNERSHIP.md    file-level lane contract (prevents collisions)
  adr/                  decisions with context and consequences
  evidence/             command logs proving each claim
  spec/                 our extensions to ANE_FRONTEND_SPEC.md (L-PROBE)
```

## Lanes

| Lane | Scope |
|---|---|
| **L-TOOL** | CLI, packaging, patch hygiene |
| **L-IR** | validated text IR: expressiveness + validation |
| **L-SCHED** | graph scheduling, cost model, placement ⭐ the differentiator |
| **L-RUN** | e5rt runtime, state lifecycle, decode, training |
| **L-PROBE** | hardware probing, dialect spec on current silicion |
| **L-LINT** | placement prediction |
| **L-TEST** | test infra and evidence harness |

Start here: `docs/BUILD_PLAN.md` §Phase 1. First three items: `TOOL-4` (protect the
fork from rot), `PROBE-1` (new knowledge, no dependencies), `IR-2` (unblocks most).

## Ground rules

1. A lane owns **files**, not features (`docs/lanes/OWNERSHIP.md`).
2. Failing test first; evidence file for anything touching hardware.
3. Never depend on the closed deploy lane.
4. Never weaken a test to make it pass — two upstream tests encoded bugs as correct
   behaviour; see `PATCHES.md` 0002/0003.

## Upstream

`mil_spec` © 2026 Adam Clark, MIT OR Apache-2.0 (this fork elects MIT).
`coyote` © 2026 Adam Clark, MIT — referenced for design only, not vendored.
