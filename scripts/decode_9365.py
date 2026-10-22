#!/usr/bin/env python3
# decode_9365.py <macho> — decode the first 0x9365 state-copy record's fields in
# a compiled ANE HWX Mach-O and print them as "dim0=D dim1=C stride=S region=R".
# Used by docs/spec/ane-port-limits-h17.spec.
import struct
import sys

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
    start, end = text_file_range(d)
    pos = None
    for i in range(start, min(end, len(d)) - 2, 2):
        if struct.unpack_from("<H", d, i)[0] == 0x9365:
            pos = i
            break
    if pos is None:
        print("no 0x9365 record", file=sys.stderr)
        sys.exit(1)
    dim1 = struct.unpack_from("<I", d, pos + 0x0A)[0]
    dim0 = struct.unpack_from("<I", d, pos + 0x0E)[0]
    stride = struct.unpack_from("<I", d, pos + 0x1C)[0]
    region = struct.unpack_from("<I", d, pos + 0x48)[0]
    print(f"dim0={dim0} dim1={dim1} stride={stride} region={region}")

if __name__ == "__main__":
    main()
