# ANE resource budgets — io ports and state<> surfaces (h17)

> **Living document.** Every number names the build and the probe that produced
> it. A verdict without provenance is not a verdict. Two related budgets live
> here so neither lane quotes half the picture.

> **Visual companion:** `artifacts/ane-descriptor-economy` — a one-page
> rendering of the full descriptor economy (tree, field tables, scaling law,
> the 54-slot cap). Open the saved HTML from the workspace artifacts dir.

## Why this file exists

A claim circulated that there is a "**~52-port limit**" that is an
"**undocumented `ANECCompile` frontend constraint**". Probing it surfaced **two
distinct budgets**, only one of which is a frontend constraint, and neither is
cleanly "52 ports":

1. **Finding 1 — the io-port limit is execution-time, not frontend.** The
   `ANECCompile` frontend accepts 200+ io ports. The real cap is at `execute_sync`
   and follows `out_cap(in) = max(63, 127 − in)`.
2. **Finding 2 — the state<> limit IS a frontend constraint.** The compiler
   rejects a 54th independent `state<>` param with `unable to allocate free BAR`.
   Boundary: **53 states compile, 54 fail.**

## Build provenance

| Field | Value |
|---|---|
| SoC | Apple M5 Max (Mac17,7, exposes `h17`) |
| macOS | 26.7.1 (25G91) |
| coremlc | 3600.25.1 |
| Probes | `milc ane validate\|compile\|run` + generated `program(1.3)` MIL |
| Generators | `scripts/gen_mix_ports.py` (io), `scripts/gen_states.py` (state) |
| Verification | boundary cells run 3–6× fresh; io model validated on 8 held-out points |
| Date | 2026-10-21 |

---

## Finding 1 — io ports: execution-time cap, NOT a frontend constraint

### The frontend accepts 200+ io ports

| total io ports | `ANECValidate` | `ANECCompile` |
|---|---|---|
| 48 / 52 / 64 / 128 / 200 | `status=0` | `status=0` (Mach-O written) |

Nothing special happens at 52. The "~52-port frontend constraint" claim does not
reproduce at the frontend.

### The real cap is at `execute_sync`

Run on the ANE via the e5rt lane (`milc ane run`), programs fail at
`execute_sync` with `Program Inference error` once the **output** count crosses a
budget that depends on the **input** count:

```
out_cap(in) = max(63, 127 − in)
```

Measured (binary search, 3× fresh at each boundary), validated on 8 held-out
(in, out) points — all predictions correct:

| in | out_cap | model |
|---|---|---|
| 1 | 126 | 126 ✓ |
| 16 | 111 | 111 ✓ |
| 32 | 95 | 95 ✓ |
| 48 | 79 | 79 ✓ |
| 64 | 63 | 63 ✓ |
| 70 / 80 / 100 / 128 | 63 | 63 ✓ (floor) |

- **Inputs alone are nearly free** (`in=4000, out=1` passes).
- The constrained axis is the **output** count against a ~127 budget shared with
  inputs, floored at 63 outputs.
- Channel width (2 → 2048 bytes/port) does **not** move the boundary → a port
  **count** budget, not an io-**byte** budget.

---

## Finding 2 — state<> surfaces: a genuine `ANECCompile` frontend constraint

Independent `state<>` params (each a per-state read→slice_update→write triple,
the ANE state contract) hit a **compiler** wall at the 54th state:

```
error: Compiler internal error: ZinBarIdManager::GetNextAvailableBarId():
unable to allocate free BAR
```

| states | `ANECValidate` | `ANECCompile` | `milc ane run` |
|---|---|---|---|
| 52 | `status=0` | `status=0` | step ok |
| 53 | `status=0` | `status=0` | step ok |
| 54 | `status=0` | **`unable to allocate free BAR`** | (compile fails first) |
| 55+ | `status=0` | **same** | — |

**Boundary: 53 independent `state<>` params compile and run; 54 fail at
`ANECCompile`.** The failure is internal (`ZinBarIdManager` — a per-state
resource-descriptor allocator), so the frontend *validates* the program but
cannot *compile* it.

### BAR table characterization (what admits 53)

**Mach-O structure (the decisive evidence).** Dumping the compiled `.macho`
section table across 16 state counts (0 → 53), the number of `__FVMLIB.__data`
segments is **exactly**:

```
__data segments = outputs + 2 × states
```

| states | outputs | measured __data | model | match |
|---|---|---|---|---|
| 0 | 1 | 1 | 1 | ✓ |
| 0 | 2 | 2 | 2 | ✓ |
| 0 | 4 | 4 | 4 | ✓ |
| 1 | 1 | 3 | 3 | ✓ |
| 2 | 1 | 5 | 5 | ✓ |
| 8 | 1 | 17 | 17 | ✓ |
| 24 | 1 | 49 | 49 | ✓ |
| 32 | 1 | 65 | 65 | ✓ |
| 48 | 1 | 97 | 97 | ✓ |
| 53 | 1 | 107 | 107 | ✓ |

So: **inputs are free; each output costs one segment; each `state<>` costs two**
(its persistent surface + its read/update working buffer).

**The BAR cap is on the state *count*, not the segment count.** The decisive
proof:

| program | total __data segments | verdict |
|---|---|---|
| 53 states + 1 out | 107 | **PASS** |
| 54 states + 1 out | 109 | **FAIL (BAR)** |
| **52 states + 50 out** | **154** | **PASS** |
| 0 states + 126 out | 126 | **PASS** |

154 segments pass while 109 fail — the table that overflows is the
**state-descriptor table** (boundary 53), not the segment table. Io and total
segments are irrelevant to it.

### The descriptor economy (what `ZinBarIdManager` allocates)

Going one level below the section table into the `__text` instruction stream:
each `state<>` compiles to a fixed set of descriptor records, identifiable by
their `0x93xx` family tags. Counting them across state counts:

| record tag | 0 states | 1 state | 2 states | 53 states | scaling |
|---|---|---|---|---|---|
| `0x9344` (descriptor-list slot) | 0 | 2 | 3 | 54 | **N + 1** |
| `0x9361` (state-copy) | 0 | 1 | 2 | 53 | **N** |
| `0x9365` (state-copy) | 0 | 1 | 2 | 53 | **N** |
| `0x9342`, `0x935a`, `0x934a` | fixed | fixed | fixed | fixed | constant |

So each `state<>` costs **one `0x9344` descriptor-list slot** (plus one extra
header slot — the +1 — present only when at least one state exists), and the two
`0x9361`/`0x9365` state-copy records are exactly the 2-per-state seen in the
`__data` segment counts.

**The BAR table holds 54 `0x9344` descriptor-list slots.** 53 states consume 53
slots + 1 header = 54, which compiles; a 54th state would need a 55th slot and
fails with `unable to allocate free BAR`. This is the precise location of the 53
budget: the `ZinBarIdManager` descriptor table, capacity **54 slots**.

The slot-record body (second word, e.g. `0x2400` / `0x2300`) is an encoded
descriptor field whose exact bit layout is **not yet decoded** — the *count* and
the *cap* are proven; the per-slot encoding is the remaining unknown (see Open
questions).

### The `0x9344` slot word, decoded

The second word of each `0x9344` record (e.g. `0x2400`, `0x2300`) is a packed
slot field:

```
word = (slot_index << 8) | (copy << 7)
```

- **high byte** (`w >> 8`): the **slot index** — sequential `0x23, 0x24, 0x25 …
  0x3e` across the program.
- **bit 7** (`w & 0x80`): the **copy selector** — which of the two records
  occupying that slot (0 or 1).

So the descriptor table is an array of **slots, each holding up to two
records**. Measured across state counts:

| states | records | slots | slots with both copies | singletons |
|---|---|---|---|---|
| 1 | 2 | 2 | 0 | 2 (0x23, 0x24) |
| 2 | 3 | 2 | 1 | 1 (0x25) |
| 16 | 17 | 9 | 8 | 1 |
| 32 | 33 | 17 | 16 | 1 |
| 53 | 54 | 28 | 26 | 2 (0x3d header, 0x3e) |

records = states + 1 (the +1 header); slots = `ceil(records / 2)`. The two
records in a full slot are a state's two descriptors — and the slot word is the
descriptor-table **(slot, position)** coordinate.

### The `0x9365` state-copy record, decoded

Reading the per-state `0x9365` record body across 10 state shapes (training +
4 held-out), the field map is:

| offset (bytes) | field | meaning |
|---|---|---|
| +0x00 | `0x9365` | record tag (4-D state-copy) |
| +0x02..+0x09 | `01 00 00 00 01 00 00 00` | flags / type constants |
| **+0x0a** (u32) | **dim1** | the inner dim (channels) |
| **+0x0e** (u32) | **dim0** | the stripe/rows dim |
| **+0x1c** (u32) | **`min(dim1×2 + 8, 32)`** | packed inner-row stride |
| +0x30 | 0 | flag byte |
| +0x40 | descriptor ref | per-state descriptor pointer (varies) |
| **+0x48** (u32) | **`dim1 × 1 MiB`** | the region's vmsize reservation |

All four held-out shapes match exactly (`[4,12]`, `[4,24]`, `[8,8]`, `[2,4]`).
So each state's descriptor record carries its **shape** (`dim0`, `dim1`), a
**packed row stride** (`min(2·dim1+8, 32)` — the fp16 row bytes plus alignment,
saturating at 32), and a **1 MiB-per-channel vmsize reservation**. The stride
saturating at 32 elements is the first hint of the inner-tile geometry the ANE
uses for state surfaces.

The `0x9344` parent record's second word (`0x2400`/`0x2300`) is still the
encoded slot field whose bit layout is undecoded — but the per-state *content*
it points to is now fully mapped.

### Pointer targets — the read/write asymmetry

The two state-copy records are **not** symmetric. Byte-comparing each across
state shapes and state counts:

| record | role | carries shape? | varies? |
|---|---|---|---|
| `0x9361` | read-side state-copy | **no** | **byte-identical** on all shapes and counts — a fixed template |
| `0x9365` | write-side state-copy | **yes** — dim0, dim1, stride, region | **9 bytes**, all on decoded fields |

The reading is structural: the read just reads the surface (no geometry
needed); the write must place the update, so it carries the shape. The **9
varying bytes** in `0x9365` (measured `[4,4,1,1]` → `[32,8,1,1]`) all land on
decoded fields — there is **no unexplained shape data** in the write record:

| byte | field | [4,4] → [32,8] |
|---|---|---|
| +0x0a | dim1 | 04 → 08 |
| +0x0e | dim0 | 04 → 20 |
| +0x1c | inner-row stride | 16 → 24 |
| +0x33 | flag byte | 01 → 02 |
| +0x42 | shape-class selector | 0x42 → 0x62 |
| +0x4a/4e/52/5e | four region reservations | 4 MiB → 8 MiB |

Probed by varying one structural knob at a time on the working rsw form:

| knob varied | boundary moves? | conclusion |
|---|---|---|
| state stripe width (rows/state: 4 → 256) | **no** (54 fails at every width) | per-**descriptor**, not per-**byte** |
| tiny states `[1,1,1,1]` (1 elem each) | **no** (54 still fails) | a **count** of states, not a byte budget |
| plain io added (32 in + 32 out) | **no** (53 states still compile) | io ports **do not** consume BAR entries |
| shared consts added (60 unused) | **no** (53 states still compile) | const buffers **do not** consume BAR entries |
| per-state transient buffers (cur + upd) | n/a — see note | **do not** count (159 named buffers would blow a 64 table; 53 passes) |

Only the persistent `state<>` **params** consume BAR entries — **two per state**
(persistent surface + read/update working buffer), exactly as the Mach-O section
counts show. The table admits **53 independent state descriptors**. The earlier
hypothesis of a "64-entry table with ~11 reserved" is **wrong**: the 52+50 = 154
segments vs 54 = 109 segments contrast proves the cap is a raw state **count**,
not a segment-table size.

### Plain io does not share the state BAR table

A 53-state program still compiles with 32 plain inputs + 32 plain outputs added.
The `state<>` budget is a **separate** resource from the Finding-1 io budget.

### This is the budget closest to the "~52" claim

The only *frontend* limit in this territory is the state<> one, and its boundary
(53) is near the claimed 52. If the "~52-port" figure came from a real
measurement, it was most likely a **state<>** count, not an io-port count — and
the precise boundary on this build is **53**, not 52.

---

## The honest bottom line

| budget | where it bites | boundary (h17, this build) |
|---|---|---|
| io ports (Finding 1) | **execution** (`execute_sync`) | `out_cap = max(63, 127 − in)` |
| state<> params (Finding 2) | **frontend** (`ANECCompile`) | **53 states** pass, 54 fail (`free BAR`); each state = 2 Mach-O `__data` segments |

- ❌ No "~52-port io-port frontend constraint" — the io frontend accepts 200+.
- ✅ The state<> budget is a real frontend constraint, boundary **53**, and it is
  the one closest to the claimed number.
- ✅ Both are count budgets, not byte budgets; they are independent of each other.

## The M4 → M5 delta

Compiling the *same* 53-state program for `h16g` (M4) and `h17` (M5) and
diffing the records: the descriptor economy is **identical** — same record
counts, same slot model, same 54-record cap (53 states compile, 54 fail with
`free BAR` on *both*). The **only** delta across all 20 record families:

| record family | h16g (M4) | h17 (M5) |
|---|---|---|
| `0x9344` (descriptor-list) | 54 | 54 |
| `0x9361` / `0x9365` (state-copy) | 53 / 53 | 53 / 53 |
| `0x1340` / `0x1342` / `0x135a` | 54 / 53 / 53 | 54 / 53 / 53 |
| `0x1440` / `0x9442` (region/segment) | 107 / 107 | 107 / 107 |
| **`0x934a`** | **1** | **2** |
| 11 singleton records | 1 | 1 |

**The M4→M5 delta is exactly one extra `0x934a` record per program on M5** —
the first `0x9344` descriptor-list record embeds `0x934a` **twice** on h17,
once on h16g. Fixed per program, independent of state count. The 54-record
state cap is unchanged. So the resource model is **portable M4 → M5**; only the
`0x934a` embedding count moved.

## Reproduce

```console
# Finding 1 (io ports, execution-time)
python3 scripts/gen_mix_ports.py 1 126 > /tmp/a.mil   # in=1 out=126
milc ane run /tmp/a.mil --steps 1                     # PASS

# M4 vs M5 (same program, both arches)
python3 scripts/gen_states.py 53 1 1 > /tmp/s53.mil
milc ane compile /tmp/s53.mil -o /tmp/cm4 --arch h16g   # M4: 1x 0x934a
milc ane compile /tmp/s53.mil -o /tmp/cm5 --arch h17    # M5: 2x 0x934a, same 54 cap
python3 scripts/gen_mix_ports.py 1 127 > /tmp/b.mil   # in=1 out=127
milc ane run /tmp/b.mil --steps 1                     # FAIL: Program Inference error

# Finding 2 (state<>, frontend)
python3 scripts/gen_states.py 53 1 1 > /tmp/s53.mil   # 53 independent states
milc ane compile /tmp/s53.mil -o /tmp/c53 --arch h17  # status=0
python3 scripts/gen_states.py 54 1 1 > /tmp/s54.mil   # 54 independent states
milc ane compile /tmp/s54.mil -o /tmp/c54 --arch h17  # unable to allocate free BAR
```

## Open questions

1. **Where does each budget live in `aned`?** Finding 1's 127/63 io budget and
   Finding 2's 53-state BAR table are *separate* unknowns in the same territory.
   `ZinBarIdManager` names the state one (a descriptor allocator); the io one is
   unlocalized.
2. **Why 54 — resolved.** The `ZinBarIdManager` descriptor-list table holds
   **54 `0x9344` records**. `0x9344` scales as **N + 1** (one record per state
   + one header). So 53 states + 1 header = 54 records compile; a 54th state
   needs a 55th record and fails with `unable to allocate free BAR`. The cap is
   a raw **record count**, not a slot-id range (the slot-id space 0x23..0x3e
   packs 2 records/slot = 56 record capacity — more than the 54 cap) and not a
   fixed byte-extent (the `__text` vmsize grows linearly with states). The
   `0x9365` state-copy record is fully decoded (shape + stride + region size)
   and the `0x9344` slot word is decoded (`(slot_index << 8) | (copy << 7)`).
3. Do the budgets move with `--arch` (h16g vs h17), state dtype/shape, or the
   per-state stripe layout? Only channel width was swept (no effect on Finding 1).
