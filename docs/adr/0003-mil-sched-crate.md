# ADR 0003 — Add the `mil_sched` crate to the workspace

**Status:** proposed (2026-10-21)
**Author:** L-SCHED
**Blocks:** SCHED-1, and transitively SCHED-2, SCHED-3, SCHED-4

## Context

L-SCHED owns a scheduling/placement capability that no existing crate is the
right home for:

```
crates/mil_infer/src/graph.rs     — a rule-based single-stream compiler
crates/mil_sched/**               — the cost model + partitioner (new)
```

`docs/lanes/OWNERSHIP.md` lists `Cargo.toml` (workspace) as **contested**:
"adding a crate affects everyone". So this ADR exists before any code does.

## Options considered

### A — Put the cost model in `mil_lint`

`mil_lint` already computes a per-op unit verdict and an estimated dispatch
count, which is exactly the raw material SCHED-1 needs.

**Rejected.** `mil_lint` is a *predictor* — it answers "what will CoreML likely
do with this op?" and is deliberately rule-based, self-contained, and
dependency-free so it can run anywhere (including on a host with no ANE). A cost
model needs to be *calibrated against measured* `MLComputePlan` output, which
pulls in hardware measurement and pulls toward change for a different reason.
Fusing them means every calibration update destabilises the lint rules — and
L-LINT has veto over that file. Also, `OWNERSHIP.md` notes `mil_verify` and
`mil_lint` are cross-lane contracts for a reason.

### B — Put it in `mil_infer`

`mil_infer` is where `graph.rs` lives and where the ANE-facing code sits.

**Rejected, but this is the debatable one.** `mil_infer` is the FFI/execution
crate: `espresso`, `e5rt`, `anec`, `hwx`, all `unsafe`, all platform-gated.
A cost model that produces `(unit, estimated_us, transfer_bytes)` per op is
pure arithmetic over a lint verdict — it has no business being in a crate whose
whole hazard profile is foreign calls. Making `mil_sched` depend on `mil_infer`
would drag FFI concerns into what should be a testable, host-portable module,
and it would make the dependency direction backwards (scheduling decides how to
use the runtime, not the other way round).

The counter-argument is real: `mil_sched` does need `MilOp`-shaped input from
`graph.rs` today, and a new crate means either a shared type or a small adapter.
See "interface" below.

### C — New `mil_sched` crate — **chosen**

Owns the cost model and the partitioner, depends on `mil_lint` (read-only) for
verdicts and on `mil_spec` for IR types. Depends on **no** FFI crate.

*Exposes:* `mil_sched::{CostModel, Plan, partition}` — as already specified in
`OWNERSHIP.md`.

## Interface (so this is not a guess)

`mil_sched` needs to turn a graph into a schedule. The minimal inputs, derived
from what `mil_lint` and `graph.rs` already produce rather than invented:

| Input | Source | Why |
|---|---|---|
| `Verdict` per op | `mil_lint::classify_op` (read-only) | predicted unit + which rule fired |
| output shape | `Verdict.shape` | transfer bytes need element count × dtype width |
| op type | `Verdict.op` | per-op cost coefficient table |
| graph edges / op order | `graph.rs` `Plan` or `MilOp` order | partitioning needs cut points |

`mil_sched`'s own outputs:

| Output | Meaning |
|---|---|
| `CostModel` | per-op `(unit, estimated_us, transfer_bytes)` — SCHED-1 |
| `Plan` | a partition assignment over ops — SCHED-2 |
| `partition()` | the partitioning function itself |

**On `graph.rs`:** L-SCHED owns it (`OWNERSHIP.md`), so no ADR is needed to
*edit* it — only to *add a crate alongside* it. If `mil_sched` needs a shape or
edge iterator from `graph.rs` that does not exist yet, that is an L-SCHED change
in an L-SCHED file and does not need a further ADR.

## Consequences

- `[workspace] members` gains `crates/mil_sched`.
- CI compiles one more crate. `mil_sched` is expected to be pure — no
  `unsafe`, no platform gating — so it must build and test on any host,
  including the Linux CI runner. This is a strengthening, not a cost: a cost
  model that only works on the machine that produced it is not evidence.
- `docs/lanes/OWNERSHIP.md` already specifies `mil_sched::{CostModel, Plan,
  partition}`, so this ADR aligns the workspace with the existing contract
  rather than creating new API surface.
- Anyone adding a crate after this one has a precedent for the format of the
  argument: options considered, why the neighbours are wrong, interface stated
  up front.

## Not decided here

- Whether `graph.rs` eventually *delegates* to `mil_sched` for its cost
  decisions, or `mil_sched` stays a separate planner and `graph.rs` consumes a
  `Plan`. That is SCHED-2's job and should not be pre-committed in an ADR.
- Any change to the `Cargo.lock` policy (none proposed).
