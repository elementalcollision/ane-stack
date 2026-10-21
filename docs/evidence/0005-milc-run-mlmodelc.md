# Evidence — patch 0005 / TOOL-2: `milc run <x.mlmodelc>`

Work items: `TOOL-2`, patch `0005`. Owner: L-TOOL.
Host: Apple M5 Max, macOS 26.7.1, coremlc 3600.25.1.

## What was wrong

`milc run <arg>` accepted only a `.mlpackage`. For a precompiled `.mlmodelc` it
read the spec from `Data/com.apple.CoreML/model.mlmodel`, which does not exist in
a compiled artifact — it carries the spec as MIL text in `model.mil`.

## Reproduction (before patch)

```console
$ ls /tmp/ir_fixed.compiled/ir_fixed.mlmodelc/
analytics  coremldata.bin  metadata.json  model.mil        # no model.mlmodel

$ milc run /tmp/ir_fixed.compiled/ir_fixed.mlmodelc --units ane --steps 2
milc run: .../model.mlmodel: No such file or directory (os error 2)   rc=1
```

## Fix

`cmd_run` now branches on the artifact kind:

- `.mlmodelc` (has `model.mil`) → parse the `func main(...)` signature with
  `summary_from_model_mil` to recover `name / shape / dtype / is_state`, then
  `Model::load` and run the artifact as-is, no recompile.
- otherwise → unchanged package path (read protobuf spec, compile if needed).

Dtypes map to the CoreML protobuf codes `dtype_of` already knows (`fp16→16`,
`int32→5`, `int64→8`, else fp32), so `synth_inputs` works unchanged. The parser
tracks `<>`/`[]` nesting so a signature like
`state<tensor<fp16, [1, 8, 64, 64]>> kv, tensor<int32, [1]> pos` splits correctly
on top-level commas.

## Acceptance (after patch)

```console
$ milc run /tmp/ir_fixed.compiled/ir_fixed.mlmodelc --units ane --steps 3
3 steps on cpu+ane: median 56.42µs  min 31.83µs  max 198.71µs  total 286.96µs  rc=0

# package path (regression) still works:
$ milc run /tmp/ir_fixed.mlpackage --units ane --steps 2
2 steps on cpu+ane: median 282.12µs ...  rc=0
```

## Regression test

`crates/milc/tests/run_cli.rs::run_compiled_mlmodelc_directly` builds a stateful
model via `ir`, compiles it through real `coremlc`, then invokes the `milc` binary
on the resulting `.mlmodelc` and asserts `steps on cpu+ane`. Skips with a note when
`coremlc` is absent (hardware-dependent; ENGINEERING.md §3.3). Passes in 0.31s.

Full suite green: `-p mil_spec -p mil_lint -p mil_passes -p mil_verify -p milc`,
plus `milc verify` 10/10.

## What this does not cover

- Output-feature reconstruction — `summary_from_model_mil` fills only
  `inputs`/`states`; `cmd_run` consumes nothing else. If a later item needs outputs
  from a compiled artifact, extend the parser to the `-> (…)` return list.
- Exotic MIL signatures (generic dims, non-tensor params). The parser returns
  `None` on anything it cannot handle and `cmd_run` errors cleanly.
