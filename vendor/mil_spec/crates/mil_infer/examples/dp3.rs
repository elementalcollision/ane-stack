// FORK(ane-stack) PROBE-2: separate modelAtURL (parse) from loadModel (deploy).
//
// RUN-1 note: loadModel failures are now a typed `EspError::Load(AneLoadError)`
// rather than a pre-formatted string, so this matches on the variant instead of
// grepping the Debug text. Output format is unchanged from PROBE-2's evidence
// file, so `docs/evidence/0010-deploy-gate-codes.md` reproduces as written.
use mil_infer::espresso::{AneLoadError, EspError, EspressoProgram};
use std::path::Path;

fn main() {
    let p = std::env::args().nth(1).unwrap();
    // load_precompiled does modelAtURL then loadModel; the Err variant tells us which.
    match EspressoProgram::load_precompiled(Path::new(&p), &[]) {
        Ok(_) => println!("RESULT: LOAD_OK"),
        Err(EspError::Load(e)) => {
            let code = match e.code {
                Some(c) => format!("0x{c:06X}"),
                None => "none".to_string(),
            };
            println!(
                "RESULT: FAIL_AT_loadModel code={code} kind={:?} form={:?}",
                e.kind, e.form
            );
        }
        Err(e) => {
            let s = format!("{e:?}");
            if s.contains("modelAtURL") {
                println!("RESULT: FAIL_AT_modelAtURL: {s}");
            } else {
                println!("RESULT: FAIL_OTHER: {s}");
            }
        }
    }
    // Silence an unused-import warning if the variant list ever changes.
    let _ = AneLoadError::decode("");
}
