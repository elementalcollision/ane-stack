# Review of `HANDOFF-2025-10-22.md`

> **Status (later on 2026-10-22):** acted on in [PR #1](https://github.com/elementalcollision/ane-stack/pull/1). The handoff is now `HANDOFF-2026-10-22.md`, and the spec and writeup were re-measured and rewritten; see the Corrections table in `docs/spec/ane-port-limits-h17.md`. Re-measurement also overturned two points this review accepted:
> - "53 states" is not the cap. It is a 55-id BAR pool, and 54 states fit when the program has no plain input.
> - "`0x9344` = states + plain inputs" was only a special case. `0x9344` = exposed states + max(1, min(in, out)).

**Reviewed:** 2026-10-22, at HEAD `9c52422`, on Apple M5 Max running macOS 26.7.1 (25G241).
**How:** Nine runners (2 Haiku 5.5, 7 Sonnet 5.5) checked each section of the handoff against the repo and against hardware. Their 131 raw findings were deduplicated to 40. Each batch of findings then went to two independent Sonnet 5.5 skeptics with different refutation lenses. Opus did the orchestration and this analysis, and re-ran every hardware claim marked **[re-run]** below.
**Read-only:** nothing in the repo was changed or committed. All probes ran in the session scratchpad.

## Verdict

The process scaffolding in the handoff is sound:
- The gates pass.
- The patches apply.
- The 53/54 state boundary is real and robust.

The descriptor-economy section, however, overstates what was measured, and several of its headline numbers are wrong. Most of the errors have one cause: every repo generator varies only one knob (dim0, or plain-io count with dead inputs). Claims were then generalised past what those generators can show. The spec harness also cannot catch regressions on its "passes" side.

The orientation section points the successor at a lane that is already claimed.

## What holds (verified)

- **Gates:**
  - `vendor-guard.sh --verify` passes (442 files).
  - `apply-patches.sh --check` reports all 17 patches applying in order.
  - The master spec, `--all` (8/8) and `shape-flex-matrix.spec` all pass once `milc` is built.
  - CI is green on the last 4 pushes.
- **State budget:** 53 states compile and 54 fail with `unable to allocate free BAR`. This held on h16g and h17, and across five state shapes (including varying dim1). **[re-run]**
- **Execution cap:**
  - It is a count budget, not a byte budget: the boundary is unchanged at 4 KiB and 16 KiB per port.
  - The slope `127 − in` is correct for in ≤ 64.
- **`__data` sections = plain outputs + 2 × states.** This was exact on 8 programs.
- **`0x9344` count = N + 1 for single-input programs.** Checked at N = 0, 1, 2, 3, 10, 26, 27, 28, 52 and 53. The slot word `(slot_index << 8) | (copy << 7)` matches the data.
- **`0x9365`:** dim1 sits at `+0x0a` and dim0 at `+0x0e`.
- **M4 → M5:** record counts, the slot decode and the 54-state failure are identical, and h17 has one extra `0x934a` for the (53,1,1) program.
- **Toolchain:**
  - `milc run` works on packages and on `.mlmodelc`.
  - `--json` works on `check`, `run` and `plan`.
  - `mil_compile::hw_gate` behaves as described.

## Findings, most severe first

### A. Technical claims that are wrong or unsupported

| # | Sev | Handoff | Finding | Evidence |
|---|---|---|---|---|
| A1 | **high** | H43-45 | **There is no floor at 63.** The real execution rule is `live_in + out ≤ 127`. The floor is an artifact of `gen_mix_ports.py:15`: output `i` reads `x{i % in}`, so when `in > out` only the first `out` inputs are live, and e5rt prunes the rest. The spec only tests in ≤ 64, where `max(63, 127−in) = 127−in`, so it cannot tell the two rules apart. The "floor" line in the spec (in=64) is just the end of the slope. | All inputs live: (65,62) pass, (65,63) **fail**; (100,27) pass, (100,28) **fail**; (126,1) pass, (127,1) **fail**. The same (100,63) passes with `gen_mix_ports.py` and fails when every input is live. **[re-run]** |
| A2 | **high** | H53, H57, H101 | **"The table holds 54 records" / "`0x9344` = states + 1 header" is refuted by the spec's own program.** The spec line that compiles 53 states + 32 in + 32 out produces **85** `0x9344` records and compiles fine. The count is *states + plain inputs*, and a 0-state program already has 1 record. The 53 limit is on state count, and its mechanism is still open, so "WHY 54 resolved" does not hold. One live alternative: the number of data-bearing segments is also N+1, which equals 54 at the cap. | `count_desc_records.py /tmp/pl_siocc/pl_sio.macho` → `0x9344 records: 85` **[re-run]** |
| A3 | **high** | H18, H63, H101 | **The spec's "passes" assertions are vacuous.** `want_out_re step 0:` also matches the *failure* output `milc ane run: step 0: execute_sync → 11`. `want_rc` is never used. This affects 4 lines, including "53 states actually run". Only the "fails" halves would catch drift, which contradicts "the harness is honest". | `gen_mix_ports.py 1 127` gives rc=1, and its output still matches `step 0:` **[re-run]** |
| A4 | **high** | H56 | **`0x9361` is not a fixed template, so the read/write asymmetry is an artifact.** The record carries dim1 at `+0x0a`, the stride class and dim1×16. In an N-state program it also embeds a per-record slot word, giving N distinct bodies. `cmp_9361.py` only compares the first 0x52 bytes of the first record, on two programs that differ only in dim0, the one dimension the read record ignores. | `cmp_9361.py` on dim1=4 vs dim1=8 → `bodies differ across programs` **[re-run]** |
| A5 | **high** | H55 | **The stride law `min(2·dim1+8, 32)` is wrong.** The observed stride is `8·min(⌈log2 dim1⌉, 4)`, which saturates at dim1 = 9, not 12. The law matches only at dim1 = 4, 8, 12 and in the saturated range. No repo generator varies dim1, so the spec checks a single point. | dim1 2/5/9 → stride 8/24/32; the law predicts 12/18/26 **[re-run]** |
| A6 | medium | H55 | **The `0x9365` region map (`+0x48` = dim1 MiB) holds only for single-state programs and for the *last* record.** The other N−1 records use a layout 4 bytes longer, with `+0x48` = 1 MiB. As a result, `decode_9365.py` on the standard 53-state binary prints `region=1048576`. | Both skeptics upheld this |
| A7 | medium | H79 | **`0x9442` count = plain outputs + 2N, not "2N+1".** The two only match when there is exactly one output. The 107 records are embedded children (54 inside `0x9344`, 53 inside `0x9361`), so "unprobed" is no longer accurate. | (52,1,50) → 154 records; 2N+1 would give 105 **[re-run]** |
| A8 | medium | H59 | **M4 → M5 is "identical" only in counts.** Every `0x9344`, `0x9361`, `0x9365` and `0x9442` body differs in arch-specific bytes (for example `0x10` → `0x20`), and the Mach-O cpusubtype is 7 vs 9. The `0x934a` delta scales with plain I/O (64 at 53 states + 32/32, 0 for some programs), so it is not "one per program, fixed". All of this comes from `--arch h16g` compiles on the M5 host; nothing was run on M4 hardware. | Both skeptics upheld this |
| A9 | medium | H80 | **Open thread 2's premise ("constant payload 0x21 — why 33?") is wrong.** The same byte is `0x31` on h16g, and on h17 it varies by child and position (`0x21`, `0xc1`, `0xe1`). It looks like a packed flags byte. | Both skeptics upheld this |
| A10 | medium | H39-41 | **"NOT frontend" omits a frontend cap.** `validate`/`compile` reject a declared in+out ≥ 256 with `MaxLiveInLiveOutExceeded`, and 128/128 fails. The repo's own `reconciliation-two-port-limits.md` already records this. | Upheld (medium/low) |
| A11 | medium | H63 | **"Executable assertions for all of it" is not true.** The spec does not assert: the floor, the `__data` formula (it is a comment only), the per-state record triple, the slot-formula derivation, stride saturation, the region "×4 slots", `0x9361` across counts, the h16g slot model, `0x9442`, or "vmsize grows linearly". | Both upheld |
| A12 | low | H48, H52 | **Two loose claims.** "All ruled out" rests on ad hoc runs for consts and dim1 that cannot be reproduced from the repo (the conclusion does hold under independent probes). The per-state triple depends on shape: dim0=1 gives 2× `0x9361` and no `0x9365`, dim1=16 gives `0x9360`/`0x9364`, and dim1=1 gives no copy records at all. | Upheld |

### B. Orientation and process: what would mislead the successor

| # | Sev | Handoff | Finding |
|---|---|---|---|
| B1 | **high** | H69, H81 | **L-SCHED is claimed, not open.** `OWNERSHIP.md:18` lists it as claimed by dave, and only L-LINT is unclaimed (`:20`). There are 28 `lane/sched` commits, the last at 09:02 on the handoff day, and `ADR-0003` is accepted. Following H81 means starting work on a lane someone else holds. "L-RUN (other agents)" also conflicts with OWNERSHIP, though skeptics rated that half as ambiguous. |
| B2 | **high** | H71 | **`apply-patches.sh --rebuild` (which H71 recommends) would delete 8 tracked files.** `crates/mil_infer/examples/{cml_exec,e5_dual_path,e5exec,mk_minflex,predseg,probe_run2_state,seg4,shape_flex_e5rt}.rs` come from no patch: they were added in b85b6fd, 26447d2 and d4579a7, and the manifest was resynced to include them. `--rebuild` uses `rsync --delete`, so it removes them and breaks `shape-flex-matrix.spec`. The guard stays green, but "vendor tree = pristine + patches" is already false. The files are recoverable from git, but the handoff does not warn. |
| B3 | medium | H81 | **"Start at SCHED-1" leaves out its status.** SCHED-1 is partially unblocked: the placement half is blocked (MLComputePlan places nothing on the ANE on either OS), the cost half is usable only on macOS 27.x, there are 4 `SCHED-1-*` evidence files, and no `mil_sched` crate exists yet. |
| B4 | medium | H20-24, H87-95 | **There is no step to build `milc`.** A plain `cargo build --release` builds only the `mil_spec` root package; the binary needs `cargo build --release -p milc`. Without it, fresh clones and worktrees FAIL the master spec and 6 evidence specs (they FAIL, not SKIP). The main checkout already has a prebuilt binary, which hides the problem. |
| B5 | medium | H73 | **The ADR-0002 summary has no OS qualification.** Appendix A records that on macOS 27.0 (one M4 Pro host), self-emitted h16g artifacts load and run, and Apple's H16 bundles load 8/8. A.4 asks for the rule to be reworded as "on 26.7.1". The handoff never states an OS or build. |
| B6 | low-med | H71 | **The patch procedure is incomplete.** <br>• The `--generate` dirty-tree refusal is skipped inside linked worktrees (`[ -d .git ]` is false there). <br>• `--rebuild` ends by running `--generate`, so for a new uncommitted patch it either fails in the main checkout or silently writes the manifest in a worktree. <br>• In practice the history uses a separate "sync manifest" commit. <br>• It omits the rule to derive patches from a committed diff against pristine + lower-numbered patches (`PATCHES.md:45-51`, evidence 0006). |
| B7 | low-med | H34, H97 | **CI protects none of the descriptor-economy claims.** Neither workflow runs `evidence-check.sh` or any spec. `--all` (H93, "the whole suite") skips both `docs/spec/*.spec` files. `cargo test --workspace` cannot be green here: 6 `mil_infer` lib tests are known pre-existing failures, and the handoff never says so. |
| B8 | low | H83 | **RUN-4 depends on SCHED-3** (`BUILD_PLAN:340`), and RUN-3 is skipped. The test behind "graph proved fwd+bwd+SGD" (`ane_onchip_backprop_training_exec`) is upstream's, and it fails on this host. |
| B9 | low | H14, H71, H72 | **Attribution rules are stated more absolutely than the repo follows them.** <br>• Only 9 of the 23 patched files carry a `FORK(ane-stack)` marker. <br>• The fork elects MIT, so Apache §4(b) applies only if relying on Apache. <br>• `ANE_FRONTEND_SPEC.md` *is* edited by patch 0015, which is the sanctioned route for corrections (OWNERSHIP clarification); ADR-0002 A.6 still has a pending correction. |
| B10 | low | H18, H31, H81 | **Several statements are looser than the evidence.** <br>• Two of the "three refuted upstream claims" (`--cpu`, `rope`) belong to `coyote`, which is not vendored, and have no measurements here. <br>• Patches 0012 and 0015 have no regression test. <br>• The 84%/65% figure is upstream's MLComputePlan *estimate*, which this repo found to be degenerate on 26.7.1. |
| B11 | nit | various | <br>• The file name says 2025 but the content says 2026. <br>• H6 gives the parent commit as HEAD. <br>• `artifacts/ane-descriptor-economy` is an `ori` artifact, not a repo path. <br>• "`__data` segments" are really sections. <br>• The spec labels two different sections "Finding 2". <br>• The decoders read the wrong `section_64` fields (addr/size at `+32`/`+40` instead of size/offset at `+40`/`+48`); counts are unaffected today, but this is latent. <br>• The writeup still has stale "slot word undecoded" paragraphs and an old provenance build (`25G91`). |

**Rejected by the skeptics:**
- The claim that NetworkJITShapesPath was mischaracterised.
- The charge that patches 0004 and 0009 have no test.
- The argument that "three" is a stale count.
- FORK.md's "single upstream commit" and the commit-convention compliance figures, which skeptics treated as repo matters rather than handoff errors.

## Suggested corrections (to the handoff and the spec)

1. **Execution cap.** Replace `max(63, 127−in)` with `live_in + out ≤ 127`. Add live-input spec lines at in > 64, plus the frontend `in+out ≤ 255` line.
2. **Pass assertions.** Anchor them with `want_rc 0`, or use `want_out_re ^step 0: [0-9]`.
3. **The cap.** Restate it as a **53-state** limit with the mechanism open. Drop "the table holds 54 records". Record `0x9344` = states + plain inputs.
4. **`0x9361` and `0x9365`.** Withdraw "fixed template". Replace the stride law with `8·min(⌈log2 dim1⌉, 4)`. Scope the region map to the final record. Add a dim1 generator so all of this can be asserted.
5. **`0x9442` and M4/M5.** Change `0x9442` to outputs + 2N. Change the M4/M5 claim to "same counts, arch-specific bytes everywhere, cross-compiled on M5". Rewrite open thread 2.
6. **Orientation.** Fix the lane table so L-SCHED shows as claimed. Give SCHED-1's real status. Add `cargo build --release -p milc`. Warn that `--rebuild` deletes the 8 unpatched examples. Qualify the deploy-lane rule as applying to macOS 26.7.1.
