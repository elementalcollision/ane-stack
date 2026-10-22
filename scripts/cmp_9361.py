#!/usr/bin/env python3
# cmp_9361.py <macho_a> <macho_b> — assert the 0x9361 (read-side state-copy)
# record body is byte-identical across two compiled programs. Used by
# docs/spec/ane-port-limits-h17.spec to assert the read/write asymmetry:
# the read record is a fixed template; only the write record (0x9365) varies.
import struct
import sys

def body(path: str, tag: int, length: int = 0x52) -> bytes:
    d = open(path, "rb").read()
    for i in range(0x50C0, len(d) - 2, 2):
        if struct.unpack_from("<H", d, i)[0] == tag:
            return d[i : i + length]
    raise SystemExit(f"no 0x{tag:x} record in {path}")

def main() -> None:
    a = body(sys.argv[1], 0x9361)
    b = body(sys.argv[2], 0x9361)
    if a != b:
        raise SystemExit("0x9361 bodies differ across programs")
    print("0x9361 byte-identical across shapes: True")

if __name__ == "__main__":
    main()
