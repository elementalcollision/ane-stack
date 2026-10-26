#!/usr/bin/env python3
# spec_to_json.py [--check FILE] [SPEC] — export an evidence spec as a structured
# list of datapoints: one item per `run` line, with its section, the comment block
# above it, the command, and every want_* expectation that follows it.
#
#   python3 scripts/spec_to_json.py                     # docs/spec/ane-port-limits-h17.spec -> stdout
#   python3 scripts/spec_to_json.py --check FILE        # exit 1 if FILE is stale
#
# The published copy lives at docs/data/ane-h17-2026-10-22/spec_datapoints.json.
# CI runs --check against it, so the public index cannot drift from the spec the
# hardware run asserts. No hardware is needed to export or check.
import hashlib
import json
import re
import sys

DEFAULT = "docs/spec/ane-port-limits-h17.spec"
SECTION = re.compile(r"^# (\d+)\. (.+)$")


def export(path: str) -> dict:
    raw = open(path, "rb").read()
    lines = raw.decode("utf-8").splitlines()
    items, requires, comment, section = [], [], [], None
    cur, banner = None, False
    for ln in lines:
        s = ln.strip()
        if not s:
            comment = [] if cur is None else comment
            continue
        if s.startswith("#"):
            m = SECTION.match(s)
            if m:
                section = {"n": int(m.group(1)), "title": m.group(2).strip()}
                comment, banner = [], True
            elif set(s) <= set("# ="):
                banner = False  # a ==== rule closes the section banner
            elif banner:
                section["title"] += " " + s.lstrip("#").strip()
            else:
                comment.append(s.lstrip("#").strip())
            continue
        cmd, _, rest = s.partition(" ")
        rest = rest.strip()
        if cmd in ("require_cmd", "require_file", "require_hw", "setup", "require_artifact"):
            requires.append({"kind": cmd, "value": rest})
        elif cmd == "run":
            cur = {"index": len(items), "section": section, "comment": " ".join(comment),
                   "run": rest, "wants": []}
            items.append(cur)
            comment = []
        elif cmd.startswith("want_") and cur is not None:
            cur["wants"].append({"kind": cmd, "value": rest})
        if cmd != "run" and not cmd.startswith("want_"):
            cur = None
    return {
        "source": path,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "probes": len(items),
        "assertions": sum(len(i["wants"]) for i in items),
        "requires": requires,
        "items": items,
    }


def main() -> None:
    args = sys.argv[1:]
    check = None
    if args[:1] == ["--check"]:
        check, args = args[1], args[2:]
    out = json.dumps(export(args[0] if args else DEFAULT), indent=1, ensure_ascii=False) + "\n"
    if check is None:
        sys.stdout.write(out)
        return
    if open(check, encoding="utf-8").read() != out:
        print(f"stale: {check} differs from the spec; regenerate with scripts/spec_to_json.py", file=sys.stderr)
        sys.exit(1)
    print(f"ok: {check} matches the spec")


if __name__ == "__main__":
    main()
