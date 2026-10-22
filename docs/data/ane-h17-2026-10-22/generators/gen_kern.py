#!/usr/bin/env python3
"""gen_kern.py NS OPS...  -- NS rsw states [4,4,1,1] (update source = raw x0), inputs x0..x{K-1} ([1,4,1,1]) , one unary-op chain output per OP
(each op applied to its own input).  OPS from: relu sigmoid tanh softmax gelu silu erf exp log inverse sin cos sqrt rsqrt abs square."""
import sys
ns = int(sys.argv[1]); ops = sys.argv[2:]
K = max(1, len(ops))
S = "[4, 4, 1, 1]"; U = "[1, 4, 1, 1]"
L = ["program(1.3)", "{"]
ps = [f"state<tensor<fp16, {S}>> kv{i}" for i in range(ns)] + [f"tensor<fp16, {U}> x{i}" for i in range(K)]
L.append(f"    func main<ios18>({', '.join(ps)}) {{")
L.append('        tensor<int32, [4]> begin = const()[val = tensor<int32, [4]>([0, 0, 0, 0])];')
L.append('        tensor<int32, [4]> end = const()[val = tensor<int32, [4]>([1, 4, 1, 1])];')
for nm in ("bm","em","sm"): L.append(f'        tensor<bool, [4]> {nm} = const()[val = tensor<bool, [4]>([false, false, false, false])];')
L.append('        tensor<int32, [4]> st = const()[val = tensor<int32, [4]>([1, 1, 1, 1])];')
L.append('        int32 ax1 = const()[val = int32(1)];')
L.append('        fp16 eps = const()[val = fp16(0.001)];')
L.append('        string mode = const()[val = string("EXACT")];')
outs = []
for i in range(ns):
    L.append(f'        tensor<fp16, {S}> cur{i} = read_state(input = kv{i})[name = string("cur{i}")];')
    L.append(f'        tensor<fp16, {S}> upd{i} = slice_update(x = cur{i}, begin = begin, end = end, begin_mask = bm, end_mask = em, squeeze_mask = sm, stride = st, update = x0)[name = string("upd{i}")];')
    L.append(f'        write_state(data = upd{i}, input = kv{i})[name = string("ws{i}")];')
    outs.append(f"upd{i}")
for j, op in enumerate(ops):
    nm = f"z{j}"
    if op == "softmax":
        L.append(f'        tensor<fp16, {U}> {nm} = softmax(x = x{j}, axis = ax1)[name = string("{nm}")];')
    elif op == "gelu":
        L.append(f'        tensor<fp16, {U}> {nm} = gelu(x = x{j}, mode = mode)[name = string("{nm}")];')
    elif op in ("log", "inverse", "rsqrt"):
        L.append(f'        tensor<fp16, {U}> {nm} = {op}(x = x{j}, epsilon = eps)[name = string("{nm}")];')
    else:
        L.append(f'        tensor<fp16, {U}> {nm} = {op}(x = x{j})[name = string("{nm}")];')
    outs.append(nm)
L.append(f"    }} -> ({', '.join(outs)});"); L.append("}")
print("\n".join(L))
