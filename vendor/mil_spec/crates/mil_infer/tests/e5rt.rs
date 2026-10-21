//! e5rt execution — real compute on the ANE, no CoreML.

use std::path::PathBuf;

const ADD_MIL: &str = r#"program(1.3)
{
    func main<ios18>(tensor<fp16, [1, 4]> x, tensor<fp16, [1, 4]> y) {
        tensor<fp16, [1, 4]> z = add(x = x, y = y)[name = string("z")];
    } -> (z);
}
"#;

fn fixture() -> PathBuf {
    let dir = std::env::temp_dir().join("e5rt_test");
    std::fs::create_dir_all(&dir).unwrap();
    let p = dir.join("add.mil");
    std::fs::write(&p, ADD_MIL).unwrap();
    p
}

fn f16(v: f32) -> u16 {
    half::f16::from_f32(v).to_bits()
}

#[test]
fn ane_executes_add() {
    let mil = fixture();
    let prog = match mil_infer::e5rt::Program::compile(
        &mil,
        mil_infer::e5rt::DeviceMask::Ane,
        &[("x", 4), ("y", 4)],
        &[("z", 4)],
        &[],
    ) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("e5rt unavailable ({e}) — skipping");
            return;
        }
    };
    eprintln!("functions: {:?}", prog.functions);
    prog.set_input_f16("x", &[f16(1.0), f16(2.0), f16(3.0), f16(4.0)])
        .unwrap();
    prog.set_input_f16("y", &[f16(10.0), f16(20.0), f16(30.0), f16(40.0)])
        .unwrap();
    prog.execute().unwrap();
    let out = prog.output_f16("z").unwrap();
    let got: Vec<f32> = out
        .iter()
        .map(|b| half::f16::from_bits(*b).to_f32())
        .collect();
    assert_eq!(got, vec![11.0, 22.0, 33.0, 44.0], "ANE computed {got:?}");
}

// ---- RUN-2: explicit state lifecycle on e5rt -----------------------------
//
// Grammar below is *measured*, not assumed. `examples/probe_run2_state.rs`
// establishes which stateful shapes `aned` accepts; two constraints from
// ANE_FRONTEND_SPEC.md (confirmed by that probe) dictate the fixture:
//
//   1. `write_state(data=..)` must receive the **terminal `slice_update`**
//      output. Writing a bare `read_state` result is rejected outright
//      (probe case 1), and writing the read result while an su exists is also
//      rejected (case 5).
//   2. `slice_update` on a state needs the FULL arg list — begin, begin_mask,
//      end, end_mask, squeeze_mask, stride, update, x (minimal form is
//      accepted on plain tensors but not on state).
//
// Readback works by returning the pre-write `read_state` value (probe case 3):
// that tensor reflects the state as it stood when the call began, i.e. what
// the previous call's `write_state` produced. That is the honest readback
// path for a state that is only writable through a slice, and it is what
// makes "did the state persist?" answerable without trusting the host buffer.

const TWO_LAYER_MIL: &str = r#"program(1.3)
{
    func main<ios18>(state<tensor<fp16, [4, 4]>> k0, state<tensor<fp16, [4, 4]>> k1, tensor<fp16, [1, 4]> wvec) {
        tensor<fp16, [4, 4]> m0 = read_state(input = k0)[name = string("m0")];
        tensor<fp16, [4, 4]> m1 = read_state(input = k1)[name = string("m1")];
        tensor<int32, [2]> beg = const()[val = tensor<int32, [2]>([0, 0])];
        tensor<int32, [2]> end = const()[val = tensor<int32, [2]>([1, 4])];
        tensor<int32, [2]> stride = const()[val = tensor<int32, [2]>([1, 1])];
        tensor<bool, [2]> bm = const()[val = tensor<bool, [2]>([false, false])];
        tensor<bool, [2]> em = const()[val = tensor<bool, [2]>([false, false])];
        tensor<bool, [2]> sm = const()[val = tensor<bool, [2]>([false, false])];
        tensor<fp16, [4, 4]> u0 = slice_update(x = m0, update = wvec, begin = beg, end = end, stride = stride, begin_mask = bm, end_mask = em, squeeze_mask = sm)[];
        tensor<fp16, [4, 4]> u1 = slice_update(x = m1, update = wvec, begin = beg, end = end, stride = stride, begin_mask = bm, end_mask = em, squeeze_mask = sm)[];
        write_state(data = u0, input = k0)[name = string("w0")];
        write_state(data = u1, input = k1)[name = string("w1")];
    } -> (m0, m1);
}
"#;

const ROWS: usize = 4;
const COLS: usize = 4;

/// Compile the two-layer fixture into a cache directory private to `tag`.
///
/// Every test gets its own cache dir and its own `.mil` path. Sharing one
/// would make the suite flaky, and not subtly: `CompileCfg::default()` sets
/// `force_recompile`, so concurrent `aned` runs writing the same e5 bundle
/// cache race each other and surface as bogus `op_create`/`e5_compiler_compile`
/// failures. Measured, not theorised — with a shared cache dir the suite
/// failed 5 of 9 under cargo's default parallelism.
fn compile_two_layer(tag: &str) -> Option<mil_infer::e5rt::Program> {
    let dir = std::env::temp_dir()
        .join("e5rt_state_test")
        .join(format!("{tag}_{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let mil = dir.join("two_layer.mil");
    std::fs::write(&mil, TWO_LAYER_MIL).unwrap();

    let cc = mil_infer::e5rt::CompileCfg {
        cache_dir: dir.join("cache"),
        force_recompile: true,
        profiling: false,
    };
    match mil_infer::e5rt::Program::compile_cfg(
        &mil,
        mil_infer::e5rt::DeviceMask::Ane,
        &[("wvec", COLS as u64)],
        &[("m0", (ROWS * COLS) as u64), ("m1", (ROWS * COLS) as u64)],
        &[("k0", (ROWS * COLS) as u64), ("k1", (ROWS * COLS) as u64)],
        &cc,
    ) {
        Ok(p) => Some(p),
        Err(e) => {
            mil_compile::hw_gate(&format!("e5rt two-layer stateful program ({e})"), false);
            None
        }
    }
}

fn bits(v: &[u16]) -> Vec<f32> {
    v.iter().map(|b| half::f16::from_bits(*b).to_f32()).collect()
}

/// Row 0 of a [4,4] state as re-ordered by the model, the rest zeros.
fn row0(v: &[u16]) -> Vec<f32> {
    bits(&v[..COLS])
}

fn zeros_after_row0(v: &[u16]) -> bool {
    v[COLS..].iter().all(|b| *b == 0u16)
}

#[test]
fn stateful_program_binds_both_layers_as_inout() {
    let Some(prog) = compile_two_layer("binds") else {
        return;
    };
    // Both kv layers must surface as state (inout) ports, not plain inputs.
    assert_eq!(
        prog.state_names(),
        vec!["k0", "k1"],
        "2-layer stateful program must expose one state port per layer"
    );
    assert_eq!(prog.state_len("k0"), Some((ROWS * COLS) as u64));
    assert_eq!(prog.state_len("k1"), Some((ROWS * COLS) as u64));
}

#[test]
fn state_persists_across_calls_and_readback_sees_previous_write() {
    let Some(prog) = compile_two_layer("persist") else {
        return;
    };
    let p = prog.reset_states().unwrap();
    assert_eq!(p, 2, "reset zeroes both layers");

    // Call 1 on a zeroed state: readback must be all zeros.
    prog.set_input_f16("wvec", &[f16(1.0), f16(2.0), f16(3.0), f16(4.0)])
        .unwrap();
    prog.execute().unwrap();
    assert_eq!(
        row0(&prog.output_f16("m0").unwrap()),
        vec![0.0; COLS],
        "call 1 readback must be the zeroed state"
    );

    // Call 2 with a new write vector: readback must now show call 1's write.
    prog.set_input_f16("wvec", &[f16(5.0), f16(6.0), f16(7.0), f16(8.0)])
        .unwrap();
    prog.execute().unwrap();
    assert_eq!(
        row0(&prog.output_f16("m0").unwrap()),
        vec![1.0, 2.0, 3.0, 4.0],
        "call 2 readback must reflect call 1's write — state persisted"
    );
    assert_eq!(
        row0(&prog.output_f16("m1").unwrap()),
        vec![1.0, 2.0, 3.0, 4.0],
        "layer 1 persisted independently of layer 0"
    );

    // Call 3: readback shows call 2's write, on both layers.
    prog.execute().unwrap();
    for layer in ["m0", "m1"] {
        assert_eq!(
            row0(&prog.output_f16(layer).unwrap()),
            vec![5.0, 6.0, 7.0, 8.0],
            "{layer} must show the previous call's write"
        );
    }
}

#[test]
fn reset_states_discards_history() {
    let Some(prog) = compile_two_layer("reset") else {
        return;
    };
    prog.set_input_f16("wvec", &[f16(9.0), f16(9.0), f16(9.0), f16(9.0)])
        .unwrap();
    prog.execute().unwrap();
    prog.execute().unwrap();

    // Sanity: the state is carrying the previous write.
    prog.execute().unwrap();
    assert_eq!(
        row0(&prog.output_f16("m0").unwrap()),
        vec![9.0; COLS],
        "precondition: state carries the write"
    );

    // After a reset the very next readback must be zeros again.
    prog.reset_states().unwrap();
    prog.execute().unwrap();
    assert_eq!(
        row0(&prog.output_f16("m0").unwrap()),
        vec![0.0; COLS],
        "reset must discard accumulated state"
    );
    assert_eq!(
        row0(&prog.output_f16("m1").unwrap()),
        vec![0.0; COLS],
        "reset applies to every layer"
    );
}

#[test]
fn save_restore_round_trips_bit_identically() {
    let Some(prog) = compile_two_layer("saverestore") else {
        return;
    };
    prog.reset_states().unwrap();

    // Reach a known state: row0 = [1,2,3,4] on both layers.
    prog.set_input_f16("wvec", &[f16(1.0), f16(2.0), f16(3.0), f16(4.0)])
        .unwrap();
    prog.execute().unwrap();
    prog.execute().unwrap();
    assert_eq!(
        row0(&prog.output_f16("m0").unwrap()),
        vec![1.0, 2.0, 3.0, 4.0],
        "precondition: state holds the first vector"
    );

    let snap = prog.save_states().unwrap();
    assert_eq!(snap.entries.len(), 2, "both layers snapshotted");
    assert_eq!(snap.len(), 2 * ROWS * COLS, "full dense tensors captured");

    // Overwrite with a different vector, twice, so the state has clearly moved.
    prog.set_input_f16("wvec", &[f16(7.0), f16(7.0), f16(7.0), f16(7.0)])
        .unwrap();
    prog.execute().unwrap();
    prog.execute().unwrap();
    assert_eq!(
        row0(&prog.output_f16("m0").unwrap()),
        vec![7.0; COLS],
        "state has moved away from the snapshot"
    );

    // Restore and prove the next readback is the snapshotted state again.
    prog.restore_states(&snap).unwrap();
    prog.execute().unwrap();
    assert_eq!(
        row0(&prog.output_f16("m0").unwrap()),
        vec![1.0, 2.0, 3.0, 4.0],
        "restore returned layer 0 to the snapshot, bit-identical"
    );
    assert_eq!(
        row0(&prog.output_f16("m1").unwrap()),
        vec![1.0, 2.0, 3.0, 4.0],
        "restore returned layer 1 to the snapshot, bit-identical"
    );
}

#[test]
fn snapshot_content_matches_readback() {
    let Some(prog) = compile_two_layer("snapmatch") else {
        return;
    };
    prog.reset_states().unwrap();
    prog.set_input_f16("wvec", &[f16(1.0), f16(2.0), f16(3.0), f16(4.0)])
        .unwrap();
    prog.execute().unwrap();
    prog.execute().unwrap();

    // The model's readback (an output port) and the host-side snapshot (the
    // bound state buffer) are two independent views of the same state. If
    // they agree, `save_states` is trustworthy; if they disagree, the bound
    // buffer is stale and `save_states` would be lying. Assert it, so the
    // weaker assumption cannot silently become the contract.
    let snap = prog.save_states().unwrap();
    let via_output = prog.output_f16("m0").unwrap();
    let via_snapshot = snap.get("k0").unwrap();
    assert_eq!(
        via_output, via_snapshot,
        "host-side snapshot must agree with the engine's own readback"
    );
    assert_eq!(row0(via_snapshot), vec![1.0, 2.0, 3.0, 4.0]);
    assert!(
        zeros_after_row0(via_snapshot),
        "only row 0 was written; the rest of the state stays zero"
    );
}

#[test]
fn restore_rejects_wrong_size_and_leaves_state_untouched() {
    let Some(prog) = compile_two_layer("badsize") else {
        return;
    };
    prog.reset_states().unwrap();
    prog.set_input_f16("wvec", &[f16(3.0), f16(3.0), f16(3.0), f16(3.0)])
        .unwrap();
    prog.execute().unwrap();
    let before = prog.state_f16("k0").unwrap();

    // A snapshot with a truncated layer must be rejected atomically.
    let mut bad = prog.save_states().unwrap();
    bad.entries
        .iter_mut()
        .find(|(n, _)| n == "k0")
        .unwrap()
        .1
        .truncate(2);
    let err = prog.restore_states(&bad).unwrap_err();
    assert!(
        matches!(
            err,
            mil_infer::e5rt::E5Error::StateSizeMismatch { ref state, want, got: 2 }
                if state == "k0" && want == (ROWS * COLS) as u64
        ),
        "expected a size mismatch naming k0, got: {err}"
    );
    assert_eq!(
        prog.state_f16("k0").unwrap(),
        before,
        "a rejected restore must not have written anything"
    );
}

#[test]
fn restore_rejects_snapshot_missing_a_layer() {
    let Some(prog) = compile_two_layer("missing") else {
        return;
    };
    prog.reset_states().unwrap();
    let mut partial = prog.save_states().unwrap();
    partial.entries.retain(|(n, _)| n != "k1");
    let err = prog.restore_states(&partial).unwrap_err();
    assert!(
        matches!(err, mil_infer::e5rt::E5Error::NoSuchState(ref n) if n.contains("k1")),
        "a snapshot missing a layer must be rejected, got: {err}"
    );
}

#[test]
fn state_f16_rejects_a_non_state_port() {
    let Some(prog) = compile_two_layer("nonstate") else {
        return;
    };
    // `wvec` is a plain input, not state — reading it as state must fail
    // loudly rather than reporting a bogus zero-filled buffer.
    let err = prog.state_f16("wvec").unwrap_err();
    assert!(
        matches!(err, mil_infer::e5rt::E5Error::NoSuchState(ref n) if n == "wvec"),
        "expected NoSuchState(wvec), got: {err}"
    );
}
