# Evidence harness spec format

Each evidence item declares its reproducible assertions in a machine-readable
spec: `docs/evidence/<NNNN>-<name>.spec`. The harness
(`scripts/evidence-check.sh`) runs the spec and verifies the documented facts
still hold. This is the L-TEST answer to "evidence can never drift from the
code": the spec is re-executed, not the prose re-pasted.

## Why not regenerate the prose

Evidence files contain volatile facts by design — latencies, absolute paths,
host names, timestamps. Byte-regenerating the prose can never produce an empty
diff, so "regenerate and diff" is the wrong criterion. What can be checked is
that **the commands the evidence is built on still behave the way the evidence
claims**: exit codes, and the stable substrings that carry the actual claim
("ok":false, a named stage, an error code, a passing test count). The spec
asserts exactly those.

## Format

A `.spec` file is line-oriented. Blank lines and `#` comments are ignored.

```
# comment
require_cmd  cargo                     # harness fails early if this tool is absent
require_cmd  xcrun
require_file vendor/mil_spec/Cargo.toml # a prerequisite path must exist

run  <shell command>                   # executed with bash, cwd = repo root
want_rc      1                         # assert exit code of the LAST run
want_out     "ok":false                # assert substring present in stdout+stderr
want_out_re  "stage":"[a-z]+"          # assert a regex matches output
want_absent  panic                     # assert substring absent
```

Multiple `run` lines execute in order; `want_*` apply to the most recent `run`.
Assertions accumulate; all must hold for the item to pass.

## Commands run with the repo root as cwd

So a spec references `vendor/mil_spec/...`, `scripts/...`, `tests/...` with the
same relative paths the evidence prose uses. Volatile facts (a latency number,
a `/tmp` path, a host) are asserted by *pattern*, not by exact string — the
spec asserts the claim, not the noise.

## Example

```
# 0006: failing milc invocations under --json yield parseable JSON
require_cmd  cargo
run  vendor/mil_spec/target/release/milc run --json /nonexistent.mlpackage --units ane 2>/dev/null
want_rc   1
want_out  "ok":false
want_out_re "error":\{[^}]*"stage"
```

## Exit behaviour

`scripts/evidence-check.sh <spec...>` runs each spec and prints a per-item
verdict plus a summary. Exit 0 iff every assertion in every spec holds.
`scripts/evidence-check.sh --all` runs every `*.spec` in `docs/evidence/`.
Specs that need hardware skip cleanly (see TEST-2).
