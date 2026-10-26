# ane-stack — project instructions

Reverse-engineering Apple's Neural Engine resource model (vendored `savageAZfck/mil_spec`).
Start with `NEXT-SESSION-PROMPT.md`, then `HANDOFF-2026-10-22.md` and
`docs/spec/ane-port-limits-h17.md`.

## Model usage (adopted 2026-10-26, after running out of tokens)

1. **Never use Fable models** — not for the main session, subagents, workflows or hooks.
2. **Opus is the orchestrator and the synthesis/analysis model.** Planning, deciding,
   writing ground-truth docs and specs, and final analysis stay with Opus.
3. **Sonnet and Haiku are the subagents**, matched to the task:
   - **Haiku:** mechanical work — file/path/flag checks, inventories, grep-and-tabulate,
     schema or consistency cross-checks, privacy scans.
   - **Sonnet:** judgement and hardware work — probes on the ANE, held-out
     measurement, adversarial review, refuting findings.

How to apply:
- Always pass `model: "sonnet"` or `model: "haiku"` explicitly on every `Agent` call
  and every workflow `agent()` call. Never rely on inheritance, which would run
  subagents on Opus. `.claude/settings.json` also defaults subagents to Sonnet and
  allowlists only `opus`, `sonnet` and `haiku`.
- Spend tokens deliberately:
  - Do it inline when a few tool calls settle it.
  - Use one subagent before a workflow, and a small workflow (≤ 5 agents) before a
    large one.
  - Say up front what a fan-out will cost.

## Working rules (details in HANDOFF-2026-10-22.md §2, §4)

- **Evidence, not documentation.** Every law needs a spec line in
  `docs/spec/ane-port-limits-h17.spec` that could fail.
  - Judge runs by `want_rc`, never by text alone; a failing run also prints `step 0:`.
  - Anchor counts with `$`.
- **Build:** `cd vendor/mil_spec && cargo build --release -p milc`.
  - Pass `--arch h17` to `milc ane validate|compile`, which default to h16g.
- **Verify:** `./scripts/evidence-check.sh --all --require-all`, `bash tests/evidence-harness.sh`,
  and `python3 scripts/spec_to_json.py --check docs/data/ane-h17-2026-10-22/spec_datapoints.json`.
- **Vendored code:** patches only (`patches/`); never hand-edit `vendor/`.
  - Do not run `apply-patches.sh --rebuild` until the 8 unpatched example files are patched in.
- **The repo is public.** No private paths, hosts, IPs, logins or emails in anything you commit.
