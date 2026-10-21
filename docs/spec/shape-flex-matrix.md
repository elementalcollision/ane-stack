# Shape-flexibility × execution-lane matrix (h17)

> **Living document.** Every cell names the build and the probe that produced it.
> A verdict without provenance is not a verdict.

## Build provenance

| Field | Value |
|---|---|
| SoC | Apple M5 Max (Mac17,7, exposes `h17`) |
| macOS | 26.7.1 (25G91) |
| coremlc | 3600.25.1 |
| Probes | `crates/mil_infer/examples/{seg4,cml_exec,shape_flex_e5rt,e5exec,mk_minflex}.rs` |
| Models | (a) converted tiny-Qwen3 decoder, (b) minimal 1-op `add(x,x)` |
| Date | 2026-10-21 |

Two execution lanes are measured. They are **not the same path**:

- **CoreML lane** — `mil_compile::compile` (coremlc) → `MLModel loadModel` with
  `MLComputeUnits` → `predict`. This is the path upstream measured on h16g.
- **e5rt lane** — `e5rt::Program::compile_auto(mil, DeviceMask)` → `aned` compiles
  the MIL itself → `execute`. New dimension added by PROBE-3.

---

## Matrix A — converted decoder graph (tiny-Qwen3, 2 layers, KV state)

`milc convert /tmp/p3model -o <pkg> --seq 4 | --seq-lens 1,4 | --seq-range 1..4`
→ CoreML lane `loadModel` + `predict` (mask KV = 2048).

| variant | cpu | cpu+gpu | all | cpu+ane |
|---|---|---|---|---|
| fixed `--seq 4` | **OK** | **OK** | **OK** | **OK** |
| `--seq-lens 1,4` (EnumeratedShapes) | **OK** | **LOAD_FAIL (-14)** | **LOAD_FAIL (-14)** | **OK** |
| `--seq-range 1..4` (ShapeRange) | **OK** | **LOAD_FAIL (-14)** | **SEGFAULT** | **SEGFAULT** |

This matches upstream's h16g table for `fixed` and `enumerated`. **Divergence:**
upstream recorded `--seq-range` on `all`/`ane` as a clean `-14`; on h17 both are a
**hard crash at `Model::load`** — `SIGSEGV` (rc=139) on most runs, occasionally
`SIGBUS` (rc=138). The signal varies run to run; the crash does not (fork-isolated,
reproduced across repeated runs). A clean failure became a crash between h16g and
h17.

---

## Matrix B — minimal 1-op model (`add(x,x)`, seq dim flexible)

`mk_minflex` emits three packages over `[1, S, 1, 1]` with the varying dim marked
symbolic (`s`). This isolates the *shape mechanism* from graph complexity.

### CoreML lane (load + predict at S=4)

| variant | cpu | cpu+gpu | all | cpu+ane |
|---|---|---|---|---|
| fixed | OK | OK | OK | OK |
| enumerated | OK | OK | OK | OK |
| range | OK | OK | OK | OK |

A single `add` places trivially everywhere — confirming the encoding is correct and
the Matrix-A failures are graph-dependent (dynamic-dim ops in the decoder), not the
shape declaration itself.

### e5rt lane (compile via `Program::compile_auto`, then execute)

| variant | cpu | gpu | ane | auto |
|---|---|---|---|---|
| fixed | COMPILE_OK | COMPILE_FAIL | COMPILE_OK | COMPILE_OK |
| enumerated | **COMPILE_FAIL** | **COMPILE_FAIL** | **COMPILE_FAIL** | **COMPILE_FAIL** |
| range | COMPILE_OK | COMPILE_FAIL | COMPILE_OK | COMPILE_OK |

Execute detail:

- **fixed** — executes at the full shape: `s=4 → y=[0,2,4,6]` (correct `x+x`).
- **range** — `compile_auto` **binds ports at the *default* shape** (`[1,1,1,1]`,
  1 element). Executing at the default works (`y=[0]`); feeding a non-default
  shape (`s=4`) fails with `set_input: overflow`. e5rt does **not** re-bind a
  flexible-range model to a non-default shape through this API.
- **enumerated** — fails at `retain_program_function(main)` with
  `function_name not found in library`, on **every** mask. e5rt cannot enumerate
  a `main` from an EnumeratedShapes package at all.

### e5rt lane on the converted decoder (Matrix A packages)

All variants, all masks: **COMPILE_FAIL** — `"Not implemented": Some ops are not
supported on any of the specified backends.` This is the op-set wall (the decoder
uses ops outside the ANE-eligible subset), **not** a shape-flexibility failure, and
is listed only to show the shape mechanism is not what blocks the e5rt lane here.

---

## Findings

1. **h16g → h17 regression in failure mode (CoreML lane, ShapeRange).** A clean
   `-14` became a segfault on `all` and `cpu+ane`. If any caller treats `-14` as
   the "range not supported" signal, that signal is now a crash on this SoC.
   (Matrix A.)

2. **The two lanes disagree fundamentally on EnumeratedShapes.** CoreML lane loads
   and predicts an EnumeratedShapes decoder on `cpu` and `cpu+ane` (the ANE
   placement Apple's docs recommend); the e5rt lane cannot even *find* the `main`
   function in the same package family. For EnumeratedShapes workloads, the e5rt
   lane is **not** an option on this build.

3. **e5rt binds ShapeRange at the default shape only.** A range-flexible model
   compiles on the e5rt lane but executes only at its default shape through
   `compile_auto`; non-default shapes overflow the bound ports. If an e5rt path
   needs runtime shape variation, it must use the JIT-shapes mechanism
   (`NetworkJITShapesPath`), which is **unprobed** — see Next Steps.

4. **Encoding is verified correct.** The minimal model runs everywhere on the
   CoreML lane, so the Matrix-A `-14`/segfault cells reflect the *graph*, not a
   malformed shape declaration. The symbolic-dim marker (`s`) in the function
   signature is load-bearing: omitting it makes coremlc reject the package with
   "input has a different shape than its parameter to main".

## What this does NOT establish

| Question | Status |
|---|---|
| Does e5rt's `NetworkJITShapesPath` mechanism re-bind flexible shapes at runtime? | **Unprobed** — the spec lists it as the documented path; we have not driven it. |
| Is the ShapeRange segfault a CoreML-framework bug or a mil_infer marshalling bug? | **Unprobed** — it reproduces fork-isolated at `Model::load`; we did not trace inside the framework. |
| Does the h16g `-14` for range-on-all still hold on h16g hardware? | **Not re-measured** — we have no h16g machine; upstream's table is taken as the baseline. |

## Next steps

1. **Probe `NetworkJITShapesPath`** (the JIT-shapes lane) for runtime shape
   re-binding on e5rt — the only untested mechanism for flexible-shape execution.
2. **Root-cause the ShapeRange segfault** at `Model::load` (LLDB backtrace) to
   determine framework vs marshalling, and whether a guard belongs in `Model::load`.
3. **Feed Matrix A into L-SCHED** as the executable constraint: for flexible-shape
   decoders, CoreML-lane `cpu`+`ane` (EnumeratedShapes) is the only reliable
   flexible ANE placement; e5rt is fixed-shape-only in practice.

## Reproduce

```console
cargo build --release -p mil_infer --example mk_minflex --example seg4 \
    --example cml_exec --example shape_flex_e5rt --example e5exec

# Matrix A (converted decoder)
milc convert /tmp/p3model -o /tmp/p3/a_fixed.mlpackage --seq 4
milc convert /tmp/p3model -o /tmp/p3/b_enum.mlpackage --seq-lens 1,4
milc convert /tmp/p3model -o /tmp/p3/c_range.mlpackage --seq-range 1..4
for v in a_fixed b_enum c_range; do for u in cpu gpu all ane; do
  ./target/release/examples/seg4 /tmp/p3/$v.mlpackage $u; done; done

# Matrix B (minimal model, both lanes)
./target/release/examples/mk_minflex /tmp/minflex
for v in fixed enum range; do for u in cpu gpu all ane; do
  ./target/release/examples/cml_exec /tmp/minflex/$v.mlpackage 4 $u; done; done
./target/release/examples/shape_flex_e5rt \
  /tmp/mf_mil_fixed/fixed.mlmodelc/model.mil \
  /tmp/mf_mil_enum/enum.mlmodelc/model.mil \
  /tmp/mf_mil_range/range.mlmodelc/model.mil
```
