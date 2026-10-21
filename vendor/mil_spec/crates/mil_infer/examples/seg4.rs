use mil_infer::{ComputeUnits, Model};
fn main() {
    std::env::set_var("RUST_BACKTRACE", "1");
    let pkg = std::path::PathBuf::from(std::env::args().nth(1).unwrap());
    let cu = match std::env::args().nth(2).as_deref() {
        Some("gpu") => ComputeUnits::CpuAndGpu,
        Some("cpu") => ComputeUnits::CpuOnly,
        Some("ane") => ComputeUnits::CpuAndNeuralEngine,
        _ => ComputeUnits::All,
    };
    let work = std::env::temp_dir().join("seg4");
    let _ = std::fs::remove_dir_all(&work);
    let c = mil_compile::compile(&pkg, &work).expect("compile");
    eprintln!("[compiled]");
    match Model::load(&c.path, cu) {
        Ok(_) => eprintln!("[load ok]"),
        Err(e) => eprintln!("[load fail] {e}"),
    }
}
