#!/usr/bin/env python3
# hwx_layout.py <macho> — print the segment/section budget of a compiled ANE HWX
# Mach-O as one stable line:
#   segments=S fvmlib=F fvmlib_data=D fvmlib_const=C data_sections=Ds const_sections=Cs kern=K
# segments = every LC_SEGMENT_64 (incl. __PAGEZERO and __TEXT); fvmlib = the
# __FVMLIB segments (one BAR id each); fvmlib_data / fvmlib_const = how many of
# those carry a __data / __const section; data_sections / const_sections = the
# section totals (states + exposed state updates + plain outputs; declared plain
# inputs); kern = the __KERN_* segments
# (lookup-table kernels for sigmoid/tanh/softmax/...; shed when the budget needs
# the slot). section_64 layout:
# sectname[16] segname[16] addr@32 size@40 offset@48.
# Used by docs/spec/ane-port-limits-h17.spec for the state<> BAR-pool model: the
# compiler budgets 57 LC_SEGMENT_64 (55 __FVMLIB/__KERN_* = 55 BAR ids, + __PAGEZERO
# + __TEXT).
# When the unpacked layout would exceed it, it sheds __KERN_* and packs every
# non-state __data section into one shared segment and every __const section into
# another; each state<> surface keeps a segment of its own, so N states need
# N+4 segments (N+3 with no data section besides the surfaces; N+3 with no plain
# input either, which is why 54 states compile when the program has no input).
import struct
import sys

def segments(d: bytes):
    ncmds = struct.unpack_from("<I", d, 0x10)[0]
    lc = 0x20
    out = []
    for _ in range(ncmds):
        cmd, cmdsz = struct.unpack_from("<II", d, lc)
        if cmd == 0x19:  # LC_SEGMENT_64
            name = d[lc + 8 : lc + 24].split(b"\0")[0].decode("latin1")
            nsects = struct.unpack_from("<I", d, lc + 64)[0]
            sects = []
            for s in range(nsects):
                so = lc + 72 + s * 80
                sects.append(d[so : so + 16].split(b"\0")[0].decode("latin1"))
            out.append((name, sects))
        lc += cmdsz
    return out

def main() -> None:
    d = open(sys.argv[1], "rb").read()
    if d[:4] != (0xBEEFFACE).to_bytes(4, "little"):
        print("not an HWX Mach-O", file=sys.stderr)
        sys.exit(2)
    segs = segments(d)
    fv = [s for n, s in segs if n == "__FVMLIB"]
    print(
        f"segments={len(segs)} fvmlib={len(fv)}"
        f" fvmlib_data={sum(1 for s in fv if '__data' in s)}"
        f" fvmlib_const={sum(1 for s in fv if '__const' in s)}"
        f" data_sections={sum(s.count('__data') for s in fv)}"
        f" const_sections={sum(s.count('__const') for s in fv)}"
        f" kern={sum(1 for n, _ in segs if n.startswith('__KERN'))}"
    )

if __name__ == "__main__":
    main()
