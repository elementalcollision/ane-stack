#!/usr/bin/env python3
# decode_copy_words.py <macho> [--last] [--diff OTHER.macho]
#
# Word-level view of the STATE-OUT copy records (family tags with the dim0 flag: 0x9265/0x9264/0x9365/0x9364),
# one line per record, in file order.  With --last the LAST family record of the file is shown instead (that is
# the state-out copy of a one-state program even when dim0 == 1, where the state-out tag carries no dim0 flag).
# Companion to decode_copy_records.py (framing, tag, header, rowbits) and docs/spec/ane-port-limits-h17.md sec. 6.
#
# All offsets below are from the 0x1041/0x1045 MARKER word (m), so they hold for every tag (the header is
# shorter by 4 bytes per absent presence flag, which shifts the TAG-relative offsets but not the MARKER-relative
# ones).  For the full 0x9365 tag the marker is at tag+0x3e.
#
#   flagw   u16 right after the 0x1342 tag that precedes the marker:  0x8000 | 0x08*[dim1 != 1] | 0x20*[dim0 != 1]
#           (| 0x04 when dim2 > 1);  0x0000 when dim0 == dim1 == 1.
#   pitch   u32: padded W-row pitch in bytes = 64 * ceil(d3 / 32)           (d2 == 1; absent when flagw == 0)
#           at m-0x10 when flagw & 0x28 == 0x28, else at m-0x0c.
#   slice   u32 at m-0x0c = pitch * dim1: present only when dim0 != 1 AND dim1 != 1 (flagw & 0x28 == 0x28).
#           (+0x32 in a 0x9365 record; the old "+0x33 flag byte" is its second byte.)
#   slice2  u32 at (core end - 8): a second copy of `slice` (same value whenever slice is present; = pitch when slice is elided).
#   form    "<u16 at m+2>/<u16 at m+4>": 803c/0142 = SHORT, 803e/0162 = LONG, 803e/0142 = computed-source LONG.
#   map     the u32 words from m+6 up to the 0x9052 tag, then '|', then the u32 at (0x9052 tag + 6); each shown as
#           1M (0x00100000), RB (rowbits << 16), 2RB (2*rowbits << 16), else hex.   SHORT: 1M,RB,RB,RB|RB
#           LONG (direct, not last): RB,1M,RB,RB,RB|2RB.
#   --diff  also print the tag-relative byte offsets (over the shorter core) at which the FIRST selected record of the two
#           files differ:  'diff: 0x0a 0x0e ...'.
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import decode_copy_records as D  # noqa: E402


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    last = "--last" in sys.argv
    if "--diff" in sys.argv:
        args = [args[0]]
    d = open(args[0], "rb").read()
    start, end = D.text_file_range(d)
    end = min(end, len(d))
    offs = [i for i in range(start, end - 2, 2) if D.u16(d, i) in D.FAMILY and D.u16(d, i - 2) == 0x8005]
    sel = offs[-1:] if last else [o for o in offs if D.u16(d, o) & 4]
    for i, o in enumerate(sel):
        r = D.decode(d, o, end)
        m = next(k for k in range(o + 0x1C, o + 0x80, 2) if D.u16(d, k) in (0x1041, 0x1045))
        t = max(k for k in range(o, m, 2) if D.u16(d, k) == 0x1342)
        flagw = D.u16(d, t + 2)
        both = (flagw & 0x28) == 0x28
        if r["dim2"] != 1 or flagw == 0:
            pitch = slc = slc2 = "-"
        else:
            pitch = D.u32(d, m - (0x10 if both else 0x0C))
            slc = D.u32(d, m - 0x0C) if both else "-"
            slc2 = D.u32(d, r["core_end"] - 8)
        p9052 = next(k for k in range(m, m + 0x40, 2) if D.u16(d, k) == 0x9052)
        rb = r["rowbits"]

        def lab(v):
            if v == 0x00100000:
                return "1M"
            if rb is not None and v == (rb << 16) & 0xFFFFFFFF:
                return "RB"
            if rb is not None and v == (2 * rb << 16) & 0xFFFFFFFF:
                return "2RB"
            return f"{v:#010x}"

        words = [D.u32(d, k) for k in range(m + 6, p9052 - 2 - 3, 4)]
        mp = ",".join(lab(v) for v in words) + "|" + lab(D.u32(d, p9052 + 6))
        if i == 0 and "--diff" in sys.argv:
            diff_main()
            return
        print(f"i={i} tag={r['tag']:#06x} dim0={r['dim0']} dim1={r['dim1']} flagw={flagw:04x} pitch={pitch} slice={slc} slice2={slc2} "
              f"form={D.u16(d, m + 2):04x}/{D.u16(d, m + 4):04x} map={mp}")


def first_record(path, last):
    d = open(path, "rb").read()
    start, end = D.text_file_range(d)
    end = min(end, len(d))
    offs = [i for i in range(start, end - 2, 2) if D.u16(d, i) in D.FAMILY and D.u16(d, i - 2) == 0x8005]
    sel = offs[-1:] if last else [o for o in offs if D.u16(d, o) & 4]
    o = sel[0]
    return d, o, D.decode(d, o, end)["core_end"]


def diff_main() -> None:
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    other = sys.argv[sys.argv.index("--diff") + 1]
    last = "--last" in sys.argv
    da, oa, ea = first_record(a[0], last)
    db, ob, eb = first_record(other, last)
    n = min(ea - oa, eb - ob)
    print("diff: " + " ".join(f"{k:#04x}" for k in range(n) if da[oa + k] != db[ob + k]))


if __name__ == "__main__":
    main()
