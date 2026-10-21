#!/usr/bin/env bash
# TOOL-4 regression test: the vendor guard must catch drift and pass on clean.
#
# This is a self-contained script test, not a Rust test — the guard is a shell
# script and the thing under test is its exit behaviour. Run with:
#
#   bash tests/vendor-guard.bats.sh
#
# Exit 0 if every assertion holds. This is the test L-TEST would veto us for
# not having. It does not touch the real vendor tree — it clones the guard's
# inputs into a scratch copy.
set -uo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
guard="$root/scripts/vendor-guard.sh"
fails=0

pass() { echo "  ok — $1"; }
fail() { echo "  FAIL — $1"; fails=$((fails+1)); }

assert_rc() { # assert_rc <expected> <desc> <cmd...>
  local want="$1" desc="$2"; shift 2
  "$@" >/dev/null 2>&1; local got=$?
  [ "$got" = "$want" ] && pass "$desc (rc=$got)" || fail "$desc (want rc=$want, got $got)"
}

assert_grep() { # assert_grep <needle> <desc> <cmd...>
  local needle="$1" desc="$2"; shift 2
  local out; out="$("$@" 2>&1)"
  echo "$out" | grep -qF "$needle" && pass "$desc" || { fail "$desc — no '$needle' in output"; echo "$out" | sed 's/^/    /'; }
}

echo "TOOL-4 vendor-guard tests"

# Work on a scratch copy of the vendored tree so the real one is never mutated.
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
mkdir -p "$scratch/vendor"
# minimal fake tree the guard can hash
cat > "$scratch/vendor/mil_spec.sample" <<'EOF'
placeholder
EOF
# Point the guard at the scratch root by faking the script layout.
mkdir -p "$scratch/scripts"
cp "$guard" "$scratch/scripts/vendor-guard.sh"
# vendor dir the script expects: <scratch>/vendor/mil_spec
rm -f "$scratch/vendor/mil_spec.sample"
mkdir -p "$scratch/vendor/mil_spec/src"
echo "fn main(){}" > "$scratch/vendor/mil_spec/src/main.rs"
echo "spec" > "$scratch/vendor/mil_spec/SPEC.md"

echo "-- verify fails with no manifest"
assert_rc 1 "no-manifest verify fails" \
  "$scratch/scripts/vendor-guard.sh" --verify

echo "-- generate creates a manifest"
assert_rc 0 "generate succeeds" \
  "$scratch/scripts/vendor-guard.sh" --generate
[ -f "$scratch/vendor/manifest.sha256" ] && pass "manifest exists" || fail "manifest missing"

echo "-- clean tree verifies"
assert_rc 0 "clean tree verifies" \
  "$scratch/scripts/vendor-guard.sh" --verify

echo "-- mutated file fails verify, naming the file"
echo "tamper" >> "$scratch/vendor/mil_spec/src/main.rs"
assert_rc 1 "tampered verify fails" \
  "$scratch/scripts/vendor-guard.sh" --verify
assert_grep "src/main.rs" "tampered file is named" \
  "$scratch/scripts/vendor-guard.sh" --verify

echo "-- restore and verify passes again"
echo "fn main(){}" > "$scratch/vendor/mil_spec/src/main.rs"
assert_rc 0 "restored tree verifies" \
  "$scratch/scripts/vendor-guard.sh" --verify

echo "-- build-output and stray artifacts are ignored"
mkdir -p "$scratch/vendor/mil_spec/target/x"
echo "built" > "$scratch/vendor/mil_spec/target/x/lib.rlib"
echo "rej" > "$scratch/vendor/mil_spec/src/main.rs.rej"
echo "orig" > "$scratch/vendor/mil_spec/src/main.rs.orig"
assert_rc 0 "target/*.rej/*.orig do not trip the guard" \
  "$scratch/scripts/vendor-guard.sh" --verify

echo
if [ "$fails" -eq 0 ]; then echo "all TOOL-4 tests passed"; exit 0; else echo "$fails TOOL-4 test(s) failed"; exit 1; fi
