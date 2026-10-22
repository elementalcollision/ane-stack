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
> The `ori` page `ane-descriptor-economy` (v1–v3) predates this re-measurement
> and draws the refuted model (54-slot table, read/write asymmetry). Do not
> extrapolate from it.

## Build provenance

| Field | Value |
|---|---|
| SoC | Apple M5 Max (Mac17,7, exposes `h17`) |
| macOS | 26.7.1 (25G241) |
| Compiler | `zin_ane_compiler v9.510.0` (from the HWX `LC_IDENT`); coremlc 3600.25.1 |
| h16g (M4) data | **cross-compiled on this M5 host only**. Nothing was loaded or run on M4 silicon. |
| Probes | `milc ane validate \| compile \| run` on generated `program(1.3)` MIL. **`validate`/`compile` default to `--arch h16g`**: always pass `--arch h17` (the spec does). `run` ignores `--arch`, so its results are always the host's. |
| Generators | `gen_live_ports.py` (every input live), `gen_mix_ports.py` (inputs beyond `out` are dead), `gen_dup_returns.py`, `gen_states.py`, `gen_states_width.py`, `gen_states_nd.py` (4-D state, `add`/`direct` update source, `noupd`, `in=0`, `conv=K`, `lut=…`), `gen_state_dtype.py` |
| Decoders | `count_desc_records.py`, `decode_slot_ordinals.py`, `hwx_layout.py`, `decode_copy_records.py`, `state_exec_predict.py` |
| Method | Four hardware runners re-measured each law family (the io runner alone made 3,886 `milc` calls; the others compiled ~900, ~1,300 and ~1,900 artifacts). Every boundary was run at least twice with 0 flips; the ANE may have been shared between runners. The decisive points were re-run by the orchestrator. A second round tested held-out points against this text (the corrections are listed at the end). |
| Spec | 84 probes, 176 assertions, PASS in ~18 s; `require_hw`-gated, and it builds milc itself |
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

**Domain.** fp16 rank-4 ports, one `main` function, `milc ane run`. **Not
measured:** fp32/int32 ports, rank ≠ 4, multi-function programs, the CoreML
lane, M4 silicon.

**Where the old "floor at 63" came from.** `gen_mix_ports.py` makes output `i`
read `x{i % in}`, so with `in > out` only the first `out` inputs are referenced,
and the run path drops the rest. At `in ≥ 64` the observed "max out = 63" was
really the diagonal `live_in = out = 63`, since 126 ≤ 127.

## 2. Frontend io cap: `declared_in + out ≤ 255`

**Law (established).** Both `milc ane validate` and `milc ane compile` reject a
program once `declared_in + out ≥ 256`. The failure is exit 1, `status=0x1 rc=1`,
`error: MaxLiveInLiveOutExceeded`.
- The boundary holds on h17 and h16g. The spec asserts it on validate for both
  arches and on compile for h17. The runners swept every split on validate and
  19 splits on compile.
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

These are flat members of a per-block descriptor trailer
`[9344] [934a]* [9442] [1340] [1341] [1440]` (any subset, in this order). Nothing
is "embedded inside" `0x9344` or `0x9361` *(strong, runner)*.

**Counts (established for `gen_states.py`-shaped programs with a plain input,
outside the fan-out regime):**

```
0x9344 = K + max(1, min(in, out))     (N ≥ 1; K = exposed states)
0x9344 = min(in, out)                 (N = 0, out ≥ 1)
```

- `gen_states 53 1 1` gives 54. `gen_states 53 32 32` gives **85**, and it compiles.
- A 53-state noupd program has **1**.
- `0x9344` is therefore **not a state table and does not cap at 54**.
- With no plain input, the raw count is K + 2 (one special).
- With a computed update source, extra compute tasks add records at
  program-dependent N *(tentative)*.

**`0x934a` (established).** One record per binary-add task whose operands are the
same tensor: 2 per task on h17, 1 on h16g. `gen_states 53 32 32` gives 64 vs 32.
Distinct-operand elementwise ops fuse into one task per program *(tentative)*.
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

**Header (strong).** All fields are LE u32 at 2-byte alignment, at offsets from
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
`scripts/state_exec_predict.py` implements the rule. **Use the predictor; the
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
