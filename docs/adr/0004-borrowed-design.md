# ADR 0004 — Design borrowed from coyote (no code)

**Status:** accepted (2026-10-21)

## Context

`coyote` (MIT, © 2026 Adam Clark) contains two ideas worth adopting that are
independent of its ANE backend — which cannot deploy here anyway (ADR-0002).

## What we borrow

### 1. Seed pre-scaling for a one-add weight update

Coyote documents (and `SPEC.md` explains) that a folded SGD step
`w -= lr * grad(loss, w)` can become **one packed add** on the ANE by
pre-scaling the loss seed by `±lr` *before* the outer product. That is, instead of
computing `dW` then scaling then adding, you seed the reverse pass with
`-lr * 2(p - t)/n` so the resulting outer product *is* the update, and the final
`add` folds into the in-place surface update.

Why it matters: an SGD step is otherwise `outer` + `mul` + `add` (three dispatches).
This makes it one. Given that dispatch count is what decides whether a graph lives
on the ANE, that is a real win, not a micro-optimisation.

**Reimplementation plan:** `BORROW-1`, against our own e5rt training lowering
(`RUN-4`). Verified against a CPU reference, not against coyote.

### 2. Compile-time constitutional checking

Three independent proofs, all verified working upstream:

- **capabilities** — `cap` sets propagate transitively; an undeclared capability
  reachable through any call path is a compile error,
- **determinism** — `det` functions may not (transitively) call `stoch` primitives,
- **secrecy** — `sealed` is a taint bit OR-ed at every op and checked at the return.

**Decision:** document the pattern; build a library only if we need agent-facing
execution (`BORROW-2`, decision-gated). It is not needed for the ANE work.

## What we explicitly do not borrow

- The language, parser, typechecker, VM, WASM backend — we are not building a language.
- Its hand-written Qwen example layer definitions — those are artifacts of having no
  macro facility, not a design to copy.
- Its ANE lowering — it targets the closed lane.

## Why reimplement rather than copy

Both are small, well-described ideas, and reimplementing against our own interfaces
avoids importing coyote's layout assumptions (its `[1,C,1,1]` / `[N,K]` contract is
tied to `mil_infer::graph`, which we are also changing in `L-SCHED`). Copying would
also require vendoring and attributing a second, untested codebase.

Attribution still applies in spirit and in `NOTICE`: the ideas are credited to
Adam Clark / `savageAZfck/coyote`.
