#!/usr/bin/env python3
# gen_dup_returns.py <n> — emit an ANE-eligible MIL program with ONE input and ONE
# computed tensor y0 = add(x0, x0) that is listed <n> times in the return tuple:
#   -> (y0, y0, ..., y0).
# Used by docs/spec/ane-port-limits-h17.spec to show the io port budget counts
# UNIQUE returned tensors, not return-list entries (n = 200 still runs).
import sys

def main() -> None:
    n = int(sys.argv[1])
    T = "tensor<fp16, [1, 4, 1, 1]>"
    print("program(1.3)")
    print("{")
    print(f"    func main<ios18>({T} x0) {{")
    print(f'        {T} y0 = add(x = x0, y = x0)[name = string("y0")];')
    print(f"    }} -> ({', '.join(['y0'] * n)});")
    print("}")

if __name__ == "__main__":
    main()
