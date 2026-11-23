# Session 2 prompt — ane-stack (written 2026-11-23)

Paste everything below the line into a new Claude Code session opened on this
repository. It replaces the 2026-10-26 prompt.

---

This is **Session 2** of **ane-stack** (`github.com/elementalcollision/ane-stack`, public).
The project reverse-engineers the Apple Neural Engine's resource model on an M5 Max (`h17`).
That ground truth feeds Chimera.Next's ANE compiler and scheduler, so a wrong law costs more
than a missing one.

## Model usage — mandatory
1. **Never use Fable models**, anywhere.
2. **You (Opus) orchestrate and do the synthesis and analysis:** plans, decisions, specs,
   ground-truth docs and final reports.
3. **Subagents are Sonnet or Haiku.** Pass `model:` explicitly on every `Agent` and workflow
   `agent()` call; never let one inherit Opus.
   - Haiku: mechanical checks, inventories, cross-checks, privacy scans.
   - Sonnet: ANE hardware probes, held-out measurement, adversarial review.
4. **Budget:**
   - Work inline when a few tool calls settle it; then one subagent; then a workflow of
     5 agents or fewer.
   - Tell me the expected fan-out before you launch a workflow.
   - Don't re-read the large files (`docs/data/`, `vendor/`) unless the task needs them.

## Safety on this Mac — mandatory
This M5 Max is also my working machine, and it **kernel-panicked twice on 2026-10-26**
during this work. Subagents don't see this prompt, so **paste this section verbatim into
every subagent prompt that touches the host.**
- **No unbounded filesystem scans.** Never run `find`, `du`, `grep -r` or `ls -R` outside the
  repo or your scratchpad: not `/tmp`, `$TMPDIR` or its parent, `~/Library` or system paths.
  - One `find` over the temp tree exhausted kernel vnodes; launchd died and the Mac
    panicked.
  - Use `-maxdepth`, `ls` of one known directory, or `stat`.
  - Outside the repo you may `stat`, `ls` or `mv` only one exact, named path (such as a
    failing spec's `/tmp/<stem>.compiled`), never a glob over a temp directory.
  - Ask me before anything broader.
- **"Light" means all of these:**
  - one `milc` process at a time, run sequentially
  - programs no bigger than the master spec's: small fp16 graphs, ≤ 53 states, and
    ≤ 64 MiB of weights plus state per program
  - no CoreML-lane (`--units ane`) compiles
  - ≤ ~10 deliberately failing compiles in a row, with a few seconds between them
- **Anything beyond "light" needs my go-ahead first.** That includes multi-GB CoreML
  compiles, many-procedure programs and CoreML-lane probes.
  - The second panic (a WindowServer watchdog) came right after CoreML-lane runs with
    54–64 states over 1024³ matmuls. The cause is unproven.
- **Heavy lines never go in the master spec.** They go in an opt-in spec that
  `--all` doesn't pick up (it globs only `docs/evidence/*.spec` and `docs/spec/*.spec`,
  non-recursively).
- **Hardware-free:** `tests/evidence-harness.sh` (it uses a fake milc) and
  `scripts/spec_to_json.py --check`.
  - Everything else under `scripts/evidence-check.sh` runs on the ANE.
  - The only hardware run that is pre-authorised is the re-baseline below.

## Where things stand (2026-11-23)
- **`main` is `e1b2824`, with CI green.** Three PRs are merged, all on 2026-10-26:
  - PR #1: the re-measured model
  - PR #2: the host-detail redaction
  - PR #3: BLOBFILE weights take no BAR id, and BLOBFILE is accepted on h17 (patch 0019)
- **The master spec** `docs/spec/ane-port-limits-h17.spec` has 124 probes and 274 assertions.
  `docs/data/ane-h17-2026-10-22/spec_datapoints.json` mirrors it, including its SHA-256,
  so **any** spec edit, even a comment, needs the JSON regenerated. CI checks it.
- **The host OS has changed.** This M5 Max now runs **macOS 26.7.3 (25G342)**. Every number
  in the writeup and spec was measured on **26.7.1 (25G241)**, and nothing has been re-run
  on 25G342 yet.
- **Git:** work in your own worktree. Run `git fetch origin` and branch from `origin/main`.
  Don't pull or switch branches in the main checkout; other sessions use it.
- **The port-caps work (call it "PC"; it used to be "work item 2") is PAUSED by me.**
  Resume it only when I say so.
  - **Where it is:** one local WIP commit, `3fe1337`, on local branch
    `lane/probe-port-caps-scope`, on top of `e1b2824`. It was saved on 2026-11-23 and has
    never been pushed.
    - Find its worktree with `git worktree list`. It is under the main checkout's
      `.claude/worktrees/`.
    - Inspect it read-only: `git -C <path> log --oneline -2` and
      `git -C <path> show --stat HEAD`. The commit message lists what's unfinished.
    - **Never run the master spec from that branch.** §10f, the heavy CoreML lane, is still
      inside it.
    - The branch's upstream is `origin/main`. When I say push, push explicitly:
      `git push -u origin lane/probe-port-caps-scope`.
    - **If the worktree or the commit is missing, stop and ask me.** Don't search for it
      outside the repo.
    - Never run `git clean`, `git checkout .`, `git reset --hard`, `git worktree remove` or
      `git worktree prune` on it.
  - **What's in it:**
    - new `scripts/gen_multi_fn.py`
    - new `examples/gen_ports_pkg.rs`, plus `examples/Cargo.toml`
    - master spec §10 (10a–10f)
    - writeup §10, whose CoreML half is still the placeholder `<!-- COREML-LANE -->`
    - the corrected `gelu` row in `docs/spec/ane-frontend-h17.md`
  - **Runner observations on 25G241: tentative, and nothing on `main` asserts them.**
    The branch has draft spec lines for the multi-function ones, but they were never run
    as part of the master spec.
    - Multi-function:
      - The frontend cap (255) and the BAR pool (55) appear to be **per function**.
      - Compile also caps the io sum over all functions at 255, and fails silently.
      - e5rt runs only `main`; the other functions are parsed, never ANE-compiled.
    - CoreML lane, **all unconfirmed** (the panic cut the mutation check short):
      - placement by cost
      - the 127 cap failing visibly
      - a **silent CPU fallback with rc 0** over 255 ports
      - the 53/54 state cap not applying. The suspected reason is that state writes run
        on the CPU; that is a hypothesis.
    - `gelu` validates, compiles and runs with `mode = "EXACT"` or
      `"TANH_APPROXIMATION"`. The fuzzer's `"tanh"` is not a valid mode, which is why
      `gelu` looked rejected.
- **Read in this order, and only as far as the task needs:**
  1. `CLAUDE.md`
  2. `HANDOFF-2026-10-22.md` §3–§6
  3. `docs/spec/ane-port-limits-h17.md` §9 (planning rules), "Corrections" and
     "Open questions"
  4. `docs/data/ane-h17-2026-10-22/README.md`, only when you need raw data

## Step 0: re-baseline on 25G342 (pre-authorised; its own branch and PR)
Do this first, before anything else in the queue. Run the steps **one at a time, in this
order**, and stop at the first failure or anything odd on the system: a stall, or a
process that won't exit. Don't repeat it in a loop.
```sh
cd vendor/mil_spec && cargo build --release -p milc && cd ../..
bash tests/evidence-harness.sh                                                 # hardware-free; expect "all evidence-harness tests passed"
python3 scripts/spec_to_json.py --check docs/data/ane-h17-2026-10-22/spec_datapoints.json   # hardware-free
./scripts/evidence-check.sh --require-all docs/spec/ane-port-limits-h17.spec   # ANE, ~35 s of small programs
./scripts/evidence-check.sh --all --require-all                                # ANE, 10 specs
```
- **If it all passes,** open a small PR from a branch off `origin/main`. It records that the
  model re-verified on 25G342, with a dated line in each of:
  - the writeup's "Build provenance"
  - the spec header (line 42 names 25G241)
  - the handoff's host line

  Keep 25G241 as the build the numbers were measured on. Regenerate the datapoints JSON,
  because the spec changed. When PC resumes later, rebase it onto this.
- **If anything fails,** rule out stale `/tmp` fixtures first (HANDOFF §6). `milc run`
  silently reuses a partial `/tmp/<stem>.compiled`, and old files there vanish while their
  directories stay.
  - Re-run the same package from a fresh path.
  - If that passes, move that one named stale cache aside and re-run the spec.
  - A fail that survives a fresh path is an **OS-drift finding**. Report it to me before
    you change any law.

Pass `--arch h17` to `milc ane validate|compile`, which default to h16g.

## Work queue (after Step 0, highest value first)
Queue numbers refer only to this list. Only item 1 is paused; every hardware step in
items 2–8 still follows "Safety".
1. **PC wrap-up — only when I say resume.** My chosen plan is a **draft PR with no hardware
   runs**:
   - First, rebase the WIP commit `3fe1337` onto Step 0's branch. Squash or reword it before
     the PR.
   - Move §10f (the CoreML lane) out of the master spec into
     `docs/spec/opt-in/coreml-lane-h17.spec`.
   - Fill in the writeup:
     - the CoreML half of §10, labelled as unconfirmed
     - the §9 rules and the coverage notes
     - Open question 2
   - Update the handoff, and remove this prompt's "PAUSED" block.
   - Add a writeup section that classifies the claims of **arXiv 2606.22283v2** (Bryngelson,
     *Apple Neural Engine: Architecture, Programming, and Performance*) against our data, as
     **agree / conflict / not covered**. Model it on "The ori pages, claim by claim".
     - Read it at `arxiv.org/abs/2606.22283v2`. If you can't fetch it, ask me for my local
       copy. Never commit the PDF.
     - Cite only the sections you have actually read.
     - Say whether each paper claim was measured, decompiled or predicted.
     - Note the chip difference: the paper's M5 "H17s" vs our M5 Max "H17C".
     - Quote short phrases only, and keep the paper's per-family shape limits out of the
       master spec.
   - Regenerate the datapoints JSON. Run **only** the hardware-free checks: the harness and
     `spec_to_json --check`. Not `evidence-check.sh`.
   - Push the branch and open a **draft** PR. It must say that the master spec was not
     re-run with §10 and that the CoreML mutation check was interrupted.
   - Then ask me whether §10a–e (light, multi-function) may be run on 25G342. PC isn't done
     until that run passes.
2. **State semantics (open Q4).** Each of these feeds the KV-cache design:
   - **First new spec line:** assert with a read-back that non-returned (`noupd`) state
     updates persist across steps. One skeptic has seen it; nothing asserts it.
   - **Settle the native-state conflict with the paper.** Its §14.7 reportedly says native
     `read_state`/`write_state` doesn't reach the engine; we run `state<>` on h17 via e5rt
     inout ports. Do a clean side-by-side: our inout binding vs a plain-input binding.
   - **Runtime-position appends.** Every probe so far writes at `begin = [0,0,0,0]`.
   - **`[2L, kvh, S, hd]` KV layouts at S = 2048:** port cost, the page rule and the
     tentative row cap. Compute the state size first; over the "light" limit, ask me.
3. **Graph coverage for the compiler.** Every probe is a small elementwise fp16 graph.
   Light probes first:
   - matmul/linear, softmax over long axes, and attention-style reads
   - numerics: compare outputs to a CPU reference, starting with the boundary programs
     and the N = 53 LUT shed into `__TEXT`
4. **Weights follow-ups (writeup §4):**
   - matmul weights
   - palettized or quantized blobs
   - more than one `weight.bin`
   - hundreds of weight tensors
   - BLOBFILE through the CoreML lane (heavy: make it opt-in and ask me first)
5. **Repo hygiene:**
   - patch 0018 for the 8 unpatched `vendor/.../examples/*.rs`, so `--rebuild` is safe
     (0018 is reserved for it)
   - the weak assertions in `docs/evidence/0002`, `0004`, `0005` and `0006`
     (`bash tests/evidence-harness.sh --lint …` lists them)
   - a generator for `/tmp/p3model`, which `shape-flex` needs
   - run specs that clear or validate their `<stem>.compiled` cache in `setup`
   - a fuzzer patch so `gelu` uses a valid mode
   - `milc run` reportedly doesn't feed inputs named `x0`..`x9`. Reproduce it before fixing;
     where in the code it breaks is not confirmed.
   - `scripts/spec_to_json.py --check` with no file argument raises an `IndexError`; it
     should print usage
   - the merged remote branches can be deleted, but ask first
6. **Open decode items and "why 55":**
   - multi-input add-chain trailers
   - the `[1000,4096]` header anomaly
   - why dim1 = 16 and dim2/dim3 = 256 are special
   - a lead for "why 55": the paper's firmware BAR-register sections (§29–§30, to be
     checked when you read it)
7. **M4 silicon.** All h16g data is cross-compiled. The only M4 is host B
   (M4 Pro, macOS 27.0), which has no Rust toolchain, so ship a prebuilt milc. A run
   there confounds SoC and OS.
8. **L-SCHED / L-RUN.** These are claimed by dave; coordinate first. See HANDOFF §5,
   items 6 and 8.

## Decisions waiting on me — ask, don't act
- **Resuming PC.**
- **Any hardware run beyond Step 0 and "light" probes** (see "Safety").
- **Merging a PR, or marking one ready.** Pushing a branch and opening a **draft** PR is
  fine for work I've asked for. Never push `lane/probe-port-caps-scope` before I say
  resume.
- **Git history:** older commits still hold the redacted host details, and the repo is
  public. Never rewrite history or force-push without my explicit go-ahead.
- **Outreach:** don't contact anyone outside this repo, including paper authors; I handle
  that. If I ask you to prepare data for sharing:
  - lead with the spec-asserted laws (`spec_datapoints.json`)
  - mark anything runner-only or unverified
  - state the chip and OS build
- **The `ori` page `ane-descriptor-economy` stays as it is.** Don't re-save it; the repo
  copy `docs/spec/ane-port-limits-h17.html` is canonical.

## How to work
- **Evidence, not documentation.** Every new law needs a spec line that would fail if the
  law were wrong.
  - Judge by `want_rc`; anchor counts with `$`.
  - Regenerate `spec_datapoints.json` with `scripts/spec_to_json.py` whenever the spec
    changes.
- **Label every claim** established / strong / tentative, and mark *(runner-only)* where
  no spec line asserts it. Say which OS build it was measured on.
- **Vendored code:** patches only (`patches/`); never hand-edit `vendor/`. Don't run
  `apply-patches.sh --rebuild` until patch 0018 lands.
- **Public repo:** scrub private paths, hosts, IPs, logins and emails from anything you
  commit. Call the second Mac "host B (M4 Pro, macOS 27.0)".
- **Commits:** `lane/<name>: <what>`. The body says what failed before, how it was verified,
  and the work-item ID.
- **Push as you go** to your own branch, and keep your PR's description current.
- **A task is done when:**
  - `./scripts/evidence-check.sh --all --require-all` passes
  - the harness passes
  - `spec_to_json --check` passes
  - CI is green
  - the writeup, the handoff and this prompt say what changed

  PC's draft PR is the exception: it is hardware-free until I approve the §10a–e run.
