// FORK(ane-stack) PROBE-2: deploy-gate decoder.
// Loads ONE HWX/Mach-O artifact through _ANEClient loadModel (precompiled path)
// and prints the outcome + error code, so each probe runs fork-isolated.
// ObjC exceptions abort the process — that IS the signal for some artifacts.
use mil_infer::espresso::EspressoProgram;
use std::path::Path;

fn main() {
    let p = std::env::args().nth(1).expect("usage: deploy_probe <artifact.hwx|.macho>");
    let path = Path::new(&p);
    // extra loadModel option keys to probe the perf-stats gate variant
    let extra: Vec<(&str, u64)> = std::env::args()
        .skip(2)
        .filter_map(|kv| {
            let (k, v) = kv.split_once('=')?;
            Some((Box::leak(k.to_string().into_boxed_str()) as &'static str, v.parse().ok()?))
        })
        .collect();
    match EspressoProgram::load_precompiled(path, &extra) {
        Ok(mut prog) => {
            println!("LOAD_OK {} in={} out={}", path.display(), prog.input_descs.len(), prog.output_descs.len());
            match prog.eval() {
                Ok(()) => println!("EVAL_OK {}", path.display()),
                Err(e) => println!("EVAL_ERR {} {:?}", path.display(), e),
            }
        }
        Err(e) => {
            // extract the hex code from the error string for stable comparison
            let s = format!("{e:?}");
            let code = s.find("0x").map(|i| s[i..].chars().take(8).collect::<String>()).unwrap_or_else(|| "????????".into());
            println!("LOAD_FAIL {} code={}", path.display(), code);
        }
    }
}
