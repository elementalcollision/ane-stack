# Next-session prompt — ane-stack (updated 2026-10-26, after PR #1 merged)

Paste everything below the line into a new Claude Code session opened on this
repository.

---

You're continuing work on **ane-stack** (`github.com/elementalcollision/ane-stack`, public).
The project reverse-engineers the Apple Neural Engine's resource model on an M5 Max
(`h17`, macOS 26.7.1). This ground truth feeds Chimera.Next's ANE compiler and scheduler.

## Model usage — mandatory (we ran out of tokens last week)
1. **Never use Fable models**, anywhere.
2. **You (Opus) orchestrate and do the synthesis and analysis.** That covers plans,
   decisions, specs, ground-truth docs and final reports.
3. **Subagents are Sonnet or Haiku**, chosen per task, with `model:` passed explicitly on every
   `Agent` and workflow `agent()` call (never inherit Opus):
   - Haiku: mechanical checks, inventories, cross-checks, privacy scans.
   - Sonnet: ANE hardware probes, held-out measurement, adversarial review.
4. **Budget:**
   - Do work inline when a few tool calls settle it.
   - Otherwise use one subagent, and only then a workflow of 5 agents or fewer.
   - Tell me the expected fan-out before launching a workflow.
   - Don't re-read large files (the datasets under `docs/data/`, `vendor/`) unless the
     task needs them.

## Where things stand
- **`main` is current.** PR #1 was merged on 2026-10-26 as `816a642`, with CI green.
  `main` has:
  - the re-measured spec and the writeup (now 124 probes and 274 assertions, with
    the 2026-10-26 BLOBFILE addendum)
  - the visual companion
  - the public datapoints in `docs/data/ane-h17-2026-10-22/`
  - the harness fixes
  - `CLAUDE.md` and `.claude/settings.json`
- **Redaction:** PR #2 (merged 2026-10-26 as `efb81f9`) removed the second Mac's host
  name, tailnet IP, SSH login and the tailnet device inventory from 10 tracked docs.
  - In docs, call that machine **"host B (M4 Pro, macOS 27.0)"**. Never write a host name,
    IP or login.
- **Read in this order, and only as far as the task needs:**
  1. `CLAUDE.md`
  2. `HANDOFF-2026-10-22.md` §3–§5
  3. `docs/spec/ane-port-limits-h17.md` §9 (planning rules), "Corrections" and
     "Open questions"
  4. `docs/data/ane-h17-2026-10-22/README.md`, only when you need raw data

## Before changing anything
```sh
cd vendor/mil_spec && cargo build --release -p milc && cd ../..
./scripts/evidence-check.sh --require-all docs/spec/ane-port-limits-h17.spec   # ~20 s, expect PASS
bash tests/evidence-harness.sh                                                 # expect 8/8
```
Pass `--arch h17` to `milc ane validate|compile`, which default to h16g.

## Decisions waiting on me — ask, don't act
- **Git history** still contains the redacted host details: they are in commits before the
  redaction, and the repo is public. Never rewrite history or force-push without my
  explicit go-ahead.
- **The `ori` page `ane-descriptor-economy` stays as it is.** Don't re-save it; the repo
  copy `docs/spec/ane-port-limits-h17.html` is canonical.

## Work queue (highest value first)
1. **Done 2026-10-26: BLOBFILE weights take no BAR id** (writeup §4; real models keep 53/54
   states). Follow-ups:
   - patch 0019 fixed the fuzzer's header-less `weight_blob` and upstream's
     "BLOBFILE rejected" claim (0018 stays reserved for the example files)
   - weights not yet measured: CoreML lane, matmul, palettized, hundreds of tensors
2. **Port caps per function and per lane:** multi-function programs and the CoreML lane.
3. **State semantics:**
   - assert that non-returned (noupd) updates persist, with a read-back
   - runtime-position appends
   - `[2L, kvh, S, hd]` KV layouts at a real S (2048)
4. **Repo hygiene:**
   - patch 0018 for the 8 unpatched `vendor/.../examples/*.rs`, so `--rebuild` is safe
   - fix the weak assertions in `docs/evidence/0002`, `0004`, `0005` and `0006`
   - add a generator for `/tmp/p3model`, which `shape-flex` needs
5. **Open decode items:**
   - multi-input add-chain trailer records
   - the `[1000,4096]` header anomaly
   - why dim1 = 16 and dim2/dim3 = 256 are special
6. **M4 silicon.** All h16g data is cross-compiled. The only M4 is the macOS 27.0 host, so a
   run there confounds SoC and OS; it also has no Rust toolchain.
7. **L-SCHED / L-RUN.** Claimed by dave; coordinate first. See HANDOFF §5 items 6–8.

## How to work
- **Evidence, not documentation.** Every new law needs a spec line that would fail if the law
  were wrong.
  - Judge by `want_rc`; anchor counts with `$`.
  - Regenerate `docs/data/ane-h17-2026-10-22/spec_datapoints.json` with
    `scripts/spec_to_json.py` whenever the spec changes; CI checks it.
- **Public repo:** scrub private paths, hosts, IPs, logins and emails from anything you commit.
- **Commits:** `lane/<name>: <what>`, with the body saying what failed before, how it was
  verified, and the work-item ID.
- **Branch from `main`, push as you go**, and keep the open PR's description current.
  Ask me before merging any PR.
- **Each task is done when:**
  - `./scripts/evidence-check.sh --all --require-all` passes
  - the harness passes
  - `spec_to_json --check` passes
  - CI is green
  - the writeup and handoff say what changed
