# 0001 / IR-1: write_state shape validation — a stateful package now compiles and runs
require_cmd  cargo
require_cmd  xcrun

# build the stateful package from our example (self-bootstrapping)
setup  cd examples && cargo run --release --example compile_ir_fixed >/dev/null

require_artifact /tmp/ir_fixed.mlpackage/Data/com.apple.CoreML/model.mlmodel

# coremlc accepts the stateful package
setup  rm -rf /tmp/irf_ev && mkdir -p /tmp/irf_ev && xcrun coremlc compile /tmp/ir_fixed.mlpackage /tmp/irf_ev >/dev/null
require_artifact /tmp/irf_ev/ir_fixed.mlmodelc

# the IR shape check rejects a mismatched whole-state write at compile time
run  cd vendor/mil_spec && cargo test --test ir write_state_shape_mismatch_rejected 2>&1
want_rc   0
want_out  write_state_shape_mismatch_rejected ... ok

# and it runs on cpu+ane
run  vendor/mil_spec/target/release/milc run /tmp/ir_fixed.mlpackage --units ane --steps 3 2>/dev/null
want_rc   0
want_out_re [0-9]+ steps on cpu\+ane
