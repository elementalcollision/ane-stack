# LEGAL.md — what the licences do and do not cover

Read this before shipping anything built here.

## Covered by the MIT/Apache-2.0 licences

`vendor/mil_spec/` is © 2026 Adam Clark, MIT OR Apache-2.0. This fork elects MIT.
You may use, modify, and redistribute the **code**, provided you:

1. retain the copyright notice and permission text (`LICENSE-MIT`),
2. carry a change notice on modified files if you rely on Apache-2.0
   (`FORK.md` + in-file `FORK(ane-stack)` comments do this).

`coyote` is MIT, © 2026 Adam Clark. **We do not vendor it.** We adopt two design
patterns and reimplement them (`docs/adr/0004-borrowed-design.md`); no code copied.
If that changes, `NOTICE` and `FORK.md` must be updated first.

## NOT covered — the part that actually matters

`mil_spec`'s ANE-native modules call **private, undocumented Apple frameworks**
through the Objective-C runtime and `dlopen`:

| Module | Apple surface |
|---|---|
| `mil_infer::anec` | `ANECompiler.framework` — `ANECValidate`, `ANECCompile` |
| `mil_infer::e5rt` | `Espresso.framework` — `e5rt_*` C API |
| `mil_infer::espresso` | `aned` XPC, `_ANEModel`, `_ANEClient`, `_ANERequest`, `_ANEIOSurfaceObject` |
| `mil_infer::hwx` | emits Apple's proprietary object format |

A permissive licence on *their* code grants nothing with respect to *Apple's*
frameworks. Those are governed by Apple's developer and software licence terms.
For distribution, DMCA §1201 (anti-circumvention) considerations may also apply
where the code bypasses a technological protection measure.

## Practical posture

| Use | Risk | Notes |
|---|---|---|
| Local research on your own machine | **Low** — same posture as `coremltools` and the wider reverse-engineered Apple tooling ecosystem | Standard practice; keep it internal |
| Internal tooling, not distributed | **Low–moderate** | No redistribution of Apple-derived logic |
| Distributed product using private frameworks | **High — get explicit sign-off** | Not a decision an engineer makes implicitly |

## The safe subset for anything shipped

Use only the **CoreML lane**, which touches public, documented APIs (`coremlc`,
`MLModel`, `MLComputePlan`):

- `mil_spec` core writer (`.mlpackage` / MIL)
- `mil_convert` (safetensors/GGUF → package)
- `mil_passes`, `mil_verify`, `mil_lint`
- `mil_compile`'s subprocess backend (`xcrun coremlc`)

Avoid for shipped artifacts: `mil_infer::{hwx, anec, e5rt, espresso}`.

## Attribution in user-facing material

Any distribution that includes vendored code must include the `NOTICE` file
contents. It is written to be directly pasteable into an about screen.
