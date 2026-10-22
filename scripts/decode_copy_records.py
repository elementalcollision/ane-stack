#!/usr/bin/env python3
# decode_copy_records.py <macho> [--reads] [--digest] [--tags]
#
# Decode EVERY state-copy record in a compiled ANE HWX Mach-O (h17 and h16g).
#
# FRAMING.  The records live in __TEXT.__text; each starts with the framing word
# 0x8005 followed by a tag 0x9[23]6[0145] (eight values: 0x9260/61/64/65 and
# 0x9360/61/64/65).  The low bits of the tag are presence flags of an
# elided-default field list:
#     0x0001  dim1 field present    (absent  <=> dim1 == 16)
#     0x0004  dim0 field present    (absent  <=> dim0 == 1)
#     0x0100  stride word present   (absent  <=> dim1 == 1, i.e. stride word 0)
# so  tag = 0x9261 + 0x100*(dim1!=1) + 4*(dim0!=1) - (dim1==16).
#
# HEADER (byte offsets from the tag word; every field a LE u32 at 2-byte
# alignment): +0x02 dim3, +0x06 dim2, then dim1 (if flagged), then dim0 (if
# flagged), then the constant 0x14000, then dim2 again; the stride word sits
# 0x0a bytes after the 0x14000 word.  With dim2 = dim3 = 1 (every shape the
# repo generators emit) stride = 8*min(ceil(log2 dim1), 4).
#
# STATE-OUT records (dim0 flag set: 0x9265/0x9264/0x9365/0x9364) copy the full
# [dim0,dim1] state-update tensor to its program-output port; there is one per
# update tensor that is returned.  The layout is chosen by the word after the
# 0x1041 marker: SHORT (0x803c) or LONG (0x803e, 4 bytes longer).
# rowbits = the u16 that appears three times just before the 0x9052 tag
# (= 16*dim1 mod 2^16 for dim2 = dim3 = 1); region = rowbits << 16
# (= dim1 MiB mod 4 GiB), what the old decode_9365.py read at +0x48 of the
# first record (that offset holds 1 MiB in the LONG layout).
#
# UPDATE-ROW records (--reads; dim0 flag clear: 0x9261/0x9260/0x9361/0x9360)
# copy the [1,dim1] update row into the state.  In dim0 == 1 programs the
# state-out copies also carry these tags (their dim0 field is elided).  Forms,
# by marker flag word: compact (0x1045 0x9800), first (0x1041 0x8004; 0x0000
# when dim1 == 1; first update-row of a program whose update source is a plain
# input), short (0x1041 0x803c) and long (0x1041 0x803e).  cost = the u16 after
# the 0x0038 word of the embedded 0x9442 child of a compact update-row
# = floor(dim0*dim1*2 / K), K = 450 on h17 (534 on h16g).
#
# OUTPUT (default = state-out records):
#   i=0 form=long dim0=4 dim1=4 stride=16 region=4194304 tag=0x9365 rowbits=64 dim2=1 dim3=1
#   summary: records=53 long=52 short=1 dim0=4 dim1=4 stride=16 uniform=yes region=4194304
# OUTPUT (--reads):
#   i=1 kind=read form=compact dim1=4 stride=16 tag=0x9361 rowbits=64 slot=0x2400 cost=0 dim2=1 dim3=1
#   summary: records=3 kind=read compact=2 first=0 short=1 long=0 dim1=4 stride=16 uniform=yes
# --digest appends core=<md5 of tag..end-of-core> to every line.
# --tags prints only the per-tag record counts:  tags: 0x9361=3 0x9365=4  (or 'tags: none').
# Exit 0 normally, 1 when no record of the requested kind exists, 2 for a non-HWX file.
import hashlib
import struct
import sys

FAMILY = {0x9260, 0x9261, 0x9264, 0x9265, 0x9360, 0x9361, 0x9364, 0x9365}


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


def u16(d, o):
    return struct.unpack_from("<H", d, o)[0]


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def decode(d: bytes, o: int, end: int):
    tag = u16(d, o)
    r = {"tag": tag, "off": o}
    r["dim3"] = u32(d, o + 0x02)
    r["dim2"] = u32(d, o + 0x06)
    p = 0x0A
    if tag & 1:
        r["dim1"] = u32(d, o + p)
        p += 4
    else:
        r["dim1"] = 16
    if tag & 4:
        r["dim0"] = u32(d, o + p)
        p += 4
    else:
        r["dim0"] = 1
    r["k14000"] = u32(d, o + p)
    r["stride"] = u32(d, o + p + 0x0A) if tag & 0x100 else 0
    # layout marker: 0x1041/0x1045 <flags>  (skip the 0x1342 prelude)
    m = None
    for k in range(o + 0x1C, min(o + 0x80, end - 4), 2):
        if u16(d, k) in (0x1041, 0x1045):
            m = k
            break
    flags = None if m is None else u16(d, m + 2)
    r["form"] = {0x803C: "short", 0x803E: "long", 0x9800: "compact", 0x8004: "first", 0x0000: "first"}.get(flags, "other")
    # rowbits: three equal u16 just before the 0x9052 tag
    p9052 = None
    if m is not None:
        for k in range(m, min(m + 0x40, end - 2), 2):
            if u16(d, k) == 0x9052:
                p9052 = k
                break
    elif not tag & 4 and not tag & 0x100:
        # dim1 == 1: the compact update-row has no 0x1045 marker, 0x9052 follows the header
        for k in range(o + 0x1C, min(o + 0x30, end - 2), 2):
            if u16(d, k) == 0x9052:
                p9052, r["form"], flags = k, "compact", 0x9801
                break
    if p9052 is not None and flags in (0x8004, 0x0000, 0x9801):
        # first read of a direct-update program: 9052 0000 014a 0040 <rowbits>
        r["rowbits"], r["rowbits_ok"] = u16(d, p9052 + 8), True
    elif p9052 is not None:
        trip = (u16(d, p9052 - 0xC), u16(d, p9052 - 8), u16(d, p9052 - 4))
        r["rowbits"], r["rowbits_ok"] = trip[2], len(set(trip)) == 1
    elif flags == 0x9800:
        r["rowbits"], r["rowbits_ok"] = u16(d, m + 0x0C), True
    else:
        r["rowbits"], r["rowbits_ok"] = None, False
    r["region"] = None if r["rowbits"] is None else r["rowbits"] << 16
    # end of core = after the 0x2031 0x0130 pair; child 0x9442 follows
    ce = None
    for k in range(o + 0x20, min(o + 0xA0, end - 4), 2):
        if u16(d, k) == 0x2031 and u16(d, k + 2) == 0x0130:
            ce = k + 4
            break
    r["core_end"] = ce
    r["slot"] = None
    r["cost"] = None
    if ce is not None and u16(d, ce) == 0x9442:
        r["slot"] = u16(d, ce + 2)
        if r["form"] == "compact":
            for k in range(ce + 0x1C, min(ce + 0x60, end - 4), 2):
                if u16(d, k) == 0x0038:
                    r["cost"] = u16(d, k + 2)
                    break
    r["digest"] = None if ce is None else hashlib.md5(d[o:ce]).hexdigest()[:12]
    return r


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    d = open(args[0], "rb").read()
    if d[:4] != (0xBEEFFACE).to_bytes(4, "little"):
        print("not an HWX Mach-O", file=sys.stderr)
        sys.exit(2)
    start, end = text_file_range(d)
    end = min(end, len(d))
    offs = [i for i in range(start, end - 2, 2) if u16(d, i) in FAMILY and u16(d, i - 2) == 0x8005]
    if "--tags" in flags:
        cnt = {}
        for o in offs:
            cnt[u16(d, o)] = cnt.get(u16(d, o), 0) + 1
        print("tags: " + (" ".join(f"0x{t:04x}={n}" for t, n in sorted(cnt.items())) or "none"))
        return
    recs = [decode(d, o, end) for o in offs]
    writes = [r for r in recs if r["tag"] & 4]
    reads = [r for r in recs if not r["tag"] & 4]
    reading = "--reads" in flags
    sel = reads if reading else writes
    dg = (lambda r: f" core={r['digest']}") if "--digest" in flags else (lambda r: "")
    for i, r in enumerate(sel):
        rb = "-" if r["rowbits"] is None else r["rowbits"]
        rg = "-" if r["region"] is None else r["region"]
        ext = f" dim2={r['dim2']} dim3={r['dim3']}"
        if not reading:
            print(f"i={i} form={r['form']} dim0={r['dim0']} dim1={r['dim1']} stride={r['stride']} "
                  f"region={rg} tag=0x{r['tag']:04x} rowbits={rb}{ext}{dg(r)}")
        else:
            sl = "-" if r["slot"] is None else f"0x{r['slot']:04x}"
            ct = "-" if r["cost"] is None else r["cost"]
            print(f"i={i} kind=read form={r['form']} dim1={r['dim1']} stride={r['stride']} "
                  f"tag=0x{r['tag']:04x} rowbits={rb} slot={sl} cost={ct}{ext}{dg(r)}")
    if not sel:
        print(f"summary: records=0 kind={'read' if reading else 'write'}")
        sys.exit(1)
    uniform = len({(r["dim0"], r["dim1"], r["stride"], r["dim2"], r["dim3"]) for r in sel}) == 1
    r0 = sel[0]
    if reading:
        c = {f: sum(1 for r in sel if r["form"] == f) for f in ("compact", "first", "short", "long")}
        print(f"summary: records={len(sel)} kind=read compact={c['compact']} first={c['first']} short={c['short']} "
              f"long={c['long']} dim1={r0['dim1']} stride={r0['stride']} uniform={'yes' if uniform else 'no'}")
    else:
        nl = sum(1 for r in sel if r["form"] == "long")
        ns = sum(1 for r in sel if r["form"] == "short")
        print(f"summary: records={len(sel)} long={nl} short={ns} dim0={r0['dim0']} dim1={r0['dim1']} "
              f"stride={r0['stride']} uniform={'yes' if uniform else 'no'} region={r0['region']}")


if __name__ == "__main__":
    main()
