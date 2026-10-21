// CoreML lane predict on a minimal flex package at a given seq len.
use mil_infer::{ComputeUnits, Model};
use std::path::Path;
fn f16s(v: &[f32]) -> Vec<u8> { v.iter().flat_map(|x| half::f16::from_f32(*x).to_le_bytes()).collect() }
fn main() {
    let pkg = Path::new(&std::env::args().nth(1).unwrap()).to_path_buf();
    let s: i64 = std::env::args().nth(2).and_then(|x| x.parse().ok()).unwrap_or(4);
    let cu = match std::env::args().nth(3).as_deref() {
        Some("gpu") => ComputeUnits::CpuAndGpu,
        Some("cpu") => ComputeUnits::CpuOnly,
        Some("ane") => ComputeUnits::CpuAndNeuralEngine,
        _ => ComputeUnits::All,
    };
    let work = std::env::temp_dir().join(format!("cml_exec_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&work);
    let c = match mil_compile::compile(&pkg, &work) { Ok(c)=>c, Err(e)=>{ println!("COMPILE_REJECT {}", e.to_string().lines().next().unwrap_or("")); return; } };
    let m = match Model::load(&c.path, cu) { Ok(m)=>m, Err(e)=>{ println!("LOAD_FAIL {e}"); return; } };
    let x: Vec<f32> = (0..s).map(|i| i as f32).collect();
    let xb = f16s(&x);
    let shp = [1, s, 1, 1];
    match m.predict(&[mil_infer::Input{name:"x", shape:&shp, data:&xb, dtype:mil_spec::DType::Fp16}]) {
        Ok(p) => {
            let o = p.outputs.iter().find(|o| o.name=="y").map(|o| o.values().len()).unwrap_or(0);
            println!("PREDICT_OK s={s} out_elems={o}");
        }
        Err(e) => println!("PREDICT_FAIL {e}"),
    }
}
