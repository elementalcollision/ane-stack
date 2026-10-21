# 0002 / PROBE-2 + ADR-0002: the e5rt lane works; the direct-HWX deploy lane is closed
require_cmd  cargo

# the working lane: hand-written MIL -> aned compiles -> executes on the ANE.
# sigmoid(1.0) = 0.7310586; the hardware returns ~0.7309570 (within fp16).
setup  ./scripts/mk-evidence-artifacts.sh sig

run  vendor/mil_spec/target/release/milc ane run /tmp/sig.mil --steps 1 2>&1
want_rc   0
want_out  z: 64/64 nonzero
want_out_re 0\.73[0-9]+

# the closed lane: a self-emitted HWX is refused by aned's deploy path.
# Any of three provenances (ours, upstream-captured, Apple-shipped) fails;
# this reproduces the our-artifact case: loadModel reports a Program load failure.
run  cd vendor/mil_spec && cargo test --release -p mil_infer --lib hwx::tests::constexpr_dequant_folding_and_hw_exec 2>&1
want_out_re Program load failure
