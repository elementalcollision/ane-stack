#!/usr/bin/env python3
# decode_slot_word.py <macho> — decode the 0x9344 descriptor-list records' slot
# words in a compiled ANE HWX Mach-O. Prints "records=R slots=S fullcopies=F".
# Used by docs/spec/ane-port-limits-h17.spec to assert the slot-word decode:
#   word = (slot_index << 8) | (copy << 7)
import struct
import sys
from collections import defaultdict

def text_file_range(d: bytes):
    ncmds = struct.unpack_from("<I", d, 0x10)[0]
    lc = 0x20
    for _ in range(ncmds):
        cmd, cmdsz = struct.unpack_from("<II", d, lc)
        if cmd == 0x19:
            seg = d[lc + 8 : lc + 24].split(b"\0")[0].decode("latin1")
            nsects = struct.unpack_from("<I", d, lc + 64)[0]
            if seg == "__TEXT":
                for s in range(nsects):
                    so = lc + 72 + s * 80
                    sect = d[so : so + 16].split(b"\0")[0].decode("latin1")
                    size = struct.unpack_from("<Q", d, so + 32)[0]
                    off = struct.unpack_from("<I", d, so + 40)[0]
                    if sect == "__text":
                        return off, off + size
        lc += cmdsz
    return 0x50C0, len(d)

def main() -> None:
    d = open(sys.argv[1], "rb").read()
    if d[:4] != (0xBEEFFACE).to_bytes(4, "little"):
        print("not an HWX Mach-O", file=sys.stderr)
        sys.exit(2)
    start, end = text_file_range(d)
    byslot = defaultdict(set)
    nrec = 0
    for i in range(start, min(end, len(d)) - 2, 2):
        if struct.unpack_from("<H", d, i)[0] == 0x9344:
            w = struct.unpack_from("<H", d, i + 2)[0]
            byslot[(w >> 8) & 0xFF].add((w >> 7) & 1)
            nrec += 1
    full = sum(1 for v in byslot.values() if v == {0, 1})
    print(f"records={nrec} slots={len(byslot)} fullcopies={full}")

if __name__ == "__main__":
    main()
