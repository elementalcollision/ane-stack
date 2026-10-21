//! RUN-2 probe: find the stateful MIL shape `aned` accepts on the ANE.
//!
//! `ANECCompile` rejects some stateful graphs the MIL parser accepts, so the
//! grammar here is measured, not assumed. Two constraints from
//! `ANE_FRONTEND_SPEC.md` drive the ladder:
//!
//!   1. `write_state(data=X)` accepts only **state-derived** X — the
//!      `read_state` result or a `slice_update` on it. Writing an arbitrary
//!      computed tensor gives InvalidMILProgram.
//!   2. `slice_update` on a state requires the **full** argument list
//!      (begin, begin_mask, end, end_mask, squeeze_mask, stride, update, x);
//!      the minimal form parses on plain tensors but not on state.
//!
//! Each attempt is independent, so one rejection cannot mask another.
//!
//! Run: cargo run -p mil_infer --example probe_run2_state --release

use std::path::PathBuf;

fn try_mil(label: &str, mil: &str, _states: &[(&str, u64)], _out: &[(&str, u64)]) {
    let dir: PathBuf = std::env::temp_dir().join("run2_probe");
    std::fs::create_dir_all(&dir).unwrap();
    let p = dir.join(format!("{label}.mil"));
    std::fs::write(&p, mil).unwrap();
    // compile_auto discovers ports from the op's own descriptors, so a
    // successful bind tells us the real names instead of guessing them.
    match mil_infer::e5rt::Program::compile_auto(&p, mil_infer::e5rt::DeviceMask::Ane) {
        Ok((prog, map)) => println!(
            "{label:34} ACCEPTED  states={:?} in={:?} inout={:?} out={:?}",
            prog.state_names(),
            map.inputs.iter().map(|(n, e)| (n.as_str(), *e)).collect::<Vec<_>>(),
            map.inouts.iter().map(|(n, e)| (n.as_str(), *e)).collect::<Vec<_>>(),
            map.outputs.iter().map(|(n, e)| (n.as_str(), *e)).collect::<Vec<_>>(),
        ),
        Err(e) => println!("{label:34} reject    {e}"),
    }
}

fn main() {
    // 1: state-derived write only, no slice_update. write_state(data=r).
    try_mil(
        "1_plain_write_state",
        r#"program(1.3)
{
    func main<ios18>(state<tensor<fp16, [1, 4]>> kv, tensor<fp16, [1, 4]> wvec) {
        tensor<fp16, [1, 4]> r = read_state(input = kv)[name = string("r")];
        write_state(data = r, input = kv)[name = string("w")];
    } -> (r);
}
"#,
        &[("kv", 4)],
        &[("out", 4)],
    );

    // 2: full-arg slice_update on state, update = runtime input, output = su.
    try_mil(
        "2_slice_update_fullargs",
        r#"program(1.3)
{
    func main<ios18>(state<tensor<fp16, [4, 4]>> mem, tensor<fp16, [1, 4]> wvec) {
        tensor<fp16, [4, 4]> m = read_state(input = mem)[name = string("m")];
        tensor<int32, [2]> beg = const()[val = tensor<int32, [2]>([0, 0])];
        tensor<int32, [2]> end = const()[val = tensor<int32, [2]>([1, 4])];
        tensor<int32, [2]> stride = const()[val = tensor<int32, [2]>([1, 1])];
        tensor<bool, [2]> bm = const()[val = tensor<bool, [2]>([false, false])];
        tensor<bool, [2]> em = const()[val = tensor<bool, [2]>([false, false])];
        tensor<bool, [2]> sm = const()[val = tensor<bool, [2]>([false, false])];
        tensor<fp16, [4, 4]> m2 = slice_update(x = m, update = wvec, begin = beg, end = end, stride = stride, begin_mask = bm, end_mask = em, squeeze_mask = sm)[];
        write_state(data = m2, input = mem)[name = string("w")];
    } -> (m2);
}
"#,
        &[("mem", 16)],
        &[("out", 16)],
    );

    // 3: same, but output the pre-write read_state value r (readback path).
    try_mil(
        "3_readback_via_read_state",
        r#"program(1.3)
{
    func main<ios18>(state<tensor<fp16, [4, 4]>> mem, tensor<fp16, [1, 4]> wvec) {
        tensor<fp16, [4, 4]> m = read_state(input = mem)[name = string("m")];
        tensor<int32, [2]> beg = const()[val = tensor<int32, [2]>([0, 0])];
        tensor<int32, [2]> end = const()[val = tensor<int32, [2]>([1, 4])];
        tensor<int32, [2]> stride = const()[val = tensor<int32, [2]>([1, 1])];
        tensor<bool, [2]> bm = const()[val = tensor<bool, [2]>([false, false])];
        tensor<bool, [2]> em = const()[val = tensor<bool, [2]>([false, false])];
        tensor<bool, [2]> sm = const()[val = tensor<bool, [2]>([false, false])];
        tensor<fp16, [4, 4]> m2 = slice_update(x = m, update = wvec, begin = beg, end = end, stride = stride, begin_mask = bm, end_mask = em, squeeze_mask = sm)[];
        write_state(data = m2, input = mem)[name = string("w")];
    } -> (m);
}
"#,
        &[("mem", 16)],
        &[("out", 16)],
    );

    // 4: two states, each with its own full-arg triple (2-layer kv shape).
    try_mil(
        "4_two_layer_triples",
        r#"program(1.3)
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
    } -> (u0);
}
"#,
        &[("k0", 16), ("k1", 16)],
        &[("out", 16)],
    );

    // 5: slice_update on state but data written is the read_state result, not
    //    the su result — is the su then dead, or must data be the last su?
    try_mil(
        "5_write_read_not_su",
        r#"program(1.3)
{
    func main<ios18>(state<tensor<fp16, [4, 4]>> mem, tensor<fp16, [1, 4]> wvec) {
        tensor<fp16, [4, 4]> m = read_state(input = mem)[name = string("m")];
        tensor<int32, [2]> beg = const()[val = tensor<int32, [2]>([0, 0])];
        tensor<int32, [2]> end = const()[val = tensor<int32, [2]>([1, 4])];
        tensor<int32, [2]> stride = const()[val = tensor<int32, [2]>([1, 1])];
        tensor<bool, [2]> bm = const()[val = tensor<bool, [2]>([false, false])];
        tensor<bool, [2]> em = const()[val = tensor<bool, [2]>([false, false])];
        tensor<bool, [2]> sm = const()[val = tensor<bool, [2]>([false, false])];
        tensor<fp16, [4, 4]> m2 = slice_update(x = m, update = wvec, begin = beg, end = end, stride = stride, begin_mask = bm, end_mask = em, squeeze_mask = sm)[];
        write_state(data = m, input = mem)[name = string("w")];
    } -> (m2);
}
"#,
        &[("mem", 16)],
        &[("out", 16)],
    );
}
