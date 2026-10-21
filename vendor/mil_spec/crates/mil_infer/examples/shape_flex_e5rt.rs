// FORK(ane-stack) PROBE-3: e5rt lane shape-flex matrix.
// For each package variant's model.mil, drive e5rt compile under each
// DeviceMask and report compile OK / compile error. This is the e5rt deploy
// mechanism's own shape-flex behaviour, distinct from the CoreML loadModel lane.
use mil_infer::e5rt::{DeviceMask, Program};
use std::path::Path;

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    if a.len() < 3 {
        eprintln!("usage: shape_flex_e5rt <fixed.mil> <enum.mil> <range.mil>");
        std::process::exit(2);
    }
    let masks: [(&str, DeviceMask); 4] = [
        ("cpu", DeviceMask::Cpu),
        ("gpu", DeviceMask::Gpu),
        ("ane", DeviceMask::Ane),
        ("auto", DeviceMask::Auto),
    ];
    for (tag, mil) in [("fixed", &a[0]), ("enumerated", &a[1]), ("range", &a[2])] {
        for (mn, mask) in &masks {
            match Program::compile_auto(Path::new(mil), *mask) {
                Ok((_p, ports)) => {
                    println!("E5RT\t{}\t{}\tCOMPILE_OK\tin={} out={}", tag, mn, ports.inputs.len(), ports.outputs.len());
                }
                Err(e) => {
                    let s = format!("{e:?}");
                    let short: String = s.chars().take(90).collect();
                    println!("E5RT\t{}\t{}\tCOMPILE_FAIL\t{}", tag, mn, short);
                }
            }
        }
    }
}
