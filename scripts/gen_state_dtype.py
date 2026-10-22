#!/usr/bin/env python3
# gen_state_dtype.py <dtype> — one state<tensor<dtype, [4, 4, 1, 1]>> with a
# plain input x0 of the same dtype as the slice_update source (no cast on the
# state path); the plain output is computed in fp16 via cast(x0).
# Only the STATE dtype varies: io/compute dtype is what made earlier probes
# reject int8/int16/bool states (an int add is itself rejected).
# Used by docs/spec/ane-port-limits-h17.spec: fp32 and int32 states are rejected;
# fp16, int16, int8, uint8 and bool states compile and run.
import sys

def main() -> None:
    dt = sys.argv[1]
    S, U = "[4, 4, 1, 1]", "[1, 4, 1, 1]"
    print("program(1.3)")
    print("{")
    print(f"    func main<ios18>(state<tensor<{dt}, {S}>> kv0, tensor<{dt}, {U}> x0) {{")
    print('        tensor<int32, [4]> begin = const()[val = tensor<int32, [4]>([0, 0, 0, 0])];')
    print('        tensor<int32, [4]> end = const()[val = tensor<int32, [4]>([1, 4, 1, 1])];')
    for nm in ("bm", "em", "sm"):
        print(f'        tensor<bool, [4]> {nm} = const()[val = tensor<bool, [4]>([false, false, false, false])];')
    print('        tensor<int32, [4]> st = const()[val = tensor<int32, [4]>([1, 1, 1, 1])];')
    print(f'        tensor<{dt}, {S}> cur0 = read_state(input = kv0)[name = string("cur0")];')
    print(f'        tensor<{dt}, {S}> upd0 = slice_update(x = cur0, begin = begin, end = end, begin_mask = bm, end_mask = em, squeeze_mask = sm, stride = st, update = x0)[name = string("upd0")];')
    print('        write_state(data = upd0, input = kv0)[name = string("ws0")];')
    print('        string f16 = const()[val = string("fp16")];')
    print(f'        tensor<fp16, {U}> xf = cast(x = x0, dtype = f16)[name = string("xf")];')
    print(f'        tensor<fp16, {U}> y0 = add(x = xf, y = xf)[name = string("y0")];')
    print("    } -> (upd0, y0);")
    print("}")

if __name__ == "__main__":
    main()
