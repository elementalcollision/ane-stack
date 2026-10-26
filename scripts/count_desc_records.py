#!/usr/bin/env python3
# count_desc_records.py <macho> [tag] — count occurrences of a 16-bit record tag
# (default 0x9344) at 2-byte alignment in the __TEXT.__text section of a compiled
# ANE HWX Mach-O. Prints "0xTTTT records: N". Used by
# docs/spec/ane-port-limits-h17.spec. 0x9344 / 0x934a / 0x9442 are 12-byte buffer
# bindings (a task's primary source / further sources / destination, see
# decode_slot_ordinals.py); 0x9344 is NOT a state table and does not cap at 54.
# Anchor the count when asserting it ("records: 2$"), since "records: 2" also
# matches 20-29.
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
                    # section_64: sectname[16] segname[16] addr@32 size@40 offset@48
                    size = struct.unpack_from("<Q", d, so + 40)[0]
                    off = struct.unpack_from("<I", d, so + 48)[0]
                    if sect == "__text":
                        return off, off + size
        lc += cmdsz
    raise SystemExit("no __TEXT.__text section")

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
