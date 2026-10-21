#!/usr/bin/env bash
# Manage the vendored upstream tree.
#
#   ./scripts/apply-patches.sh --rebuild   # reset vendor/mil_spec/ to pristine
#                                          # upstream + patches applied once,
#                                          # then regenerate the manifest
#   ./scripts/apply-patches.sh --check     # dry-run every patch, change nothing
#
# --rebuild is the authoritative way to (re)create vendor/mil_spec/: it clones
# pristine upstream at the pinned sha, applies patches in order exactly once,
# and asserts each patch appears exactly once in the result. Use it whenever
# you add a patch or doubt the tree's integrity. See docs/evidence/0006 for why.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname "$here")"
vendor="$root/vendor/mil_spec"
sha="20f097fb34969cd577342a4d7996fbf5464998c8"
url="https://github.com/savageAZfck/mil_spec.git"

shopt -s nullglob
patches=("$root"/patches/[0-9]*.patch)
[ ${#patches[@]} -gt 0 ] || { echo "no patches found" >&2; exit 1; }

mode="${1:-}"
case "$mode" in
  --check)
    # Verify the whole patch set applies, in order, to a PRISTINE clone. Testing
    # each patch independently against the working tree is wrong for stacked
    # patches (later patches assume earlier ones), which is exactly the case we
    # have. See docs/evidence/0006.
    work="$(mktemp -d)"
    trap 'rm -rf "$work"' EXIT
    git clone --quiet "$url" "$work/up"
    (cd "$work/up" && git checkout --quiet "$sha" && rm -rf .git)
    fail=0
    for p in "${patches[@]}"; do
      echo "==> $(basename "$p")"
      if patch -d "$work/up" -p1 --forward --silent -i "$p"; then
        echo "    applied"
      else
        echo "    CONFLICT"; fail=1
      fi
    done
    echo
    [ $fail -eq 0 ] && echo "all patches apply to pristine upstream, in order" \
                    || echo "conflicts present"
    exit $fail
    ;;
  --rebuild)
    echo "rebuilding vendor/mil_spec/ from pristine upstream + patches"
    work="$(mktemp -d)"
    trap 'rm -rf "$work"' EXIT
    git clone --quiet "$url" "$work/up"
    (cd "$work/up" && git checkout --quiet "$sha" && rm -rf .git)
    for p in "${patches[@]}"; do
      echo "==> $(basename "$p")"
      patch -d "$work/up" -p1 --forward -i "$p"
    done
    # assert no patch content appears twice (double-apply guard)
    if grep -c "write_state shape mismatch" "$work/up/src/ir.rs" 2>/dev/null | grep -qE '^[2-9]'; then
      echo "ERROR: patch 0001 content appears multiple times (double-apply)" >&2
      exit 1
    fi
    # preserve build cache across the rebuild
    rsync -a --delete --exclude target --exclude 'manifest.sha256' "$work/up/" "$vendor/"
    "$root/scripts/vendor-guard.sh" --generate
    echo
    echo "rebuilt. verify with: ./scripts/vendor-guard.sh --verify"
    echo "then run the test suite before committing."
    ;;
  *)
    echo "usage: $0 {--rebuild|--check}" >&2
    exit 2
    ;;
esac
