# ADR 0002 — The direct-HWX deploy lane is closed; plan around it

**Status:** accepted (2026-10-21). **This is the most consequential decision in the repo.**

## Context

`mil_spec`'s headline feature is emitting the ANE's Mach-O ("HWX") format directly,
with no Apple codegen — the "sovereign" path. Its tests show 22 emitted artifacts
are byte-identical to ones captured from Apple's compiler. It looks like it works.

It does not deploy. I measured four provenances through the same
`_ANEClient loadModel` path on this machine (Apple M5 Max, macOS 26.7.1):

| Artifact | Origin | Result |
|---|---|---|
| `c64k1.hwx`, `c64k2.hwx`, `mixed64x32_32x64.hwx` | captured from Apple's compiler | ❌ `0x170004` |
| `model.macho` | **`ANECCompile` on this machine, this session** | ❌ `0x170004` |
| `cnn_frame_enhancer_192p.H16.espresso.hwx` | **Apple, shipped in `/System/Library`** | ❌ `0x130004` |
| `synthesis_net_GridNet_pyrlite.H18.espresso.hwx` | **Apple, shipped** | ❌ `0x130004` |
| several `.H17.espresso.hwx` | Apple, shipped | ❌ un-catchable ObjC exception |
| MIL → `aned` compiles → `e5rt` execute | — | ✅ **works** |

## Decision

**No work item may depend on deploying self-emitted HWX.** The acceptable use of
the HWX emitter is *generating and verifying bytes* (byte-identity vs captured
artifacts), which remains valuable and testable.

All "runs on the ANE" work targets the **e5rt lane** (`aned` compiles the MIL
itself) or the **CoreML lane**.

## Rationale

Apple's **own** shipped artifacts fail through the same loader, with a *different*
error code, and some crash. That is not a bug in the emitter — it is a
deployment-path gate. Candidate causes (PROBE-2 will settle):

- **Arch mismatch.** `ANECCompile` targets `h16g`; Apple's bundles here are
  `H13`–`H18`; this M5 exposes `h17`. Every bundle on this machine predates it.
- **AOT/signing envelope.** Post-OS-version changes to how `aned` accepts
  predeployed programs (per-arch fingerprint, `precompilation_info` lane,
  restricted-access entitlement).

Either way, reimplementing the emitter in-house inherits the same wall. Its
byte-identity evidence actually shows the *format* was correctly understood — for
the OS generation it was captured on.

## Consequences

- The most novel-sounding upstream capability is the least usable one. Say so
  loudly; it is the single easiest thing to overclaim from these repos.
- Upstream `coyote run` cannot execute here (except `--cpu` organism programs),
  because it routes non-organism programs through the closed lane. Our plan does
  not depend on `coyote`.
- **The working lane's limitations are different** — program-size ceiling, dynamic
  shapes, no scheduler, no int/bool tensor math — and those are addressable. The
  build plan targets those instead.
- PROBE-2 should record whether this is permanent or version-gated, so we revisit
  if Apple opens the path.

## Evidence

`docs/evidence/0002-deploy-lane.md` (full command log).
