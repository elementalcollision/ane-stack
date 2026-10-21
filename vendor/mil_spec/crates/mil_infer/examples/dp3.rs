// FORK(ane-stack) PROBE-2: separate modelAtURL (parse) from loadModel (deploy).
use mil_infer::espresso::EspressoProgram;
use std::path::Path;
fn main() {
    let p = std::env::args().nth(1).unwrap();
    // load_precompiled does modelAtURL then loadModel; the Err message tells us which failed.
    match EspressoProgram::load_precompiled(Path::new(&p), &[]) {
        Ok(_) => println!("RESULT: LOAD_OK"),
        Err(e) => {
            let s = format!("{e:?}");
            if s.contains("modelAtURL") { println!("RESULT: FAIL_AT_modelAtURL: {s}"); }
            else if s.contains("loadModel") {
                let code = s.find("0x").map(|i| s[i..].chars().take(8).collect::<String>()).unwrap_or("none".into());
                println!("RESULT: FAIL_AT_loadModel code={code}");
            } else { println!("RESULT: FAIL_OTHER: {s}"); }
        }
    }
}
