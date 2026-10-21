# 0006 / TOOL-2 process fix: patch set applies to pristine upstream exactly once
require_cmd  cargo
require_cmd  git

# patch 0001's content appears exactly once in the vendored tree
# (the double-apply regression: it must not be present at two sites)
run  grep -c "write_state shape mismatch" vendor/mil_spec/src/ir.rs
want_rc   0
want_out  1

# patches 0001..0006 (the set 0006 covered) apply in order to pristine upstream.
# 0007+ are later, separately-owned additions and are intentionally out of
# scope for this item — the full-set invariant is CI's job, not this evidence.
run  ./scripts/apply-patches.sh --check 0001 0002 0003 0004 0005 0006 2>&1
want_rc   0
want_out  all patches apply to pristine upstream, in order
