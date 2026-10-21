use mil_spec::ir::{compile, IrError};
use mil_spec::{encode_model, write_mlpackage, ModelMeta};

fn compile_ok(src: &str) -> mil_spec::ir::Program {
    compile(src).unwrap_or_else(|e| panic!("should compile: {e}\n---\n{src}"))
}

fn compile_err(src: &str) -> IrError {
    match compile(src) {
        Ok(_) => panic!("should fail:\n{src}"),
        Err(e) => e,
    }
}

#[test]
fn simple_elementwise() {
    let p = compile_ok(
        "input x: fp16[1,4,1,1]\n\
         y = mul(x, x)\n\
         output y",
    );
    assert_eq!(p.inputs.len(), 1);
    assert_eq!(p.outputs.len(), 1);
    assert_eq!(p.types["y"].shape, vec![1, 4, 1, 1]);
}

#[test]
fn scalar_broadcast() {
    let p = compile_ok(
        "input x: fp16[1,4,1,1]\n\
         k = const_f16(0.5)\n\
         y = mul(x, k)\n\
         output y",
    );
    assert_eq!(p.types["y"].shape, vec![1, 4, 1, 1]);
}

#[test]
fn shape_mismatch_rejected() {
    let e = compile_err(
        "input a: fp16[1,4,1,1]\n\
         input b: fp16[1,8,1,1]\n\
         y = add(a, b)\n\
         output y",
    );
    assert!(e.message.contains("shape mismatch"));
}

#[test]
fn undefined_name_rejected() {
    let e = compile_err("input x: fp16[1,4,1,1]\ny = mul(x, z)\noutput y");
    assert!(e.message.contains("undefined value z"));
}

#[test]
fn reshape_preserves_elements() {
    compile_ok(
        "input x: fp16[1,4,1,1]\n\
         y = reshape(x, [4,1,1,1])\n\
         output y",
    );
    let e = compile_err(
        "input x: fp16[1,4,1,1]\n\
         y = reshape(x, [3,1,1,1])\n\
         output y",
    );
    assert!(e.message.contains("preserves elements"));
}

#[test]
fn transpose_permutation_checked() {
    let p = compile_ok(
        "input x: fp16[1,4,1,1]\n\
         y = transpose(x, perm=[0,3,2,1])\n\
         output y",
    );
    assert_eq!(p.types["y"].shape, vec![1, 1, 1, 4]);

    let e = compile_err(
        "input x: fp16[1,4,1,1]\n\
         y = transpose(x, perm=[0,1,1])\n\
         output y",
    );
    assert!(e.message.contains("permutation") || e.message.contains("rank"));
}

#[test]
fn matmul_inner_dims_checked() {
    let p = compile_ok(
        "input x: fp16[1,64]\n\
         w = const_blob(\"@model_path/weights/weight.bin\", 128, fp16, [64,32])\n\
         y = matmul(x, w)\n\
         output y",
    );
    assert_eq!(p.types["y"].shape, vec![1, 32]);

    let e = compile_err(
        "input x: fp16[1,64]\n\
         w = const_blob(\"f\", 0, fp16, [32,32])\n\
         y = matmul(x, w)\n\
         output y",
    );
    assert!(e.message.contains("inner dims"));
}

#[test]
fn conv1x1_channels_checked() {
    let p = compile_ok(
        "input x: fp16[1,4,1,1]\n\
         w = const_blob(\"f\", 0, fp16, [8,4,1,1])\n\
         y = conv1x1(x, w)\n\
         output y",
    );
    assert_eq!(p.types["y"].shape, vec![1, 8, 1, 1]);

    let e = compile_err(
        "input x: fp16[1,4,1,1]\n\
         w = const_blob(\"f\", 0, fp16, [8,9,1,1])\n\
         y = conv1x1(x, w)\n\
         output y",
    );
    assert!(e.message.contains("channel mismatch"));
}

#[test]
fn concat_multi_input() {
    let p = compile_ok(
        "input a: fp16[1,4,1,1]\n\
         input b: fp16[1,4,1,1]\n\
         y = concat([a, b], 1)\n\
         output y",
    );
    assert_eq!(p.types["y"].shape, vec![1, 8, 1, 1]);
}

#[test]
fn stateful_roundtrip() {
    // FORK(ane-stack): the original form concatenated a [1,8,1,64] step onto a
    // [1,8,64,64] state and wrote the [1,8,65,64] result back — a shape the
    // state can never hold. It only "passed" because write_state validated
    // dtype and nothing else; coremlc rejected the encoded program. The IR has
    // no slice_update, so a same-shape whole-state write is the only legal
    // form here. Upstream: 20f097f.
    let p = compile_ok(
        "state kv: fp16[1,8,64,64]\n\
         input step: fp16[1,8,64,64]\n\
         cur = read_state(kv)\n\
         merged = add(cur, step)\n\
         write_state(kv, merged)\n\
         output merged",
    );
    assert_eq!(p.states.len(), 1);
    assert_eq!(p.types["merged"].shape, vec![1, 8, 64, 64]);
    // fn_inputs must include the state as a State value type
    assert_eq!(p.fn_inputs.len(), 2);
}

#[test]
fn write_state_shape_mismatch_rejected() {
    // Regression: a value whose shape differs from the state's declared shape
    // must fail at compile time, not at coremlc.
    let e = compile_err(
        "state kv: fp16[1,8,64,64]\n\
         input step: fp16[1,8,1,64]\n\
         cur = read_state(kv)\n\
         merged = concat([cur, step], 2)\n\
         write_state(kv, merged)\n\
         output merged",
    );
    assert!(
        e.message.contains("write_state shape mismatch"),
        "expected a shape mismatch, got: {}",
        e.message
    );
}

#[test]
fn undeclared_state_rejected() {
    let e = compile_err("v = read_state(missing)\noutput v");
    assert!(e.message.contains("undefined state"));
}

#[test]
fn rms_norm_d_checked() {
    let p = compile_ok(
        "input x: fp16[1,64,1,1]\n\
         g = const_blob(\"f\", 0, fp16, [64,1,1])\n\
         y = rms_norm(x, g, 64, 1e-5)\n\
         output y",
    );
    assert_eq!(p.types["y"].shape, vec![1, 64, 1, 1]);

    let e = compile_err(
        "input x: fp16[1,64,1,1]\n\
         g = const_blob(\"f\", 0, fp16, [64,1,1])\n\
         y = rms_norm(x, g, 32, 1e-5)\n\
         output y",
    );
    assert!(e.message.contains("channel dim"));
}

#[test]
fn no_outputs_rejected() {
    let e = compile_err("input x: fp16[1,4,1,1]\ny = mul(x, x)");
    assert!(e.message.contains("no outputs"));
}

#[test]
fn double_definition_rejected() {
    let e = compile_err(
        "input x: fp16[1,4,1,1]\n\
         input x: fp16[1,8,1,1]\n\
         output x",
    );
    assert!(e.message.contains("already defined"));
}

#[test]
fn compiles_to_valid_package() {
    let p = compile_ok(
        "input x: fp16[1,4,1,1]\n\
         k = const_f16(2.0)\n\
         y = mul(x, k)\n\
         z = reshape(y, [4,1,1,1])\n\
         output z",
    );
    let spec = encode_model(
        &p.inputs,
        &p.outputs,
        &p.states,
        &p.block,
        &p.fn_inputs,
        &ModelMeta::new(8, "CoreML5"),
    );
    let dir = std::env::temp_dir().join(format!("mil_ir_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    write_mlpackage(&dir, &spec, None).unwrap();
    assert!(dir.join("Manifest.json").exists());
    assert!(dir.join("Data/com.apple.CoreML/model.mlmodel").exists());
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn q8_weight_lowers() {
    let p = compile_ok(
        "input x: fp16[1,4,1,1]\n\
         w = const_q8(\"@model_path/weights/weight.bin\", 128, 4096, [4,4,1,1])\n\
         xf = reshape(x, [1,4])\n\
         wf = reshape(w, [4,4])\n\
         y = matmul(xf, wf)\n\
         output y",
    );
    // int8 data + fp16 scale + dequant op = 3 ops for the const_q8 helper
    assert!(p
        .block
        .ops
        .iter()
        .any(|o| o.ty == "constexpr_blockwise_shift_scale"));
}

#[test]
fn slice_update_whole_state_write() {
    // slice_update with begin..end == full dims == whole-state write; update
    // shape must equal state shape exactly.
    let p = compile_ok(
        "state kv: fp16[1,8,64,64]\n\
         input step: fp16[1,8,64,64]\n\
         cur = read_state(kv)\n\
         merged = add(cur, step)\n\
         su = slice_update(kv, begin=[0,0,0,0], end=[1,8,64,64], update=merged)\n\
         write_state(kv, su)\n\
         output su",
    );
    assert_eq!(p.types["su"].shape, vec![1, 8, 64, 64]);
    assert_eq!(
        p.block
            .ops
            .iter()
            .filter(|o| o.ty == "slice_update")
            .count(),
        1
    );
}

#[test]
fn slice_update_region_write() {
    // Incremental write into a stripe: write row 3 of a 4-row state.
    let p = compile_ok(
        "state kv: fp16[4,8,64,64]\n\
         input row: fp16[1,8,64,64]\n\
         su = slice_update(kv, begin=[3,0,0,0], end=[4,8,64,64], update=row)\n\
         write_state(kv, su)\n\
         output su",
    );
    assert_eq!(p.types["su"].shape, vec![4, 8, 64, 64]);
    assert_eq!(
        p.block
            .ops
            .iter()
            .filter(|o| o.ty == "slice_update")
            .count(),
        1
    );
}

#[test]
fn slice_update_begin_end_must_match_rank() {
    let e = compile_err(
        "state kv: fp16[4,8,64,64]\n\
         input row: fp16[1,8,64,64]\n\
         su = slice_update(kv, begin=[0,0,0], end=[4,8,64], update=row)\n\
         output su",
    );
    assert!(e.message.contains("begin/end must match rank"));
}

#[test]
fn slice_update_update_shape_must_match_region() {
    // Writing a 2-row update into a 1-row region must fail.
    let e = compile_err(
        "state kv: fp16[4,8,64,64]\n\
         input rows: fp16[2,8,64,64]\n\
         su = slice_update(kv, begin=[0,0,0,0], end=[1,8,64,64], update=rows)\n\
         output su",
    );
    assert!(
        e.message.contains("update shape") || e.message.contains("doesn't match"),
        "expected update-shape mismatch, got: {}",
        e.message
    );
}

#[test]
fn slice_update_range_invalid_is_rejected() {
    let e = compile_err(
        "state kv: fp16[4,8,64,64]\n\
         input row: fp16[1,8,64,64]\n\
         su = slice_update(kv, begin=[3,0,0,0], end=[4,8,64,64], update=row)\n\
         su2 = slice_update(kv, begin=[5,0,0,0], end=[6,8,64,64], update=row)\n\
         output su2",
    );
    assert!(e.message.contains("invalid for dim"));
}

// IR-3 — state contract: one read_state per state.
#[test]
fn state_double_read_rejected() {
    let e = compile_err(
        "state kv: fp16[4,8,64,64]\n\
         input row: fp16[1,8,64,64]\n\
         a = read_state(kv)\n\
         b = read_state(kv)\n\
         tmp = add(a, b)\n\
         su = slice_update(kv, begin=[0,0,0,0], end=[4,8,64,64], update=tmp)\n\
         write_state(kv, su)\n\
         output su",
    );
    assert!(
        e.message.contains("at most one read_state per state"),
        "expected double-read rejection, got: {}",
        e.message
    );
}

// IR-3 — state contract: write_state after each slice_update.
#[test]
fn state_slice_update_without_write_rejected() {
    let e = compile_err(
        "state kv: fp16[4,8,64,64]\n\
         input row: fp16[4,8,64,64]\n\
         cur = read_state(kv)\n\
         tmp = add(cur, row)\n\
         su = slice_update(kv, begin=[0,0,0,0], end=[4,8,64,64], update=tmp)\n\
         output su",
    );
    assert!(
        e.message.contains("slice_update(s) but 0 write_state(s)"),
        "expected missing-write rejection, got: {}",
        e.message
    );
}

// IR-3 — state contract: write_state count must match slice_update count.
#[test]
fn state_write_slice_count_mismatch_rejected() {
    let e = compile_err(
        "state kv: fp16[4,8,64,64]\n\
         input row: fp16[4,8,64,64]\n\
         cur = read_state(kv)\n\
         tmp = add(cur, row)\n\
         su = slice_update(kv, begin=[0,0,0,0], end=[4,8,64,64], update=tmp)\n\
         write_state(kv, su)\n\
         write_state(kv, su)\n\
         output su",
    );
    assert!(
        e.message.contains("1 slice_update(s) but 2 write_state(s)"),
        "expected count-mismatch rejection, got: {}",
        e.message
    );
}
