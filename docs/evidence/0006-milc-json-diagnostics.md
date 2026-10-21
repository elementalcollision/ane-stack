# Evidence — patch 0006 / TOOL-3: machine-readable `milc --json` diagnostics

Work items: `TOOL-3`, patch `0006`. Owner: L-TOOL. Needed by: L-TEST.
Host: Apple M5 Max, macOS 26.7.1.

## What was wrong

Every `milc` error printed a stage string to stderr. An agent asserting on a
failure had to grep text — brittle and language-dependent.

## Accept criterion (BUILD_PLAN)

> a failing `milc` invocation under `--json` yields parseable JSON.

## What was built

A top-level `--json` flag (or `MILC_JSON=1`) that makes a supported subcommand
emit its result — success or failure — as a single JSON envelope on **stdout**:

```
{"ok":bool,"command":"...", ...payload...}
{"ok":false,"command":"...","error":{"stage","code","message","path"}}
```

Human `eprintln` output is unchanged and stays on stderr, so `2>/dev/null` yields
clean parseable stdout. The flag is stripped before subcommand parsers run, so
`--json` is accepted anywhere on the command line. `milc plan --json` keeps its
existing op-table success output (already structured); it gains the error envelope.

## Evidence (failing invocations → parseable JSON)

```console
$ milc run --json /nonexistent.mlpackage --units ane 2>/dev/null; echo rc=$?
{"ok":false,"command":"run","error":{"stage":"io","code":null,"message":"No such file or directory (os error 2)","path":".../model.mlmodel"}}
rc=1

$ milc check --json /nonexistent 2>/dev/null; echo rc=$?
{"ok":false,"command":"check","path":"/nonexistent","errors":["cannot read ..."],"warnings":[]}
rc=1

$ milc plan --json /nonexistent.mlpackage 2>/dev/null; echo rc=$?
{"ok":false,"command":"plan","error":{"stage":"compile",...,"path":"/nonexistent.mlpackage"}}
rc=1
```

Success carries real data, not just `ok`:

```console
$ milc run --json /tmp/ir_fixed.compiled/ir_fixed.mlmodelc --units ane --steps 3 2>/dev/null
{"ok":true,"command":"run","path":"...","units":"cpu+ane","steps":3,
 "latencies_ns":[36625,66584,237916],"median_ns":66584,"min_ns":36625,
 "max_ns":237916,"total_ns":341125}
```

`milc plan --json` success (unchanged op-table) still parses:

```console
$ milc plan --json /tmp/...mlmodelc --units ane 2>/dev/null | python3 -m json.tool | head
{ "units": "CpuAndNeuralEngine", "ops": [ { "op": "ios18.read_state", ... } ], ... }
```

`MILC_JSON=1` works without the flag:

```console
$ MILC_JSON=1 milc run /nonexistent.mlpackage --units ane
{"ok":false,"command":"run","error":{...}}
```

## Regression tests

`crates/milc/tests/run_cli.rs` gains 4 assertions (envelopes parse for failing
`check`/`run`/`plan`; `MILC_JSON=1` honoured). All 5 tests in the file pass;
full suite green; `milc verify` 10/10.

## What it does not cover

- Only `check`/`run`/`plan` are JSON-enabled; the other subcommands still print
  text. Extend `emit_diag`/`emit_ok` usage per command as lanes need them.
- The error `code` field is `null` for most paths — it is reserved for named
  codes (e.g. `BAD_UNITS`, `MISSING_ARG`) that only a few paths set so far.
  Uniform codes are a follow-up, not required for the accept criterion.
