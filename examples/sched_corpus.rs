//! L-SCHED SCHED-1: calibration corpus generator.
//!
//! Builds a spread of `.mlpackage` files from IR source so `milc plan --vs-lint`
//! can be run against each one. The point is to characterise *which op classes*
//! `mil_lint` mis-predicts, and in which direction, before writing a cost model
//! — a model calibrated on a disagreement nobody has diagnosed is unfalsifiable.
//!
//! Each package is deliberately small and structurally simple, so a
//! disagreement can be attributed to a specific op rather than to graph shape.
//! The stateful ones exist because RUN-2 made that path testable.
//!
//! Run: cargo run --release --example sched_corpus --manifest-path examples/Cargo.toml

use mil_spec::ir::compile;
use mil_spec::{encode_model, write_mlpackage, ModelMeta};
use std::path::Path;

/// (name, IR source). Kept in one table so the corpus is auditable at a glance.
const CORPUS: &[(&str, &str)] = &[
    // Pure elementwise fp16 — the easy positive case.
    (
        "elemwise",
        "input x: fp16[1,64,1,1]\ny = mul(x, x)\noutput y",
    ),
    // A graph large enough that CoreML should prefer the ANE for placement
    // reasons rather than keep it on CPU by size. Included precisely so a
    // systematic "everything lands on cpu" reading can be told apart from a
    // "tiny graphs are never planned onto the ANE" effect.
    (
        "big_elemwise",
        "input a: fp16[1,4096,1,1]\n\
         b = mul(a, a)\n\
         c = add(b, b)\n\
         d = mul(c, c)\n\
         e = add(d, d)\n\
         output e",
    ),
    // Elementwise with a matmul: a compute-heavy fp16 chain.
    (
        "matmul_chain",
        "input x: fp16[1,64,1,1]\n\
         w = const_blob(\"@model_path/weights/w.bin\", 0, fp16, [64,32])\n\
         xf = reshape(x, [1,64])\n\
         wf = reshape(w, [64,32])\n\
         y = matmul(xf, wf)\n\
         z = mul(y, y)\n\
         output z",
    ),
    // conv1x1 — an op class where fp32 vs fp16 flips the verdict.
    (
        "conv1x1",
        "input x: fp16[1,8,1,1]\n\
         w = const_blob(\"@model_path/weights/w.bin\", 0, fp16, [16,8,1,1])\n\
         y = conv1x1(x, w)\n\
         output y",
    ),
    // rms_norm — a reduction. `MLComputePlan` places reductions differently
    // in different builds, so this is the class worth watching.
    (
        "rmsnorm",
        "input x: fp16[1,64,1,1]\n\
         g = const_blob(\"@model_path/weights/g.bin\", 0, fp16, [64,1,1])\n\
         y = rms_norm(x, g, 64, 1e-5)\n\
         output y",
    ),
    // softmax — the other reduction class PROBE-1 flagged as a family.
    (
        "softmax",
        "input x: fp16[1,8,64]\n\
         y = softmax(x, 2)\n\
         output y",
    ),
    // Stateful — RUN-2's path. Expects read_state/write_state.
    (
        "stateful",
        "state kv: fp16[1,8,64,64]\n\
         input step: fp16[1,8,64,64]\n\
         cur = read_state(kv)\n\
         merged = add(cur, step)\n\
         write_state(kv, merged)\n\
         output merged",
    ),
    // int32 const only — lint rules exempt `const` and `cast` from the integer
    // rule, so a bare int32 const is *not* a `Unit::Cpu` prediction. Included to
    // pin down what the integer rule actually fires on, rather than assuming.
    (
        "int32_const",
        "input x: fp16[1,4,1,1]\n\
         s = const_i32([1,2,3])\n\
         output x",
    ),
    // cast into fp32 then back — the dtype-flip class. Note the IR's elementwise
    // gate is fp16-only, so the fp32 tensor is produced by `cast` and consumed
    // by `cast`, never by `mul`: this is the honest way to express a dtype flip
    // in this IR, and it keeps the mul gate satisfied.
    (
        "cast_chain",
        "input x: fp16[1,4,1,1]\n\
         f = cast(x, to=fp32)\n\
         b = cast(f, to=fp16)\n\
         output b",
    ),
];

fn build(name: &str, src: &str, dir: &Path) -> Result<(), String> {
    let p = compile(src).map_err(|e| format!("{name}: IR error: {e}"))?;
    let spec = encode_model(
        &p.inputs,
        &p.outputs,
        &p.states,
        &p.block,
        &p.fn_inputs,
        &ModelMeta::new(10, "CoreML9"),
    );
    let out = dir.join(format!("{name}.mlpackage"));
    write_mlpackage(&out, &spec, None).map_err(|e| format!("{name}: write: {e}"))?;
    println!("{name:16} {}", out.display());
    Ok(())
}

fn main() {
    let dir = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "/tmp/sched_corpus".into());
    let _ = std::fs::remove_dir_all(&dir);
    let dir = Path::new(&dir);
    std::fs::create_dir_all(dir).expect("mkdir");

    let mut fail = 0;
    for (name, src) in CORPUS {
        if let Err(e) = build(name, src, dir) {
            eprintln!("FAIL {e}");
            fail += 1;
        }
    }
    if fail > 0 {
        eprintln!("{fail} of {} corpus entries failed to build", CORPUS.len());
        std::process::exit(1);
    }
    println!("--- corpus: {} packages in {}", CORPUS.len(), dir.display());
}
