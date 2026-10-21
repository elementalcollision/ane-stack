use mil_infer::{ComputeUnits, Model};
fn f16s(v: &[f32]) -> Vec<u8> { v.iter().flat_map(|x| half::f16::from_f32(*x).to_le_bytes()).collect() }
fn main() {
    let pkg = std::path::PathBuf::from("/tmp/p3/c_range.mlpackage");
    let cu = match std::env::args().nth(1).as_deref() { Some("gpu")=>ComputeUnits::CpuAndGpu, Some("cpu")=>ComputeUnits::CpuOnly, Some("ane")=>ComputeUnits::CpuAndNeuralEngine, _=>ComputeUnits::All };
    let work = std::env::temp_dir().join(format!("ps_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&work);
    let c = mil_compile::compile(&pkg, &work).expect("compile");
    eprintln!("[stage] compiled");
    let m = Model::load(&c.path, cu).expect("load");
    eprintln!("[stage] loaded; predicting with 2048-KV feed");
    let s=4i64; let kv=2048i64; let d=16i64; let hd=8i64;
    let sh=|v:&[i64]|->&'static [i64]{Box::leak(v.to_vec().into_boxed_slice())};
    let x: Vec<f32>=(0..d*s).map(|i|0.05*((i*7%13) as f32)-0.3).collect();
    let cs: Vec<f32>=(0..s*hd).map(|i|(i as f32*0.1).cos()).collect();
    let sn: Vec<f32>=(0..s*hd).map(|i|(i as f32*0.1).sin()).collect();
    let mut mk=vec![-1e4f32;(s*kv) as usize];
    for p in 0..s { for k in 0..=p.min(kv-1) { mk[(p*kv+k) as usize]=0.0; } }
    let ins=vec![
        mil_infer::Input{name:"x",shape:sh(&[1,d,s,1]),data:Box::leak(f16s(&x).into_boxed_slice()),dtype:mil_spec::DType::Fp16},
        mil_infer::Input{name:"cos",shape:sh(&[1,1,s,hd]),data:Box::leak(f16s(&cs).into_boxed_slice()),dtype:mil_spec::DType::Fp16},
        mil_infer::Input{name:"sin",shape:sh(&[1,1,s,hd]),data:Box::leak(f16s(&sn).into_boxed_slice()),dtype:mil_spec::DType::Fp16},
        mil_infer::Input{name:"mask",shape:sh(&[1,1,s,kv]),data:Box::leak(f16s(&mk).into_boxed_slice()),dtype:mil_spec::DType::Fp16},
        mil_infer::Input{name:"pos",shape:sh(&[1]),data:Box::leak(Box::new(0i32.to_le_bytes())),dtype:mil_spec::DType::Int32},
        mil_infer::Input{name:"seq",shape:sh(&[1]),data:Box::leak(Box::new(4i32.to_le_bytes())),dtype:mil_spec::DType::Int32},
    ];
    let st=m.new_state().ok();
    match m.predict_with_state(st.as_ref(), &ins) { Ok(_)=>eprintln!("[stage] PREDICT_OK"), Err(e)=>eprintln!("[stage] PREDICT_FAIL {e}") }
}
