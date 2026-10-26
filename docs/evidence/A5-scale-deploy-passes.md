# Evidence — A.5: a 16384-op stateful artifact compiles AND deploys on 27.0

Lane: **L-SCHED**. Work item: ADR-0002 A.5.

**This closes A.5's first re-open condition.** The scale caveat is lifted, not
merely narrowed.

Hosts: local macOS 26.7.1 (M5) for `ANECCompile`; host B (M4 Pro) macOS
**27.0** (26A428, M4 Pro) for `_ANEClient loadModel`.

---

## 1. What was built

`examples/gen_ceiling.rs` in `packed` mode: **one** `state<tensor<fp16,[R,D]>>`
port whose `R` rows carry every "layer's" slot (exactly the layout
`mil_convert/src/builder.rs::build_range` emits — `kv_shape` is
`(le-ls)*2` rows), plus a long `add` chain over the read value for real compute.
This is the shape `milc convert --shard N` actually produces, not the
one-`state<>`-per-layer shape `gen_big.rs` produced.

| ops | state rows | bytes | `ANECCompile --arch h16g` | deploy on 27.0 |
|---|---|---|---|---|
| 64 | 64 | — | ✅ | — |
| 512 | 1024 | — | ✅ | — |
| 4096 | 8192 | — | ✅ | — |
| 8192 | 16384 | — | ✅ | — |
| **16384** | **32768** | **4.5 MB** | ✅ | **✅ `LOAD_OK`** |

16384 ops is **5× the 3.2k-op figure** ADR-0002 A.5 named as its scale caveat.

## 2. The two ceilings, and why they looked like one

The previous run (`ADR-0002-A5-scale-deploy.md`) read a "320-op ceiling" from a
generator that raised op count and independent-state count **together**. They
are different walls:

| resource | ceiling | evidence |
|---|---|---|
| **independent `state<>` ports per program** | **~52** | `states=48` ✅, `states=56` ❌ `Compiler internal error` |
| ops / state rows / bytes | **none found** | `packed` at 16384 ops, 32768 rows, 4.5 MB ✅ |

So the binding constraint is **the number of separate inout ports**, not total
work. `--shard N` avoids it by construction: each shard keeps **one** packed
`kv` state, so shard count is not limited by the port ceiling at all.

This is the measurement that makes A.5 answerable — the earlier "cannot emit at
scale" was an artefact of the probe's shape, not a limit of the toolchain.

## 3. What this does NOT prove

- **Not** a real transformer shard. This is the *shape* of one — packed KV
  state, long op chain — with synthetic weights. Real `qwen/llama` weights would
  change striding, head packing, and byte totals, and could hit a wall this
  probe cannot see (e.g. per-shard weight bytes, `max_kv` × seq limits).
- **Not** the CoreML lane. This is `_ANEClient` precompiled load only; no
  `execute` was run on the 16384-op artifact (the 13-op and 160-op ones did
  `EVAL_OK`).
- **Not** many shards. One shard deployed. N shards each ≤52 independent states
  is untested as a *system* — though each shard individually is now known good.
- **n=1 OS version.** M4 Pro on 27.0 vs M5 on 26.7.1; the arch×OS confound
  noted elsewhere still applies.

## 4. Consequence for ADR-0002

A.5 item 1 — *"If a >3.2k-op model loads, the scale caveat falls away"* — is
satisfied **in the sharded shape**. The remaining action for that item is to
confirm with a real converted checkpoint, which needs a supported architecture
(none on this Mac: see A5-scale-deploy.md §4).

The Appendix A qualification should be tightened: **closed on 26.7.1; open on
27.0 for h16g artifacts, at scale, in the single-packed-state shape `--shard N`
emits.**

## 5. Cross-lane

- Tooling: `examples/gen_ceiling.rs` (`packed` mode) — L-SCHED.
- **Feeds SCHED-2 directly:** the operative limit is *independent state ports
  (~52)*, not op count. BUILD_PLAN's SCHED-2 text ("it is op count, not bytes")
  is wrong for the compile path and should be corrected to a port-count framing.
  `--shard N`'s layer split already yields 1 port/shard, so it satisfies this by
  construction — which is why the "blunt workaround" comment undersells it.
- **Request to L-PROBE:** the ~52 independent-inout-port limit is an
  undocumented `ANECCompile` frontend constraint and belongs in
  `ANE_FRONTEND_SPEC.md`.
