# Evidence — PROBE-2: decoding the deploy-gate error codes

Work item: `PROBE-2`. Owner: L-PROBE.
Host: Apple M5 Max (Mac17,7, exposes `h17`), macOS 26.7.1 (25G91), cargo 1.95.0.
Every probe ran fork-isolated (a standalone example binary per artifact) because
ObjC exceptions abort the process — see `crates/mil_infer/examples/dp3.rs`.

## Question

ADR-0002 records that self-emitted HWX will not deploy (`0x170004`) and Apple's
own shipped bundles also fail (`0x130004`). Two hypotheses were open:

- **H-arch** — arch mismatch (`ANECCompile` defaults to `h16g`; this M5 is `h17`).
- **H-sign** — an AOT/signing envelope change in how `aned` accepts predeployed programs.

Deciding between them determines whether ADR-0002 is arch-specific (fixable by
targeting the right arch) or a harder gate.

## Method

Each artifact was passed to `EspressoProgram::load_precompiled` (the
`_ANEModel modelAtURL:` + `_ANEClient loadModel:` precompiled path). `dp3.rs`
separates the two stages: a parse failure names `modelAtURL`, a deploy failure
names `loadModel` and extracts the hex code. All failures occurred at
`loadModel` — parsing always succeeded.

## Results

| Artifact | Form | Origin | Stage | Code |
|---|---|---|---|---|
| `sig.macho` (h16g compile) | bare Mach-O | `ANECCompile` here | loadModel | **`0x170004`** |
| `sig.macho` (h17 compile) | bare Mach-O | `ANECCompile --arch h17` here | loadModel | **`0x170004`** |
| `cnn_frame_enhancer_192p.H16.espresso.hwx` | Apple `.espresso.hwx` | **Apple, shipped in `/System/Library`** | loadModel | **`0x130004`** |
| `synthesis_net_GridNet_pyrlite.H18.espresso.hwx` | Apple `.espresso.hwx` | **Apple, shipped** | loadModel | **`0x130004`** |
| `H17C.e5` (aned's own e5rt cache bundle) | FlatBuffer `.e5` | **`aned` itself, this session** | loadModel | **`0x120004`** |
| `sig.mil` via `milc ane run` (e5rt lane) | — | `aned` compiles + binds + `execute_sync` | — | ✅ **runs on the ANE** |

Stability: every code reproduced identically across repeated runs. `ESP_CLIENT`
variants: `shared` → `0x170004`; `private` → `loadModel failed: unknown`;
`new` → `_ANEClient connection nil` (only `shared` is usable).

## What this rules out — arch is NOT the gate (H-arch rejected)

The `--arch h17` compile provably took effect: `cmp` shows the bytes differ and
the artifact embeds `-t h17` (vs `-t h16g`). Yet it fails with the **identical**
code `0x170004` as the h16g build. If arch targeting were the cause, an
h17-targeted artifact would behave differently on an h17 machine. It does not.
Apple's own `H18` bundle (the closest shipped arch) also fails. **Arch mismatch
is ruled out as the cause of the gate.**

## What this rules in — the gate is form-specific, not provenance-specific

Three distinct codes cluster by **artifact form**, not by who produced it:

- `0x170004` — bare Mach-O (ours *and* Apple's compiled Mach-O)
- `0x130004` — Apple `.espresso.hwx` bundles
- `0x120004` — `aned`'s own `.e5` FlatBuffer bundle

`aned`'s **own** bundle (`H17C.e5`, produced by `e5rt` compilation on this very
machine) is *also* refused by `_ANEClient loadModel`. So the gate is not "Apple
trusts its own signature and not ours" — `aned`'s own output does not pass this
path either. **This refutes the naive signing-envelope reading of H-sign.**

The refined conclusion: `_ANEClient loadModel` on this OS build accepts **none**
of the artifact forms we can present — bare Mach-O, Apple espresso bundle, or
`aned`'s e5 bundle. The `0x1X0004` code family varies by form, suggesting
per-format rejection at a validation stage inside `createProgramInstanceForModel`,
not a signature check.

## The positive control — the working lane does NOT use this path

`milc ane run /tmp/sig.mil` executes the *same* program on the ANE
(~242µs, `z=0.73095703` ≈ sigmoid(1.0)). That lane (`e5rt`) binds an op from
`aned`'s signed e5 bundle and drives it with `execute_sync` — it never calls
`_ANEClient loadModel`. **The deploy gate is specific to the `_ANEClient`
precompiled path, which is the path the HWX-emitter deploy story depends on.**

## Statement (the PROBE-2 accept criterion)

**No externally-presented artifact deploys through `_ANEClient loadModel` on this
OS build** — not our Mach-O (h16g or h17), not Apple's compiled Mach-O, not
Apple's shipped espresso bundles, not even `aned`'s own e5 bundle. The gate is
form-specific and sits in the `_ANEClient` precompiled path; it is **not**
arch-targeting and **not** a simple "Apple-signed vs ours" check.

**ADR-0002 is version/OS-specific, not arch-specific, and is not fixable by
emitting different bytes.** The e5rt lane (where `aned` compiles the MIL itself)
is unaffected and remains the working path. The only way the `_ANEClient` path
opens is an OS change (or an entitlement the OS grants to deploy predeployed
programs); neither is in our control.

## Commands (reproduce)

```console
# build the probes
cargo build --release -p mil_infer --example dp3 --example deploy_probe

# compile the same program for two arches and deploy each
milc ane compile /tmp/sig.mil -o /tmp/c16 --arch h16g
milc ane compile /tmp/sig.mil -o /tmp/c17 --arch h17
./target/release/examples/dp3 /tmp/c16/sig.macho   # 0x170004
./target/release/examples/dp3 /tmp/c17/sig.macho   # 0x170004

# Apple's shipped bundles
./target/release/examples/dp3 /System/Library/.../cnn_frame_enhancer_192p.H16.espresso.hwx   # 0x130004

# aned's own e5 bundle (produced by an e5rt compile into /tmp/e5cache)
./target/release/examples/dp3 /tmp/e5cache/.../H17C.bundle/H17C.e5                            # 0x120004

# positive control: the working lane
milc ane run /tmp/sig.mil --steps 1   # runs on the ANE
```
