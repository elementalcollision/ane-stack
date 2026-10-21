// FORK(ane-stack) ADR-0002 A.5: generate a LARGE MIL program to test whether the
// macOS 27.0 deploy gate opens at scale, not only for a 13-op model.
//
// No supported-architecture checkpoint exists on this Mac: the 36-layer Jina
// model is `JinaEmbeddingsV4Model` and the only cached models are BERT encoders
// (`BertModel`), neither of which `mil_convert` accepts (it handles
// qwen2/qwen3/llama/mistral only). So the scale axis ADR-0002 A.5 names ("a
// >3.2k-op model") is tested directly on the emitter's own input instead.
//
// GRAMMAR WARNING — learned by breaking it first. Each layer must write back the
// *terminal slice_update* output with the FULL argument list. A first version
// emitted `write_state(data = add(...))` and every size was rejected with
// InvalidMILProgram — exactly the form mil_infer/examples/probe_run2_state.rs
// cases 1/5 proved rejected.
//
// RESOURCE WARNING — learned second. Per-layer copies of the six index consts
// inflate op count without adding compute, and the ANEC frontend hits
// MaxLiveInputs / Compiler-internal-error at a few hundred ops. So the consts
// are hoisted once and shared by every layer, and op count is grown with real
// compute (`+` chains) instead of const duplication.
//
// Usage: gen_big <layers> [out.mil]

use std::path::Path;

fn main() {
    let layers: usize = std::env::args()
        .nth(1)
        .and_then(|s| s.parse().ok())
        .unwrap_or(64);
    let out = std::env::args()
        .nth(2)
        .unwrap_or_else(|| "/tmp/hw/big.mil".into());

    let kv = 16usize; // rows in each layer's K cache
    let d = 32usize; // hidden

    let mut s = String::new();
    s.push_str("program(1.3)\n{\n    func main<ios18>(");
    for l in 0..layers {
        s.push_str(&format!("state<tensor<fp16, [{kv}, {d}]>> k{l}, "));
    }
    s.push_str(&format!("tensor<fp16, [1, {d}]> x) {{\n"));

    // Hoisted index consts, shared by every layer's slice_update.
    s.push_str(
        "        tensor<int32, [2]> b0 = const()[val = tensor<int32, [2]>([0, 0])];\n",
    );
    s.push_str(&format!(
        "        tensor<int32, [2]> e0 = const()[val = tensor<int32, [2]>([{kv}, {d}])];\n"
    ));
    s.push_str(
        "        tensor<int32, [2]> st0 = const()[val = tensor<int32, [2]>([1, 1])];\n",
    );
    for c in ["bm0", "em0", "sm0"] {
        s.push_str(&format!(
            "        tensor<bool, [2]> {c} = const()[val = tensor<bool, [2]>([false, false])];\n"
        ));
    }

    let mut prev = "x".to_string();
    for l in 0..layers {
        s.push_str(&format!(
            "        tensor<fp16, [{kv}, {d}]> m{l} = read_state(input = k{l})[name = string(\"m{l}\")];\n"
        ));
        // The update tile is genuine compute over the read value, so growing
        // the layer count grows real work rather than const noise.
        s.push_str(&format!(
            "        tensor<fp16, [{kv}, {d}]> t{l} = add(x = m{l}, y = m{l})[name = string(\"t{l}\")];\n"
        ));
        s.push_str(&format!(
            "        tensor<fp16, [{kv}, {d}]> u{l} = slice_update(x = m{l}, update = t{l}, begin = b0, end = e0, stride = st0, begin_mask = bm0, end_mask = em0, squeeze_mask = sm0)[name = string(\"u{l}\")];\n"
        ));
        s.push_str(&format!(
            "        write_state(data = u{l}, input = k{l})[name = string(\"w{l}\")];\n"
        ));
        s.push_str(&format!(
            "        tensor<fp16, [1, {d}]> r{l} = add(x = {prev}, y = {prev})[name = string(\"r{l}\")];\n"
        ));
        prev = format!("r{l}");
    }
    s.push_str(&format!("    }} -> ({prev});\n}}\n"));

    let bytes = s.len();
    let ops = s.matches("[name = string(").count();
    let p = Path::new(&out);
    if let Some(dir) = p.parent() {
        std::fs::create_dir_all(dir).unwrap();
    }
    std::fs::write(p, &s).unwrap();
    println!("wrote {out} — {layers} layers, ~{ops} named ops, {bytes} bytes");
}
