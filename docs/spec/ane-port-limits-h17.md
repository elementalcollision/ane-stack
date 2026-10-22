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
| state<> params (Finding 2) | **frontend** (`ANECCompile`) | **53 states** pass, 54 fail (`free BAR`) |

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
2. **Is 53 a table size or a derived limit?** 53 is not a power of two; the BAR
   table is likely 64 with ~11 reserved for the program + io descriptors, or each
   state's read/update buffers share the table. The BAR arithmetic per state is
   unprobed.
3. Do the budgets move with `--arch` (h16g vs h17), state dtype/shape, or the
   per-state stripe layout? Only channel width was swept (no effect on Finding 1).
