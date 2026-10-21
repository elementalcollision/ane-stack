# Evidence — the direct-HWX deploy lane is closed (ADR-0002)

Work item: `PROBE-2` (initial finding — deeper decode still to do).
Host: Apple M5 Max (Mac17,7), macOS 26.7.1, cargo 1.95.0.

## Claim under test

Upstream asserts self-emitted HWX deploys to the ANE. `mil_spec`'s own
`hwx::tests::*_byte_identical` suite (22 tests) shows the bytes match Apple's
compiler. Does that mean it runs?

## Method

All artifacts were passed to `mil_infer::espresso::EspressoProgram::load_precompiled`
— the `_ANEModel` / `_ANEClient` deploy path — on the same machine, in isolated
processes (ObjC exceptions abort a Rust process, so each probe is its own run).

## Results

| Artifact | Origin | Code / result |
|---|---|---|
| `c64k1.hwx`, `c64k2.hwx`, `mixed64x32_32x64.hwx` | captured upstream from Apple's compiler | `0x170004` |
| `model.macho` | `ANECCompile` **on this machine, this session** (h16g, `ModelMaxDramUsage = 24992`) | `0x170004` |
| `cnn_frame_enhancer_192p.H16.espresso.hwx` | **Apple, shipped in `/System/Library`** | `0x130004` |
| `synthesis_net_GridNet_pyrlite.H18.espresso.hwx` | **Apple, shipped** | `0x130004` (stable over 2 runs) |
| `cnn_frame_enhancer_{96p,480p,544p}.H17.espresso.hwx` | Apple, shipped | `fatal runtime error: Rust cannot catch foreign exceptions, aborting` |

The lane that **does** work:

```console
$ milc ane run /tmp/sig.mil --steps 1
step 0: 211.292µs
z: 64/64 nonzero, head [0.73095703, ...]
```
`sigmoid(1.0)` = `0.7310586`; hardware returned `0.73095703`, within fp16 rounding.

## Interpretation

Three different provenances fail — including **Apple's own shipped artifacts** —
with **different error codes**, plus un-catchable ObjC exceptions on `H17`. This is
the signature of a deployment-path gate, not a malformed binary:

- `0x170004` — our artifacts (and upstream's captured ones)
- `0x130004` — Apple's OS-shipped bundles
- exception — Apple `H17` bundles

Most likely causes (to be settled by `PROBE-2`):

1. **Arch mismatch.** `ANECCompile` targets `h16g`; system bundles are `H13`–`H18`;
   this M5 exposes `h17`.
2. **AOT/signing envelope changes** in recent macOS for predeployed programs.

## What this proves / does not prove

- **Proves:** the emitter is not the blocker; reimplementing it would inherit the
  same wall. Byte-identity evidence is valid for the OS generation it was captured on.
- **Does not prove:** that the gate is permanent, or that no path deploys. A
  different OS version, a different SoC, or a signed envelope may work. `PROBE-2`
  owns settling this.
- **Does not prove:** anything about e5rt, which is unaffected.

## Consequence

ADR-0002: no work item depends on deploying self-emitted HWX. The HWX emitter's
acceptable use is generating and verifying bytes.
