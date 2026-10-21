#!/usr/bin/env bash
# Apply our patch set to the vendored upstream tree, in order.
#
#   ./scripts/apply-patches.sh          # apply (idempotent)
#   ./scripts/apply-patches.sh --check  # dry-run every patch, change nothing
#
# Re-vendoring resets vendor/mil_spec/ to pristine; this restores our diff.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname "$here")"
vendor="$root/vendor/mil_spec"
check=false
[ "${1:-}" = "--check" ] && check=true

[ -d "$vendor" ] || { echo "no vendored tree at $vendor" >&2; exit 1; }

shopt -s nullglob
patches=("$root"/patches/[0-9]*.patch)
[ ${#patches[@]} -gt 0 ] || { echo "no patches found" >&2; exit 1; }

fail=0
for p in "${patches[@]}"; do
  echo "==> $(basename "$p")"
  if $check; then
    if patch -d "$vendor" -p1 --dry-run --silent -i "$p" >/dev/null 2>&1; then
      echo "    would apply"
    elif patch -d "$vendor" -p1 --dry-run --silent -R -i "$p" >/dev/null 2>&1; then
      echo "    already applied"
    else
      echo "    CONFLICT"; fail=1
    fi
  else
    patch -d "$vendor" -p1 --forward -i "$p" >/dev/null 2>&1 \
      && echo "    applied" \
      || echo "    already applied"
    rm -f "$vendor"/*.rej "$vendor"/*/*.rej "$vendor"/*/*/*.rej 2>/dev/null || true
  fi
done

$check && { echo; [ $fail -eq 0 ] && echo "all patches OK" || echo "conflicts present"; exit $fail; }
echo; echo "done — now run: cargo test --workspace"
