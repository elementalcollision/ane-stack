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

fn milc(args: &[&str]) -> (i32, String, String) {
    let out = Command::new(milc_bin())
        .args(args)
        .output()
        .expect("spawn milc");
    (
        out.status.code().unwrap_or(-1),
        String::from_utf8_lossy(&out.stdout).into_owned(),
        String::from_utf8_lossy(&out.stderr).into_owned(),
    )
}

/// Tiny hand-rolled JSON field extractor — asserts a `"key":` appears and
/// returns the raw value up to the delimiter. Good enough for asserting on
/// envelopes without pulling in serde_json.
fn json_has(out: &str, key: &str) -> bool {
    out.contains(&format!("\"{}\":", key))
}

fn coremlc() -> bool {
    mil_compile::coremlc_path().is_some()
}

// ---------- TOOL-3: structured --json diagnostics ----------

#[test]
#[cfg(target_os = "macos")]
fn failing_run_emits_parseable_json_envelope() {
    let (rc, stdout, _stderr) = milc(&["run", "--json", "/nonexistent.mlpackage", "--units", "ane"]);
    assert_ne!(rc, 0, "a missing package must fail");
    // stdout must be a single JSON envelope: ok=false, an error object with a
    // stage, and no trailing junk after the closing brace.
    let t = stdout.trim();
    assert!(t.starts_with('{') && t.ends_with('}'), "not a JSON object: {t}");
    assert!(json_has(t, "ok"), "no ok field: {t}");
    assert!(t.contains("\"ok\":false"), "ok should be false: {t}");
    assert!(json_has(t, "error"), "no error field: {t}");
    assert!(json_has(t, "stage"), "error must carry a stage: {t}");
    assert!(json_has(t, "path"), "error must carry a path: {t}");
}

#[test]
#[cfg(target_os = "macos")]
fn failing_check_emits_parseable_json_envelope() {
    let (rc, stdout, _stderr) = milc(&["check", "--json", "/nonexistent"]);
    assert_ne!(rc, 0);
    let t = stdout.trim();
    assert!(t.contains("\"ok\":false"), "check should report ok=false: {t}");
    assert!(json_has(t, "errors"), "check must report an errors array: {t}");
    assert!(json_has(t, "path"), "check must report the path: {t}");
}

#[test]
#[cfg(target_os = "macos")]
fn failing_plan_emits_parseable_json_envelope() {
    let (rc, stdout, _stderr) = milc(&["plan", "--json", "/nonexistent.mlpackage"]);
    assert_ne!(rc, 0);
    let t = stdout.trim();
    assert!(t.contains("\"ok\":false"), "plan should report ok=false: {t}");
    assert!(json_has(t, "error"), "plan must carry an error: {t}");
    assert!(json_has(t, "stage"), "plan error must carry a stage: {t}");
}

#[test]
#[cfg(target_os = "macos")]
fn milc_json_env_var_is_honoured() {
    let out = Command::new(milc_bin())
        .args(["run", "/nonexistent.mlpackage", "--units", "ane"])
        .env("MILC_JSON", "1")
        .output()
        .expect("spawn milc");
    let t = String::from_utf8_lossy(&out.stdout);
    assert!(
        t.trim().starts_with('{') && t.contains("\"ok\":false"),
        "MILC_JSON=1 should produce the envelope without the flag: {t}"
    );
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
    if !mil_compile::hw_gate("coremlc", coremlc()) {
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

// ---------- SCHED-1 patch 0016: degenerate-plan warning ----------

/// `milc plan --vs-lint` must warn when the compute plan placed nothing off the
/// CPU, because on macOS 26.x `MLComputePlan` does exactly that — including for
/// CoreML-authored Apple models — which makes the agreement rate measure the
/// plan rather than `mil_lint`. Pins the warning's presence: a silent low rate
/// is what briefly made L-SCHED read a lint bug into a broken oracle.
#[test]
#[cfg(target_os = "macos")]
fn vs_lint_warns_when_the_plan_is_cpu_only() {
    if !mil_compile::hw_gate("coremlc (needed to compile the fixture)", coremlc()) {
        return;
    }
    let dir = std::env::temp_dir().join(format!("milc_vslint_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();

    let src = "state kv: fp16[1,8,64,64]\n\
               input step: fp16[1,8,64,64]\n\
               cur = read_state(kv)\n\
               merged = add(cur, step)\n\
               write_state(kv, merged)\n\
               output merged\n";
    let p = mil_spec::ir::compile(src).expect("fixture compiles");
    let spec = mil_spec::encode_model(
        &p.inputs,
        &p.outputs,
        &p.states,
        &p.block,
        &p.fn_inputs,
        &mil_spec::ModelMeta::new(10, "CoreML9"),
    );
    let pkg = dir.join("pkg.mlpackage");
    mil_spec::write_mlpackage(&pkg, &spec, None).expect("package written");

    let (_rc, _stdout, stderr) = milc(&[
        "plan",
        "--vs-lint",
        pkg.to_str().unwrap(),
        "--units",
        "ane",
    ]);
    assert!(
        stderr.contains("WARNING: the compute plan placed every op on the CPU"),
        "expected the degenerate-plan warning, got stderr:\n{stderr}"
    );
    assert!(
        stderr.contains("SCHED-1-positive-control.md"),
        "warning must point at the evidence, got stderr:\n{stderr}"
    );

    let _ = std::fs::remove_dir_all(&dir);
}

/// The warning must be *conditional*. On a host where `MLComputePlan` genuinely
/// places ops off the CPU, an all-cpu warning would be a false alarm — so this
/// asserts the warning is tied to the plan's actual composition rather than
/// being unconditional. Where the plan is cpu-only it fires; the negative case
/// needs a host that plans onto the ANE, which is asserted by absence of the
/// warning only when such a plan exists, so it is deliberately not asserted
/// here. See docs/evidence/SCHED-1-positive-control.md for what a real
/// non-cpu plan would look like.
#[test]
#[cfg(target_os = "macos")]
fn vs_lint_warning_is_not_unconditional() {
    // A package that fails to compile must not produce the warning — the
    // warning is about a degenerate plan, not about failure.
    let (_rc, _stdout, stderr) = milc(&["plan", "--vs-lint", "/nonexistent.mlpackage"]);
    assert!(
        !stderr.contains("WARNING: the compute plan placed every op on the CPU"),
        "a compile failure must not be reported as a degenerate plan:\n{stderr}"
    );
}
