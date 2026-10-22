#!/usr/bin/env python3
# state AND plain input in <dtype>, update = x0 directly (no cast); y0 = add(cast(x0->fp16), same) in fp16.
# usage: gen_dtype_v2.py dtype [d0 d1 d2 d3]
import sys
dt=sys.argv[1]
d0,d1,d2,d3=(int(x) for x in (sys.argv[2:6] if len(sys.argv)>=6 else (4,4,1,1)))
S=f"[{d0}, {d1}, {d2}, {d3}]"; U=f"[1, {d1}, {d2}, {d3}]"
L=["program(1.3)","{",f"    func main<ios18>(state<tensor<{dt}, {S}>> kv0, tensor<{dt}, {U}> x0) {{"]
L.append('        tensor<int32, [4]> begin = const()[val = tensor<int32, [4]>([0, 0, 0, 0])];')
L.append(f'        tensor<int32, [4]> end = const()[val = tensor<int32, [4]>([1, {d1}, {d2}, {d3}])];')
for nm in ("bm","em","sm"):
    L.append(f'        tensor<bool, [4]> {nm} = const()[val = tensor<bool, [4]>([false, false, false, false])];')
L.append('        tensor<int32, [4]> st = const()[val = tensor<int32, [4]>([1, 1, 1, 1])];')
L.append(f'        tensor<{dt}, {S}> cur0 = read_state(input = kv0)[name = string("cur0")];')
L.append(f'        tensor<{dt}, {S}> upd0 = slice_update(x = cur0, begin = begin, end = end, begin_mask = bm, end_mask = em, squeeze_mask = sm, stride = st, update = x0)[name = string("upd0")];')
L.append('        write_state(data = upd0, input = kv0)[name = string("ws0")];')
L.append('        string f16 = const()[val = string("fp16")];')
L.append(f'        tensor<fp16, {U}> xf = cast(x = x0, dtype = f16)[name = string("xf")];')
L.append(f'        tensor<fp16, {U}> y0 = add(x = xf, y = xf)[name = string("y0")];')
L.append("    } -> (upd0, y0);")
L.append("}")
print("\n".join(L))
