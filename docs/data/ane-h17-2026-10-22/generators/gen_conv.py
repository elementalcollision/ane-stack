#!/usr/bin/env python3
"""gen_conv.py NS D1 L [mode] -- NS rsw states [4,D1,1,1] (update source = x0 raw), one input x0 [1,D1,1,1],
one output = chain of L 1x1 convs (inline fp16 weights, D1->D1) on x0.  mode=chain (default) | par (L parallel convs, L outputs)"""
import sys
ns, d1, Lc = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
mode = sys.argv[4] if len(sys.argv) > 4 else "chain"
S = f"[4, {d1}, 1, 1]"; U = f"[1, {d1}, 1, 1]"
L = ["program(1.3)", "{"]
ps = [f"state<tensor<fp16, {S}>> kv{i}" for i in range(ns)] + [f"tensor<fp16, {U}> x0"]
L.append(f"    func main<ios18>({', '.join(ps)}) {{")
L.append('        tensor<int32, [4]> begin = const()[val = tensor<int32, [4]>([0, 0, 0, 0])];')
L.append(f'        tensor<int32, [4]> end = const()[val = tensor<int32, [4]>([1, {d1}, 1, 1])];')
for nm in ("bm","em","sm"): L.append(f'        tensor<bool, [4]> {nm} = const()[val = tensor<bool, [4]>([false, false, false, false])];')
L.append('        tensor<int32, [4]> st = const()[val = tensor<int32, [4]>([1, 1, 1, 1])];')
L.append('        tensor<int32, [2]> cst = const()[val = tensor<int32, [2]>([1, 1])];')
L.append('        string cpt = const()[val = string("valid")];')
L.append('        tensor<int32, [4]> cpd = const()[val = tensor<int32, [4]>([0, 0, 0, 0])];')
L.append('        tensor<int32, [2]> cdl = const()[val = tensor<int32, [2]>([1, 1])];')
L.append('        int32 cgr = const()[val = int32(1)];')
W = ", ".join(["0.25" if (i % (d1+1) == 0) else "0.0" for i in range(d1*d1)])
for k in range(Lc):
    L.append(f'        tensor<fp16, [{d1}, {d1}, 1, 1]> w{k} = const()[val = tensor<fp16, [{d1}, {d1}, 1, 1]>([{W}])];')
outs = []
for i in range(ns):
    L.append(f'        tensor<fp16, {S}> cur{i} = read_state(input = kv{i})[name = string("cur{i}")];')
    L.append(f'        tensor<fp16, {S}> upd{i} = slice_update(x = cur{i}, begin = begin, end = end, begin_mask = bm, end_mask = em, squeeze_mask = sm, stride = st, update = x0)[name = string("upd{i}")];')
    L.append(f'        write_state(data = upd{i}, input = kv{i})[name = string("ws{i}")];')
    outs.append(f"upd{i}")
prev = "x0"
for k in range(Lc):
    src = prev if mode == "chain" else "x0"
    nm = f"c{k}"
    L.append(f'        tensor<fp16, {U}> {nm} = conv(x = {src}, weight = w{k}, strides = cst, pad_type = cpt, pad = cpd, dilations = cdl, groups = cgr)[name = string("{nm}")];')
    prev = nm
    if mode == "par": outs.append(nm)
if mode == "chain": outs.append(prev)
L.append(f"    }} -> ({', '.join(outs)});"); L.append("}")
print("\n".join(L))
