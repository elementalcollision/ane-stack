# 0007 / IR-2 (L-IR): slice_update is expressible in the IR and validated
require_cmd  cargo

# the five slice_update tests pass in the vendored tree
run  cd vendor/mil_spec && cargo test --test ir 2>&1
want_rc   0
want_out  slice_update_whole_state_write ... ok
want_out  slice_update_region_write ... ok
want_out  slice_update_begin_end_must_match_rank ... ok
want_out  slice_update_update_shape_must_match_region ... ok
want_out  slice_update_range_invalid_is_rejected ... ok
# The named slice_update tests must pass. Do NOT assert a total count — IR-3/IR-4
# legitimately grew the suite (22 → 29+), and a hard count makes this evidence rot
# the moment another lane adds a test. The durable claim is that these five pass.
want_out_re test result: ok\. [0-9]+ passed; 0 failed

# the conformance battery is unaffected (the IR addition is additive)
run  cd vendor/mil_spec && ./target/release/milc verify 2>&1
want_rc   0
want_out  10 cases, 0 failed
