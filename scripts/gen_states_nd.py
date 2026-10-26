#!/usr/bin/env python3
# gen_states_nd.py <nstates> <d0> <d1> <d2> <d3> <in> <out> [add|direct] [noupd]
#                  [conv=K] [lut=op[,op...]]
#                  [blob=K [blobdir=DIR] [bpath=abs|rel|mp] [bshare]] [wch=C]
#
# Emit an ANE-eligible MIL program with <nstates> independent
# state<tensor<fp16, [d0,d1,d2,d3]>> params (each its own
# read->slice_update->write triple), <in> plain inputs of shape [1,d1,d2,d3]
# and <out> plain passthrough outputs y_j = add(x_{j%in}, x_{j%in}).
#
#   add     (default) the slice_update source is the add-chain
#           u = x0 + x1 + ... + x{in-1}, so EVERY declared input is live;
#   direct  the slice_update source is x0 itself (the gen_states.py structure:
#           no ANE compute before the update);
#   noupd   the state-update tensors upd_i are NOT returned as program outputs
#           (only the <out> plain outputs are); no state-out copy record
#           (0x9365 family) is then emitted.
#   in = 0  the update source is u = fill(1.0), so the program has no plain
#           input and no __const segment (frees one BAR id: 54 states compile).
#   conv=K  K extra outputs conv(u) with an inline (nested-literal) [d1,d1,1,1]
#           fp16 weight each — a weighted op inside the state program.
#   lut=ops one extra output op(u) per listed lookup-table op (sigmoid, tanh, exp).
#   blob=K  K extra outputs conv(u) whose [C,C,1,1] fp16 weight is a BLOBFILE
#           const (weights/weight.bin, CoreML blob v2) instead of an inline
#           literal. The file is written to DIR/weights/weight.bin (blobdir=DIR,
#           required with blob=; created). bpath picks the path spelling in the
#           MIL: abs (default) = absolute path of that file; rel =
#           weights/weight.bin (resolves against the CURRENT directory, not the
#           MIL's); mp = @model_path/weights/weight.bin (resolves against the
#           MIL's directory). bshare = all K consts reference ONE blob offset
#           (1 distinct tensor) instead of K distinct blobs.
#   wch=C   weight channel count for the conv=/blob= weights ([C,C,1,1]); default
#           d1. When C != d1 the conv input is concat(u x C/d1) on axis 1
#           (needs d1 | C; with in=0 a [1,C,d2,d3] fill), so weight size is
#           decoupled from the state shape. Each conv/blob adds one plain
#           output, so the run-lane port law (states + in + exposed updates +
#           outputs <= 127) caps K at 53 states unless noupd is given.
#
# States are fp16 here; for other state dtypes see gen_state_dtype.py (fp32 and
# int32 states are rejected, int16/int8/uint8/bool run). Used by
# docs/spec/ane-port-limits-h17.spec for the BAR pool,
# the state port cost, the copy-record laws and the state execution page rule.
import os
import struct
import sys


def blob_file(path, tensors):
    """Write a CoreML weight.bin v2 file holding one fp16 blob per entry of
    `tensors` (lists of float values); return each blob's metadata offset.
    Layout: 64 B storage header (count u32, version u32 = 2), then per blob a
    64 B-aligned 64 B metadata record (sentinel 0xDEADBEEF u32, dtype u32 = 1
    fp16, size u64, absolute data offset u64, zero pad) followed by the data."""
    buf = bytearray(struct.pack("<II", len(tensors), 2))
    buf += bytes(64 - len(buf))
    offs = []
    for vals in tensors:
        buf += bytes((-len(buf)) % 64)
        offs.append(len(buf))
        data = struct.pack(f"<{len(vals)}e", *vals)
        meta = struct.pack("<IIQQ", 0xDEADBEEF, 1, len(data), len(buf) + 64)
        buf += meta + bytes(64 - len(meta)) + data
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(buf)
    return offs


def wval(r, c, j):
    return (((r * 13 + c * 7 + j * 5) % 41) - 20) / 100


def main() -> None:
    a = sys.argv[1:]
    ns, d0, d1, d2, d3, ni, no = (int(x) for x in a[:7])
    opts = a[7:]
    mode = "direct" if "direct" in opts else "add"
    noupd = "noupd" in opts
    nconv = next((int(o[5:]) for o in opts if o.startswith("conv=")), 0)
    luts = next((o[4:].split(",") for o in opts if o.startswith("lut=")), [])
    nblob = next((int(o[5:]) for o in opts if o.startswith("blob=")), 0)
    blobdir = next((o[8:] for o in opts if o.startswith("blobdir=")), None)
    if nblob and blobdir is None:
        sys.exit("blob=K needs blobdir=DIR")
    bpath = next((o[6:] for o in opts if o.startswith("bpath=")), "abs")
    bshare = "bshare" in opts
    wch = next((int(o[4:]) for o in opts if o.startswith("wch=")), d1)
    S = f"[{d0}, {d1}, {d2}, {d3}]"
    U = f"[1, {d1}, {d2}, {d3}]"
    lines = ["program(1.3)", "{"]
    params = [f"state<tensor<fp16, {S}>> kv{i}" for i in range(ns)]
    params += [f"tensor<fp16, {U}> x{i}" for i in range(ni)]
    lines.append(f"    func main<ios18>({', '.join(params)}) {{")
    lines.append('        tensor<int32, [4]> begin = const()[val = tensor<int32, [4]>([0, 0, 0, 0])];')
    lines.append(f'        tensor<int32, [4]> end = const()[val = tensor<int32, [4]>([1, {d1}, {d2}, {d3}])];')
    for nm in ("bm", "em", "sm"):
        lines.append(f'        tensor<bool, [4]> {nm} = const()[val = tensor<bool, [4]>([false, false, false, false])];')
    lines.append('        tensor<int32, [4]> st = const()[val = tensor<int32, [4]>([1, 1, 1, 1])];')
    if ni == 0:
        lines.append(f'        tensor<int32, [4]> ushape = const()[val = tensor<int32, [4]>([1, {d1}, {d2}, {d3}])];')
        lines.append('        fp16 uval = const()[val = fp16(1.0)];')
        lines.append(f'        tensor<fp16, {U}> u = fill(shape = ushape, value = uval)[name = string("u")];')
        src = "u"
    elif mode == "direct":
        src = "x0"
    elif ni == 1:
        lines.append(f'        tensor<fp16, {U}> u = add(x = x0, y = x0)[name = string("u")];')
        src = "u"
    else:
        acc = "x0"
        for k in range(1, ni):
            nm = "u" if k == ni - 1 else f"u_{k}"
            lines.append(f'        tensor<fp16, {U}> {nm} = add(x = {acc}, y = x{k})[name = string("{nm}")];')
            acc = nm
        src = "u"
    outs = []
    for i in range(ns):
        lines.append(f'        tensor<fp16, {S}> cur{i} = read_state(input = kv{i})[name = string("cur{i}")];')
        lines.append(
            f'        tensor<fp16, {S}> upd{i} = slice_update(x = cur{i}, begin = begin, end = end, begin_mask = bm, end_mask = em, squeeze_mask = sm, stride = st, update = {src})[name = string("upd{i}")];'
        )
        lines.append(f'        write_state(data = upd{i}, input = kv{i})[name = string("ws{i}")];')
        if not noupd:
            outs.append(f"upd{i}")
    for j in range(no):
        s = f"x{j % ni}" if ni > 0 else "u"
        lines.append(f'        tensor<fp16, {U}> y{j} = add(x = {s}, y = {s})[name = string("y{j}")];')
        outs.append(f"y{j}")
    for j, op in enumerate(luts):
        lines.append(f'        tensor<fp16, {U}> l{j} = {op}(x = {src})[name = string("l{j}")];')
        outs.append(f"l{j}")
    if nconv or nblob:
        lines.append('        tensor<string, []> cpt = const()[val = string("valid")];')
        lines.append('        tensor<int32, [2]> cst = const()[val = tensor<int32, [2]>([1, 1])];')
        lines.append('        tensor<int32, [4]> cpd = const()[val = tensor<int32, [4]>([0, 0, 0, 0])];')
        lines.append('        tensor<int32, [2]> cdl = const()[val = tensor<int32, [2]>([1, 1])];')
        lines.append('        tensor<int32, []> cgr = const()[val = int32(1)];')
    UW = f"[1, {wch}, {d2}, {d3}]"
    csrc = src
    if (nconv or nblob) and wch != d1:
        if wch % d1:
            sys.exit("wch must be a multiple of d1")
        if ni == 0:
            # no plain input: the conv input is a wide fill (a concat of fills is rejected)
            lines.append(f'        tensor<int32, [4]> cshape = const()[val = tensor<int32, [4]>([1, {wch}, {d2}, {d3}])];')
            lines.append(f'        tensor<fp16, {UW}> cin = fill(shape = cshape, value = uval)[name = string("cin")];')
        else:
            lines.append('        tensor<int32, []> cax = const()[val = int32(1)];')
            lines.append('        tensor<bool, []> cil = const()[val = bool(false)];')
            lines.append(f'        tensor<fp16, {UW}> cin = concat(axis = cax, interleave = cil, values = ({", ".join([src] * (wch // d1))}))[name = string("cin")];')
        csrc = "cin"
    for j in range(nconv):
        rows = ["[" + ", ".join(f"[[{(((r * 13 + c * 7 + j * 5) % 41) - 20) / 100:.2f}]]" for c in range(wch)) + "]" for r in range(wch)]
        lines.append(f'        tensor<fp16, [{wch}, {wch}, 1, 1]> w{j} = const()[val = tensor<fp16, [{wch}, {wch}, 1, 1]>([{", ".join(rows)}])];')
        lines.append(f'        tensor<fp16, {UW}> cv{j} = conv(dilations = cdl, groups = cgr, pad = cpd, pad_type = cpt, strides = cst, weight = w{j}, x = {csrc})[name = string("cv{j}")];')
        outs.append(f"cv{j}")
    if nblob:
        ntens = 1 if bshare else nblob
        wfile = os.path.join(os.path.abspath(blobdir), "weights", "weight.bin")
        offs = blob_file(wfile, [[wval(r, c, j) for r in range(wch) for c in range(wch)] for j in range(ntens)])
        pstr = {"abs": wfile, "rel": "weights/weight.bin", "mp": "@model_path/weights/weight.bin"}[bpath]
        for j in range(nblob):
            off = offs[0 if bshare else j]
            lines.append(f'        tensor<fp16, [{wch}, {wch}, 1, 1]> bw{j} = const()[val = tensor<fp16, [{wch}, {wch}, 1, 1]>(BLOBFILE(path = string("{pstr}"), offset = uint64({off})))];')
            lines.append(f'        tensor<fp16, {UW}> bcv{j} = conv(dilations = cdl, groups = cgr, pad = cpd, pad_type = cpt, strides = cst, weight = bw{j}, x = {csrc})[name = string("bcv{j}")];')
            outs.append(f"bcv{j}")
    lines.append(f"    }} -> ({', '.join(outs)});")
    lines.append("}")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
