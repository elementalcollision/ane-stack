# ANE port limits — execution-time, not frontend (h17)

> **Living document.** Every number names the build and the probe that produced
> it. A verdict without provenance is not a verdict.

## Why this file exists

A claim circulated that there is a "**~52-port limit**" that is an
"**undocumented `ANECCompile` frontend constraint**". I probed it before
recording it. **The claim as framed does not reproduce.** What actually exists
is a *different*, precise, execution-time limit. This file records the measured
model, not the claim.

## Build provenance

| Field | Value |
|---|---|
| SoC | Apple M5 Max (Mac17,7, exposes `h17`) |
| macOS | 26.7.1 (25G91) |
| Probe | `milc ane validate|compile|run` + generated `program(1.3)` MIL |
| Generator | `in` inputs / `out` outputs, each `y_i = add(x, x)` passthrough |
| Verification | boundary cells run 3–6× fresh; model validated on 8 unseen points |
| Date | 2026-10-21 |

---

## Finding 1 — there is NO ~52-port `ANECCompile` frontend constraint

Sweeping port counts through the frontend on `h17`:

| total ports | `ANECValidate` | `ANECCompile` |
|---|---|---|
| 48 | `status=0` | `status=0` |
| 52 | `status=0` | `status=0` |
| 64 | `status=0` | `status=0` |
| 128 | `status=0` | `status=0` (Mach-O written, 524288 bytes) |
| 200 | `status=0` | `status=0` |

The frontend accepts 200+ ports with no complaint. Nothing special happens at 52.

## Finding 2 — the limit is at execution time, and it has a precise shape

The same programs run on the ANE via the e5rt lane (`milc ane run`) fail at
`execute_sync` with:

```
ANEProgramProcessRequestDirect() Failed with status=0x2 : statusType=0x9: Program Inference error
```

The boundary is **not** a total-port count. It is a per-axis output cap that
depends on the input count:

```
out_cap(in) = max(63, 127 − in)
```

Measured (binary search, 3× at each boundary):

| in | out_cap (measured) | max(63, 127 − in) |
|---|---|---|
| 1 | 126 | 126 ✓ |
| 8 | 119 | 119 ✓ |
| 16 | 111 | 111 ✓ |
| 32 | 95 | 95 ✓ |
| 48 | 79 | 79 ✓ |
| 50 | 77 | 77 ✓ |
| 60 | 67 | 67 ✓ |
| 64 | 63 | 63 ✓ |
| 70 | 63 | 63 ✓ |
| 80 | 63 | 63 ✓ |
| 100 | 63 | 63 ✓ |
| 128 | 63 | 63 ✓ |

Model validated on 8 held-out (in, out) points — all predictions correct.

**Inputs alone are nearly free** (`in=4000, out=1` passes). The constrained axis
is the **output** count, against a budget of ~127 shared with inputs, floored at
63 outputs no matter how many inputs.

### Not a byte limit

Channel-width sweep at a fixed port count (2 → 2048 bytes per port) does **not**
move the boundary. This is a port-**count** budget, not an io-**byte** budget.

## The honest bottom line

- ❌ **No "~52-port" limit exists.** 52 compiles and runs fine.
- ❌ **Not a frontend (`ANECCompile`) constraint.** The frontend accepts 200+.
- ✅ **Execution-time output cap:** `out_cap = max(63, 127 − in)`, on the e5rt
  execution lane, h17.

If a "~52-port" figure was observed elsewhere, it was on a different OS build,
SoC, or lane. Re-derive before quoting any number — this one is measured only on
h17 / macOS 26.7.1.

## Reproduce

```console
python3 gen_mix.py <in> <out> > /tmp/p.mil

# frontend accepts anything:
milc ane validate /tmp/p.mil --arch h17            # status=0
milc ane compile  /tmp/p.mil -o /tmp/c --arch h17  # status=0, Mach-O

# execution is where the limit lives:
milc ane run /tmp/p.mil --steps 1
#   in=1, out=126 → PASS
#   in=1, out=127 → FAIL: Program Inference error
#   in=64, out=63 → PASS;  in=64, out=64 → FAIL
```

## Open questions

1. Where in `aned` does the 127/63 budget live — a fixed port table, an io-surface
   allocation, or a deployment-descriptor field? Not yet localized.
2. Does `out_cap` move with `--arch` (h16g vs h17), port dtype, or per-port rank?
   Only channel width was swept (no effect); rank/dtype unprobed.
3. The 63-output floor: is it a separate hard table, or the point where the
   `127 − in` line meets a fixed output-table size? The two-read model
   (`min(126, 127 − in)` with a 63 floor) fits everything measured but the floor's
   origin is unprobed.
