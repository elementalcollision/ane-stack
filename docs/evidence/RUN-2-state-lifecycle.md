# Evidence — RUN-2: explicit state lifecycle on e5rt

Lane: `L-RUN` (claimed in `docs/lanes/OWNERSHIP.md`, 2026-10-21).
Work item: `RUN-2` — stateful programs on e5rt with explicit state lifecycle.
Status: **done**.

Host: Apple M5 (h17), macOS 26.7.1. Every result below was produced on the ANE.

---

## 1. What was wrong

`state<>` parameters surface as e5rt **inout** ports: resident across calls,
readable and writable in place. Upstream verified that residency, but left it
implicit. A caller could only mutate state by binding a value into the port —
there was no way to inspect it, reset it, or snapshot and roll it back. A KV
cache was therefore not a first-class object: it could not be tested
bit-exactly, and there was no cheap "start a fresh decode" operation.

## 2. What was added

Four operations on `mil_infer::e5rt::Program`, plus a plain-data snapshot type.
All four operate on the already-bound buffers that `execute()` reads and writes
in place, so a snapshot round-trip is meaningful rather than a copy of a stale
host mirror.

| API | Does |
|---|---|
| `reset_states() -> Result<usize>` | zero every state port; returns how many |
| `state_f16(name) -> Result<Vec<u16>>` | read one state port as fp16 bits |
| `state_names() -> Vec<&str>` | the state ports, in bind order |
| `state_len(name) -> Option<u64>` | element count of one state port |
| `save_states() -> Result<StateSnapshot>` | snapshot every port in one call |
| `restore_states(&StateSnapshot)` | roll every port back, atomically |

`StateSnapshot` is deliberately **plain data** (`Vec<(String, Vec<u16>)>`), not
an opaque handle, so a caller can persist, diff or log it and choose its own
serialisation. A convenience `get(name)` / `len()` / `is_empty()` sit on top.

Three `E5Error` variants were added, because the existing ones could not
express these failures honestly:

- `NoSuchState(String)` — a port was addressed that is not state.
- `StateSizeMismatch { state, want, got }` — snapshot has the wrong extent.
- `StateCorrupt(String)` — reserved for a malformed snapshot payload.

No exhaustive `match` over `E5Error` existed anywhere in the workspace
(checked before adding), so these are purely additive.

## 3. The grammar is measured, not assumed — and the docs were wrong

My first fixture followed `ANE_FRONTEND_SPEC.md` line 59 literally:

> `write_state(data=X, input=st)` accepts **any tensor X** of matching type.

That program was **rejected** (`e5_compiler_compile → 11`). The same file
contradicts itself at line 281:

> `write_state(data=X, input=st)` accepts **only** state-derived X: the
> `read_state` result or a `slice_update`/`slice_by_index` chain on it.

Rather than guess which sentence was right, I wrote
`crates/mil_infer/examples/probe_run2_state.rs` — a ladder of five independent
attempts. Measured result:

| # | Shape | Verdict |
|---|---|---|
| 1 | `write_state(data = read_state_result)` | **reject** `e5_compiler_compile → 11` |
| 2 | full-arg `slice_update` → write su, output su | **ACCEPTED** |
| 3 | same, but output the pre-write `read_state` | **ACCEPTED** |
| 4 | two states, each its own full-arg triple | **ACCEPTED** |
| 5 | `write_state(data = read_state)` while an su exists | **reject** `e5_compiler_compile → 11` |

Conclusions, all measured:

1. **Line 281 is correct; line 59 is wrong** for the ANE path. `write_state`
   data must be state-derived, and specifically must be the *terminal*
   `slice_update` output — case 1 (bare read result) and case 5 (read result
   with a live su) both fail.
2. `slice_update` on a state needs the **full** argument list (`begin`,
   `begin_mask`, `end`, `end_mask`, `squeeze_mask`, `stride`, `update`, `x`).
3. **Case 3 is the readback path.** Returning the pre-write `read_state` value
   yields a tensor reflecting the state as it stood when the call began — i.e.
   the previous call's write. That is how the tests observe state without
   trusting the host-side buffer.

`compile_auto` was used during probing because it discovers the real port names
from the op's own descriptors. A first attempt with guessed port names failed at
`retain_port`, which is a misleading error; `compile_auto` reported the truth
(`inout=[("mem",16)]`, `out=[("m2",16)]`).

## 4. The fixture

Two layers, one state each — the 2-layer KV-cache shape acceptance asks for.
Each layer gets its own `read_state` → full-arg `slice_update` → `write_state`
triple. `update` is a runtime input `wvec`, so the test controls what lands in
the state. Both pre-write read values are model outputs, giving two independent
readback channels.

## 5. Test results

`crates/mil_infer/tests/e5rt.rs`, 9 tests, **all hardware-executed**:

```
$ MIL_REQUIRE_HW=1 cargo test -p mil_infer --test e5rt
test ane_executes_add ... ok
test stateful_program_binds_both_layers_as_inout ... ok
test state_persists_across_calls_and_readback_sees_previous_write ... ok
test reset_states_discards_history ... ok
test save_restore_round_trips_bit_identically ... ok
test snapshot_content_matches_readback ... ok
test restore_rejects_wrong_size_and_leaves_state_untouched ... ok
test restore_rejects_snapshot_missing_a_layer ... ok
test state_f16_rejects_a_non_state_port ... ok
test result: ok. 9 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```

`MIL_REQUIRE_HW=1` turns a hardware skip into a hard failure (L-TEST's patch
0009 discipline), so "9 passed" here means nine tests genuinely ran on the ANE —
not three that ran and six that quietly returned.

Run three times back-to-back, identical results (0.31 / 0.32 / 0.32 s). No
flakiness.

Acceptance mapping:

| Acceptance criterion | Test |
|---|---|
| 2-layer stateful program runs N steps on e5rt | `state_persists_across_calls_and_readback_sees_previous_write` |
| state round-trips through save/restore | `save_restore_round_trips_bit_identically` |
| bit-identical continuation | same test: post-restore readback equals the snapshot |
| both layers are real state ports | `stateful_program_binds_both_layers_as_inout` |

## 6. A flakiness bug I found and fixed in my own tests

The first version of these tests shared one E5 cache directory across all seven
tests. Under cargo's default parallelism that **failed 5 of 9** with bogus
errors (`op_create → 13`, `e5_compiler_compile → 2`).

Cause: `CompileCfg::default()` sets `force_recompile = true`, so concurrent
`aned` runs write the same e5 bundle cache and race each other. It is not a
hardware fault and not a defect in `e5rt.rs` — it is a test-isolation defect.

Fix: each test compiles into its own cache directory and its own `.mil` path,
keyed by test tag and pid. Recorded here rather than quietly fixed because a
future reader who reintroduces a shared cache will see the same confusing
failures, and this note is the explanation.

## 7. What this does NOT prove

Stated plainly, because the lane is audited:

- **Not** that state survives across *processes*. e5rt state is resident in the
  bound buffers of one `Program`; `StateSnapshot` is in-memory only. A durable
  KV cache needs a caller-chosen serialisation, which these APIs deliberately
  contain no opinion about.
- **Not** that `restore_states` settles the device-side state. The tests assert
  the host-side buffers restore exactly, that the engine's own readback agrees
  with them (`snapshot_content_matches_readback`), and that execution continues
  correctly afterwards — three separate observations, not one atomicity claim.
  The test asserting snapshot-vs-readback agreement exists *precisely because*
  the engine agreeing is a weaker assumption than the buffer being right, and
  it is asserted rather than assumed.
- **Not** dynamic positions. `begin`/`end` must be `const` on state; this
  fixture writes a fixed row. Runtime-position KV append is the unprobed
  `NetworkJITShapesPath` mechanism (`ANE_FRONTEND_SPEC.md`).
- **Not** multi-layer performance. No timing is claimed; 2 layers here is a
  correctness fixture, not a benchmark.

## 8. Cross-lane notes

- Touched only L-RUN-owned files: `crates/mil_infer/src/e5rt.rs` and
  `crates/mil_infer/tests/e5rt.rs`, plus a new
  `examples/probe_run2_state.rs` (L-RUN/L-PROBE shared; L-PROBE is claimed by
  dave for PROBE work, so this probe is named for its work item).
- **Request to L-PROBE:** `ANE_FRONTEND_SPEC.md` lines 59 and 281 contradict
  each other on whether `write_state` accepts an arbitrary tensor. The ANE path
  says it does not. Section 3 above is a reproduction; the doc is in
  `vendor/`, so correcting it is a patch, not an edit.
- No `src/lib.rs` change — `src/lib.rs` is contested and RUN-2 did not need it,
  because the fixture MIL is written as text rather than through `Block`.

## 9. Pre-existing failures, not introduced here

`cargo test -p mil_infer --lib` reports 6 failures, all in `graph.rs` /
`hwx.rs` — files this work item never touched. Verified pre-existing by
stashing these changes and re-running: the same 6 fail on the unmodified tree.

```
graph::tests::graph_fuses_conv_chain_and_conv_silu
graph::tests::ane_onchip_backprop_training_exec
graph::tests::graph_scheduler_rms_q8_swiglu_exec
hwx::tests::constexpr_dequant_folding_and_hw_exec
hwx::tests::numeric_parity_emitted_vs_anec_vs_cpu_ref
hwx::tests::roundtrip_compile_and_decompile_hwx
```

These sit in L-SCHED (`graph.rs`) and shared `hwx.rs` territory. Recorded so
they are not mistaken for RUN-2 regressions, and so their owner sees them.
