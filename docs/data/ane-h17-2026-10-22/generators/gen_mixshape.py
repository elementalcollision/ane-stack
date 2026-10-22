#!/usr/bin/env python3
"""gen_mixshape.py NA NB : NA states [4,4,1,1] then NB states [64,32,1,1]; inputs xa [1,4,1,1], xb [1,32,1,1]; outputs ya, yb (add(x,x))."""
import sys
na, nb = int(sys.argv[1]), int(sys.argv[2])
cls = [("a", 4, 4)] * na + [("b", 64, 32)] * nb
ps = [f"state<tensor<fp16, [{d0}, {d1}, 1, 1]>> kv{i}" for i, (c, d0, d1) in enumerate(cls)] + ["tensor<fp16, [1, 4, 1, 1]> xa", "tensor<fp16, [1, 32, 1, 1]> xb"]
L = ["program(1.3)", "{", f"    func main<ios18>({', '.join(ps)}) {{"]
L.append('        tensor<int32, [4]> begin = const()[val = tensor<int32, [4]>([0, 0, 0, 0])];')
L.append('        tensor<int32, [4]> enda = const()[val = tensor<int32, [4]>([1, 4, 1, 1])];')
L.append('        tensor<int32, [4]> endb = const()[val = tensor<int32, [4]>([1, 32, 1, 1])];')
for nm in ("bm","em","sm"): L.append(f'        tensor<bool, [4]> {nm} = const()[val = tensor<bool, [4]>([false, false, false, false])];')
L.append('        tensor<int32, [4]> st = const()[val = tensor<int32, [4]>([1, 1, 1, 1])];')
outs = []
for i, (c, d0, d1) in enumerate(cls):
    S = f"[{d0}, {d1}, 1, 1]"
    L.append(f'        tensor<fp16, {S}> cur{i} = read_state(input = kv{i})[name = string("cur{i}")];')
    L.append(f'        tensor<fp16, {S}> upd{i} = slice_update(x = cur{i}, begin = begin, end = end{c}, begin_mask = bm, end_mask = em, squeeze_mask = sm, stride = st, update = x{c})[name = string("upd{i}")];')
    L.append(f'        write_state(data = upd{i}, input = kv{i})[name = string("ws{i}")];')
    outs.append(f"upd{i}")
L.append('        tensor<fp16, [1, 4, 1, 1]> ya = add(x = xa, y = xa)[name = string("ya")];')
L.append('        tensor<fp16, [1, 32, 1, 1]> yb = add(x = xb, y = xb)[name = string("yb")];')
outs += ["ya", "yb"]
L.append(f"    }} -> ({', '.join(outs)});"); L.append("}")
print("\n".join(L))
