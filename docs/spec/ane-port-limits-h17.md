# ANE resource budgets on h17 — io ports, the BAR pool, and the HWX records

> **Living document, re-measured 2026-10-22, then re-evaluated the same day.**
> This version **supersedes** the 2026-10-21/22 text: five of its headline laws
> did not reproduce (see [Corrections](#corrections-to-the-previous-version)).
>
> **Coverage contract.** Every law has a confidence label.
> - **established**: dense measurement with repeated boundaries, **and** at least
>   one line in `docs/spec/ane-port-limits-h17.spec` that would fail if the law
>   were wrong.
> - **strong**: consistent over many programs, but either the mechanism is
>   inferred or the law is checked by runners and skeptics, not by the spec.
> - **tentative**: fitted on few points or one generator family.
>
> Claims marked *(runner-only)* have no spec line. The spec asserts every headline
> law and the boundaries a planner needs, not every sentence.
>
> **Visual companion:** `docs/spec/ane-port-limits-h17.html` draws this model.
> The older `ori` page `ane-descriptor-economy` (v1–v3) drew the refuted one; v1
> is archived with a banner at `docs/spec/history/ane-descriptor-economy-v1.html`.
> Every claim on v1–v3 has been classified; see
> [The ori pages, claim by claim](#the-ori-pages-v1v3-claim-by-claim).

## Build provenance

| Field | Value |
|---|---|
| SoC | Apple M5 Max (Mac17,7, exposes `h17`) |
| macOS | 26.7.1 (25G241) |
| Compiler | `zin_ane_compiler v9.510.0` (from the HWX `LC_IDENT`); coremlc 3600.25.1 |
| h16g (M4) data | **cross-compiled on this M5 host only**. Nothing was loaded or run on M4 silicon. |
| Probes | `milc ane validate \| compile \| run` on generated `program(1.3)` MIL. **`validate`/`compile` default to `--arch h16g`**: always pass `--arch h17` (the spec does). `run` ignores `--arch`, so its results are always the host's. |
| Generators | `gen_live_ports.py` (every input live), `gen_mix_ports.py` (inputs beyond `out` are dead), `gen_dup_returns.py`, `gen_states.py`, `gen_states_width.py`, `gen_states_nd.py` (4-D state, `add`/`direct` update source, `noupd`, `in=0`, `conv=K`, `lut=…`), `gen_state_dtype.py` |
| Decoders | `count_desc_records.py`, `decode_slot_ordinals.py`, `hwx_layout.py`, `decode_block_trailers.py` (block framing and trailers), `decode_copy_records.py`, `decode_copy_words.py` (word-level copy-record view), `state_exec_predict.py` |
| Method | Four hardware runners re-measured each law family (the io runner alone made 3,886 `milc` calls; the others compiled ~900, ~1,300 and ~1,900 artifacts). Every boundary was run at least twice with 0 flips; the ANE may have been shared between runners. The decisive points were re-run by the orchestrator. A second round tested held-out points against this text (the corrections are listed at the end). |
| Spec | 102 probes, 219 assertions, PASS in ~20 s; `require_hw`-gated; builds milc itself; passes from an empty temp directory (self-contained) |
| Datapoints | `docs/data/ane-h17-2026-10-22/`: the spec as structured JSON (CI drift-checked), the runners' raw measurement logs (3,908 io-call rows, 2,281 state-cap rows, held-out batches, copy-record and trailer sweeps, a 44-row state-dtype table), the runner-only generators, and the review/claim audit trail; scrubbed of private paths and host details |
| Date | 2026-10-22 |

Reading a run result:
- **Pass:** `milc ane run` exits 0 and prints a line starting `step 0: <time>`.
- **Fail:** exit 1 and `milc ane run: step 0: execute_sync → 11 … Program Inference error`.
  That text also contains `step 0:`, so always judge by exit code.
- A pass is **not a numeric check**: outputs are not compared (see §9, "What this does not cover").

---

## The model in one table

| # | Budget / law | Where it bites | Boundary on h17 (this build) | Confidence | Spec § |
|---|---|---|---|---|---|
| 1 | Execution io cap | `execute_sync` | `live_in + unique_out ≤ 127` (no floor) | established | 1 |
| 2 | Frontend io cap | `ANECValidate` / `ANECCompile` | `declared_in + out ≤ 255` (`MaxLiveInLiveOutExceeded`) | established | 2 |
| 3 | States cost io ports | both caps | each state = 1 input port; each returned update = 1 output port; `write_state` is a liveness root | established | 3 |
| 4 | BAR pool (the state cap) | `ANECCompile` (`ZinBarIdManager`) | 55 BAR ids = 55 `__FVMLIB` segments; each state owns one ⇒ **53 states** with a plain input, **54** without | established (count) / strong (mechanism) | 4 |
| 5 | Buffer-binding records | HWX `__text` | `0x9344`/`0x934a`/`0x9442` = 12-byte bindings; slot word = segment ordinal (or a special word below `0x2300`) | established | 5 |
| 6 | State-copy records | HWX `__text` | tag = presence flags; stride = `8·min(⌈log2 dim1⌉, 4)` | established | 6 |
| 7 | State execution | `execute_sync` | 64 B row padding must not add a 16 KiB page; state dtype fp16/int16/int8/uint8/bool | established (asserted points) / strong (rule) | 7 |
| 8 | h16g vs h17 | compiler output | same **compile-time** caps and record laws; `0x934a` 1 vs 2 per binary-add task; runtime caps unmeasured on M4 | established (cross-compile) | 8 |

---

## 1. Execution-time io cap: `live_in + unique_out ≤ 127`

**Law (established).** A program executes on the ANE iff

```
live_in + unique_out (+ n_states + n_exposed_states, see §3) ≤ 127
```

**What counts as a live input.** An input is counted if it is reachable from a
**root**. The roots are the returned outputs **and every `write_state`** (see §3).
- Not counted: unreferenced inputs, inputs read only by a dead op, inputs read
  only by a dead add-chain.
- Counted, even with no effect on the value: an input whose contribution is
  multiplied by 0 still counts *(strong: one boundary pair, runner-only)*.

**What counts as an output.** `unique_out` counts **distinct returned tensors**: one
tensor listed 200 times in the return tuple is one port *(strong; one point
asserted)*.

**Hazard: an input returned unchanged.** An output that *is* an input tensor
(`-> (x0, …)`) costs no execution port, and **`milc ane run` returns it as zeros**.
An input whose only use is being returned does not compile at all. The frontend
still counts it. Route pass-throughs through an op. *(strong, runner-only)*

**Boundary and failure.**
- There is **no floor**: (126, 1) runs; (127, 1), (65, 63) and (100, 28) fail.
- Failure: exit 1, `status=0x2 : statusType=0x9: Program Inference error`.
- It is a **count**: ports of `[1,8192,1,1]` (16 KiB, asserted) and up to
  `[1,262144,1,1]` or `[1,16,64,64]` (runner) hit the same boundary.

| in (all live) | max out | in + out |
|---|---|---|
| 1 | 126 | 127 |
| 16 | 111 | 127 |
| 32 | 95 | 127 |
| 48 | 79 | 127 |
| 63 | 64 | 127 |
| 64 | 63 | 127 |
| 65 | 62 | 127 |
| 80 | 47 | 127 |
| 100 | 27 | 127 |
| 126 | 1 | 127 |

Each row was bisected. A dense 2-D sweep then checked (IN, 127−IN) PASS and
(IN, 128−IN) FAIL for every IN in 1..126, twice: 504 runs, 0 anomalies. The second
round added held-out checks at (40, 87/88), (90, 37/38), (10, 117/118) and
(120, 7/8), and a mixed-liveness case; all held.

**Domain.** fp16 rank-4 ports, one `main` function, `milc ane run`. Rank 3 was
spot-checked at (40, 87/88) and holds. **Not measured:** fp32/int32 ports (one
fp32-port program failed to run), other ranks, multi-function programs, the
CoreML lane, M4 silicon.

**Where the old "floor at 63" came from.** `gen_mix_ports.py` makes output `i`
read `x{i % in}`, so with `in > out` only the first `out` inputs are referenced,
and the run path drops the rest. At `in ≥ 64` the observed "max out = 63" was
really the diagonal `live_in = out = 63`, since 126 ≤ 127.

## 2. Frontend io cap: `declared_in + out ≤ 255`

**Law (established).** Both `milc ane validate` and `milc ane compile` reject a
program once `declared_in + out ≥ 256`. The failure is exit 1, `status=0x1 rc=1`,
`error: MaxLiveInLiveOutExceeded`.
- The spec asserts the boundary on validate and compile for h17, and on validate
  for h16g at 128 + 128 only. The runners swept every split on validate on both
  arches, and 19 splits on compile.
- validate/compile count **declared** inputs, dead ones included: (254, 1) ok,
  (255, 1) rejected.
- The run path prunes dead inputs first, so the same file runs. On the run path
  the 255 applies to *live* ports: above 255 live ports it fails as
  `ANECCompile() FAILED`; from 128 to 255 it fails at execution (§1).
- On validate/compile, an input whose **only** use is a dead op fails with
  `CompilationFailure`; the run path prunes it *(strong, runner-only)*.
- Zero outputs *(strong, runner-only)*. A **stateless** program with no output is
  rejected by validate and compile, produces no macho, and does not run. A
  **stateful** program that returns nothing validates and compiles, but does not
  load.

## 3. States cost io ports

**Law (established).** In both caps, every `state<>` the program uses counts as
**one input port**. Every state whose updated tensor is returned counts as one
more **output port**; it is an ordinary output.

```
execution:  (live_in + n_states) + (unique_out + n_exposed_states) ≤ 127
frontend:   (declared_in + n_states) + (out + n_exposed_states)    ≤ 255
```

**`write_state` is a liveness root.** An input whose only consumer is a state
update still costs a port, even when the update is not returned. This is the
shape of a no-return KV append. Asserted: 3 noupd states with 100 inputs that
feed only the update, plus 24 outputs, gives 127 and runs; 25 outputs fails.

| program | ports | runs? |
|---|---|---|
| 53 states, all updates returned, 1 in, 20 out | 53+1+53+20 = 127 | yes |
| same, 21 out | 128 | no (`status=0x2`) |
| 53 states, **no** update returned, 1 in, 73 out | 53+1+73 = 127 | yes |
| same, 74 out | 128 | no |
| 3 noupd states, 100 inputs feeding only the update, 24 out | 127 | yes |
| same, 25 out | 128 | no |
| `gen_states.py 53 32 32` (the old spec's "plain io does not share the budget" program) | 53+32+53+32 = 170 | **compiles, does not run** |
| frontend: 126 exposed states, 1 in, 1 out | 254 | validates |
| frontend: 127 exposed states | 256 | `MaxLiveInLiveOutExceeded` |

A program that returns all its state updates has 21 plain io ports left at 53
states. Not returning the updates frees one port per state.

A **read-only** state (read, never written) also costs one input port, and its
returned read is an ordinary output *(strong, runner)*. A declared state that is
**never referenced** is pruned at execution and costs no port there, but
validate/compile count it *(strong, runner-only)*. Write-only states and states
with a dead read do not compile on the run path.

**Domain.** State shapes `[4,4]`, `[1,4]`, `[4,1]`, `[4,16]`, `[4,64]`, `[64,4]`,
`[4,32]`, plus `[8,16,1,32]` and `[4,2048,1,32]` and partial exposure (K < N) in
the second round. N up to 53 (126 for the frontend); IN up to 100.

## 4. The BAR pool: why 53 (and when 54)

**Count (established).**

| program | `__FVMLIB` segments | compiles | runs |
|---|---|---|---|
| 53 states + 1 plain in + 1 out | 55 | yes | yes |
| 54 states + 1 plain in + 1 out | — | **no**: `ZinBarIdManager::GetNextAvailableBarId(): unable to allocate free BAR` (milc exit 1); the run lane reports `ANECCompile() FAILED` | — |
| 54 states, **no plain input** (update source `fill` or a nested const literal), 1 out | 55 | **yes** | **yes** |
| 55 states, no plain input, 1 out | — | no (`free BAR`) | — |
| 53 states + 1 in + 1 out + an inline **conv weight** | 55 (`__KERN_0` shed) | yes | yes |
| 54 of the same | — | no | — |
| 53 states + 1 in + 1 out + a **sigmoid** (LUT op) | 55 (`__KERN_0` shed) | yes | yes |
| 53 states, `[64,32]` each, 32 in + 32 out | 55 | yes | (exceeds §3/§7) |
| 54 of the same | — | no | — |
| 53 states, **no update returned** (one `0x9344` in the whole program) | 55 | yes | yes |
| 54 of the same | — | no | — |

**State dtype does not move the pool (established).**
- With a plain input: int8 and int16 states hit the same 53/54 as fp16. int8 at
  53 runs. (asserted)
- Without a plain input: int8 states hit the same 54/55. (asserted)
- Runner: uint8 and bool, noupd variants, and int8 states up to `[16,64,1,32]`
  behave the same way.

Beyond these asserted cases, the runners found the same boundary across:
- state shape: dim0 4..256, dim1 1..64, mixed shapes
- op chains up to 200 ops
- plain io from 1 to 100
- states whose update is not returned
- the number of exposed states
- h16g

Only removing a shared segment moves it. The second round confirmed
`N_max = 55 − [any output: plain or exposed update] − [any plain input]` in all 8
combinations of (plain input?, plain output?, updates exposed?), at N_max and
N_max + 1, twice each *(runner)*. A program with no output of any kind compiles
`55 − [plain input]` states, but the bundle does not load (`op_create -> 13`).

**Mechanism (strong; inferred from the compiled HWX, not from allocator source).**
- Every `__FVMLIB` segment (or `__KERN_*` segment) of the output Mach-O is one BAR
  id, and there are 55 ids (0..54).
- **Layout** depends only on the section count `B = const + data sections`. If
  `B ≤ 55`, it is split: one segment per section (asserted at B = 55). Otherwise it
  is packed: every non-surface `__data` section goes into **one** segment, and
  every `__const` section into **one** segment (asserted at B = 56). A state
  surface is never packed.
- **Kernel segment.** `__KERN_0` is a separate decision. It is produced by LUT ops
  and by conv, and there is at most one. It is kept only if a BAR id is still
  free; at the edge, it is shed into `__TEXT`.
- So the packed minimum is `N + 1 (data) + 1 (const)`, and `N + 2 ≤ 55 ⇒ N ≤ 53`.
  Without a plain input there is no const segment, so `N + 1 ≤ 55 ⇒ N ≤ 54`.
- **`__DATA` scratch (strong, runner + orchestrator).** Once an intermediate
  tensor exceeds about 2 MiB, the compiler adds a `__DATA.__bss` scratch segment
  (`hwx_layout.py` reports `scratch=1`), so the Mach-O can have 58 load-command
  segments. This segment is **not** a BAR-pool consumer: 53/54 is unchanged.

Why the pool is 55 is **not determined**: it could be hardware BAR registers, or
64 minus reserved ids. Inline-literal conv weights do **not** consume a BAR id.
Weights passed as BLOBFILE remain **untested**: `const`+BLOBFILE is rejected on
h17 (`docs/spec/ane-frontend-h17.md`), and weights fed as plain inputs cost io
ports instead.

**Section economy (established).**
- `#__data` sections = `N + K + plain_out`, where K = number of exposed states.
  The old "`outputs + 2N`" is the K = N case.
- `#__const` sections = declared plain inputs.
- `#0x9442` = `#__data` sections, plus one per intermediate spilled to the
  `__DATA` scratch.

**Practical note.** `mil_convert`'s `--shard` layout keeps **one packed KV
state** per shard (`builder.rs`: `(layers*2, kvh, max_kv, dh)`), so the 53-state
cap does not bind there; the page rule (§7) and the port caps (§1–§3) do. The
cap matters for designs with one state per layer or per head.

## 5. Buffer-binding records: `0x9344`, `0x934a`, `0x9442`

**Format (established for `__FVMLIB` bindings, h17 and h16g).** Each record is 12
bytes:

```
[tag u16][bar_word u16][offset u32][0 u32]
bar_word = 0x2300 + 0x80 · ordinal        (= (0x46 + ordinal) << 7)
offset   = section.addr − segment.vmaddr  (0 when the buffer owns its segment)
```

`ordinal` is the 0-based index of the target `__FVMLIB` segment in load-command
order, i.e. the BAR id. The old reading `(slot_index << 8) | (copy << 7)` is the
same bits (`slot_index = 0x23 + ordinal/2`, `copy = ordinal & 1`), and there is
no "slot holding two records".

**Special bindings (established for no-input programs; strong otherwise).** Some
well-formed records have `bar_word < 0x2300`, which means they bind a buffer that
is not an `__FVMLIB` segment.
- `0x2080` is the source of a `fill` or inline constant (asserted).
- Larger words below `0x2300` bind the `__DATA` scratch.
- Non-uniform per-channel inline constants also produce special words *(runner)*.

`decode_slot_ordinals.py` reports these as `special=` and validates everything
else against the segment table (`format_ok=1`). `bars` counts the referenced
`__FVMLIB` ordinals; the const segment of a dead input is never referenced, so
`bars` can be less than `fvmlib`.

| tag | role |
|---|---|
| `0x9344` | a task's **primary source** binding (an input, a state surface feeding a copy-out task, or a special source) |
| `0x934a` | a **further source** of a binary task |
| `0x9442` | the task's **destination** |

**Block framing and trailers (established; `decode_block_trailers.py`).**
- `__TEXT.__text` is a 0x10-byte preamble followed by a chain of blocks. Each
  block starts 16-byte aligned with `[u16 idx][u16 size]`, where idx = 0, 1, 2, …
  and size is the block length in u32 words including that header word. The
  chain ends exactly at the end of `__text`.
- Every block ends with a **flat** descriptor trailer
  `[9344 12B] [934a 12B]* [9442 12B] [1340 8B] [1341 8B] [1440 8B]` (any subset,
  in this order). The 8-byte members are `[tag u16][0x2200][flags u32]`.
- Nothing is embedded inside `0x9344` or `0x9361`. In `gen_states`-shaped programs
  (plain-input or self-add), no trailer tag occurs outside a trailer, except where
  a state dimension equals a tag value: that value then
  appears as a header u16, and `decode_block_trailers.py` reports `chain_ok=0`.
  `count_desc_records.py`'s raw u16 scan would also count it *(runner)*.
- **Open:** in multi-input add-chain programs (`gen_states_nd … add` with ≥ 5
  inputs), the raw `0x934a`/`0x1341` counts exceed what the trailer parser
  attributes to trailers. These programs emit extra source records that are not
  yet decoded *(runner census, dataset `trailer_census_*.json`)*.
- In `gen_states 53 1 1` there are 107 blocks:
  - one full trailer (block 0, the plain-output add task), with 7 members on h17
    (two `0x934a`) and 6 on h16g
  - 53 trailers of `[9344, 9442, 1340, 1440]`
  - 53 of `[9442, 1440]`

The `ori` page v1 showed a "`0x9344` record" with sub-records at
`+0x0c/+0x18/+0x24/+0x30/+0x38/+0x40`. That is exactly the h17 full trailer laid
end to end (12 + 12 + 12 + 12 + 8 + 8 + 8 bytes). On h16g every member after the
single `0x934a` sits 12 bytes earlier.

v1's "u32 tail (1, 3, 1, 1, 1, 4)" is not part of `0x9344`. It is the **next**
block's pre-frame window (block + 0x1c, up to its first `0x8005` frame). When that
next block is a state-copy block (dim2 = 1, d3 < 129), the window mirrors the copy
record's header: `[1][(stride class + 1) << 16 | 1][0x10001][d3][d2][d1]`. It is
independent of N and dim0, and identical on both arches. At dim1 = 9 it reads
`1,50001,10001,1,1,9` (asserted). Two other forms occur *(runner)*:
- at dim1 = 16 the d1 word is absent and the third word is `0x8001`, the same
  elision as tag `0x9360`
- before a compute block it reads `1,1,10001,d3,d2,d1`

**Counts (established for `gen_states.py`-shaped programs with a plain input,
outside the fan-out regime):**

```
0x9344 = K + max(1, min(in, out))     (N ≥ 1; K = exposed states)
0x9344 = min(in, out)                 (N = 0, out ≥ 1)
```

- `gen_states 53 1 1` gives 54. `gen_states 53 32 32` gives **85**, and it compiles.
- A 53-state noupd program has **1**.
- `0x9344` is therefore **not a state table and does not cap at 54**.
- **Stateless programs always have at least one record**, so the `ori` page's
  "0 records at 0 states" is wrong. With a plain input the count is
  `min(in, out)` (asserted at (1,1); runner at (3,2) and (5,50)). With no plain
  input it is exactly 1, a special binding. A stateless no-input program compiles
  but does not run (`e5_compiler_compile` fails; asserted).
- With no plain input and N ≥ 1, the raw count is K + 1 at N = 1 and K + 2 from
  N = 2 on, with one special (asserted at N = 1 and 2).
- With a computed update source, extra compute tasks add records at
  program-dependent N *(tentative)*.

**`0x934a` (established).** One record per binary-add task whose operands are the
same tensor: 2 per task on h17, 1 on h16g. `gen_states 53 32 32` gives 64 vs 32.
In a single distinct-operand elementwise chain the outputs fuse into one task
*(tentative)*. Multi-input add chains instead show about 2 per add on h17
*(runner census; open)*.
Unary ops emit none *(strong, runner)*.

**Fan-out regime (tentative; fitted at in = 1).** When one live input feeds about
41 or more self-add outputs (`out + ⌈N/2⌉ ≥ 41` at in = 1), the compiler inserts a
copy block. Those outputs lose their `0x934a`/`0x1341`, and the update-row count
becomes N + 1. `gen_states 52 1 50` is inside this regime.

**Trailer flag byte (strong; bit meanings tentative; runner-only).**
- The byte the old text called "constant payload 0x21" exists only in `0x1340`,
  `0x1341` and `0x1440`.
- Values seen: `0x21` = buffer with a single consumer; `0xe1`/`0xc1` = shared by
  ≥ 2 tasks (`0xc1` on the last consumer).
- Only `0x1440` differs between arches: bit `0x10` is set on h16g.

## 6. State-copy records (`0x92xx` / `0x93xx` family)

**Tag (established, h17 = h16g).** Every record is framed by the u16 `0x8005`
followed by one of eight tags. The low bits are presence flags:

```
tag = 0x9261 + 0x100·[dim1 ≠ 1] + 0x004·[dim0 ≠ 1] − 0x001·[dim1 = 16]
```

| bit | meaning | default when absent |
|---|---|---|
| `0x0001` | dim1 field present | dim1 = 16 |
| `0x0004` | dim0 field present | dim0 = 1 |
| `0x0100` | stride word present | stride 0 (dim1 = 1) |

So `0x9365`/`0x9361` are not "write-side"/"read-side" kinds. They are the same
record with different fields present.
- `dim1 = 16` ⇒ `0x9364`/`0x9360` (asserted).
- `dim1 = 1` ⇒ `0x9265`/`0x9261` (asserted).
- `dim0 = 1` ⇒ both roles carry `0x9361` (asserted).

**Exception (established):** a state with `dim3 = 256` **or** `dim2 = 256`, exactly,
emits **no** copy record at all, and the program still runs. 255 and 257 emit
records. The cause is unknown; other special values may exist.

**Roles (established).**
- **Update-row copy** (dim0 field absent): writes the `[1, dim1]` update row into
  the state. There is one per state, except that the first state has none when
  the update source is computed on the ANE, and there are N + 1 in the fan-out
  regime.
- **State-out copy** (dim0 field present when dim0 > 1): copies the full updated
  state to its output port. There is one per **returned** update, and none in a
  noupd program (asserted).

**Header (strong; one open exception: at `[1000,4096]`, an 8 MB state, the dim0
field reads 500).** All fields are LE u32 at 2-byte alignment, at offsets from
the tag: `+0x02` dim3, `+0x06` dim2, then dim1 (if flagged), then dim0 (if flagged),
then the constant `0x14000`, then dim2 again. The stride word is `0x0a` past
`0x14000` (that is `+0x1c` in `0x9365`).

**Stride (established at dim0 = 4, both arches; strong for other dim0 and both
roles).**

```
stride = 8 · min(⌈log2 dim1⌉, 4)       (dim2 = dim3 = 1; measured for dim1 ≤ 4096)
dim1:   1 | 2 | 3–4 | 5–8 | ≥ 9
stride: — | 8 | 16  | 24  | 32
```

The old law `min(2·dim1 + 8, 32)` agrees only at dim1 = 4, 8 and ≥ 12.
*(tentative)* For dim2 > 1 the stride word gains a few bits, and for
`d3 ≥ 129` it gains `2¹⁹`.

**Row width and "region" (strong for dim2 = dim3 = 1; runner-only).**
- With `d3 ≤ 8`: `rowbits = 16·dim1` (row width in fp16 bits) and
  `region = rowbits << 16 = dim1 MiB`. This is a packed row-width field, not a
  vmsize reservation.
- With `d3 > 8`: `rowbits = 16·dim1·⌈d3/8⌉` up to a dim1-dependent saturation
  *(tentative)*, so `region ≠ dim1 MiB`.
- **SHORT/LONG layouts.** State-out records come in two layouts. LONG is 4 bytes
  longer: its `+0x48` holds 1 MiB, and `dim1 MiB` sits at `+0x44`. **When the
  update source is a plain input used directly**, only the last state-out record
  is SHORT (asserted). With a computed source the pattern differs, e.g. 2 SHORT
  at N = 3 and N = 20, and has no closed form.
- **Decoder limits.** `decode_copy_records.py` decodes state-out records with
  dim0 > 1 in either layout. For dim0 = 1 programs both roles share the
  update-row tag, so use `--reads` or `--tags`. A noupd program's first
  update-row, and update-rows with dim2 > 1, decode as `form=other`.

**Word-level fields (established; `decode_copy_words.py`, offsets from the `0x1041`
marker so they hold for every tag; 328/328 state-out records with dim0 ≠ 1 and
dim1 ≠ 1 fit, of 329 decoded).**

| field | value | where (in `0x9365`) |
|---|---|---|
| flag word | `0x8000 | 0x08·[dim1≠1] | 0x20·[dim0≠1] | 0x04·[dim2>1]` (`0x8028` for a dim2 = 1 `0x9365`); `0` when d0 = d1 = d2 = 1, with no pitch or slice words | right after the `0x1342` tag, tag+0x28 |
| **pitch** | `64·⌈d3/32⌉` bytes, the padded row length of the page rule (§7); also holds for dim2 > 1, but the decoder prints it only for dim2 = 1 | tag+0x2e |
| slice | `pitch · dim1` when dim2 = 1, present only when dim0 ≠ 1 and dim1 ≠ 1. With dim2 > 1 this word is `pitch · d2`, and `pitch · d1 · d2` follows at tag+0x36 *(runner)* | tag+0x32 |
| slice copy | `slice` again (equals pitch when slice is elided) | 8 bytes before the end of the core |
| form words | first word `0x803c` SHORT / `0x803e` LONG (sets the record length); second word `0x0142` / `0x0162` | marker+2, marker+4 |

- **The two form words are independent.** Observed pairs: (803c, 0142) ×207,
  (803e, 0162) ×98, (803e, 0142) ×24 (a one-state computed-source program with
  ≥ 2 inputs and ≥ 2 outputs; asserted), and never (803c, 0162).
- **SHORT word map (direct update source):** `1M, RB, RB, RB | RB`, where 1M is
  `⌈d3/8⌉ MiB` for d3 ≤ 128 (2 MiB at d3 = 9, 5 MiB at d3 = 33; asserted). Beyond
  that it caps: 16 MiB for dim1 ≥ 8 from d3 = 129, and 32 MiB at dim1 = 2
  *(runner; not monotone near the cap)*.
- **Direct LONG word map:** `RB, 1M, RB, RB, RB | 2RB` (asserted on the 53-state
  program).
- With a direct source, exactly four words equal `rowbits << 16` in both layouts.
  A computed source (the generator's default `add`) sets extra low bits, e.g.
  `1M|0x10 … RB|0x40` in SHORT, so only three words equal RB *(runner)*.
  `rowbits` is a u16 and wraps mod 2¹⁶.
- No Mach-O segment size tracks these words: every `__FVMLIB` vmsize is 16 KiB.
  The old "region vmsize" reading has no counterpart.
- **What v2 actually saw.** The `ori` page v2 compared `[4,4]` and `[32,8]` and
  reported 9 varying bytes, including "`+0x42` selector `0x42 → 0x62`" and
  "`+0x33` flag `01 → 02`". Two one-state SHORT records actually differ at
  `0x0a 0x0e 0x1c 0x33 0x4a 0x4e 0x52 0x5e 0x77` (asserted).
  - `+0x33` is the second byte of `slice` (dim1/4).
  - `+0x42` stays `0x42` in every SHORT record; `0x62` is the low byte of the LONG
    word `0x0162`, which non-last records of multi-state programs carry.

**The update-row record is not a fixed template.** It carries dim1, the stride
word, rowbits and a per-record buffer binding (asserted at dim1 = 8). The old
"byte-identical across shapes and counts" compared only two programs that
differed in dim0, the one dimension this record leaves out.

**Cost-like field (strong; meaning unknown; runner-only).** In compact update-row
records, a u16 equals `⌊dim0·dim1·2 / K⌋` with K = 450 on h17 and 534 on h16g.

## 7. State execution and size limits

**Page rule (strong; 190+ shapes in round one, held-out shapes in round two,
0 misses; 9 points asserted).** An fp16 state `[d0,d1,d2,d3]` always compiles,
but it **executes** only if

```
rows = d0·d1·d2,  true = rows·d3·2,  padded = rows·64·⌈2·d3/64⌉
ceil(true / 16384) == ceil(padded / 16384)
```

Otherwise it fails with `status=0x1d : statusType=0x9: Program Inference error`.
`scripts/state_exec_predict.py` implements the rule. **The 64-B row is in the
compiled record:** the copy record's `pitch` word is `64·⌈d3/32⌉`, so
`padded = rows · pitch` exactly. At `[4,4,1,33]` the pitch is 128 and
padded = 16 · 128 = 2048, which is what the predictor computes. The rule's
"padding" is the compiler's own row pitch. **Use the predictor; the
shortcuts are only sufficient conditions.**
- `d3 % 32 == 0` ⇒ there is no padding, so the state always executes. Very large
  states run, e.g. `[4,16,1,16384]`.
- `d3 ≤ 32` and `rows ≤ 256` ⇒ the state executes. `rows ≤ 256` is *necessary*
  only for `d3 ≤ 16`: `[1,300,1,31]` runs, `[1,260,1,31]` fails (both asserted).
- `d3 > 32` and not a multiple of 32 ⇒ small row counts can already fail:
  head_dim 80 runs at 85 rows and fails at 86 (both asserted). Pad such a d3 to a
  multiple of 32.
- **Read-back is padded.** A state with `d3 % 32 ≠ 0` is stored with 64-B row
  padding, so a host read of the state image is not dense *(strong, runner)*. The
  returned update tensor is dense.

**State dtype (established).** fp16, int16, int8, uint8 and bool states compile and
run when the io and compute around them stay in supported dtypes; int8 and bool
are asserted. fp32 states fail (`CompilationFailure`) and int32 states fail
(`status=0x1`). The earlier "fp16 only" result came from changing the whole
program's dtype: an int8 `add` is itself rejected.

**Compile-time size caps (tentative).** Very large states are rejected
(`CompilationFailure`) in a way that depends on rows (every axis except W), e.g.
`[1,x,1,1]` above x = 2²². W-heavy states compile far past 16 MiB.

## 8. h16g (M4) vs h17 (M5)

All h16g evidence is **cross-compiled on the M5 host**. It shows compiler-output
equivalence, not M4 behaviour. The runtime caps (127, the page rule) and loading
are **unmeasured on M4**. The only M4 available is also the only macOS 27.0 host
(ADR-0002 Appendix A), so a run there changes SoC and OS at once.

Established (compile time):
- the same frontend cap (asserted at 128 + 128)
- the same BAR pool (asserted at 54 with a plain input)
- the same slot-ordinal decode
- the same stride law (asserted at dim1 = 5)
- `0x934a` 1 vs 2 per binary-add task (asserted)

Byte deltas *(runner)*. Record counts other than `0x934a` are equal on 123 grid
programs. The bytes that differ are:
- Mach-O `cpusubtype` 7 → 9
- the `0x1440` flag bit `0x10`
- the last u16 of each copy record, `0x0010` → `0x0020`
- a middle-block header word
- `ModelMaxDramUsage`, which grows by the `__text` growth

Everything else (`0x9344`, `0x9442`, `0x1340`, `0x1341`, …) is byte-identical.

## 9. Planning rules for a compiler or scheduler

For one `main` on h17, macOS 26.7.1:

1. **Ports at execution:** `live_in + n_states + unique_out + n_exposed_states ≤ 127`.
   Liveness roots are the returned outputs **and** every `write_state`. Return a
   state's update only if you need it; each one costs a port. *Persistence of
   non-returned updates across steps* was spot-checked by one skeptic
   (read-back), not asserted. Treat it as likely, not proven (open Q4).
2. **Ports at the frontend:** `declared_in + n_states + out + n_exposed_states ≤ 255`.
   Drop dead inputs before validate/compile, because those paths count them.
3. **States:** `N ≤ 55 − [any plain output or exposed state] − [any plain input]`,
   so 53 in practice. Inline conv weights and LUT ops don't lower it; BLOBFILE
   weights are untested.
4. **State shape:** if `d3 % 32 == 0`, it executes. Otherwise ask
   `state_exec_predict.py`. Shorthand: `d3 ≤ 32 and d0·d1·d2 ≤ 256` is safe; pad
   d3 values like 80 up to 96 or 128. head_dim 64/128 KV layouts
   `[2L, kvh, S, hd]` already satisfy `d3 % 32 == 0` for any S.
5. **State dtype:** fp16, int16, int8, uint8 or bool; not fp32 or int32.
6. **Budgets are counts.** Port width and state size do not move rules 1–3 (port
   width is asserted; state size is runner-checked).
7. **Never return an input unchanged.** It is returned as zeros on the run path.
8. Pass `--arch` explicitly to validate/compile. Re-run
   `./scripts/evidence-check.sh --require-all docs/spec/ane-port-limits-h17.spec` on
   any new OS build or SoC before trusting these numbers there.

**What this does not cover.**
- **Graphs:** every probe is a small elementwise graph (add/mul/sub/unary, LUT
  ops, one conv form) over fp16 rank-4 tensors. No matmul, attention, softmax over
  long axes, or fused real-model graphs.
- **Numerics:** a pass is exit 0 plus a timing line. Outputs were spot-checked,
  not compared.
- **State updates:** all are constant-index row writes at `begin = [0,0,0,0]`
  along d0. Runtime-position appends, updates along d3, and attention-style reads
  are untested.
- **Scope:** one function, one host, one OS build, the e5rt run lane. The CoreML
  lane and multi-function programs are unmeasured.

---

## Corrections to the previous version

| Previous claim | Status | What holds instead | Spec § |
|---|---|---|---|
| `out_cap(in) = max(63, 127 − in)`, "floored at 63" | **wrong** | `live_in + out ≤ 127`, no floor; the floor came from dead inputs | 1 |
| "NOT frontend"; "frontend accepts 200+ io ports" | incomplete | frontend cap `declared_in + out ≤ 255` | 2 |
| "Plain io does not share the state budget" (53 st + 32 in + 32 out) | **wrong** for execution | it compiles, but states are io ports and 170 > 127, so it does not run | 3 |
| "53 states compile + run; 54 fail" as the cap | incomplete | 55-id BAR pool; 54 states fit without a plain input | 4 |
| "`__data` segments = outputs + 2 × states" (surface + working buffer) | special case | sections = N + exposed + outputs | 5 |
| "`0x9344` = states + 1 header; the table holds 54 records" (WHY 54 "resolved") | **wrong** | buffer bindings, K + max(1, min(in, out)); 85 and 1 at 53 states | 5 |
| Slot word = (slot, copy), "slots each holding 2 records" | reinterpreted | the bits are a segment's BAR ordinal (same bits, so no line can fail on this) | 5 |
| `0x9442` = "2N + 1 segment family", unprobed | **wrong** | one destination binding per `__data` section (+ spilled intermediates) | 5 |
| `0x934a`: "one extra per program on M5, fixed" | **wrong** | +1 per binary-add task on h17 | 8 |
| Embedded children carry "constant payload 0x21" | **wrong** | a flags byte; arch bit on `0x1440` only (runner-only) | — |
| `0x9361` "fixed template, byte-identical across shapes and counts" | **wrong** | the update-row record carries dim1, stride and rowbits | 6 |
| `0x9365` stride `min(2·dim1 + 8, 32)` | **wrong** | `8·min(⌈log2 dim1⌉, 4)`, saturating at dim1 = 9 | 6 |
| Region `dim1 × 1 MiB` "vmsize reservation, ×4 slots" | reinterpreted | `rowbits << 16` for d3 ≤ 8; LONG/SHORT layouts | 6 |
| M4 → M5 "identical, the only delta one `0x934a`" | incomplete | same compile-time counts and laws; arch bytes differ in `0x1440`, copy-record tails and block headers | 8 |
| Spec "executable assertions for all of it" | was false | the pass side was vacuous; every headline law now has a line that fails under the old claim | — |

**Second-pass corrections (re-evaluation of this rewrite, same day).** The
first draft of this rewrite stated nine things wrongly, and they were caught by
held-out testing and audit before merge:
- "fp16 states only"
- "`d3 < 32` needs `rows ≤ 256`" (a necessity claim)
- a planning rule 4 that admitted head_dim-80 states that fail
- `live_in` without `write_state` roots
- the binding format and `0x9442` laws stated without the special-word and
  scratch domains
- "weights cannot be compiled"
- "dim3 = 256" alone as the no-copy exception
- zero-output behaviour
- "every claim has a spec line"

Each now has a spec line or an explicit *(runner-only)* label.

## The ori pages (v1–v3), claim by claim

The visual companion first lived in the `ori` workspace as `ane-descriptor-economy`:
- v1 at 09:12, v2 at 09:14 (adds the read/write asymmetry and byte table), and
  v3 at 09:42 (adds "WHY 54" and the M4/M5 delta), all on 2026-10-22.
- sha256: v1 `ac3179c2…3418d0e`, v2 `4e1e932e…bc7112`, v3 `1ab9a17b…64ccfb7`.

A Haiku runner classified all **91** factual claims on the three versions against
this writeup:

| status | count |
|---|---|
| refuted | 37 |
| partially true | 26 |
| holds | 14 |
| holds, reinterpreted | 6 |
| not settled by this writeup | 8 |

Two Sonnet runners then measured the 8 unsettled claims, and they are settled
above. The headline items:

| page claim | status | now | § |
|---|---|---|---|
| "descriptor table cap: 54 slots; 53 states + 1 header" | refuted | 55-id BAR pool; `0x9344` is not a table | 4, 5 |
| "53 states is the hard ceiling, independent of io, dtype, stripe width, segment count" | partially true | independent of **dtype** (newly measured) and stripe width; not of io (states cost ports) or segment kind (54 without a plain input) | 3, 4 |
| "cost per state: 2 `__data` segs + 1 slot" | refuted | `N + K + plain_out` sections; one segment per state surface | 4 |
| "`0x9344` record: `0x934a`×2 at +0x0c/+0x18, `0x9442` at +0x24, 1340/1341/1440 at +0x30/+0x38/+0x40" | holds, reinterpreted | the h17 full trailer laid end to end | 5 |
| "u32 tail (1, 3, 1, 1, 1, 4) — type/count constants" | refuted | the next block's pre-frame window, mirroring the copy header | 5 |
| "payload 0x21 (33, constant)" | refuted | flags byte (0x21 / 0xc1 / 0xe1; 0x31 on h16g) | 5 |
| "0 states: 0 records" | refuted | at least 1 record always | 5 |
| "`0x9361` read: fixed template; `0x9365` write: carries the shape" | refuted | one record type with presence flags; both carry dim1/stride | 6 |
| "stride = `min(2·dim1 + 8, 32)`" | refuted | `8·min(⌈log2 dim1⌉, 4)` | 6 |
| "+0x40 shape-class selector (dim1 ≤ 4 vs ≥ 8)", "+0x42: 0x42 → 0x62" | refuted | SHORT/LONG form words, independent of shape | 6 |
| "+0x33 flag byte 01 → 02" | holds, reinterpreted | second byte of `slice = 64·dim1·⌈d3/32⌉` | 6 |
| "+0x44 constant 0x00100000" | partially true | `⌈d3/8⌉ MiB` in SHORT records; RB in LONG | 6 |
| "region vmsize = dim1 × 1 MiB, ×4 identical reservations" | partially true | four `rowbits << 16` words (= dim1 MiB only for d3 ≤ 8); not a vmsize | 6 |
| "`out_cap(in) = max(63, 127 − in)`; frontend accepts 200+" | refuted / incomplete | `live_in + out ≤ 127`; frontend ≤ 255 | 1, 2 |
| "M4 → M5 identical; only delta one `0x934a`" | partially true | compile-time laws equal; `0x934a` +1 per add task; arch bytes differ | 8 |
| "`__text` vmsize grows linearly with states" | holds *(runner: `__text` ≈ 320 + 384·N bytes in `gen_states`)*, but it is not why the cap exists | — | 4 |
| "Every number is reproduced; nothing here is guessed" | refuted | the page's spec checks were vacuous on the pass side | — |

## Open questions

1. **Why 55 BAR ids,** and do BLOBFILE weights consume one?
2. **Where 127 and 255 come from,** and whether they are per function. The CoreML
   lane and multi-function programs are unmeasured.
3. **M4 silicon,** with a toolchain on the 27.0 M4 host. A run there confounds SoC
   and OS.
4. **State semantics.** Is persistence across steps for non-returned updates
   reliable (assert it with a read-back)? What do multiple writes, cross-state
   copies, runtime-position appends and `[1,H,S,D]` KV layouts with real S cost?
5. **Copy-record details:** SHORT/LONG with computed sources; why `dim1 = 16` (16
   elements or 32 bytes?) and `dim2/dim3 = 256` are special; the cost-like field;
   the d3 and dim2 sub-laws.
6. **Fan-out threshold** for non-add ops, and for N > 0 at in > 1.
7. **Numerics:** add value checks for boundary programs, including the LUT table
   shed into `__TEXT` at N = 53.

## Reproduce

```sh
cd vendor/mil_spec && cargo build --release -p milc && cd ../..          # the spec also does this itself
./scripts/evidence-check.sh --require-all docs/spec/ane-port-limits-h17.spec   # SKIP must not pass silently
python3 scripts/state_exec_predict.py 1 1 86 80                         # will this state execute?
```
