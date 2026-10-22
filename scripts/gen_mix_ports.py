#!/usr/bin/env python3
# gen_mix_ports.py <in> <out> — emit an ANE-eligible MIL program with <in> input
# ports and <out> output ports, each y_i = add(x, x) passthrough. Used by the
# port-limits probe (docs/spec/ane-port-limits-h17.spec).
import sys

def main() -> None:
    ni, no = int(sys.argv[1]), int(sys.argv[2])
    lines = ["program(1.3)", "{"]
    args = ", ".join(f"tensor<fp16, [1, 4, 1, 1]> x{i}" for i in range(ni))
    lines.append(f"    func main<ios18>({args}) {{")
    outs = []
    for i in range(no):
        src = f"x{i % ni}"
        lines.append(
            f'        tensor<fp16, [1, 4, 1, 1]> y{i} = add(x = {src}, y = {src})[name = string("y{i}")];'
        )
        outs.append(f"y{i}")
    lines.append(f"    }} -> ({', '.join(outs)});")
    lines.append("}")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
