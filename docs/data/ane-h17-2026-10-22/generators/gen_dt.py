#!/usr/bin/env python3
"""gen_dt.py NS D1 DT_IN DT_OUT -- NS states [4,D1,1,1] (rsw from u=x0 add), one input x0 of dtype DT_IN, one output of dtype DT_OUT (via cast)."""
import sys
ns, d1 = int(sys.argv[1]), int(sys.argv[2]); dti, dto = sys.argv[3], sys.argv[4]
S = f"[4, {d1}, 1, 1]"; U = f"[1, {d1}, 1, 1]"
L = ["program(1.3)", "{"]
ps = [f"state<tensor<fp16, {S}>> kv{i}" for i in range(ns)] + [f"tensor<{dti}, {U}> xin"]
L.append(f"    func main<ios18>({', '.join(ps)}) {{")
L.append('        tensor<int32, [4]> begin = const()[val = tensor<int32, [4]>([0, 0, 0, 0])];')
L.append(f'        tensor<int32, [4]> end = const()[val = tensor<int32, [4]>([1, {d1}, 1, 1])];')
for nm in ("bm","em","sm"): L.append(f'        tensor<bool, [4]> {nm} = const()[val = tensor<bool, [4]>([false, false, false, false])];')
L.append('        tensor<int32, [4]> st = const()[val = tensor<int32, [4]>([1, 1, 1, 1])];')
if dti != "fp16":
    L.append('        string d16 = const()[val = string("fp16")];')
    L.append(f'        tensor<fp16, {U}> x0 = cast(x = xin, dtype = d16)[name = string("x0")];')
else:
    L.append(f'        tensor<fp16, {U}> x0 = add(x = xin, y = xin)[name = string("x0")];')
outs = []
for i in range(ns):
    L.append(f'        tensor<fp16, {S}> cur{i} = read_state(input = kv{i})[name = string("cur{i}")];')
    L.append(f'        tensor<fp16, {S}> upd{i} = slice_update(x = cur{i}, begin = begin, end = end, begin_mask = bm, end_mask = em, squeeze_mask = sm, stride = st, update = x0)[name = string("upd{i}")];')
    L.append(f'        write_state(data = upd{i}, input = kv{i})[name = string("ws{i}")];')
    outs.append(f"upd{i}")
if dto != "fp16":
    L.append(f'        string dout = const()[val = string("{dto}")];')
    L.append(f'        tensor<{dto}, {U}> y0 = cast(x = x0, dtype = dout)[name = string("y0")];')
else:
    L.append(f'        tensor<fp16, {U}> y0 = add(x = x0, y = x0)[name = string("y0")];')
outs.append("y0")
L.append(f"    }} -> ({', '.join(outs)});"); L.append("}")
print("\n".join(L))
