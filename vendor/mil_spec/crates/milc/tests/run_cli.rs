//! `milc run` end-to-end for TOOL-2: a compiled `.mlmodelc` must run directly,
//! not only a `.mlpackage`. Regression for the dispatch fix (patch 0005).
//!
//! Builds a tiny stateful model, compiles it, then invokes the `milc` binary
//! on the resulting `.mlmodelc` and asserts success. Skips (with a note) when
//! `coremlc` is unavailable, since the compiled artifact is the thing under test.

use std::path::PathBuf;
use std::process::Command;

fn milc_bin() -> PathBuf {
    // The test binary lives in target/<profile>/deps; the milc bin is beside it.
    let exe = std::env::current_exe().expect("current_exe");
    let deps = exe.parent().expect("deps");
    let target = deps.parent().expect("target");
    target.join(format!("milc{}", std::env::consts::EXE_SUFFIX))
}

fn coremlc() -> bool {
    mil_compile::coremlc_path().is_some()
}

fn write_stateful_pkg(dir: &std::path::Path) -> std::path::PathBuf {
    use mil_spec::ir::compile;
    use mil_spec::{encode_model, write_mlpackage, ModelMeta};

    let src = r#"
        state kv: fp16[1,8,64,64]
        input step: fp16[1,8,64,64]
        cur = read_state(kv)
        merged = add(cur, step)
        write_state(kv, merged)
        output merged
    "#;
    let p = compile(src).expect("ir compiles");
    let spec = encode_model(
        &p.inputs,
        &p.outputs,
        &p.states,
        &p.block,
        &p.fn_inputs,
        &ModelMeta::new(10, "CoreML9"),
    );
    let pkg = dir.join("t2.mlpackage");
    write_mlpackage(&pkg, &spec, None).expect("write package");
    pkg
}

#[test]
#[cfg(target_os = "macos")]
fn run_compiled_mlmodelc_directly() {
    if !coremlc() {
        eprintln!("coremlc unavailable — skipping run_compiled_mlmodelc_directly");
        return;
    }
    let dir = std::env::temp_dir().join(format!("milc_t2_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let pkg = write_stateful_pkg(&dir);

    // Compile the package into a standalone .mlmodelc.
    let cm = mil_compile::compile(&pkg, &dir.join("compiled")).expect("coremlc compiles");
    let mlmodelc = cm.path;
    assert!(mlmodelc.join("model.mil").exists(), "compiled has model.mil");

    // The acceptance criterion: milc run on the compiled artifact directly.
    let out = Command::new(milc_bin())
        .arg("run")
        .arg(&mlmodelc)
        .args(["--units", "ane", "--steps", "2"])
        .output()
        .expect("spawn milc");
    let stderr = String::from_utf8_lossy(&out.stderr);
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        out.status.success(),
        "milc run <mlmodelc> failed\nstdout:{stdout}\nstderr:{stderr}"
    );
    assert!(
        stdout.contains("steps on cpu+ane"),
        "expected a run summary, got:\n{stdout}"
    );

    let _ = std::fs::remove_dir_all(&dir);
}
