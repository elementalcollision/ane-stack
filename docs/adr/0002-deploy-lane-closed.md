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

---

# APPENDIX A — Qualification (2026-10-22, second pass on macOS 27.0)

> **This appendix qualifies, and does not replace, the decision above.** The
> Context/Decision/Rationale are kept verbatim because they were measured on
> macOS 26.7.1 and remain true of that OS. What follows records that they are
> **not true of macOS 27.0**, and changes nothing about where work goes — yet.

## A.1 What changed

A macOS 27.0 host became reachable (`davids-mac-mini`, tailnet `100.127.197.66`,
user `davidgraham`, **M4 Pro**, build `26A428`) and PROBE-2's probes were re-run
there with the same binaries, so the difference is the OS and not the build.
Full data: `docs/evidence/PROBE-2-macos27-result.md`.

The single most decisive result is one artifact on two hosts:

| artifact | macOS 26.7.1 | macOS 27.0 |
|---|---|---|
| `two_layer.mil` → `ANECCompile --arch h16g` → Mach-O | ❌ `0x170004` | **✅ `LOAD_OK` + `EVAL_OK`** (in=1, out=2) |
| same model, `--arch h17` | ❌ `0x170004` | ❌ failed (`underlying=0x13`) |

The model is not a toy: 13 ops, two `state<>` layers, full-arg
`slice_update` triples — the RUN-2 fixture. It loads **and executes** on 27.0.

So: **"closed at the OS level" is an OS-version statement, not an invariant.**
The closure is real on 26.7.1 and open on 27.0 for h16g images.

## A.2 What the arch split now looks like

Apple's own shipped bundles on 27.0, same binary, same command:

| arch | verdict |
|---|---|
| **H16** | **`LOAD_OK` (8/8)** |
| H13 · H14 · H15 · H17 | failed (8/8 each) |

H16 is uniquely accepted. PROBE-2 on 26.7.1 *rejected* H-arch — on 26.7.1 h16g
and h17 artefacts failed identically, so the gate looked arch-independent. On
27.0 the loader plainly discriminates by arch. **This is not the same gate,
and the two OS builds must not be described with one sentence.**

## A.3 Why the decision does NOT change

The Decision says no item may *depend* on deploying self-emitted HWX. That still
holds, for reasons that are now stronger rather than weaker:

1. **26.7.1 is the machine the plan was built for**, and it is still closed
   there. Anything depending on the deploy lane is unbuildable for the current
   work.
2. **27.0's acceptance is arch-specific and unexplained.** We know *which*
   image loads, not *why* — allowlist, entitlement, or capability are all
   unmeasured. A dependency on an unexplained acceptance is a dependency on
   Apple's unevidenced behaviour.
3. **The verifying step is untested at scale.** One 13-op model loads and evals.
   Nothing says a real transformer shard does. Program-size ceiling, state
   residency across many layers, and int/bool ops are all unprobed on that path.
4. **The e5rt and CoreML lanes remain the only *verified-general* paths**, and
   PROBE-2's positive control (`milc ane run`, ~242 µs) works on both OSes
   without any of the above caveats.

So the Decision stands. What changes is the **strength of the claim**: it is no
longer "deploy is closed", it is "deploy is closed on 26.7.1, open on 27.0 for
h16g images for reasons we do not yet understand".

## A.4 The one sentence that must be qualified

The README's ground rule — *"Never depend on the closed deploy lane"* — is
correct as guidance but is now load-bearing on a weaker basis than when written.
It should read as: never depend on the deploy lane **on 26.7.1**; a 27.0 path
exists and is uncharacterised.

## A.5 What would re-open this ADR

Concrete, ordered, cheapest first:

1. **A real transformer shard, h16g, through `_ANEClient` on 27.0** — `mil_spec`
   → `ANECompile --arch h16g` → `dp3`/`deploy_probe` on the mini. If a >3k-op
   model loads, the *scale* caveat falls away.
2. **Why H16** — diff the accepted vs rejected image headers, or check against a
   non-Apple-compiled h16g bundle. Separates allowlist from capability.
3. **Class 4 re-run:** `aned`'s own `.e5` bundle. PROBE-2's "even aned's own
   output is refused" is 26.7.1-only and may now *pass*, which would change the
   picture again.
4. **A second 27.0 host** — the current data is n=1 per OS, and one host is a
   machine configuration as much as an OS build.

Until 1–4 land, **ADR-0002 stays accepted as written, with this appendix.**

## A.6 Cross-lane

- Produced by L-SCHED at the lane owner's direction, using L-PROBE's PROBE-2
  instrument. PROBE-2 remains the owner of the deploy-gate conclusion; this
  appendix is the ADR record of new data.
- **`ANE_FRONTEND_SPEC.md`'s `0x1X0004` family is 26.x-specific.** macOS 27.0
  emits `…bad program image…(underlying=0x13)` instead. Patch 0014's parser was
  corrected (patch 0017); the spec's code table is L-PROBE's to amend.
- **e5rt on 27.0 is untested.** No Rust toolchain was installed on that box (the
  probes need none, being `dlopen`-based), so the positive control has not been
  re-run there. Worth doing before anyone plans work that needs it.
