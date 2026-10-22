#!/usr/bin/env bash
# evidence-harness.sh — regression test for scripts/evidence-check.sh semantics.
#
#   bash tests/evidence-harness.sh [path/to/evidence-check.sh]   # semantics (default: repo harness)
#   bash tests/evidence-harness.sh --lint <spec>...               # spec hygiene: run lines lacking want_rc
#
# Uses a FAKE milc (no hardware, no cargo) and scratch specs in a mktemp root,
# so it never touches the real tree, /tmp/pl_* or any shared /tmp artifact.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "${1:-}" = "--lint" ]; then
  shift
  offenders="$(for f in "$@"; do
    awk -v f="$f" '
      /^run[[:space:]]/     { if (pending) print f ":" pl ": run without want_rc"; pending = 1; pl = NR; next }
      /^want_rc[[:space:]]/ { pending = 0 }
      END { if (pending) print f ":" pl ": run without want_rc" }' "$f"
  done)"
  if [ -z "$offenders" ]; then echo "lint: every run line has a want_rc"; exit 0; fi
  echo "$offenders"; exit 1
fi

harness="${1:-$here/../scripts/evidence-check.sh}"
harness="$(cd "$(dirname "$harness")" && pwd)/$(basename "$harness")"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
root="$work/root"
mkdir -p "$root/scripts" "$root/docs/evidence" "$root/docs/spec" "$root/vendor/mil_spec/target/release"
cp "$harness" "$root/scripts/evidence-check.sh"
cat > "$root/vendor/mil_spec/target/release/milc" <<'EOF'
#!/usr/bin/env bash
# FAKE milc: emulates the output text and exit codes of crates/milc/src/main.rs.
case "$*" in
  *over.mil*) echo "milc ane run: step 0: execute_sync → 11 ... Program Inference error" >&2; exit 1 ;;
  *ok.mil*)   echo "step 0: 1.2ms"; echo "z: 64/64 nonzero"; exit 0 ;;
  *kind*)     echo 'milc run: infer manifest: kind is not "milshards"' >&2; exit 1 ;;
  *)          exit 2 ;;
esac
EOF
chmod +x "$root/vendor/mil_spec/target/release/milc"

fails=0
check() { # check <desc> <want-rc> <needle-or-empty> ; uses $rc $out
  local desc="$1" want="$2" needle="$3"
  if [ "$rc" != "$want" ]; then echo "  FAIL — $desc (harness rc=$rc, want $want)"; fails=$((fails+1)); return; fi
  if [ -n "$needle" ] && ! grep -qF -- "$needle" <<<"$out"; then echo "  FAIL — $desc (no '$needle' in output)"; fails=$((fails+1)); return; fi
  echo "  ok   — $desc"
}
spec() { # spec <name> <body>   (writes docs/evidence/<name>.spec and runs it alone)
  printf '%s\n' "$2" > "$root/docs/evidence/$1.spec"
  out="$(cd "$root" && bash scripts/evidence-check.sh "docs/evidence/$1.spec" 2>&1)"; rc=$?
}

echo "evidence-harness semantics — harness: $harness"

spec control_pass 'run vendor/mil_spec/target/release/milc ane run ok.mil --steps 1 2>&1
want_rc 0
want_out_re ^step 0: [0-9]'
check "control: real success passes" 0 "PASS"

spec pass_side_on_fail 'run vendor/mil_spec/target/release/milc ane run over.mil --steps 1 2>&1
want_rc 0
want_out_re ^step 0: [0-9]'
check "anchored pass-side fails when execution fails" 1 "want_rc 0, got 1"

spec fail_side_rc1 'run vendor/mil_spec/target/release/milc ane run over.mil --steps 1 2>&1
want_rc 1
want_out Inference error'
check "fail-side with rc 1 and substring passes" 0 "PASS"

spec fail_beats_skip 'run echo hello
want_out goodbye
require_cmd no_such_tool_zz_qq'
check "a FAIL is never reported as SKIP (exit must be 1)" 1 "FAIL"

spec stdin_not_shared 'run echo before
run cat
want_rc 0
want_out MARKER-THAT-IS-NOT-PRESENT-ANYWHERE'
check "run lines do not consume later assertions" 1 "MARKER-THAT-IS-NOT-PRESENT"

spec hw_gate_skips 'require_hw /usr/bin/false
run echo never-runs
want_out never-runs'
check "require_hw probe failure SKIPs (exit 0)" 0 "SKIP"

mkdir -p "$root/docs/spec"; printf 'run echo hi\nwant_out hi\n' > "$root/docs/spec/dirspec.spec"
out="$(cd "$root" && bash scripts/evidence-check.sh --all 2>&1)"
if grep -qF "dirspec.spec" <<<"$out"; then echo "  ok   — --all includes docs/spec/*.spec"; else echo "  FAIL — --all does not include docs/spec/*.spec"; fails=$((fails+1)); fi

out="$(cd "$root" && bash scripts/evidence-check.sh --require-all 2>&1)"; rc=$?
check "an empty selection is an error, not a green run" 2 ""

if [ "$fails" -eq 0 ]; then echo "all evidence-harness tests passed"; exit 0; fi
echo "$fails evidence-harness test(s) failed"; exit 1
