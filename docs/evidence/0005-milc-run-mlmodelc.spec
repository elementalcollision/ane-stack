# 0005 / TOOL-2 (patch 0005): milc run accepts a compiled .mlmodelc directly
require_cmd  cargo
require_cmd  xcrun

setup  ./scripts/mk-evidence-artifacts.sh ir_fixed

require_artifact /tmp/ir_fixed.compiled/ir_fixed.mlmodelc/model.mil

# the acceptance criterion: run the compiled artifact directly, no package spec
run  vendor/mil_spec/target/release/milc run /tmp/ir_fixed.compiled/ir_fixed.mlmodelc --units ane --steps 3 2>/dev/null
want_rc   0
want_out_re [0-9]+ steps on cpu\+ane
want_absent model.mlmodel: No such file

# regression: the package path still works through the same binary
run  vendor/mil_spec/target/release/milc run /tmp/ir_fixed.mlpackage --units ane --steps 2 2>/dev/null
want_rc   0
want_out_re [0-9]+ steps on cpu\+ane
