#!/usr/bin/env python3
# gen_states_shape.py <nstates> <dim0> <dim1> <in> <out> — emit an ANE-eligible
# MIL program with <nstates> independent state<tensor<fp16, [dim0, dim1, 1, 1]>>
# params (each its own read->slice_update->write triple), <in> plain inputs of
# shape [1, dim1, 1, 1] and <out> plain passthrough outputs.
#
# Unlike gen_states.py (dim1 fixed at 4; inputs beyond <out> are dead), this
# varies dim1 and keeps EVERY declared input live: the slice_update source is the
# add-chain u = x0 + x1 + ... + x{in-1} (a const when in == 0), and output j is
# add(x_{j%in}, x_{j%in}). Used by docs/spec/ane-port-limits-h17.spec for the
# shape-dependent record laws (0x9365 stride/region, 0x9361 geometry) and the
# 0x9344 = states + inputs economy.
import sys

def main() -> None:
    ns, d0, d1, ni, no = (int(a) for a in sys.argv[1:6])
    S = f"[{d0}, {d1}, 1, 1]"
    U = f"[1, {d1}, 1, 1]"
    lines = ["program(1.3)", "{"]
    params = [f"state<tensor<fp16, {S}>> kv{i}" for i in range(ns)]
    params += [f"tensor<fp16, {U}> x{i}" for i in range(ni)]
    lines.append(f"    func main<ios18>({', '.join(params)}) {{")
    lines.append('        tensor<int32, [4]> begin = const()[val = tensor<int32, [4]>([0, 0, 0, 0])];')
    lines.append(f'        tensor<int32, [4]> end = const()[val = tensor<int32, [4]>([1, {d1}, 1, 1])];')
    for nm in ("bm", "em", "sm"):
        lines.append(f'        tensor<bool, [4]> {nm} = const()[val = tensor<bool, [4]>([false, false, false, false])];')
    lines.append('        tensor<int32, [4]> st = const()[val = tensor<int32, [4]>([1, 1, 1, 1])];')
    if ni == 0:
        ones = ", ".join(["1.0"] * d1)
        lines.append(f'        tensor<fp16, {U}> u = const()[val = tensor<fp16, {U}>([{ones}])];')
    elif ni == 1:
        lines.append(f'        tensor<fp16, {U}> u = add(x = x0, y = x0)[name = string("u")];')
    else:
        acc = "x0"
        for k in range(1, ni):
            nm = "u" if k == ni - 1 else f"u_{k}"
            lines.append(f'        tensor<fp16, {U}> {nm} = add(x = {acc}, y = x{k})[name = string("{nm}")];')
            acc = nm
    outs = []
    for i in range(ns):
        lines.append(f'        tensor<fp16, {S}> cur{i} = read_state(input = kv{i})[name = string("cur{i}")];')
        lines.append(
            f'        tensor<fp16, {S}> upd{i} = slice_update(x = cur{i}, begin = begin, end = end, begin_mask = bm, end_mask = em, squeeze_mask = sm, stride = st, update = u)[name = string("upd{i}")];'
        )
        lines.append(f'        write_state(data = upd{i}, input = kv{i})[name = string("ws{i}")];')
        outs.append(f"upd{i}")
    for j in range(no):
        src = f"x{j % ni}" if ni > 0 else "u"
        lines.append(f'        tensor<fp16, {U}> y{j} = add(x = {src}, y = {src})[name = string("y{j}")];')
        outs.append(f"y{j}")
    lines.append(f"    }} -> ({', '.join(outs)});")
    lines.append("}")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
