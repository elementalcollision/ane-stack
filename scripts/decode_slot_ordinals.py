#!/usr/bin/env python3
# decode_slot_ordinals.py <macho> — decode the buffer-binding records of a
# compiled ANE HWX Mach-O. Every 0x9344 / 0x934a / 0x9442 record is 12 bytes:
#   [tag u16][bar_word u16][offset u32][0 u32]
#   bar_word = (0x46 + ordinal) << 7        (== 0x2300 + 0x80*ordinal)
#   offset   = section.addr - segment.vmaddr of a section inside that segment
# where ordinal is the 0-based index of the target __FVMLIB segment in
# LC_SEGMENT_64 order (__PAGEZERO excluded). 0x9344 = a task's primary source,
# 0x934a = further sources, 0x9442 = the destination.
# Prints one line:
#   records=R bars=B max_ordinal=M input_ordinal=I format_ok=1
# records = number of 0x9344 records; bars = distinct ordinals referenced by
# any of the three tags; input_ordinal = the ordinal every 0x934a record
# addresses (-1 if there are none or they differ); format_ok=0 if any record
# violates the layout above. Used by docs/spec/ane-port-limits-h17.spec.
import struct
import sys

def parse(d: bytes):
    ncmds = struct.unpack_from("<I", d, 0x10)[0]
    lc = 0x20
    fv, text = [], None
    for _ in range(ncmds):
        cmd, cmdsz = struct.unpack_from("<II", d, lc)
        if cmd == 0x19:
            seg = d[lc + 8 : lc + 24].split(b"\0")[0].decode("latin1")
            vmaddr = struct.unpack_from("<Q", d, lc + 24)[0]
            nsects = struct.unpack_from("<I", d, lc + 64)[0]
            sects = []
            for s in range(nsects):
                so = lc + 72 + s * 80
                sects.append(
                    (d[so : so + 16].split(b"\0")[0].decode("latin1"),
                     struct.unpack_from("<Q", d, so + 32)[0],
                     struct.unpack_from("<Q", d, so + 40)[0],
                     struct.unpack_from("<I", d, so + 48)[0])
                )
            if seg == "__FVMLIB":
                fv.append((vmaddr, {a - vmaddr for _, a, _, _ in sects}))
            if seg == "__TEXT":
                for n, _, size, off in sects:
                    if n == "__text":
                        text = (off, off + size)
        lc += cmdsz
    if text is None:
        raise SystemExit("no __TEXT.__text section")
    return fv, text

def main() -> None:
    d = open(sys.argv[1], "rb").read()
    if d[:4] != (0xBEEFFACE).to_bytes(4, "little"):
        print("not an HWX Mach-O", file=sys.stderr)
        sys.exit(2)
    fv, (start, end) = parse(d)
    n9344 = 0
    bars, in_ord = set(), set()
    ok, mx = 1, -1
    for i in range(start, min(end, len(d)) - 12, 2):
        tag = struct.unpack_from("<H", d, i)[0]
        if tag not in (0x9344, 0x934A, 0x9442):
            continue
        w, off, z = struct.unpack_from("<HII", d, i + 2)
        k = (w >> 7) - 0x46
        if w & 0x7F or k < 0 or k >= len(fv) or z != 0 or off not in fv[k][1]:
            ok = 0
            continue
        bars.add(k)
        mx = max(mx, k)
        if tag == 0x9344:
            n9344 += 1
        if tag == 0x934A:
            in_ord.add(k)
    inp = next(iter(in_ord)) if len(in_ord) == 1 else -1
    print(f"records={n9344} bars={len(bars)} max_ordinal={mx} input_ordinal={inp} format_ok={ok}")

if __name__ == "__main__":
    main()
