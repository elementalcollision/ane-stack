#!/usr/bin/env bash
# vendor-guard.sh — assert vendor/mil_spec/ matches its recorded baseline.
#
# The failure this guards against: someone edits a file under vendor/mil_spec/
# by hand, or drops in new vendored code, without producing a numbered patch in
# patches/ and an entry in PATCHES.md / FORK.md. That is the #1 way a fork rots.
#
#   ./scripts/vendor-guard.sh --generate   # (re)build the baseline manifest
#   ./scripts/vendor-guard.sh --verify     # fail if the tree has drifted
#   ./scripts/vendor-guard.sh --status     # human-readable drift report
#
# The manifest lives at vendor/manifest.sha256 and is checked in. Regenerate it
# ONLY as part of applying or re-vendoring patches — never to silence a drift.
#
# Exit codes: 0 = clean / generated; 1 = drift or missing manifest; 2 = usage.

set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname "$here")"
vendor="$root/vendor/mil_spec"
manifest="$root/vendor/manifest.sha256"

sha256() {
  # Stable SHA-256 of a file's bytes; sha256sum on Linux, shasum on macOS.
  if command -v sha256sum >/dev/null 2>&1; then sha256sum -- "$1"; else shasum -a 256 -- "$1"; fi
}

hash_tree() {
  # Print "<sha256>  <relpath>" for every file under vendor/mil_spec/, excluding
  # build output and transient editor/patch artifacts, sorted by path.
  [ -d "$vendor" ] || { echo "no vendored tree at $vendor" >&2; exit 2; }
  (
    cd "$vendor"
    find . -type f \
      -not -path './target/*' \
      -not -name '*.rej' \
      -not -name '*.orig' \
      -not -name '.DS_Store' \
      -print0 | LC_ALL=C sort -z |
      while IFS= read -r -d '' f; do
        # normalise "./x" -> "x"
        printf '%s  %s\n' "$(sha256 "$f" | awk '{print $1}')" "${f#./}"
      done
  )
}

mode="${1:-}"
case "$mode" in
  --generate)
    [ -d "$vendor" ] || { echo "no vendored tree at $vendor" >&2; exit 2; }
    hash_tree > "$manifest"
    n=$(wc -l < "$manifest" | tr -d ' ')
    echo "wrote $manifest ($n entries)"
    echo "commit this together with the patches it represents."
    ;;
  --verify)
    if [ ! -f "$manifest" ]; then
      echo "ERROR: no manifest at $manifest" >&2
      echo "run: scripts/vendor-guard.sh --generate" >&2
      exit 1
    fi
    tmp="$(mktemp)"
    trap 'rm -f "$tmp"' EXIT
    hash_tree > "$tmp"
    if diff -q "$manifest" "$tmp" >/dev/null 2>&1; then
      echo "OK: vendor tree matches baseline ($(wc -l < "$manifest" | tr -d ' ') files)"
      exit 0
    fi
    echo "DRIFT detected in vendor/mil_spec/:" >&2
    diff "$manifest" "$tmp" | grep -E '^[<>]' | sed 's/^/  /' | head -50 >&2
    echo "" >&2
    echo "If this is intentional, it must come from a numbered patch:" >&2
    echo "  1. record it in PATCHES.md and patches/00NN-<name>.patch" >&2
    echo "  2. scripts/vendor-guard.sh --generate" >&2
    echo "  3. commit the patch AND the regenerated manifest together" >&2
    echo "If not intentional: git checkout -- vendor/mil_spec/" >&2
    exit 1
    ;;
  --status)
    if [ ! -f "$manifest" ]; then echo "no manifest; nothing to compare" >&2; exit 1; fi
    tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT
    hash_tree > "$tmp"
    diff "$manifest" "$tmp" | grep -E '^[<>]' | sed 's/^/  /' || echo "clean"
    ;;
  *)
    echo "usage: $0 {--generate|--verify|--status}" >&2
    exit 2
    ;;
esac
