# ANE resource budgets on h17 — io ports, the BAR pool, and the HWX records

> **Living document, re-measured 2026-10-22.** Every law below has a domain (what
> was varied), a confidence label, and the section of
> `docs/spec/ane-port-limits-h17.spec` that asserts it. This version **supersedes**
> the 2026-10-21/22 text: five of its headline laws did not reproduce (see
> [Corrections](#corrections-to-the-previous-version)). If a sentence here has no
> spec line and no domain, treat it as a hypothesis.
>
> Confidence labels: **established** = dense measurement, boundaries repeated,
> asserted by the spec; **strong** = consistent over many programs but the
> mechanism is inferred or only partly asserted; **tentative** = fitted on few
> points or a single generator family.
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
| h16g (M4) data | **cross-compiled on this M5 host only**; nothing was loaded or run on M4 silicon |
| Probes | `milc ane validate \| compile \| run` on generated `program(1.3)` MIL |
| Generators | `gen_live_ports.py` (every input live), `gen_mix_ports.py` (inputs beyond `out` are dead), `gen_dup_returns.py`, `gen_states.py`, `gen_states_width.py`, `gen_states_nd.py` (4-D state shape, `add`/`direct` update source, `noupd`, `in=0`) |
| Decoders | `count_desc_records.py`, `decode_slot_ordinals.py`, `hwx_layout.py`, `decode_copy_records.py`, `state_exec_predict.py` |
| Method | Re-measured by four independent hardware runners (~4,000 `milc` calls, every boundary run at least twice, 0 flips), then the decisive points re-run by the orchestrator. Spec: 60+ assertions, PASS in ~14 s. |
| Date | 2026-10-22 |

Reading a run result: a **passing** `milc ane run` exits 0 and prints a line that
starts `step 0: <time>`. A **failing** one exits 1 and prints
`milc ane run: step 0: execute_sync → 11 … Program Inference error`, which also
contains `step 0:`. Always judge by exit code.

---

## The model in one table

| # | Budget / law | Where it bites | Boundary on h17 (this build) | Confidence | Spec § |
|---|---|---|---|---|---|
| 1 | Execution io cap | `execute_sync` | `live_in + unique_out ≤ 127` (no floor) | established | 1 |
| 2 | Frontend io cap | `ANECValidate` / `ANECCompile` | `declared_in + out ≤ 255` (`MaxLiveInLiveOutExceeded`) | established | 2 |
| 3 | States cost io ports | both caps | each state = 1 input port; each returned update = 1 output port | strong | 3 |
| 4 | BAR pool (the state cap) | `ANECCompile` (`ZinBarIdManager`) | 55 BAR ids = 55 `__FVMLIB` segments; each state owns one ⇒ **53 states** with a plain input, **54** without | established (count) / strong (mechanism) | 4 |
| 5 | Buffer-binding records | HWX `__text` | `0x9344`/`0x934a`/`0x9442` = 12-byte bindings; slot word = segment ordinal | established | 5 |
| 6 | State-copy records | HWX `__text` | tag = presence flags; stride = `8·min(⌈log2 dim1⌉, 4)` | established | 6 |
| 7 | State execution size | `execute_sync` | 64 B row padding must not add a 16 KiB page (`d3 < 32` ⇒ `d0·d1·d2 ≤ 256`) | strong | 7 |
| 8 | h16g vs h17 | compiler output | same caps and laws; `0x934a` 1 vs 2 per binary-add task | established (cross-compile) | 8 |

---

## 1. Execution-time io cap: `live_in + unique_out ≤ 127`

**Law (established).** A program executes on the ANE iff

```
live_in + unique_out (+ n_states + n_exposed_states, see §3) ≤ 127
```

- `live_in` counts declared inputs that are **reachable from a returned output**.
  Unreferenced inputs, inputs read only by a dead op, and inputs read only by a
  dead add-chain are not counted. Reachability is what counts, not value
  dependence: `x · 0` added into an output still counts.
- `unique_out` counts **distinct returned tensors**. One tensor listed 200 times in
  the return tuple is one port.
- There is **no floor**. (126, 1) runs; (127, 1), (65, 63) and (100, 28) fail.
- Failure: exit 1, `status=0x2 : statusType=0x9: Program Inference error`.
- It is a **count** budget. Ports from `[1,4,1,1]` up to `[1,262144,1,1]` (512 KiB
  each, 64 MiB aggregate) and `[1,16,64,64]` hit the same boundary.

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
(IN, 128−IN) FAIL for every IN in 1..126, twice: 504 runs, 0 anomalies.

**Domain.** fp16 rank-4 ports, IN 1..126, OUT 1..254, one `main` function,
`milc ane run`. **Not measured:** fp32/int32 ports, rank ≠ 4, multi-function
programs, the CoreML lane, M4 silicon.

**Where the old "floor at 63" came from.** `gen_mix_ports.py` makes output `i` read
`x{i % in}`, so with `in > out` only the first `out` inputs are referenced, and the
run path drops the rest. At `in ≥ 64` the observed "max out = 63" was really the
diagonal `live_in = out = 63` (126 ≤ 127). The old spec only probed in ≤ 64, where
`max(63, 127−in)` and `127−in` agree.

## 2. Frontend io cap: `declared_in + out ≤ 255`

**Law (established).** `milc ane validate` and `milc ane compile` reject a program
once `declared_in + out ≥ 256`, with exit 1, `status=0x1 rc=1` and
`error: MaxLiveInLiveOutExceeded`. This holds on h17 and h16g, at every split
(a sweep over IN 1..254 for validate on both arches, plus 19 asymmetric splits
for compile).

- validate/compile count **declared** inputs, dead ones included: (254, 1) ok,
  (255, 1) rejected.
- The run path prunes dead inputs first, so there the same 255 applies to
  `live_in + out`. A file that validate rejects can still run: `gen_mix_ports 255 1`
  runs. When the run path does exceed 255 live ports, it fails as
  `ANECCompile() FAILED`.
- The frontend check comes before the execution check: 128 + 128 live ports is a
  frontend rejection, while 127 + 128 reaches execution and fails there.
- On the validate/compile path, an input whose **only** use is a dead op makes the
  program fail with `CompilationFailure` (strong); the run path prunes it.
- Zero-output programs are rejected by validate (`CompilationFailure`). `compile`
  still emits an artifact, but it does not load or run.

So "the frontend accepts 200+ io ports" is true up to 255 declared ports and false
from 256. The old spec's comment "frontend accepts 128" referred to 64 + 64.

## 3. States cost io ports

**Law (strong; boundaries asserted).** In both caps, every `state<>` param counts
as **one input port**, and every state whose updated tensor is returned counts as
one more **output port** (it is an ordinary output). For the execution cap:

```
(live_in + n_states) + (unique_out + n_exposed_states) ≤ 127
```

| program | ports | runs? |
|---|---|---|
| 53 states, all updates returned, 1 in, 20 out | 53+1+53+20 = 127 | yes |
| same, 21 out | 128 | no (`status=0x2`) |
| 53 states, **no** update returned, 1 in, 73 out | 53+1+73 = 127 | yes |
| same, 74 out | 128 | no |
| `gen_states.py 53 32 32` (the old spec's "plain io does not share the budget" program) | 53+32+53+32 = 170 | **compiles, does not run** |

Practical consequence: a program that returns all of its state updates has 21
plain io ports left at 53 states. Not returning the updates frees one port per
state. The frontend cap counts states the same way, so with all updates returned
N ≤ 126 validates (1 plain in, 1 plain out).

**Domain.** States `[4,4]`, `[1,4]`, `[4,1]`, `[4,16]`, `[4,64]`, `[64,4]`,
`[4,32]`; N in {0, 1, 2, 10, 26, 53}; IN in {1, 32}. **Not measured:** read-only
states and states read twice; whether a state's port cost differs on the CoreML
lane.

## 4. The BAR pool: why 53 (and when 54)

**Count (established).**

| program | `__FVMLIB` segments | compiles | runs |
|---|---|---|---|
| 53 states + 1 plain in + 1 out | 55 | yes | yes |
| 54 states + 1 plain in + 1 out | — | **no**: `ZinBarIdManager::GetNextAvailableBarId(): unable to allocate free BAR` (milc exit 1, `status=0x16 rc=22`) | — |
| 54 states, **no plain input** (update source = `fill`), 1 out | 55 | **yes** | **yes** |
| 55 states, no plain input, 1 out | — | no (`free BAR`) | — |
| 53 states, `[64,32]` each, 32 in + 32 out | 55 | yes | (exceeds §3/§7) |
| 54 of the same | — | no | — |
| 53 states, **no update returned** (one `0x9344` in the whole program) | 55 | yes | yes |
| 54 of the same | — | no | — |

The same 53/54 boundary holds for state shape (dim0 4..256, dim1 1..64, mixed
shapes), op count and kind (chains up to 200 ops, LUT ops), plain io 1..100,
read-only vs read-update-write states, the number of exposed states, and arch
(h16g). Only removing a shared segment moves it. With no plain input, 54 states
fit. With no output, 54 compile, but the bundle does not load.

**Mechanism (strong; inferred from the compiled HWX, not from allocator source).**

- Every `__FVMLIB` segment of the output Mach-O is one BAR id, and there are
  55 ids (0..54). The Mach-O never has more than 57 `LC_SEGMENT_64`: 55 `__FVMLIB`
  (or `__KERN_*`) segments + `__PAGEZERO` + `__TEXT`. Across 1,284 artifacts, 0
  violations.
- **Split layout.** If the unpacked layout fits, every section gets its own
  segment: `N` state surfaces, one copy-out buffer per exposed state, one per
  plain output, one per **declared** plain input, plus `__KERN_0` if the program
  has a lookup-table op (sigmoid/tanh/softmax/exp/…).
- **Packed layout.** Otherwise the compiler sheds `__KERN_0` (folding the table
  into `__TEXT`), packs every non-surface `__data` section into **one** segment
  and every `__const` section into **one** segment. A state surface is never
  packed.
- So the packed minimum is `N + 1 (data) + 1 (const)`, and `N + 2 ≤ 55 ⇒ N ≤ 53`.
  Without a plain input there is no const segment, so `N + 1 ≤ 55 ⇒ N ≤ 54`.

Why the pool is 55 is **not determined**: it could be hardware BAR registers, or
64 minus reserved ids. **Untested:** whether a weight segment (conv/matmul
BLOBFILE) is an unpackable consumer. If it is, real models get **fewer than 53**
states. Weighted programs could not be compiled through `milc ane compile` here.

**Section economy (established).**
- `#__data` sections = `N + K + plain_out`, where K = number of exposed states.
  The old "`outputs + 2N`" is the K = N case, which every repo generator happens
  to produce.
- `#__const` sections = declared plain inputs.
- `#0x9442` = `#__data` sections.

## 5. Buffer-binding records: `0x9344`, `0x934a`, `0x9442`

**Format (established, h17 and h16g).** Each record is 12 bytes:

```
[tag u16][bar_word u16][offset u32][0 u32]
bar_word = 0x2300 + 0x80 · ordinal        (= (0x46 + ordinal) << 7)
offset   = section.addr − segment.vmaddr  (0 when the buffer owns its segment)
```

`ordinal` is the 0-based index of the target `__FVMLIB` segment in load-command
order, i.e. the BAR id. The old reading `(slot_index << 8) | (copy << 7)` is the
same bits (`slot_index = 0x23 + ordinal/2`, `copy = ordinal & 1`). There is no
"slot holding two records".

| tag | role |
|---|---|
| `0x9344` | a task's **primary source** binding (an input, or a state surface feeding a copy-out task) |
| `0x934a` | a **further source** of a binary task |
| `0x9442` | the task's **destination** (one per `__data` section) |

They are flat members of a per-block descriptor trailer that ends every block of
`__TEXT.__text`. The trailer grammar is `[9344] [934a]* [9442] [1340] [1341] [1440]`
(any subset, in this order). Nothing is "embedded inside" `0x9344` or `0x9361`.
`decode_slot_ordinals.py` validates every record against the segment table.

**Counts (established for `gen_states.py`-shaped programs):**

```
0x9344 = K + max(1, min(in, out))     (N ≥ 1; K = exposed states)
0x9344 = min(in, out)                 (N = 0, out ≥ 1)
```

- `gen_states 53 1 1` → 54. `gen_states 53 32 32` → **85**, and it compiles.
  A noupd 53-state program → **1**.
- `0x9344` is therefore **not a state table and does not cap at 54**. The old
  "N + 1 (one header)" is the case K = N with one live input.
- When the update source is a computed tensor (`gen_states_nd.py … add`), extra
  compute tasks add records at program-dependent N. This is **tentative** and not
  modelled.

**`0x934a` (established).**
- One record per binary-add task whose operands are the same tensor
  (`y = add(x, x)`): 2 per task on h17 and 1 on h16g.
- `gen_states 53 32 32` gives 64 on h17 and 32 on h16g.
- Distinct-operand elementwise ops fuse into one task per program (tentative), so
  the "+1 per program" reading is only true there.
- Unary ops emit none.

**Fan-out regime (strong).** When one live input feeds about 41 or more self-add
outputs (`out + ⌈N/2⌉ ≥ 41` at in = 1), the compiler inserts a copy block and
drops those outputs' `0x934a`/`0x1341` records. `gen_states 52 1 50`, the old
writeup's "decisive" example, is inside this regime.

**Trailer flag byte (strong; bit meanings tentative).**
- The byte the old text called "constant payload 0x21" exists only in `0x1340`,
  `0x1341` and `0x1440`.
- Values seen: `0x21` = buffer with a single consumer; `0xe1`/`0xc1` = shared by
  ≥ 2 tasks (`0xc1` on its last consumer).
- Only `0x1440` differs between arches: bit `0x10` is set on h16g (`0x31`/`0xf1`).
- It is a flags byte, not a constant, so "why 33?" was the wrong question.

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
- `dim1 = 16` ⇒ `0x9364`/`0x9360`.
- `dim1 = 1` ⇒ `0x9265`/`0x9261`.
- `dim0 = 1` ⇒ both roles carry `0x9361`.
- Exception: `dim3 = 256` emits no copy record at all, and the program still runs.

**Roles (established).**
- **Update-row copy** (dim0 field absent): writes the `[1, dim1]` update row into
  the state. There is one per state, except that the first state has none when
  the update source is computed on the ANE.
- **State-out copy** (dim0 field present when dim0 > 1): copies the full updated
  state to its output port. There is one per **returned** update, and none in a
  noupd program.

**Header (strong).** All fields are LE u32 at 2-byte alignment, at offsets from
the tag: `+0x02` dim3, `+0x06` dim2, then dim1 (if flagged), then dim0 (if flagged),
then the constant `0x14000`, then dim2 again. The stride word is `0x0a` past
`0x14000` (that is `+0x1c` in `0x9365`).

**Stride (established, h17 = h16g).**

```
stride = 8 · min(⌈log2 dim1⌉, 4)       (dim2 = dim3 = 1)
dim1:   1 | 2 | 3–4 | 5–8 | ≥ 9
stride: — | 8 | 16  | 24  | 32
```

The law is independent of dim0 and N, and identical in both roles. The old law
`min(2·dim1 + 8, 32)` agrees only at dim1 = 4, 8 and ≥ 12. dim2 > 1 adds bits to
the stride word (tentative sub-law).

**Row width and "region" (strong).** `rowbits = 16·dim1` (row width in fp16 bits,
mod 2¹⁶), and `region = rowbits << 16 = dim1 MiB`. It is a packed row-width field,
**not a vmsize reservation**. State-out records come in two layouts, SHORT and
LONG. LONG is 4 bytes longer, and its `+0x48` holds a constant 1 MiB, so
`dim1 MiB` sits at `+0x44`. In plain-input programs only the **last** state-out
record is SHORT. That is why the old first-record decoder printed `region=1048576`
on every multi-state binary. `decode_copy_records.py` decodes every record in
either layout.

**The update-row record is not a fixed template.** It carries dim1, the stride
word, rowbits and a per-record buffer binding. The old "byte-identical across
shapes and counts" compared only two programs that differed in dim0, which is
the one dimension this record leaves out.

**Cost-like field (strong; meaning unknown).** In compact update-row records, a
u16 equals `⌊dim0·dim1·2 / K⌋` with K = 450 on h17 and 534 on h16g. It may be a
compiler cost estimate. Its units and its consumer are unknown.

## 7. State execution and size limits

**Page rule (strong; 190+ shapes, 0 misses; three points asserted).** An fp16
`state<tensor<fp16,[d0,d1,d2,d3]>>` always compiles, but it **executes** only if

```
rows = d0·d1·d2,  true = rows·d3·2,  padded = rows·64·⌈2·d3/64⌉
ceil(true / 16384) == ceil(padded / 16384)
```

- Otherwise it fails with `status=0x1d : statusType=0x9: Program Inference error`.
- Corollaries: with `d3` a multiple of 32 there is no padding, and very large
  states run (`[4,16,1,16384]`). With `d3 < 32`, a state needs `d0·d1·d2 ≤ 256`.
  `[4,64,1,1]` runs and `[4,65,1,1]` fails.
- `state_exec_predict.py` implements the rule.
- For KV caches this means: put the long axis in `d3` as a multiple of 32.

**dtype (established).** Only fp16 states compile on this path. fp32 fails with
`CompilationFailure`; int8/uint8/int16/int32/bool fail with `InvalidMILProgram`.

**Compile-time size caps (tentative).** Very large states are rejected
(`CompilationFailure`) in a way that depends on rows (every axis except W), e.g.
`[1,x,1,1]` above x = 2²². W-heavy states compile far past 16 MiB. The formula is
unknown.

## 8. h16g (M4) vs h17 (M5)

All h16g evidence is **cross-compiled on the M5 host**. That shows compiler-output
equivalence, not M4 silicon behaviour. Established:

- Same frontend cap (255), same BAR pool (53 / 54 states), same slot-ordinal
  decode, same stride and row laws.
- `0x934a`: 1 per binary-add task on h16g, 2 on h17. The h17 surplus is +1 **per
  add task**, not +1 per program.
- Every other record **count** is equal on 123 grid programs. Record **bytes**
  differ in arch fields:
  - Mach-O `cpusubtype` 7 → 9
  - the `0x1440` flag bit `0x10`
  - the last u16 of each copy record, `0x0010` → `0x0020`, which is a granule
    constant and not a stride cap
  - a middle-block header word
  - `ModelMaxDramUsage`, which grows by the `__text` growth

## 9. Planning rules for a compiler or scheduler

For one `main` on h17, macOS 26.7.1:

1. **Ports at execution:** `live_in + n_states + unique_out + n_exposed_states ≤ 127`.
   Return a state's update only if you need it, since each one costs a port.
2. **Ports at the frontend:** `declared_in + n_states + out + n_exposed_states ≤ 255`.
   Drop dead inputs before validate/compile, because those paths count them.
3. **States:** `N ≤ 55 − (1 if any plain output or exposed state) − (1 if any plain
   input)`, so 53 in practice. Treat weights as a possible extra consumer until
   measured.
4. **State shape:** keep `d3 % 32 == 0`, or `d0·d1·d2 ≤ 256`. Use fp16 only.
5. **Budgets are counts.** Port width and state width do not move 1–3.
6. Re-run `./scripts/evidence-check.sh docs/spec/ane-port-limits-h17.spec` on any
   new OS build or SoC before trusting these numbers there.

---

## Corrections to the previous version

| Previous claim | Status | What holds instead | Spec § |
|---|---|---|---|
| `out_cap(in) = max(63, 127 − in)`, "floored at 63" | **wrong** | `live_in + out ≤ 127`, no floor; the floor came from dead inputs in `gen_mix_ports.py` | 1 |
| "NOT frontend"; "frontend accepts 200+ io ports" | incomplete | frontend cap `declared_in + out ≤ 255` | 2 |
| "Plain io does not share the state budget" (53 st + 32 in + 32 out) | **wrong** for execution | it compiles, but states are io ports and 170 > 127, so it does not run | 3 |
| "53 states compile + run; 54 fail" as the cap | incomplete | 55-id BAR pool; 54 states fit without a plain input | 4 |
| "`__data` segments = outputs + 2 × states" (surface + working buffer) | special case | sections = N + exposed + outputs; the second N is returned updates | 4 |
| "`0x9344` = states + 1 header; the table holds 54 records" (WHY 54 "resolved") | **wrong** | buffer bindings, K + max(1, min(in, out)); 85 and 1 at 53 states; not a table | 5 |
| Slot word = (slot, copy), "slots each holding 2 records" | reinterpreted | the bits are the BAR ordinal of a segment | 5 |
| `0x9442` = "2N + 1 segment family", unprobed | **wrong** | one destination binding per `__data` section | 5 |
| `0x934a`: "one extra per program on M5, fixed" | **wrong** | +1 per binary-add task on h17 | 5, 8 |
| Embedded children carry "constant payload 0x21" | **wrong** | a flags byte; arch bit on `0x1440` only | 5 |
| `0x9361` "fixed template, byte-identical across shapes and counts" | **wrong** | update-row record carries dim1, stride and rowbits | 6 |
| `0x9365` stride `min(2·dim1 + 8, 32)` | **wrong** | `8·min(⌈log2 dim1⌉, 4)`, saturating at dim1 = 9 | 6 |
| Region `dim1 × 1 MiB` "vmsize reservation, ×4 slots" | reinterpreted | `rowbits << 16`; LONG/SHORT layouts | 6 |
| M4 → M5 "identical, the only delta one `0x934a`" | incomplete | same counts and laws; arch bytes differ in every record | 8 |
| Spec "executable assertions for all of it" | was false | the pass side was vacuous; now every claim above has a line | — |

## Open questions

1. **Why 55 BAR ids,** and does a weight (BLOBFILE) segment consume one? The
   second question decides the practical state cap for real models.
2. **Where 127 and 255 come from** (7- and 8-bit port indices?), and whether they
   are per function. Multi-function programs and the CoreML lane are unmeasured.
3. **M4 silicon:** all h16g data is cross-compilation.
4. **State semantics:** does a noupd program persist state at runtime (needs a
   read-back probe)? What do read-only states, multiple writes, and cross-state
   copies cost?
5. **Copy-record details:** the SHORT/LONG rule for computed update sources, the
   `dim1 = 16` special case (16 elements or 32 bytes? only fp16 compiles, so the
   two cannot be separated), `dim3 = 256` dropping all copy records, the
   cost-like field, and the dim2 > 1 stride sub-law.
6. **Fan-out threshold** (~41 consumers) for non-add ops and for N > 0 at in > 1.

## Reproduce

```sh
cd vendor/mil_spec && cargo build --release -p milc && cd ../..   # the spec also does this itself
./scripts/evidence-check.sh docs/spec/ane-port-limits-h17.spec   # every law above
python3 scripts/state_exec_predict.py 4 16 1 1024                # will this state execute?
```
