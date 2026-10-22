# Evidence — reconciling the two ANE port limits

Lane: **L-SCHED** validating L-PROBE's `docs/spec/ane-port-limits-h17.md`.

**Verdict: L-PROBE is right that the "~52-port frontend limit" does not
reproduce, and my earlier note was wrong as framed. But my measurement was not
a mistake — it was measuring a *different, additional* limit that their probe
did not cover. Both are real and they do not conflict.**

---

## 1. The apparent contradiction

| claim | source | says |
|---|---|---|
| "~52-port ANECCompile frontend limit" | L-SCHED, `A5-anecompile-ceiling-is-ports-not-ops.md` | frontend refuses >52 `state<>` ports |
| "no frontend constraint; 200+ ports OK" | L-PROBE, `ane-port-limits-h17.md` | frontend accepts everything; limit is at execution |

## 2. L-Probe's finding reproduces exactly

Ran their generator and their executable spec on this host:

- `evidence-check.sh ane-port-limits-h17.spec` → **PASS (1/1)** on hardware,
  so their `out_cap = max(63, 127 − in)` execution model is verified.
- Their plain-tensor ladder: `in=out=48/64/96` compile, `128` fails with
  `MaxLiveInLiveOutExceeded`. So the frontend *does* have a far higher ceiling
  than 52 — my "~52" framing was wrong as stated.

## 3. And my measurement still reproduces, unchanged

On the same host, same `milc`, same build — independent `state<>` ports, no
plain ports:

| `state<>` ports | `ANECCompile --arch h17` |
|---|---|
| 48 | ✅ |
| 52 | ✅ |
| 53 | ✅ |
| **54** | ❌ **`Compiler internal error`** |
| 55 / 56 / 64 | ❌ `Compiler internal error` |

Exact boundary: **between 53 and 54**. This is reproducible on the host their
probe also used (M5, macOS 26.7.1), so it is not an OS or SoC difference.

## 4. The discriminator: two separate budgets

| | plain `tensor<>` in/out | `state<>` inout |
|---|---|---|
| boundary | ~128 plain ports (compile), `MaxLiveInLiveOutExceeded` | **~53 `state<>` ports**, `Compiler internal error` |
| error code | `MaxLiveInLiveOutExceeded` | `Compiler internal error` |
| budget | shared in/out, `max(63, 127 − in)`, at **execution** | per-program count, at **ANECCompile** |

Two decisive checks:

- **They are separate budgets, not one shared counter.** `40 state<> + 16 plain`
  (56 ports) → **compiles**. If the 53-`state<>` limit were a total-port rule,
  56 total would fail. It does not; it fails only when `state<>` alone exceeds
  ~53.
- **The plain-port budget is not the same wall.** Their sweep reaches 200 plain
  ports through the frontend fine; `state<>` cannot get past 53.

So: `ANECCompile` has **two** distinct port budgets — a plain in/out budget
(~128) with a *different failure code*, and a much tighter one for
`state<>` inout ports (~53) that fails as a compiler-internal error.

## 5. Where each number came from, and how to quote it

- L-Probe used `scripts/gen_mix_ports.py`, which emits **plain tensor in/out
  ports** (`x_i` → `y_i` passthrough). It never emits `state<>`. So their
  "no frontend constraint" conclusion is correct *for the port kind they
  measured*.
- My `examples/gen_ceiling.rs` `states` mode emits **`state<>` ports only**
  (`read_state` per state). It never measured plain ports, so its "~52 ports"
  was really "~53 `state<>` ports".
- **Neither is wrong. Both were over-generalised.** L-Probe's "no frontend
  constraint" understates the `state<>` case; my "~52-port frontend limit"
  overstated it into a single universal number.

## 6. What this changes operationally

Only one thing, and it is the one L-SCHED depends on: my A.5 conclusion said
"the binding resource is independent inout ports (~52)". **That stands**, and is
now better characterised — the exact figure is ~53 and it is `state<>`-specific.

The SCHED-2 framing correction survives: `milc convert --shard N` emits **one
packed `kv` state per shard**, so shards sit far under 53 `state<>` ports and the
constraint does not bind. That is still why the 16384-op artifact compiled.

## 7. Request to L-Probe

`ane-port-limits-h17.md` is correct but incomplete for the `state<>` port kind.
Suggest one added finding: **a second, tighter `state<>`-inout budget at ~53
ports with a distinct `Compiler internal error`**, measured on the same host.
Both numbers then live in one document with provenance, rather than each lane
quoting half of it. I am not editing their file (L-PROBE owns `docs/spec/**`).
