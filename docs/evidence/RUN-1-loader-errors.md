# Evidence — RUN-1: structured loader error decoding

Lane: `L-RUN` (claimed in `docs/lanes/OWNERSHIP.md`, 2026-10-21).
Work item: `RUN-1` — loader error decoding.
Status: **done**.

Host: Apple M5 (h17), macOS 26.7.1. Codes verified against real artifacts.
Depends on: `PROBE-2` (`docs/evidence/0010-deploy-gate-codes.md`) — landed first.

---

## 1. What was wrong

`_ANEClient loadModel:options:qos:error:` refusals surfaced as one opaque string:

```
loadModel failed: createProgramInstanceForModel:modelToken:modelFilePath:qos:…:error::
    Program load failure (0x170004)
```

A caller could only `contains()` it. `examples/dp3.rs` did exactly that, and its
extraction was actively wrong: it sliced 8 characters from the first `0x`, so a
signed code (`-0x170004`) yielded `-0x17000` — a valid-looking but incorrect
value. Any test or dashboard built on that would silently report the wrong code.

## 2. What was added

`mil_infer::espresso::AneLoadError`, carried by a new `EspError::Load` variant,
replacing the formatted string at the single place it was produced
(`load_inner`, the `loadModel` failure branch).

| Field | Meaning |
|---|---|
| `code: Option<u32>` | the numeric code, parsed leniently |
| `kind: AneLoadKind` | named variant, or `Unrecognised` / `NoCode` |
| `form: Option<ArtifactForm>` | artifact form the code discriminates |
| `raw: String` | the complete NSError description, unmodified |

Behaviour:

- `suggested_cause() -> Option<&'static str>` — a hypothesis for each measured
  code; **`None` for unrecognised codes**. Inventing a cause for a code we have
  never measured would be worse than admitting ignorance.
- `is_known_deploy_gate() -> bool` — true only for the three measured codes, so
  a caller can distinguish "the documented gate" from a novel failure.
- `presented_form(path)` — the form inferred from the path, for diagnostics.

The taxonomy comes from PROBE-2's measured table, and is encoded as data:

| Code | Kind | Form | Seen for |
|---|---|---|---|
| `0x170004` | `BareMachoRejected` | `BareMacho` | our `ANECCompile` output *and* Apple's compiled Mach-O |
| `0x130004` | `EspressoBundleRejected` | `EspressoBundle` | Apple `.espresso.hwx` shipped in `/System/Library` |
| `0x120004` | `E5BundleRejected` | `E5Bundle` | `aned`'s own e5rt cache bundle |

## 3. Verification on real artifacts

Each family re-confirmed on hardware after the change, via the reproduction
commands from `docs/evidence/0010-deploy-gate-codes.md`:

```console
$ ./target/release/examples/dp3 /tmp/c17/sig.macho
RESULT: FAIL_AT_loadModel code=0x170004 kind=BareMachoRejected form=Some(BareMacho)

$ ./target/release/examples/dp3 /System/Library/PrivateFrameworks/VideoProcessing.framework/Versions/A/Resources/cnn_frame_enhancer_192p.H13.espresso.hwx
RESULT: FAIL_AT_loadModel code=0x130004 kind=EspressoBundleRejected form=Some(EspressoBundle)

$ ./target/release/examples/dp3 /var/folders/…/H17C.bundle/H17C.e5
RESULT: FAIL_AT_loadModel code=0x120004 kind=E5BundleRejected form=Some(E5Bundle)
```

Note the `H13` variant of the Apple bundle (PROBE-2 recorded `H16`/`H18`); the
code is identical, which reinforces PROBE-2's conclusion that the gate is
form-specific rather than arch- or provenance-specific.

## 4. Test results

`cargo test -p mil_infer --lib run1_tests` → **9 passed, 0 failed**.

Per-observed-code table test, as acceptance requires:

`every_measured_code_decodes_to_a_named_variant` walks the measured table and
asserts code → kind → form → a non-`None` cause for all three.

The remaining eight guard the decode against the ways it could lie:

| Test | Guards against |
|---|---|
| `real_captured_description_decodes` | the verbatim hardware capture not decoding |
| `unrecognised_code_is_not_guessed` | mapping an unmeasured code onto a known one |
| `missing_code_is_reported_as_such` | conflating "no code" with "unknown code" |
| `negative_prefixed_code_still_decodes` | the `-0x17000` bug `dp3.rs` had |
| `malformed_token_yields_no_code` | `0x`, `0xZZZ`, `(0x)` yielding a bogus value |
| `only_the_first_hex_token_is_read` | selector text containing other hex |
| `presented_form_is_inferred_from_the_path` | path-form inference |
| `display_never_hides_the_code_or_raw_text` | an operator losing the original bytes |

Consequential suites unaffected:
- `cargo test -p mil_infer --lib` → 37 passed, 6 failed (the same 6 pre-existing
  `graph.rs`/`hwx.rs` failures recorded in `RUN-2-state-lifecycle.md` §9 —
  verified not introduced here).
- `MIL_REQUIRE_HW=1 cargo test -p mil_infer --test e5rt` → 9 passed.
- `cargo test -p mil_spec --test ir` → 29 passed.
- `cargo test -p mil_infer --test anec` → 2 passed.

## 5. A regression I caused and repaired

Changing `EspError::Msg(format!("loadModel failed: {msg}"))` to
`EspError::Load(..)` silently broke PROBE-2's documented reproduction: `dp3.rs`
branched on `Debug` text containing `"loadModel"`, which the new variant does
not emit. It started printing `FAIL_OTHER`.

Repaired by matching the variant instead of grepping a string — which is the
point of the work item — and the output format was kept compatible so
`docs/evidence/0010-deploy-gate-codes.md` still reproduces, now with `kind` and
`form` appended.

Recorded rather than quietly fixed because it is exactly the failure mode this
item exists to remove: a string-grepping consumer. Any *other* caller that
grepped `"loadModel"` would have broken the same way. A workspace-wide search
found none — `dp3.rs` was the only grepper.

## 6. What this does NOT prove

- **Not** that the code space is fully mapped. There are three measured codes;
  Apple-private descriptions can add more. `Unrecognised` is the honest landing
  spot, and `suggested_cause()` returns `None` there rather than guessing.
- **Not** that a code's meaning is stable across OS versions. The decode is a
  heuristic over an undocumented private string, which is why `raw` is always
  retained and why this is documented as heuristic rather than contractual.
- **Not** that `0x1X0004` codes are the *only* failure family. Only `loadModel`
  refusals are decoded. `modelAtURL:` parse failures still return
  `EspError::Msg` and are distinguished by their text; they were out of scope
  for RUN-1, which is about the loader gate.
- **Not** any change to the deploy gate itself. RUN-1 makes failures legible; it
  does not make anything deploy. `docs/adr/0002` stands.

## 7. Cross-lane notes

- Touched only L-RUN files: `crates/mil_infer/src/espresso.rs`,
  `crates/mil_infer/examples/dp3.rs`.
- `dp3.rs` is the probe PROBE-2 relies on. The behavioural change (typed match
  instead of string grep) is recorded here and in `PATCHES.md` so PROBE-2's
  owner sees it.
- **Request to L-PROBE:** `ANE_FRONTEND_SPEC.md` still carries the line 59 /
  line 281 contradiction about `write_state` (found during RUN-2). Unrelated to
  RUN-1, still outstanding.
- Pre-existing failures not introduced here: 6 in `graph.rs`/`hwx.rs`, plus
  `examples/e5_mut.rs` failing to build (`CompileCfg` missing `profiling`, same
  family as the `gate0` defect). Both verified by stashing these changes.
