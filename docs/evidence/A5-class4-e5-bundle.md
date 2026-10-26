# Evidence — A.5 class 4: `aned`'s own `.e5` bundle, re-tested

Lane: **L-SCHED**. Work item: ADR-0002 A.5 item 3.

**Answer: `aned`'s own `.e5` bundle is still refused on macOS 27.0 — but the
32-bit code is not the `0x1X0004` deploy gate, and the two loaders behave
differently on the same file.** PROBE-2's class-4 claim survives on 27.0, but
its *framing* ("the same loader refuses everything") was slightly wrong.

Hosts: local macOS **26.7.1** (M5) and host B (M4 Pro) macOS **27.0**
(26A428, M4 Pro).

## 1. Two loaders, not one

`examples/e5_dual_path.rs` (new) puts both paths in one run on the same bundle:

| loader | entry | what it is |
|---|---|---|
| `_ANEClient` | `EspressoProgram::load_precompiled` → `_ANEModel modelAtURL:` + `_ANEClient loadModel:options:qos:error:` | the **deploy** path — presenting a predeployed program |
| e5rt | `e5rt::Program::from_e5_bundle` → `e5rt_program_library_create` | the **supported use** path — build an op from an on-disk bundle |

PROBE-2's class-4 evidence used only the first. They are not the same
statement, and the codebase's own docs (`e5rt.rs` line 469) describe
`from_e5_bundle` as "the precompiled path, no MIL compile at all" — i.e.
loading a precompiled bundle is *normal e5rt operation*, not a deploy attempt.

## 2. Results, same bundle, two OSes

Fresh bundle produced locally by `milc ane run` (so it is `aned`'s *own*
output from this session, not a stale cache artifact — a 5 KB `.e5` is the
normal size here, confirmed by a size histogram across 90+ bundles):

| macOS | `_ANEClient loadModel` | `e5rt program_library_create` |
|---|---|---|
| **26.7.1** | refused `0x120004` | refused, rc `8` |
| **27.0** | refused, rc `1` | refused, rc `8` |

So on **both** OSes the deploy path refuses `aned`'s own bundle. Class 4 stands.

## 3. The macOS 27.0 message changes the reading

Raw text on 27.0:

```text
…error:: Program load failed — no memory (transient; retry under lower
memory pressure) (underlying=0x1)
```

This is **not** the `0x120004` deploy code and not the `bad program image
(underlying=0x13)` code either. On its face it is a *transient resource*
condition, which would mean "not a gate".

Checked rather than assumed:

- **5 consecutive runs, all `0x1`** — stable, not transient in practice.
- **Memory pressure is genuinely low on that host**: 24 GB total, 77%
  system-wide free, swap 11 MB used of 1024 MB. So the message does not
  correspond to a real memory shortfall.

Conclusion: the 27.0 loader reports a *transient* cause for what is, in
practice, a persistent refusal. Treating it as "just retry under lower memory
pressure" would be wrong — that is the message's face value, contradicted by
measurement.

**This mirrors an existing pattern:** the macOS 27.0 `write_state` probe
(PROBE-1 correction) also had its cause *mis-stated* relative to h16g, and
`ANE_FRONTEND_SPEC.md` line 59 vs 281 was the same shape — a documented claim
that a measurement contradicts. The 27.0 loader's diagnostics are less
trustworthy than 26.x's, not more.

## 4. `from_e5_bundle` fails identically on both OSes (rc 8), and why that is not a regression

`program_library_create → 8` ("Invalid E5 path specified" from
`GetE5PathFromCompositeBundle`) reproduces on the outer bundle dir, the
`H17C.bundle` dir, and `main/main_ane`. **This is a path-shape issue in the
probe, not a finding about the loader** — `lib_create` wants a specific
composite layout that this run did not produce, and no caller in the codebase
passes these exact paths either.

Recorded so it is not later mis-cited as "e5rt cannot load `.e5` bundles".
The supported e5rt flow (`compile_auto` / `milc ane run`) demonstrably *does*
build ops from `aned`'s bundles — 9/9 tests pass with `MIL_REQUIRE_HW=1`, and
`milc ane run` executed on this very session's bundle.

## 5. Consequence for ADR-0002

A.5 item 3 is **answered, and class 4 survives macOS 27.0**: `aned`'s own `.e5`
output is refused by the deploy path on both OSes. PROBE-2's reasoning that
this is "not a signing check" still holds — but the *reason* on 27.0 is a
misleading transient-resource code rather than a stable form code.

The Appendix A qualification should note: **closed on 26.7.1; open on 27.0 for
h16g artifacts at scale; and `aned`'s own `.e5` output is refused on both** —
so "even aned's own output fails" is not evidence against 27.0's opening.

## 6. Cross-lane

- Tooling: `examples/e5_dual_path.rs` (L-SCHED). A throwaway `raw_err_dp`
  probe was used to dump the raw 27.0 text and deleted afterwards.
- **L-RUN:** the macOS 27.0 `no memory (transient; …)` code is not in patch
  0017's measured table. A `take_code` correction already handles the *nested*
  code; what is missing is a `kind` for a transient-resource refusal, which is
  arguably not a deploy-gate variant at all.
- No vendor change; no patch; no manifest drift from this item.
