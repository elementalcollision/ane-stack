# Evidence — patch 0001: `write_state` shape validation

Work items: `IR-1`, patches `0001`/`0002`/`0003`.
Host: Apple M5 Max (Mac17,7), macOS 26.7.1, cargo 1.95.0, coremlc 3600.25.1.

## What was wrong

`mil_spec::ir` bound a value to `write_state` checking **dtype only** (`src/ir.rs:805`):

```rust
let v = self.lookup(parts[1], n)?;
if v.dtype != st.dtype {
    return err(n, format!("write_state dtype mismatch: ..."));
}
self.block.write_state(parts[0], parts[1]);
```

A state is always written whole, so a value of any other shape is unrepresentable —
yet it passed validation and failed later inside `coremlc`.

## Reproduction (before patch)

Program: `state kv: fp16[1,8,64,64]`, input `[1,8,1,64]`, `concat([cur, step], 2)`
→ `[1,8,65,64]`, written back to `kv`.

```console
$ xcrun coremlc compile …/mil_ir_demo.mlpackage /tmp/ir_c
coremlc: error: Failed to parse the model specification.
  Error: Unable to parse ML Program: in operation kv_write_state:
  Unexpected type for the data parameter.
```

`ir::compile` had **accepted** this program. (It is also the program in upstream's
own `examples/compile_ir.rs`, which additionally pins `(8, "CoreML5")` while
`read_state` requires CoreML9 — so the example fails either way.)

## Fix

Added an exact shape comparison after the dtype check, with a `FORK(ane-stack)`
comment and the upstream sha.

## Test delta

`cargo test --test ir`:

```
test stateful_roundtrip ... ok
test write_state_shape_mismatch_rejected ... ok   # new
test result: ok. 17 passed; 0 failed
```

**Note on `stateful_roundtrip`:** this upstream test *encoded the bug*. It asserted
that the `[1,8,65,64]` concat was a valid whole-state write:

```
thread 'stateful_roundtrip' panicked at tests/ir.rs:5:37:
should compile: ir line 5: write_state shape mismatch: state [1, 8, 64, 64] vs value [1, 8, 65, 64]
```

That failure is the fix working. The test was corrected to a legal same-shape
additive write (the IR has no `slice_update`, so a whole-state write is the only
expressible form — tracked as `IR-2`), and a new test asserts the rejection.
The same bug appeared in `mil_verify`'s conformance case `stateful-kv` (patch 0003).

## Payoff — a stateful package now compiles and runs

```console
$ cargo run --release --example compile_ir_fixed
wrote /tmp/ir_fixed.mlpackage

$ xcrun coremlc compile /tmp/ir_fixed.mlpackage /tmp/irf
$ ls /tmp/irf
ir_fixed.mlmodelc

$ milc run /tmp/ir_fixed.mlpackage --units ane --steps 3
compiled /tmp/ir_fixed.compiled/ir_fixed.mlmodelc via coreml.framework
3 steps on cpu+ane: median 99.42µs  min 62.92µs  max 280.29µs  total 442.63µs
```

A stateful model executes on `cpu+ane`. Before the patch this was unreachable in
the documented IR path.

## Confidence

- The shape rule is stated by the spec and matches `Block::write_state`'s contract
  (state written whole). No ambiguity.
- Regression tests cover accept (legal) and reject (mismatch).
- Full suite green: `-p mil_spec -p mil_lint -p mil_passes -p mil_verify`, plus
  `milc verify` → `10 cases, 0 failed`.
