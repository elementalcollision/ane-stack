# Evidence — A.5: the `ANECCompile` ceiling is INOUT PORTS, not op count

Lane: **L-SCHED**. Work item: ADR-0002 A.5 (blocker) + feeds SCHED-2.

Supersedes the working assumption in `ADR-0002-A5-scale-deploy.md`, which read
the 320-op ladder as an op-count limit. It is not.

> **CORRECTED 2026-10-22 (L-Probe validation).** This file's headline — "the
> ceiling is inout ports, not op count" — is right, but the **"~52" figure and
> the word "frontend constraint" were both wrong as universal statements.**
> L-Probe (`docs/spec/ane-port-limits-h17.md`, verified: their executable spec
> passes on hardware) showed plain `tensor<>` in/out ports compile to ~128 and
> have no 52-port wall. This file measured `state<>` ports only.
>
> The correct statement is **two separate budgets**: plain ports ~128 with
> `MaxLiveInLiveOutExceeded`, and **`state<>` inout ports ~53** with
> `Compiler internal error`. Reconciled in
> `docs/evidence/reconciliation-two-port-limits.md`, which includes the decisive
> check that they are separate counters (40 `state<>` + 16 plain = 56 total
> ports compiles).
>
> Everything in §2's operational conclusions survives unchanged — the conclusion
> that matters is "`--shard N` emits one packed `kv` state per shard and so sits
> far under 53".

---

## 1. Why the earlier reading was wrong

`examples/gen_big.rs` raises op count and state count **together** — one
`state<>` per layer, ~5 ops per layer. Its failure at 320 ops therefore could not
distinguish "too many ops" from "too many inout ports".

`examples/gen_ceiling.rs` varies them independently:

| mode | states | ops | result |
|---|---|---|---|
| `ops` | 1 | 64 | ✅ |
| `ops` | 1 | 256 | ✅ |
| `ops` | 1 | **1024** | ✅ |
| `ops` | 1 | **4096** | ✅ |
| `states` | 4 | 4 | ✅ |
| `states` | 16 | 16 | ✅ |
| `states` | 32 | 32 | ✅ |
| `states` | 48 | 48 | ✅ |
| `states` | 56 | 56 | ❌ `Compiler internal error` |
| `states` | 64 | 64 | ❌ `Compiler internal error` |
| `states` | 256 | 256 | ❌ `MaxLiveInLiveOutExceeded` |

**4096 ops compile. 56 states do not.** The binding resource is the number of
`state<>` (inout) ports, and the boundary is between 48 and 56 — call it ~52.

## 2. Why this matters more than the correction itself

1. **The 3.2k-op figure in ADR-0002 A.5 was the wrong target.** A >3.2k-op
   artifact *compiles* (`ops=4096` ✅). What does not compile is a shard with
   > ~52 KV-cache states. A 36-layer transformer has 36 K-caches plus V-caches
   plus everything else — it crosses the real ceiling, but by **state count**,
   not op count.
2. **`milc convert --shard N` is the right tool, and for a measurable reason.**
   Sharding splits states across separately-compiled shards. If the wall is
   ports-per-program, sharding works by construction — and the shard count is
   not `--shard 4`, it is `ceil(total_states / ~52)`. That is a computable
   number, which is exactly what SCHED-2 needs and what the current "blunt
   workaround" comment in BUILD_PLAN says is missing.
3. **It re-targets the deploy question.** A.5 asked whether real-scale HWX
   deploys. The right shape to test is now: *many shards, each ≤52 states and
   many ops*, each deployed. That is testable today.

## 3. What is still unknown

- The exact ceiling (48 passes, 56 fails — untested in between) and whether it
  is a fixed count or scales with tensor bytes. Both are cheap to measure.
- Whether it is per-`func` or per-program, and whether output ports count too
  (this probe used 1 output).
- Whether `--shard N`'s existing shard layout actually respects it, or whether
  it was tuned for the plan-builder ceiling (a different wall, already flagged
  not to conflate).

## 4. Next step, and the prioritisation decision

**`milc convert --shard N` first**, because:
- it is the mechanism that turns an unbuildable artifact into a buildable one,
  so it gates the deploy test;
- the ceiling measurement gives it a real target (≤52 states/shard) rather
  than a flag a human guesses;
- SCHED-2's acceptance ("partition to maximise ANE placement subject to the op
  limit, decide shard count from the model rather than a flag") is now a
  *state*-count computation, which is a cleaner and more testable criterion
  than the op-count one it was written for.

SCHED-2's op-count framing should be corrected to a state-port framing — its
own accept text says "it is op count, not bytes", which this measurement
contradicts for the compile path.

## 5. Cross-lane

- Tooling: `examples/gen_ceiling.rs` (L-SCHED), registered in `examples`.
- No vendor change, no patch, no manifest drift.
- **Request to L-PROBE:** the ~52 inout-port ceiling is an undocumented
  `ANECCompile` frontend limit and belongs in `ANE_FRONTEND_SPEC.md`'s limits
  section, alongside the stateful-emitting rules we already corrected.
