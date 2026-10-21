// FORK(ane-stack) PROBE-3: build three minimal flexible-shape packages.
//
// A single `add(x, x)` over a [1, S, 1, 1] fp16 tensor, where S is:
//   - fixed 4                      (fixed.mlpackage)
//   - EnumeratedShapes {1, 4}      (enum.mlpackage)
//   - ShapeRange 1..4              (range.mlpackage)
//
// Minimal on purpose: the converted LLM decoder graph carries ops e5rt cannot
// place on any backend, which would conflate "op not supported" with "shape
// mechanism rejected". One op keeps shape flexibility the only variable.

use mil_spec::*;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

fn build(out: &Path, flex: Option<Flex>) {
    // The declared feature shape is the *default* shape: for EnumeratedShapes
    // it must be the first enumerated entry; for ShapeRange the lower bound.
    // Declaring [1,4,1,1] while the flex default is [1,1,1,1] is a validator
    // error ("input has a different shape than its parameter to main").
    let default_shape: Vec<i64> = match &flex {
        None => vec![1, 4, 1, 1],
        Some(Flex::Enumerated(es)) => es.shapes[0].clone(),
        Some(Flex::Range(sr)) => sr.dims.iter().map(|(lo, _)| *lo).collect(),
    };
    // the op's I/O shapes and the function signature must use the same default
    let mut b = Block::new();
    let y = b.add("x", "x", &default_shape, "y");
    b.outputs = vec![y];

    let inputs = [Feature {
        name: "x".into(),
        shape: default_shape.clone(),
        dtype: DType::Fp16,
        is_state: false,
    }];
    let outputs = [Feature {
        name: "y".into(),
        shape: default_shape.clone(),
        dtype: DType::Fp16,
        is_state: false,
    }];
    let fn_inputs = [NVT {
        name: "x".into(),
        ty: ValueType::Tensor(TensorType::f16(&default_shape)),
    }];

    let mut flexmap: BTreeMap<String, Flex> = BTreeMap::new();
    // The varying dim (index 1, the sequence axis) must be marked *symbolic* in
    // the function signature, or the validator rejects the package: a flexible
    // feature with a concrete fn-signature shape is "different shape than its
    // parameter to main". Matches the upstream working flex model's `sym` map.
    let mut syms: BTreeMap<String, Vec<Option<String>>> = BTreeMap::new();
    let spec = match &flex {
        None => encode_model(&inputs, &outputs, &[], &b, &fn_inputs, &ModelMeta::new(10, "CoreML9")),
        Some(fx) => {
            // apply the same flex to both the input and the output feature
            flexmap.insert("x".into(), fx.clone());
            flexmap.insert("y".into(), fx.clone());
            for n in ["x", "y"] {
                syms.insert(n.to_string(), vec![None, Some("s".to_string()), None, None]);
            }
            encode_model_flexible(&inputs, &outputs, &[], &b, &fn_inputs, &ModelMeta::new(10, "CoreML9"), &flexmap, &syms)
                .expect("encode flexible")
        }
    };
    write_mlpackage(out.as_ref(), &spec, None).unwrap();
    println!("wrote {}", out.display());
}

fn main() {
    let dir = std::env::args()
        .nth(1)
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/tmp/minflex"));
    std::fs::create_dir_all(&dir).unwrap();
    build(&dir.join("fixed.mlpackage"), None);
    build(
        &dir.join("enum.mlpackage"),
        Some(Flex::Enumerated(EnumeratedShapes {
            shapes: vec![vec![1, 1, 1, 1], vec![1, 4, 1, 1]],
        })),
    );
    build(
        &dir.join("range.mlpackage"),
        Some(Flex::Range(ShapeRange {
            dims: vec![(1, 1), (1, 4), (1, 1), (1, 1)],
        })),
    );
}
