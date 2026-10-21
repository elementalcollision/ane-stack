# Evidence — TEST-2: hardware-conditional test discipline

Work item: `TEST-2`, patch `0009`. Owner: L-TEST.
Host: Apple M5 Max, macOS 26.7.1 (hardware-present verification); the
no-hardware path is exercised by shadowing `xcrun`.

## Accept criterion (BUILD_PLAN)

> Audit for tests that silently no-op without hardware. Replace silent skips
> with explicit, logged skips and a `--require-hw` flag that turns a skip into
> a failure. *Accept:* CI run without hardware reports N skipped, not N passed.

## The lie

A hardware-gated test that runs without hardware has three honest options and
one dishonest one. The dishonest one — what the suite did at **27 call sites
across 10 test files** — is `return` early, so cargo reports the test as
**PASSED** while it did no work:

```rust
#[test]
fn binary_e2e() {
    let p = run("binary", ...);
    let Some(p) = p else { return };   // run() returned None when coremlc absent
    ...
}
// cargo: "test binary_e2e ... ok"   ← nothing was checked
```

On a no-hardware CI runner, the entire e2e surface was a wall of green that
meant nothing. `#[ignore]`d tests already report correctly (cargo counts them
as "ignored"); the runtime early-return is the lie.

## The fix

`mil_compile::hw_gate(reason, available) -> bool`:

- **default (hardware absent):** prints `SKIP: hardware unavailable (<reason>)`
  (greppable, machine-countable) and returns `false` so the test early-returns —
  visible, not silent.
- **`MIL_REQUIRE_HW=1`:** the skip becomes `panic!("SKIP: hardware required but
  unavailable (<reason>); MIL_REQUIRE_HW=1")` — a hard failure, so CI can assert
  coverage.

Plus `mil_compile::count_hw_skips(output)` for a CI summary to turn "0 failed"
into "N passed, M skipped".

Converted all 27 gates: `if !coremlc() { return; }`, `if
mil_compile::coremlc_path().is_none() { return; }`, the ops_e2e `run()` helper's
`return None`, and lora's compound `!hf.exists() || ...` gate.

## Verification

**No-hardware runner** (xcrun shadowed so `coremlc_path()` returns None):

```console
$ PATH=/tmp/noxcrun:$PATH cargo test --release -p mil_infer --test ops_e2e binary_e2e -- --exact --nocapture
SKIP: hardware unavailable (coremlc (binary))
test result: ok. 1 passed; 0 failed; 0 ignored    # loud skip, honest pass

$ PATH=/tmp/noxcrun:$PATH MIL_REQUIRE_HW=1 cargo test --release -p mil_infer --test ops_e2e binary_e2e -- --exact
thread 'binary_e2e' panicked at crates/mil_compile/src/lib.rs:184:9:
SKIP: hardware required but unavailable (coremlc (binary)); MIL_REQUIRE_HW=1
test result: FAILED. 0 passed; 1 failed           # hard failure, as designed
```

**Hardware present (default and `MIL_REQUIRE_HW=1`):** both run and pass —
no SKIP lines, no spurious panics.

**CI:** `.github/workflows/hw-skip-discipline.yml` runs the gated suite on a
Linux runner (no coremlc) and asserts SKIP lines fire with zero failures, and
that `MIL_REQUIRE_HW=1` fails loudly.

## What it does not do

- Does not convert the `#[ignore]`d tests to runtime gates — those already
  count honestly; converting them would change every lane's default workflow
  (they'd need `-- --ignored`).
- Does not make cargo *itself* print "N skipped" for runtime gates — cargo has
  no such channel; the SKIP lines are the machine-countable record, and
  `count_hw_skips` + the CI step produce the number.

## Cross-lane note

This touched test files under `crates/mil_convert`, `crates/mil_infer`,
`crates/mil_verify`, `crates/milc` — cross-cutting, which is L-TEST's remit
(`docs/lanes/OWNERSHIP.md` leaves `crates/*/tests/` unclaimed by product lanes).
Each change is a one-line gate swap; no test logic altered. Full suite green.
