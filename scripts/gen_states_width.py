#!/usr/bin/env python3
# gen_states_width.py <nstates> <width> — like gen_states.py but each state is a
# [width, 4, 1, 1] stripe (dim0 = width). Used to test whether the BAR table is
# per-descriptor (width-independent) or per-byte.
import sys

def main() -> None:
    ns, w = int(sys.argv[1]), int(sys.argv[2])
    lines = ["program(1.3)", "{"]
    params = [f"state<tensor<fp16, [{w}, 4, 1, 1]>> kv{i}" for i in range(ns)]
    params += ["tensor<fp16, [1, 4, 1, 1]> x0"]
    lines.append(f"    func main<ios18>({', '.join(params)}) {{")
    lines.append('        tensor<int32, [4]> begin = const()[val = tensor<int32, [4]>([0, 0, 0, 0])];')
    lines.append('        tensor<int32, [4]> end = const()[val = tensor<int32, [4]>([1, 4, 1, 1])];')
    for nm in ("bm", "em", "sm"):
        lines.append(f'        tensor<bool, [4]> {nm} = const()[val = tensor<bool, [4]>([false, false, false, false])];')
    lines.append('        tensor<int32, [4]> st = const()[val = tensor<int32, [4]>([1, 1, 1, 1])];')
    outs = []
    for i in range(ns):
        lines.append(f'        tensor<fp16, [{w}, 4, 1, 1]> cur{i} = read_state(input = kv{i})[name = string("cur{i}")];')
        lines.append(
            f'        tensor<fp16, [{w}, 4, 1, 1]> upd{i} = slice_update(x = cur{i}, begin = begin, end = end, begin_mask = bm, end_mask = em, squeeze_mask = sm, stride = st, update = x0)[name = string("upd{i}")];'
        )
        lines.append(f'        write_state(data = upd{i}, input = kv{i})[name = string("ws{i}")];')
        outs.append(f"upd{i}")
    lines.append(f"    }} -> ({', '.join(outs)});")
    lines.append("}")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
