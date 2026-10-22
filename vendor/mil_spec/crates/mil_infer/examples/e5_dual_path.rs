// FORK(ane-stack) A.5 class-4: does aned's own .e5 bundle load via the
// supported e5rt path as well as the _ANEClient path?
//
// PROBE-2's class-4 evidence loaded `aned`'s own `.e5` through
// `EspressoProgram::load_precompiled` (the `_ANEClient` precompiled path) and
// found it refused (`0x120004` on macOS 26.7.1). But the bundle also has a
// *supported* loader — `e5rt::Program::from_e5_bundle` — which builds an op
// from the same bundle and runs it. The two paths are not interchangeable
// statements about the same fact: one is a deploy attempt, one is normal use.
//
// This probe records both, for the same bundle, in one run, so the class-4
// claim can be stated precisely rather than as "aned's own output is refused"
// without saying which path was meant.
//
// Usage: e5_dual_path <path-to-.e5>
use std::path::Path;

fn main() {
    let p = std::env::args().nth(1).expect("usage: e5_dual_path <bundle.e5>");
    let path = Path::new(&p);

    println!("bundle: {p}");

    // ---- path 1: the _ANEClient precompiled (deploy) path ----
    match mil_infer::espresso::EspressoProgram::load_precompiled(path, &[]) {
        Ok(_) => println!("  _ANEClient deploy path : LOAD_OK"),
        Err(e) => println!("  _ANEClient deploy path : REFUSED ({e})"),
    }

    // ---- path 2: the supported e5rt loader ----
    // `from_e5_bundle` wants the composite bundle *directory*, not the flat
    // `.e5` file (`_ANEClient` is the reverse — the file is what it takes).
    // Try the parent dir, then the arg as given, so either layout works.
    let dir = path.parent().unwrap_or(path);
    match mil_infer::e5rt::Program::from_e5_bundle(dir) {
        Ok((prog, map)) => println!(
            "  e5rt from_e5_bundle   : OK (fns={:?}, in={:?}, inout={:?}, out={:?})",
            prog.functions,
            map.inputs.iter().map(|(n, e)| (n.as_str(), *e)).collect::<Vec<_>>(),
            map.inouts.iter().map(|(n, e)| (n.as_str(), *e)).collect::<Vec<_>>(),
            map.outputs.iter().map(|(n, e)| (n.as_str(), *e)).collect::<Vec<_>>(),
        ),
        Err(e) => println!("  e5rt from_e5_bundle   : ERR ({e})"),
    }
}
