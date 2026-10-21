# 0005 / TOOL-4: the vendored-tree guard catches drift, passes on clean
require_cmd  cargo

# the full self-contained regression suite against a scratch copy
run  bash tests/vendor-guard.bats.sh 2>&1
want_rc   0
want_out  all TOOL-4 tests passed

# and the guard itself, run against the real tree, passes when clean.
# (uses --status which is read-only, so L-IR's in-flight edits are reported
# but this spec only asserts the tool runs and reports, not that it's clean.)
run  ./scripts/vendor-guard.sh --status 2>&1
want_rc   0
