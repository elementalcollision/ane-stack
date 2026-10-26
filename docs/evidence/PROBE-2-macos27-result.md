# Evidence — PROBE-2: deploy gate re-run on macOS 27.0

Lane: **L-SCHED, executing a PROBE-2 measurement.** Re-run at the lane owner's
direction using the macOS 27.0 host that became available. The deployment-gate
instrument and conclusions are L-PROBE's; this is new data, not a rewrite.

Hosts:

| | Host | OS | HW |
|---|---|---|---|
| **A** | local (this M5 Max) | macOS **26.7.1** (25G241) | Apple M5 (h17) |
| **B** | a second Mac on the owner's private network | macOS **27.0** (26A428) | Apple M4 Pro |

Same `dp3` / `deploy_probe` binaries on both (copied, arm64 macOS, no rebuild) —
the probes `dlopen` the frameworks at runtime — so any difference is the OS.

Prior finding under re-test: `docs/evidence/0010-deploy-gate-codes.md`
("No externally-presented artifact deploys … on this OS build").

---

## 1. Headline result: the gate opens on macOS 27.0, and it is ARCH-specific

The single most decisive comparison — one artifact, two hosts:

| artifact | macOS 26.7.1 (A) | macOS 27.0 (B) |
|---|---|---|
| `sig.macho`, **h16g**-compiled | **`0x170004`** (`BareMachoRejected`) | **`LOAD_OK`** (load *and* `EVAL_OK`) |
| `sig.macho`, **h17**-compiled | `0x170004` | **`0x13`** failed |

Same bytes. One loads, one rejects, by OS. On A both were rejected. So
**macOS 26.7.1's blanket rejection is an OS-build behaviour, not a property of
our artifacts.**

## 2. Arch matrix — and PROBE-2's H-arch hypothesis is back

Apple's own shipped `.espresso.hwx` bundles (8 resolutions × 5 arches), on B:

| arch | verdict | count |
|---|---|---|
| **H16** | **`LOAD_OK`** | 8/8 |
| H13, H14, H15, H17 | `0x13` failed | 8/8 each |

A perfect split. Apple's own `H16` bundles load on B; every other arch fails,
including `H17` — which is close to B's own SoC family. Cross-checked by sending
A's copies to B: `apple_h16.espresso.hwx` → `LOAD_OK`;
`apple_h17.espresso.hwx` → failed. So it is the *arch in the artifact*, read by
the 27.0 loader.

**This resurrects H-arch, which PROBE-2 rejected on 26.7.1**, where an
h17-targeted artifact failed identically to h16g and the gate looked
arch-independent. On 27.0 the discriminate is plainly arch — and specifically
**H16 is accepted**. That is consistent with what each OS's loader was built to
trust, but this does not establish *why*; see §5.

## 3. The error text changed materially

`0x1X0004` no longer describes macOS 27.0. Raw text on B:

```text
…optOutOfModelMemoryUnwiring:intermediateBufferSizeHint:error::
    Program load failed — bad program image (model may be corrupt or
    incompatible) (underlying=0x13)
```

Three things follow:

- The `0x1X0004` family in `ANE_FRONTEND_SPEC.md` and patch 0014's table is
  **26.x-specific** and should not be presented as general.
- The code is **`0x13`**, and it is the *underlying* value, not the whole
  message. Patch 0014's `take_code` grabs the first `0x` token in the
  description — which on 27.0 yields `Some(19)` from the wrong position and
  classifies it `Unrecognised` with `form=None`. **Patch 0014 needs updating for
  27.x's message shape**; it currently reports a wrong code on this OS.
- The new text carries a **human-actionable cause** ("bad program image / model
  may be corrupt or incompatible"), which `0x170004` never did.

## 4. Not tested

- **Class 4 (`aned`'s own `.e5` bundle).** No `.e5` exists on B — e5rt has never
  compiled there (no Rust toolchain, none installed). So the "aned's own output
  is refused too" evidence is still 26.7.1-only and has **not** been re-tested.
  Notable: the positive control may now pass, since the gate demonstrably opens.
- **`ESP_CLIENT` variants** (`shared`/`private`/`new`). `dp3` uses `shared`, which
  is the usable one; the private/new variants' 27.0 behaviour is unknown.
- **Whether the small h16g Mach-O is *typical*.** It loads, and it is the same
  tiny sigmoid `sig.mil` used on A. That a *trivial* program deploys on 27.0
  does not mean a real transformer shard does.

## 5. What this does NOT settle (stated plainly)

- **Why H16.** The data shows the loader accepts H16 and rejects H13–H15 and
  H17. It does not say whether that is an entitlement, an allowlist of
  known-good images, or an arch capability check. Distinguishing those needs
  more than a verdict.
- **Whether our own HWX can deploy on 27.0 if targeted H16.** Probably the single
  most valuable next probe, and *not* done here: it needs an `ANECompile` with
  `--arch H16` against a model whose program image 27.0 accepts. The local
  `milc ane compile --arch h16g` output already loads on B — which is exactly
  that, and is encouraging — but it is a 2-op sigmoid, see §4.
- **Cross-arch confound:** A is M5/h17, B is M4 Pro. That the accepted arch is
  `H16` and B is an M4 is suggestive but this is n=1 host per OS.

## 6. Consequence for ADR-0002

ADR-0002 says the deploy lane is "closed at the OS level" and warns against
proposing anything that emits a binary and runs it. **That statement needs
qualifying:** it is closed on macOS 26.7.1 and, at least for H16 images, **open
on 27.0**. This does not overturn the project's direction — the two working
lanes (CoreML, e5rt) remain the only *verified-general* paths — but the blanket
"closed" is no longer true as written, and the ground rule "never depend on the
closed deploy lane" now rests on a weaker basis than when it was written.

Recommendation (owner's call, recorded not actioned): re-run
`milc ane compile --arch h16g` on a *real* model against B before treating
ADR-0002 as permanent. If a real model's HWX deploys on 27.0, ADR-0002 should be
amended rather than left standing as an absolute.

## 7. Cross-lane notes

- Method: probes `scp`'d to B, artifacts `scp`'d to B, no toolchain installed on
  that machine. Keys that do *not* work for B are recorded in git history so
  nobody re-tries them. Access was over SSH on the private network (host, address
  and login deliberately not recorded in this public repo).
- **Request to L-RUN:** patch 0014's `AneLoadError::take_code` mis-parses macOS
  27.0's message (returns `Some(19)` from the underlying value). A 27.x
  correction is needed before the typed error is trusted there.
- **Request to L-PROBE:** §1–§3 are PROBE-2's territory. This file is data for
  that lane, produced by L-SCHED; the conclusions and any spec/ADR edit are
  L-PROBE's to make.
