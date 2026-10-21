#!/usr/bin/env bash
# evidence-check.sh — re-execute evidence specs and assert the documented facts
# still hold. This is TEST-1: evidence that cannot drift from the code, because
# it is re-run, not re-read.
#
#   ./scripts/evidence-check.sh --all              # every *.spec in docs/evidence/
#   ./scripts/evidence-check.sh <spec> [spec...]   # specific specs
#   ./scripts/evidence-check.sh --list             # list specs and their items
#
# Spec format: docs/evidence/SPEC.md
#
# Exit 0 iff every assertion in every selected spec holds. Specs whose
# `require_cmd` tools are missing are reported as SKIP, not FAIL (TEST-2's
# hardware-conditional discipline), and do not affect the exit code unless
# --require-all is passed.

set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname "$here")"
cd "$root"

RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; DIM=$'\033[2m'; RST=$'\033[0m'

pass_count=0; fail_count=0; skip_count=0
require_all=false

run_spec() {
    local spec="$1" name
    name="$(basename "$spec")"
    local last_out="" last_rc=0 item_fail=0 skip=false
    local -a missing=()

    while IFS= read -r raw || [ -n "$raw" ]; do
        # strip full-line comments, then trim leading/trailing whitespace.
        # (do NOT strip inline `#`: want_out values may contain them.)
        case "$raw" in ''|\#*) continue ;; esac
        local line="${raw#"${raw%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [ -z "$line" ] && continue
        local cmd rest
        case "$line" in
            *" "*)
                cmd="${line%%[[:space:]]*}"
                rest="${line#"$cmd"}"
                # collapse leading whitespace on rest
                rest="${rest#"${rest%%[![:space:]]*}"}"
                ;;
            *)
                cmd="$line"; rest=""
                ;;
        esac
        case "$cmd" in
            require_cmd)
                if ! command -v "$rest" >/dev/null 2>&1; then
                    missing+=("$rest"); skip=true
                fi
                ;;
            require_file)
                if [ ! -e "$rest" ]; then
                    echo "  ${RED}FAIL${RST} $name: required file missing: $rest"
                    item_fail=1
                fi
                ;;
            run)
                if $skip; then continue; fi
                last_out="$(bash -c "$rest" 2>&1)"; last_rc=$?
                ;;
            want_rc)
                if $skip; then continue; fi
                if [ "$last_rc" != "$rest" ]; then
                    echo "  ${RED}FAIL${RST} $name: want_rc $rest, got $last_rc"
                    echo "       ${DIM}cmd output tail: $(echo "$last_out" | tail -1)${RST}"
                    item_fail=1
                fi
                ;;
            want_out)
                if $skip; then continue; fi
                if ! grep -qF -- "$rest" <<<"$last_out"; then
                    echo "  ${RED}FAIL${RST} $name: want_out substring not found: $rest"
                    echo "       ${DIM}output: $(echo "$last_out" | head -3 | tr '\n' ' ')${RST}"
                    item_fail=1
                fi
                ;;
            want_out_re)
                if $skip; then continue; fi
                if ! grep -qE -- "$rest" <<<"$last_out"; then
                    echo "  ${RED}FAIL${RST} $name: want_out_re no match: $rest"
                    echo "       ${DIM}output: $(echo "$last_out" | head -3 | tr '\n' ' ')${RST}"
                    item_fail=1
                fi
                ;;
            want_absent)
                if $skip; then continue; fi
                if grep -qF -- "$rest" <<<"$last_out"; then
                    echo "  ${RED}FAIL${RST} $name: want_absent substring present: $rest"
                    item_fail=1
                fi
                ;;
            setup)
                # Rebuild a prerequisite artifact so evidence is self-contained
                # and never depends on something that lived only in /tmp once.
                if $skip; then continue; fi
                if ! bash -c "$rest" >/dev/null 2>&1; then
                    echo "  ${RED}FAIL${RST} $name: setup failed: $rest"
                    item_fail=1
                fi
                ;;
            require_artifact)
                # A path the evidence needs; if absent and a prior setup didn't
                # make it, the item cannot be reproduced — FAIL, loudly.
                if $skip; then continue; fi
                if [ ! -e "$rest" ]; then
                    echo "  ${RED}FAIL${RST} $name: required artifact missing: $rest"
                    item_fail=1
                fi
                ;;
            *)
                echo "  ${RED}FAIL${RST} $name: unknown directive: $cmd"
                item_fail=1
                ;;
        esac
    done < "$spec"

    if $skip; then
        echo "  ${YEL}SKIP${RST} $name: missing tool(s): ${missing[*]}"
        skip_count=$((skip_count+1))
        $require_all && fail_count=$((fail_count+1))
    elif [ "$item_fail" -eq 0 ]; then
        echo "  ${GRN}PASS${RST} $name"
        pass_count=$((pass_count+1))
    else
        fail_count=$((fail_count+1))
    fi
}

# ---- arg parsing ----
mode="${1:-}"
case "$mode" in
    --list)
        ls "$root"/docs/evidence/*.spec 2>/dev/null | while read -r s; do basename "$s"; done
        exit 0
        ;;
    --all)
        shift
        [ "${1:-}" = "--require-all" ] && require_all=true
        shopt -s nullglob
        specs=("$root"/docs/evidence/*.spec)
        [ ${#specs[@]} -gt 0 ] || { echo "no specs found in docs/evidence/" >&2; exit 1; }
        ;;
    --require-all)
        require_all=true; shift
        specs=("$@")
        ;;
    "" )
        echo "usage: $0 {--all [--require-all]|--require-all <spec...>|<spec...>}" >&2
        exit 2
        ;;
    *)
        specs=("$@")
        ;;
esac

echo "evidence-check — re-running $(echo "${specs[@]}" | wc -w | tr -d ' ') spec(s)"
for spec in "${specs[@]}"; do
    [ -f "$spec" ] || { echo "  ${RED}FAIL${RST} no such spec: $spec"; fail_count=$((fail_count+1)); continue; }
    run_spec "$spec"
done

echo
echo "pass: $pass_count   fail: $fail_count   skip: $skip_count"
[ "$fail_count" -eq 0 ]
