#!/usr/bin/env python3
# decode_block_trailers.py <macho> — frame the __TEXT.__text of a compiled ANE HWX Mach-O into
# BLOCKS and decode each block's descriptor TRAILER.
#
# BLOCK framing (verified on 124 programs / 2771 blocks, h17 and h16g):
#   __text starts with a 0x10-byte preamble; blocks follow.  A block starts with
#   [u16 idx][u16 size], idx = 0,1,2,... and size = the block length in u32 words INCLUDING this
#   header word.  The next block header is at align16(start + 4*size).  The chain ends exactly
#   at the end of __text.
# TRAILER: every block ends with a run of flat, consecutive records, in this order, any subset:
#   [0x9344 12B][0x934a 12B]*[0x9442 12B][0x1340 8B][0x1341 8B][0x1440 8B]
#   (12B = [tag u16][bar_word u16][offset u32][0 u32]; 8B = [tag u16][0x2200 u16][flags u32]).
#   The run ends at the block end (before the pad to 16 bytes).
# Output (3 lines):
#   blocks=B chain_ok=1 trailers: 53x[9442,1440] 53x[9344,9442,1340,1440] 1x[9344,934a,934a,9442,1340,1341,1440]
#   first9344: block=0 9344@+0x00 934a@+0x0c ... 1440@+0x40 end@+0x48 nexthdr@+0x4c   (offsets from that 0x9344 tag)
#   nextblock: idx=1 size=39 prewords=1,30001,10001,1,1,4 frame=0x9361
#     prewords = the u32 words from nextblock+0x1c up to its first 0x8005 frame word.
# Exit 0, or 1 if the chain/trailer invariants do not hold, 2 for a non-HWX file.
import struct
import sys
from collections import Counter

T12 = {0x9344, 0x934A, 0x9442}
T8 = {0x1340, 0x1341, 0x1440}
ORDER = [0x9344, 0x934A, 0x9442, 0x1340, 0x1341, 0x1440]


def text_range(d: bytes):
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
                    if d[so : so + 16].split(b"\0")[0] == b"__text":
                        return (struct.unpack_from("<I", d, so + 48)[0],
                                struct.unpack_from("<I", d, so + 48)[0] + struct.unpack_from("<Q", d, so + 40)[0])
        lc += cmdsz
    raise SystemExit("no __TEXT.__text section")


def u16(t, o):
    return struct.unpack_from("<H", t, o)[0]


def u32(t, o):
    return struct.unpack_from("<I", t, o)[0]


def blocks(t):
    out, o = [], 0x10
    while o + 4 <= len(t):
        idx, sz = struct.unpack_from("<HH", t, o)
        if sz == 0:
            break
        out.append((idx, o, o + 4 * sz))
        o = (o + 4 * sz + 15) & ~15
    return out


def trailer(t, start, end):
    pos, items = end, []
    while pos - 8 >= start:
        if u16(t, pos - 8) in T8 and u16(t, pos - 6) == 0x2200:
            items.append((u16(t, pos - 8), pos - 8))
            pos -= 8
        elif pos - 12 >= start and u16(t, pos - 12) in T12:
            items.append((u16(t, pos - 12), pos - 12))
            pos -= 12
        else:
            break
    return items[::-1]


def main() -> None:
    d = open(sys.argv[1], "rb").read()
    if d[:4] != (0xBEEFFACE).to_bytes(4, "little"):
        print("not an HWX Mach-O", file=sys.stderr)
        sys.exit(2)
    s, e = text_range(d)
    t = d[s:e]
    bl = blocks(t)
    ok = bool(bl) and [b[0] for b in bl] == list(range(len(bl))) and bl[-1][2] == len(t)
    seqs, first = Counter(), None
    for i, (idx, o, end) in enumerate(bl):
        tr = trailer(t, o, end)
        seq = tuple(x for x, _ in tr)
        seqs[seq] += 1
        order = [ORDER.index(x) for x in seq]
        if order != sorted(order):
            ok = False
        raw = [u16(t, x) for x in range(o, end - 1, 2)]
        stray = sum(1 for x in range(o, end - 1, 2) if u16(t, x) in (T12 | T8)) - len(tr)
        if stray:
            ok = False  # a trailer tag outside the trailer run
        if first is None and 0x9344 in seq:
            first = (i, tr, end)
    print(f"blocks={len(bl)} chain_ok={int(ok)} trailers: "
          + " ".join(f"{c}x[{','.join(f'{x:04x}' for x in sq)}]" for sq, c in seqs.most_common()))
    if first:
        i, tr, end = first
        b = next(off for x, off in tr if x == 0x9344)
        nh = (end + 15) & ~15
        print(f"first9344: block={i} " + " ".join(f"{x:04x}@+0x{off - b:02x}" for x, off in tr if off >= b)
              + f" end@+0x{end - b:02x} nexthdr@+0x{nh - b:02x}")
        if i + 1 < len(bl):
            idx, o, nend = bl[i + 1]
            f = next((x for x in range(o + 4, nend - 2, 2) if u16(t, x) == 0x8005), None)
            if f is not None:
                words = ",".join(f"{u32(t, x):x}" for x in range(o + 0x1C, f, 4))
                print(f"nextblock: idx={idx} size={(nend - o) // 4} prewords={words} frame=0x{u16(t, f + 2):04x}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
