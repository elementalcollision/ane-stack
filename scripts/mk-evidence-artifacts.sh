#!/usr/bin/env bash
# mk-evidence-artifacts.sh — build the shared /tmp artifacts evidence specs
# reference, so no evidence item depends on something that lived in /tmp once.
#
#   ./scripts/mk-evidence-artifacts.sh            # build everything below
#   ./scripts/mk-evidence-artifacts.sh ir_fixed   # just the package + compiled
#   ./scripts/mk-evidence-artifacts.sh sig        # just /tmp/sig.mil
#
# Idempotent: existing artifacts are left in place (delete to force a rebuild).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname "$here")"
milc="$root/vendor/mil_spec/target/release/milc"
vendor="$root/vendor/mil_spec"

mk_sig() {
  if [ ! -f /tmp/sig.mil ]; then
    cat > /tmp/sig.mil <<'EOF'
program(1.3)
{
    func main<ios18>(tensor<fp16, [1, 64, 1, 1]> x) {
        tensor<fp16, [1, 64, 1, 1]> z = sigmoid(x = x)[name = string("z")];
    } -> (z);
}
EOF
  fi
}

mk_ir_fixed() {
  # The stateful package — built by our own example against the vendored mil_spec.
  if [ ! -f /tmp/ir_fixed.mlpackage/Data/com.apple.CoreML/model.mlmodel ]; then
    (cd "$root/examples" && cargo run --release --example compile_ir_fixed >/dev/null)
  fi
  # The compiled artifact (TOOLS-2/0005 evidence runs it directly).
  if [ ! -f /tmp/ir_fixed.compiled/ir_fixed.mlmodelc/model.mil ]; then
    [ -f "$milc" ] || (cd "$vendor" && cargo build --release -p milc)
    rm -rf /tmp/ir_fixed.compiled
    "$milc" compile /tmp/ir_fixed.mlpackage -o /tmp/ir_fixed.compiled >/dev/null
  fi
}

what="${1:-all}"
case "$what" in
  sig)       mk_sig ;;
  ir_fixed)  mk_ir_fixed ;;
  all)       mk_sig; mk_ir_fixed ;;
  *) echo "usage: $0 {sig|ir_fixed|all}" >&2; exit 2 ;;
esac
