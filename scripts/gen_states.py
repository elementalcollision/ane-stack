#!/usr/bin/env python3
# gen_states.py <nstates> <in> <out> — emit an ANE-eligible MIL program with
# <nstates> independent state<> params (each its own read->slice_update->write
# triple, per the ANE state contract), plus <in> plain inputs and <out> plain
# passthrough outputs. Used by the state<> budget probe.
#
# Each state is its own stripe (per-state rsw triple, full slice_update args).
import sys

def main() -> None:
    ns, ni, no = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    lines = ["program(1.3)", "{"]
    params = [f"state<tensor<fp16, [4, 4, 1, 1]>> kv{i}" for i in range(ns)]
    params += [f"tensor<fp16, [1, 4, 1, 1]> x{i}" for i in range(ni)]
    lines.append(f"    func main<ios18>({', '.join(params)}) {{")

    # shared const args for slice_update (full arg list, required on state)
    lines.append('        tensor<int32, [4]> begin = const()[val = tensor<int32, [4]>([0, 0, 0, 0])];')
    lines.append('        tensor<int32, [4]> end = const()[val = tensor<int32, [4]>([1, 4, 1, 1])];')
    lines.append('        tensor<bool, [4]> bm = const()[val = tensor<bool, [4]>([false, false, false, false])];')
    lines.append('        tensor<bool, [4]> em = const()[val = tensor<bool, [4]>([false, false, false, false])];')
    lines.append('        tensor<bool, [4]> sm = const()[val = tensor<bool, [4]>([false, false, false, false])];')
    lines.append('        tensor<int32, [4]> st = const()[val = tensor<int32, [4]>([1, 1, 1, 1])];')

    # one rsw triple per state; the update source is the first plain input
    # (or a const if there are no plain inputs)
    update_src = "x0" if ni > 0 else "one"
    if ni == 0:
        # a flat literal ([1.0, 1.0, 1.0, 1.0]) is rejected for a rank-4 type; use fill
        lines.append('        tensor<int32, [4]> oshape = const()[val = tensor<int32, [4]>([1, 4, 1, 1])];')
        lines.append('        fp16 oval = const()[val = fp16(1.0)];')
        lines.append('        tensor<fp16, [1, 4, 1, 1]> one = fill(shape = oshape, value = oval)[name = string("one")];')
    outs = []
    for i in range(ns):
        lines.append(f'        tensor<fp16, [4, 4, 1, 1]> cur{i} = read_state(input = kv{i})[name = string("cur{i}")];')
        lines.append(
            f'        tensor<fp16, [4, 4, 1, 1]> upd{i} = slice_update(x = cur{i}, begin = begin, end = end, begin_mask = bm, end_mask = em, squeeze_mask = sm, stride = st, update = {update_src})[name = string("upd{i}")];'
        )
        lines.append(f'        write_state(data = upd{i}, input = kv{i})[name = string("ws{i}")];')
        outs.append(f"upd{i}")
    # plain passthrough outputs
    for j in range(no):
        src = f"x{j % ni}" if ni > 0 else "one"
        lines.append(f'        tensor<fp16, [1, 4, 1, 1]> y{j} = add(x = {src}, y = {src})[name = string("y{j}")];')
        outs.append(f"y{j}")
    lines.append(f"    }} -> ({', '.join(outs)});")
    lines.append("}")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
