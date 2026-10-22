#!/usr/bin/env python3
# gen_state_dtype.py <dtype> [<nstates>] [noupd] [noin]
#
# <nstates> (default 1) independent state<tensor<dtype, [4, 4, 1, 1]>> params, each its own
# read -> slice_update -> write triple.  The slice_update source is ONE plain input x0 of the same
# dtype as the states (no cast on the state path); the plain output is computed in fp16 via
# cast(x0).  Only the STATE dtype varies: io/compute dtype is what made earlier probes reject
# int8/int16/bool states (an int add is itself rejected).
#   noupd  the updated tensors upd_i are NOT returned (only y0 is).
#   noin   no plain input: the update source is an fp16 fill cast to <dtype> (a fill with an
#          int/bool value is InvalidMILProgram), so the program has no __const section and
#          one more state fits (54 instead of 53).  y0 = add(one, one).
# With the defaults (N = 1) the output is byte-identical to the previous gen_state_dtype.py.
# Used by docs/spec/ane-port-limits-h17.spec: fp32 and int32 states are rejected;
# fp16, int16, int8, uint8 and bool states compile and run, and hit the same BAR pool
# (53 states, 54 with 'noin') as fp16.
import sys


def main() -> None:
    dt = sys.argv[1]
    rest = sys.argv[2:]
    n = int(rest[0]) if rest and rest[0].isdigit() else 1
    noupd, noin = "noupd" in rest, "noin" in rest
    S, U = "[4, 4, 1, 1]", "[1, 4, 1, 1]"
    p = ["program(1.3)", "{"]
    params = [f"state<tensor<{dt}, {S}>> kv{i}" for i in range(n)]
    if not noin:
        params.append(f"tensor<{dt}, {U}> x0")
    p.append(f"    func main<ios18>({', '.join(params)}) {{")
    p.append('        tensor<int32, [4]> begin = const()[val = tensor<int32, [4]>([0, 0, 0, 0])];')
    p.append('        tensor<int32, [4]> end = const()[val = tensor<int32, [4]>([1, 4, 1, 1])];')
    for nm in ("bm", "em", "sm"):
        p.append(f'        tensor<bool, [4]> {nm} = const()[val = tensor<bool, [4]>([false, false, false, false])];')
    p.append('        tensor<int32, [4]> st = const()[val = tensor<int32, [4]>([1, 1, 1, 1])];')
    src = "x0"
    if noin:
        p.append('        tensor<int32, [4]> oshape = const()[val = tensor<int32, [4]>([1, 4, 1, 1])];')
        p.append('        fp16 oval = const()[val = fp16(1.0)];')
        p.append(f'        tensor<fp16, {U}> one = fill(shape = oshape, value = oval)[name = string("one")];')
        p.append(f'        string dts = const()[val = string("{dt}")];')
        p.append(f'        tensor<{dt}, {U}> src = cast(x = one, dtype = dts)[name = string("src")];')
        src = "src"
    outs = []
    for i in range(n):
        p.append(f'        tensor<{dt}, {S}> cur{i} = read_state(input = kv{i})[name = string("cur{i}")];')
        p.append(f'        tensor<{dt}, {S}> upd{i} = slice_update(x = cur{i}, begin = begin, end = end, begin_mask = bm, end_mask = em, squeeze_mask = sm, stride = st, update = {src})[name = string("upd{i}")];')
        p.append(f'        write_state(data = upd{i}, input = kv{i})[name = string("ws{i}")];')
        if not noupd:
            outs.append(f"upd{i}")
    if noin:
        p.append(f'        tensor<fp16, {U}> y0 = add(x = one, y = one)[name = string("y0")];')
    else:
        p.append('        string f16 = const()[val = string("fp16")];')
        p.append(f'        tensor<fp16, {U}> xf = cast(x = x0, dtype = f16)[name = string("xf")];')
        p.append(f'        tensor<fp16, {U}> y0 = add(x = xf, y = xf)[name = string("y0")];')
    outs.append("y0")
    p.append(f"    }} -> ({', '.join(outs)});")
    p.append("}")
    print("\n".join(p))


if __name__ == "__main__":
    main()
