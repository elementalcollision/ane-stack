// FORK(ane-stack): patched copy of examples/compile_ir.rs demonstrating a
// loadable stateful package. Upstream example is left untouched for reference.
use mil_spec::ir::compile;
use mil_spec::{encode_model, write_mlpackage, ModelMeta};

fn main() {
    let src = r#"
        state kv: fp16[1,8,64,64]
        input step: fp16[1,8,64,64]
        cur = read_state(kv)
        merged = add(cur, step)
        write_state(kv, merged)
        output merged
    "#;
    let p = compile(src).expect("compile");
    let spec = encode_model(&p.inputs, &p.outputs, &p.states, &p.block, &p.fn_inputs,
        &ModelMeta::new(10, "CoreML9"));
    let dir = std::path::Path::new("/tmp/ir_fixed.mlpackage");
    let _ = std::fs::remove_dir_all(dir);
    write_mlpackage(dir, &spec, None).unwrap();
    println!("wrote {}", dir.display());
}
