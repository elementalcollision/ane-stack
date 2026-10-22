#!/usr/bin/env python3
# gen_live_ports.py <in> <out> [C [H [W]]] — emit an ANE-eligible MIL program with
# <in> input ports and <out> output ports in which EVERY declared input is live.
# Each port is a tensor<fp16, [1, C, H, W]> (C defaults to 4, H and W to 1; widen
# them to show a port budget counts ports, not bytes).
# When in >= out, input i is folded into output (i % out) through an add chain;
# when in < out, outputs reuse inputs round-robin (y_j = add(x_{j%in}, x_{j%in})).
#
# Why not gen_mix_ports.py: there output i reads x{i % in}, so when in > out only
# the first `out` inputs are referenced and the e5rt lane drops the rest. That
# makes the execution cap look "floored at 63" when it is not. Used by
# docs/spec/ane-port-limits-h17.spec for the execution-time io cap.
import sys

def main() -> None:
    ni, no = int(sys.argv[1]), int(sys.argv[2])
    c = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    h = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    w = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    T = f"tensor<fp16, [1, {c}, {h}, {w}]>"
    lines = ["program(1.3)", "{"]
    args = ", ".join(f"{T} x{i}" for i in range(ni))
    lines.append(f"    func main<ios18>({args}) {{")
    if ni >= no:
        groups = [[i for i in range(ni) if i % no == j] for j in range(no)]
    else:
        groups = [[j % ni] for j in range(no)]
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
    lines.append(f"    }} -> ({', '.join(outs)});")
    lines.append("}")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
