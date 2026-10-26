#!/usr/bin/env python3
# gen_dead_ports.py <live> <out> <extra> <mode> [pos] [C] — emit an ANE-eligible
# MIL program with <live>+<extra> declared inputs and <out> outputs. The <live>
# inputs are all live (folded into the outputs exactly as gen_live_ports.py does).
# The <extra> inputs never reach an output:
#   mode=unref  : declared but never referenced by any op
#   mode=deadop : referenced only by a dead op  d_k = add(x_k, x_k)  whose result
#                 is not returned (one dead op per extra input)
#   mode=deadchain: referenced only by ONE dead add-chain over all extras
# pos=tail (default) puts the extras after the live inputs; pos=head puts them first.
# C is the channel width (default 4). Used to show what counts as an input for the
# execution-time io cap (docs/spec/ane-port-limits-h17.spec).
import sys

def main() -> None:
    live, no, extra, mode = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    pos = sys.argv[5] if len(sys.argv) > 5 else "tail"
    c = int(sys.argv[6]) if len(sys.argv) > 6 else 4
    T = f"tensor<fp16, [1, {c}, 1, 1]>"
    n = live + extra
    if pos == "tail":
        live_ids = list(range(live)); extra_ids = list(range(live, n))
    else:
        extra_ids = list(range(extra)); live_ids = list(range(extra, n))
    lines = ["program(1.3)", "{"]
    lines.append(f"    func main<ios18>({', '.join(f'{T} x{i}' for i in range(n))}) {{")
    if live >= no:
        groups = [[live_ids[i] for i in range(live) if i % no == j] for j in range(no)]
    else:
        groups = [[live_ids[j % live]] for j in range(no)]
    outs = []
    for j, g in enumerate(groups):
        if len(g) == 1:
            lines.append(f'        {T} y{j} = add(x = x{g[0]}, y = x{g[0]})[name = string("y{j}")];')
        else:
            acc = f"x{g[0]}"
            for k, idx in enumerate(g[1:]):
                nm = f"y{j}" if k == len(g) - 2 else f"t{j}_{k}"
                lines.append(f'        {T} {nm} = add(x = {acc}, y = x{idx})[name = string("{nm}")];')
                acc = nm
        outs.append(f"y{j}")
    if mode == "deadop":
        for k in extra_ids:
            lines.append(f'        {T} d{k} = add(x = x{k}, y = x{k})[name = string("d{k}")];')
    elif mode == "deadchain" and extra_ids:
        acc = f"x{extra_ids[0]}"
        for k, idx in enumerate(extra_ids[1:]):
            nm = f"dc{k}"
            lines.append(f'        {T} {nm} = add(x = {acc}, y = x{idx})[name = string("{nm}")];')
            acc = nm
        if len(extra_ids) == 1:
            lines.append(f'        {T} dc0 = add(x = x{extra_ids[0]}, y = x{extra_ids[0]})[name = string("dc0")];')
    lines.append(f"    }} -> ({', '.join(outs)});")
    lines.append("}")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
