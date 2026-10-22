#!/usr/bin/env python3
# count_desc_records.py <macho> — count the 0x9344 descriptor-list records in a
# compiled ANE HWX Mach-O, scanning only the __text section (where descriptor
# records live). Prints "0x9344 records: N". Used by
# docs/spec/ane-port-limits-h17.spec to assert the descriptor-table economy
# (N+1 records for N states; the table caps at 54).
import struct
import sys

def text_file_range(d: bytes):
    """Return (start, end) file offsets of the __TEXT.__text section."""
    ncmds = struct.unpack_from("<I", d, 0x10)[0]
    lc = 0x20
    for _ in range(ncmds):
        cmd, cmdsz = struct.unpack_from("<II", d, lc)
        if cmd == 0x19:  # LC_SEGMENT_64
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
    return 0x50C0, len(d)  # fallback: the observed __text offset

def main() -> None:
    d = open(sys.argv[1], "rb").read()
    if d[:4] != (0xBEEFFACE).to_bytes(4, "little"):
        print("not an HWX Mach-O", file=sys.stderr)
        sys.exit(2)
    tag = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x9344
    start, end = text_file_range(d)
    c = sum(
        1
        for i in range(start, min(end, len(d)) - 2, 2)
        if struct.unpack_from("<H", d, i)[0] == tag
    )
    print(f"0x{tag:04x} records: {c}")

if __name__ == "__main__":
    main()
