# Evidence — ADR-0002 A.5: does the deploy gate open at SCALE on macOS 27.0?

Lane: **L-SCHED**, at the lane owner's direction. Closes A.5's first re-open
condition ("a real transformer shard, h16g, through `_ANEClient` on 27.0").

Hosts: local macOS **26.7.1** (M5); host B (M4 Pro) macOS **27.0** (26A428,
M4 Pro), via `milc ane compile` locally + `dp3`/`deploy_probe` on the mini.

---

## 1. Answer, in one line

**The 3.2k-op question cannot be answered, because `ANECCompile` will not produce
an artifact that large on this machine — and the gate opens at every size the
emitter *can* reach.**

## 2. What the emitter can actually reach

Scale ladder of a genuine multi-layer stateful MIL (one `state<>` per layer,
full-arg `slice_update` triple each — the grammar `probe_run2_state.rs` proved
required), compiled `--arch h16g` locally:

| layers | named ops | `ANECCompile` | error |
|---|---|---|---|
| 2 | 10 | ✅ | — |
| 4 | 20 | ✅ | — |
| 32 | 160 | ✅ | — |
| 64 | 320 | ❌ | `Compiler internal error` |
| 128 | 640 | ❌ | `Compiler internal error` |
| 256 | 1280 | ❌ | `MaxLiveInLiveOutExceeded` |
| 512 | 2560 | ❌ | `MaxLiveInLiveOutExceeded` |

So the practical ceiling from this toolchain is **a few hundred ops**, and the
3.2k-op target ADR-0002 A.5 names is ~an order of magnitude beyond it.

**This is a new finding and it is not a deploy-gate result.** The wall at
320–640 ops is `ANECCompile`'s *resource* limits (`MaxLiveInLiveOutExceeded`,
compiler-internal), i.e. a frontend/sizer constraint on the emitter's own input,
not a deploy refusal. It sits upstream of the question ADR-0002 A.5 asks.

Two process notes, so the numbers are reproducible rather than anecdotal:
- an earlier version of the generator emitted `write_state(data=add(...))` and
  every size failed with `InvalidMILProgram`. That is the rejected form
  (`probe_run2_state.rs` cases 1/5), not a scale limit — a false start.
- per-layer copies of the six index consts hit `MaxLiveInputs` at a few hundred
  ops *without adding compute*. Hoisting them once recovered ~160 ops of headroom.
  If anyone re-runs this, hoist the consts.

## 3. Deploy behaviour across every size that DID compile

Artifacts compiled locally for **h16g** and loaded on **macOS 27.0** through
`_ANEClient loadModel`:

| artifact | macOS 26.7.1 | macOS 27.0 |
|---|---|---|
| 13-op 2-layer stateful (ADR-0002 Appendix A) | ❌ `0x170004` | **✅ LOAD_OK + EVAL_OK** |
| 160-op 32-layer stateful | not tested | **✅ LOAD_OK** |
| 10-op, 20-op spot checks | not tested | **✅ LOAD_OK** |

Every h16g artifact that exists, loads. Nothing in the 10→160-op range suggests
a size cliff — but **nothing above 320 ops exists to test**, so "no cliff" is
an absence of evidence, not evidence of absence.

## 4. Why a real transformer shard was NOT used

ADR-0002 A.5 asked for one. It is not available on this Mac:

- The only sizeable decoder checkpoint is a 36-layer Jina
  (`JinaEmbeddingsV4Model`, hidden 2048, ~4 GB) — **not** in `mil_convert`'s
  supported set, which is `qwen2 | qwen3 | qwen3_moe | llama | mistral`
  (`crates/mil_convert/src/config.rs::supported`).
- The only cached models are BERT **encoders** (`BertModel`: bge-small,
  all-MiniLM). Also unsupported, and a different task shape.
- Every `.gguf` on disk is a vocab-only shard (largest 10 MB), no weights.

So the scale axis was tested on the emitter's *input* rather than through a
converted checkpoint. That is a real substitution and it limits the conclusion:
these MIL programs have the op *structure* of a KV-cache shard but not the
*string* lengths, head counts, and vocab scale of a real model, and those are
exactly what the sizer limits turn on.

## 5. Effect on ADR-0002

**A.5 remains open, and now for a different reason than it was written.**

A.5 was written to ask "does real-scale HWX deploy on 27.0?" The blocker is no
longer the deploy gate — it is that **we cannot emit a real-scale HWX artifact at
all**. Re-ordered:

1. **Get past `ANECCompile`'s ~320-op ceiling** — `--shard N` via `milc convert`
   exists precisely for the plan-builder's op ceiling (BUILD_PLAN SCHED-2), and
   is the natural next step. **Blocks the rest.**
2. Only then re-test deploy at each shard's real op count.

The qualification in ADR-0002 Appendix A still stands and is unchanged: closed
on 26.7.1, open on 27.0 for h16g at every size reachable so far.

## 6. Cross-lane

- Tooling: `examples/gen_big.rs` (L-SCHED). Registered in `examples/Cargo.toml`
  at the workspace root, which is still **owned by no lane** — same request to
  L-TOOL as before.
- **Request to L-SCHED's own future self / SCHED-2:** the 320-op ceiling is
  directly relevant to SCHED-2's partitioning work, which already tracks a
  ~3.2k op plan-builder limit. That limit and this one are different walls
  (plan-builder vs ANECCompile) and should not be conflated.
- No vendor change, no patch, no manifest drift.
