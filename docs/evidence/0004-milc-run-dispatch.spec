# 0004 / TOOL-1 (patch 0004): milc run <pkg> dispatches to the package path, not the shard loader
require_cmd  cargo
require_cmd  xcrun

# self-bootstrap the package (case-insensitive Manifest.json is the trigger)
setup  ./scripts/mk-evidence-artifacts.sh ir_fixed

require_artifact /tmp/ir_fixed.mlpackage

# a plain package must run, not be misrouted to the shard loader
run  vendor/mil_spec/target/release/milc run /tmp/ir_fixed.mlpackage --units ane --steps 2 2>/dev/null
want_rc   0
want_out_re [0-9]+ steps on cpu\+ane
want_absent kind is not "milshards"
