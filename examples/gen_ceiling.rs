// FORK(ane-stack) ADR-0002 A.5: disambiguate what the ~320-op ANECCompile
// ceiling actually limits.
//!
//! `examples/gen_big.rs` showed a scale ladder failing at 320 ops with
//! `Compiler internal error` and at 1280 with `MaxLiveInLiveOutExceeded`. But
//! that generator raises op count and inout-port count *together* — one state
//! per layer, ~5 ops per layer — so it cannot say which resource is the wall.
//!
//! This probe varies them independently:
//!
//!   mode `ops`    few states, MANY ops    (long stateless chain)
//!   mode `states` MANY states, few ops    (one triple per state)
//!
//! whichever fails first is the binding resource, and that determines whether
//! `milc convert --shard N` (which splits states across shards) can work around
//! it at all.
//!
//! Usage: gen_ceiling <ops|states> <n> [out.mil]

use std::path::Path;

fn main() {
    let mode = std::env::args().nth(1).unwrap_or_else(|| "ops".into());
    let n: usize = std::env::args()
        .nth(2)
        .and_then(|s| s.parse().ok())
        .unwrap_or(512);
    let out = std::env::args()
        .nth(3)
        .unwrap_or_else(|| "/tmp/hw/ceil.mil".into());

    let d = 32usize;
    let n2: usize = std::env::args()
        .nth(4)
        .and_then(|s| s.parse().ok())
        .unwrap_or(2 * n);
    let mut s = String::new();
    s.push_str("program(1.3)\n{\n    func main<ios18>(");

    match mode.as_str() {
        // Few states, many ops: long elementwise chain over one state.
        "ops" => {
            s.push_str(&format!("tensor<fp16, [1, {d}]> x) {{\n"));
            s.push_str(
                "        tensor<int32, [2]> b0 = const()[val = tensor<int32, [2]>([0, 0])];\n",
            );
            let mut prev = "x".to_string();
            for i in 0..n {
                s.push_str(&format!(
                    "        tensor<fp16, [1, {d}]> y{i} = add(x = {prev}, y = {prev})[name = string(\"y{i}\")];\n"
                ));
                prev = format!("y{i}");
            }
            s.push_str(&format!("    }} -> ({prev});\n}}\n"));
        }
        // One packed state, many ops: the shape --shard N actually emits.
        // One `kv` state whose rows carry every layer's slot, as
        // mil_convert/src/builder.rs build_range does (kv_shape has
        // (le-ls)*2 rows), plus a long per-layer op chain.
        "packed" => {
            s.push_str(&format!("state<tensor<fp16, [{n2}, {d}]>> kv, tensor<fp16, [1, {d}]> x) {{\n"));
            s.push_str(&format!(
                "        tensor<fp16, [{n2}, {d}]> m = read_state(input = kv)[name = string(\"m\")];\n"
            ));
            let mut prev = "m".to_string();
            for i in 0..n {
                s.push_str(&format!(
                    "        tensor<fp16, [{n2}, {d}]> y{i} = add(x = {prev}, y = {prev})[name = string(\"y{i}\")];\n"
                ));
                prev = format!("y{i}");
            }
            s.push_str(&format!("    }} -> ({prev});\n}}\n"));
        }
        // Many states, few ops each: a read per state.
        "states" => {
            for i in 0..n {
                s.push_str(&format!(
                    "state<tensor<fp16, [4, {d}]>> k{i}, "
                ));
            }
            s.push_str(&format!("tensor<fp16, [1, {d}]> x) {{\n"));
            s.push_str(
                "        tensor<int32, [2]> b0 = const()[val = tensor<int32, [2]>([0, 0])];\n",
            );
            for i in 0..n {
                s.push_str(&format!(
                    "        tensor<fp16, [4, {d}]> m{i} = read_state(input = k{i})[name = string(\"m{i}\")];\n"
                ));
            }
            s.push_str("    } -> (m0);\n}\n");
        }
        other => {
            eprintln!("unknown mode {other:?} — use ops|states");
            std::process::exit(2);
        }
    }

    let bytes = s.len();
    let ops = s.matches("[name = string(").count();
    let p = Path::new(&out);
    if let Some(dir) = p.parent() {
        std::fs::create_dir_all(dir).unwrap();
    }
    std::fs::write(p, &s).unwrap();
    println!("wrote {out} — mode={mode} n={n} ops={ops} bytes={bytes}");
}
