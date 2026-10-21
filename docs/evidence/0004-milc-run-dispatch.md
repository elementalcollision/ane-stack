# Evidence — patch 0004: `milc run` shard dispatch

Work item: `TOOL-1` (patch), unblocks `TOOL-2`.
Host: Apple M5 Max (Mac17,7), macOS 26.7.1.

## What was wrong

`cmd_run` decided whether its argument was a shard bundle with:

```rust
if path.join("manifest.json").exists() {
    return run_sharded(&path, units, steps);
}
```

Every CoreML `.mlpackage` contains **`Manifest.json`** (capital M). macOS APFS is
case-insensitive by default, so the test matched ordinary packages and sent them
to the shard loader.

## Reproduction (before patch)

```console
$ milc run /tmp/ir_fixed.mlpackage --units ane --steps 3
milc run: infer manifest: kind is not "milshards"
```

Proving the case-insensitive match:

```console
$ ls /tmp/ir_fixed.mlpackage/
Data        Manifest.json

$ python3 -c "import os; print(os.path.exists('/tmp/ir_fixed.mlpackage/manifest.json'))"
True
```

No ordinary `.mlpackage` could ever be run. This is not a stateful-model issue —
it affects every package.

## Fix

Require the absence of `Data/com.apple.CoreML/model.mlmodel`, which no shard
bundle has:

```rust
if path.join("manifest.json").exists()
    && !path.join("Data/com.apple.CoreML/model.mlmodel").exists()
{
    return run_sharded(&path, units, steps);
}
```

## After

```console
$ milc run /tmp/ir_fixed.mlpackage --units ane --steps 3
compiled /tmp/ir_fixed.compiled/ir_fixed.mlmodelc via coreml.framework
3 steps on cpu+ane: median 99.42µs  min 62.92µs  max 280.29µs  total 442.63µs
```

## Confidence

High for the package path. **Not covered by a test yet** — `TOOL-2` should add one
(a CLI integration test asserting `milc run <pkg>` dispatches to the package path,
not `run_sharded`). Recorded here rather than silently claimed as done.

## Note on `milc run <x.mlmodelc>`

Separately broken, and *not* fixed by this patch: given a compiled `.mlmodelc`,
`cmd_run` looks for `Data/com.apple.CoreML/model.mlmodel` inside it and fails
(`No such file or directory`). A `.mlmodelc` contains `model.mil`, not
`model.mlmodel`. Tracked as `TOOL-2`.
