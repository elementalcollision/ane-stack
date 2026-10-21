# PROBE-3: shape-flex × lane matrix — re-executed against observed behaviour.
# Asserts the *mechanism-level* claims in docs/spec/shape-flex-matrix.md, not the
# volatile details (paths, µs). Regenerates its own minimal models and artifacts.
require_cmd  cargo
require_cmd  xcrun

# --- build the probes and the minimal models (self-bootstrapping) ---
setup  cd vendor/mil_spec && cargo build --release -p mil_infer --example mk_minflex --example cml_exec --example shape_flex_e5rt --example e5exec --example seg4 >/dev/null 2>&1
setup  rm -rf /tmp/minflex /tmp/mf_mil_fixed /tmp/mf_mil_enum /tmp/mf_mil_range && vendor/mil_spec/target/release/examples/mk_minflex /tmp/minflex >/dev/null
require_artifact /tmp/minflex/fixed.mlpackage
require_artifact /tmp/minflex/enum.mlpackage
require_artifact /tmp/minflex/range.mlpackage

# compile the minimal variants to get model.mil for the e5rt lane
setup  cd vendor/mil_spec && ./target/release/milc compile /tmp/minflex/fixed.mlpackage -o /tmp/mf_mil_fixed >/dev/null 2>&1 && ./target/release/milc compile /tmp/minflex/enum.mlpackage -o /tmp/mf_mil_enum >/dev/null 2>&1 && ./target/release/milc compile /tmp/minflex/range.mlpackage -o /tmp/mf_mil_range >/dev/null 2>&1
require_artifact /tmp/mf_mil_fixed/fixed.mlmodelc/model.mil
require_artifact /tmp/mf_mil_enum/enum.mlmodelc/model.mil
require_artifact /tmp/mf_mil_range/range.mlmodelc/model.mil

# --- Matrix B, CoreML lane: the minimal model loads+predicts on every unit ---
# (a single add places trivially; this proves the encoding is correct)
run  vendor/mil_spec/target/release/examples/cml_exec /tmp/minflex/enum.mlpackage 4 ane 2>&1
want_out  PREDICT_OK

run  vendor/mil_spec/target/release/examples/cml_exec /tmp/minflex/range.mlpackage 4 all 2>&1
want_out  PREDICT_OK

# --- Matrix B, e5rt lane: the three shape mechanisms behave as documented ---
# fixed: compiles and executes at full shape
run  vendor/mil_spec/target/release/examples/e5exec /tmp/mf_mil_fixed/fixed.mlmodelc/model.mil 4 2>&1
want_out  EXEC_OK

# enumerated: e5rt cannot find `main` — function_name not found
run  vendor/mil_spec/target/release/examples/e5exec /tmp/mf_mil_enum/enum.mlmodelc/model.mil 1 2>&1
want_out  function_name not found in library

# range: compiles, but binds ports at the DEFAULT shape; feeding s=4 overflows
run  vendor/mil_spec/target/release/examples/e5exec /tmp/mf_mil_range/range.mlmodelc/model.mil 4 2>&1
want_out  overflow
# and at the default shape it executes
run  vendor/mil_spec/target/release/examples/e5exec /tmp/mf_mil_range/range.mlmodelc/model.mil 1 2>&1
want_out  EXEC_OK

# --- Matrix A headline: ShapeRange on cpu+ane is a hard crash, not a clean -14 ---
# The converted LLM range variant segfaults at Model::load on `all` and `ane`.
# Regenerate the converted decoder package if absent.
setup  cd vendor/mil_spec && cargo build --release -p mil_infer --example predseg >/dev/null 2>&1
setup  if [ ! -d /tmp/p3/c_range.mlpackage ]; then cd vendor/mil_spec && ./target/release/milc convert /tmp/p3model -o /tmp/p3/c_range.mlpackage --seq-range 1..4 >/dev/null 2>&1; fi
require_artifact /tmp/p3/c_range.mlpackage

# a clean load prints [stage] loaded and rc=0; a crash exits rc>=128 (SIGSEGV=139
# or SIGBUS=138 — the signal varies run to run, the crash does not). Assert the
# crash as a hard-crash exit, not a specific signal.
run  vendor/mil_spec/target/release/examples/predseg ane >/dev/null 2>&1; rc=$?; [ $rc -ge 128 ] && echo "CRASH rc=$rc"
want_out_re  CRASH rc=1[0-9][0-9]

run  vendor/mil_spec/target/release/examples/predseg all >/dev/null 2>&1; rc=$?; [ $rc -ge 128 ] && echo "CRASH rc=$rc"
want_out_re  CRASH rc=1[0-9][0-9]

# and the control: range on cpu loads cleanly (rc=0)
run  vendor/mil_spec/target/release/examples/predseg cpu >/dev/null 2>&1; rc=$?; echo "rc=$rc"
want_out  rc=0
