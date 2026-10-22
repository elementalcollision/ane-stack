#!/usr/bin/env python3
# gen_states_nd.py <nstates> <d0> <d1> <d2> <d3> <in> <out> [add|direct] [noupd]
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
#
# Only fp16 states compile on the ANE path (fp32/int8/int16/int32/bool states
# are rejected). Used by docs/spec/ane-port-limits-h17.spec for the BAR pool,
# the state port cost, the copy-record laws and the state execution page rule.
import sys

def main() -> None:
    a = sys.argv[1:]
    ns, d0, d1, d2, d3, ni, no = (int(x) for x in a[:7])
    opts = a[7:]
    mode = "direct" if "direct" in opts else "add"
    noupd = "noupd" in opts
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
    lines.append(f"    }} -> ({', '.join(outs)});")
    lines.append("}")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
