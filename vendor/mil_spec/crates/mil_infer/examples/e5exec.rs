use mil_infer::e5rt::{DeviceMask, Program};
use std::path::Path;
fn main() {
    let mil = std::env::args().nth(1).unwrap();
    let s: i64 = std::env::args().nth(2).and_then(|x| x.parse().ok()).unwrap_or(4);
    let (mut p, _pm) = Program::compile_auto(Path::new(&mil), DeviceMask::Ane).expect("compile");
    let n = s as usize;
    let x: Vec<u16> = (0..n).map(|i| half::f16::from_f32(i as f32).to_bits()).collect();
    p.set_input_f16("x", &x).expect("set input");
    p.execute().expect("exec");
    let y = p.output_f16("y").expect("output");
    let yf: Vec<f32> = y.iter().map(|b| half::f16::from_bits(*b).to_f32()).collect();
    println!("EXEC_OK s={s} y[..{}]={:?}", yf.len().min(6), &yf[..yf.len().min(6)]);
}
