# ANE resource budgets — io ports and state<> surfaces (h17)

> **Living document.** Every number names the build and the probe that produced
> it. A verdict without provenance is not a verdict. Two related budgets live
> here so neither lane quotes half the picture.

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

## Reproduce

```console
# Finding 1 (io ports, execution-time)
python3 scripts/gen_mix_ports.py 1 126 > /tmp/a.mil   # in=1 out=126
milc ane run /tmp/a.mil --steps 1                     # PASS
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
2. **Is 53 a table size or a derived limit?** **Resolved.** The cap is a raw
   state **count** on the `ZinBarIdManager` descriptor table, capacity **54
   `0x9344` slots**: 53 states + 1 header slot = 54 (compiles); a 54th state
   needs a 55th slot (fails). Each `state<>` costs 2 Mach-O `__data` segments
   (the `0x9361`/`0x9365` state-copy pair) + 1 descriptor-list slot. What is NOT
   yet decoded: the per-slot record encoding (the `0x9344` body's second word,
   e.g. `0x2400`/`0x2300`) — the count and cap are proven, the slot-field layout
   is the remaining unknown.
3. Do the budgets move with `--arch` (h16g vs h17), state dtype/shape, or the
   per-state stripe layout? Only channel width was swept (no effect on Finding 1).
