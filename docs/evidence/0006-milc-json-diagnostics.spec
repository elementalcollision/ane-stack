# 0006 / TOOL-3: failing milc invocations under --json yield parseable JSON
require_cmd  cargo

# failing run: ok=false, an error object with a stage and a path
run  vendor/mil_spec/target/release/milc run --json /nonexistent.mlpackage --units ane 2>/dev/null
want_rc   1
want_out  "ok":false
want_out  "command":"run"
want_out_re "error":\{[^}]*"stage"

# failing check: ok=false with an errors array
run  vendor/mil_spec/target/release/milc check --json /nonexistent 2>/dev/null
want_rc   1
want_out  "ok":false
want_out  "errors":[

# failing plan: ok=false with an error carrying a stage
run  vendor/mil_spec/target/release/milc plan --json /nonexistent.mlpackage 2>/dev/null
want_rc   1
want_out  "ok":false
want_out_re "error":\{[^}]*"stage"

# MILC_JSON=1 honoured without the flag
run  env MILC_JSON=1 vendor/mil_spec/target/release/milc run /nonexistent.mlpackage --units ane 2>/dev/null
want_rc   1
want_out  "ok":false

# success envelope carries real latency data, parseable by python's json
run  vendor/mil_spec/target/release/milc run --json /tmp/ir_fixed.compiled/ir_fixed.mlmodelc --units ane --steps 2 2>/dev/null
want_rc   0
want_out  "ok":true
want_out_re "median_ns":[0-9]+
