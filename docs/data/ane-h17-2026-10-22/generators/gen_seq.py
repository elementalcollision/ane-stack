#!/usr/bin/env python3
"""gen_seq.py NS D1 OPS [src=x0]  -- NS rsw states [4,D1,1,1] (update source x0 raw), input x0 [1,D1,1,1],
output = chain of ops (comma list) on x0:  add, mul, relu, sigmoid, softmax (axis 1), rsum (reduce_sum axis 1 keepdims -> [1,1,1,1]) ...
(shape-changing ops end the elementwise chain; later ops see the new shape).  `none` = no chain (state-only)."""
import sys
ns, d1 = int(sys.argv[1]), int(sys.argv[2]); ops = [o for o in sys.argv[3].split(",") if o and o != "none"]
S = f"[4, {d1}, 1, 1]"
L = ["program(1.3)", "{"]
ps = [f"state<tensor<fp16, {S}>> kv{i}" for i in range(ns)] + [f"tensor<fp16, [1, {d1}, 1, 1]> x0"]
L.append(f"    func main<ios18>({', '.join(ps)}) {{")
L.append('        tensor<int32, [4]> begin = const()[val = tensor<int32, [4]>([0, 0, 0, 0])];')
L.append(f'        tensor<int32, [4]> end = const()[val = tensor<int32, [4]>([1, {d1}, 1, 1])];')
for nm in ("bm","em","sm"): L.append(f'        tensor<bool, [4]> {nm} = const()[val = tensor<bool, [4]>([false, false, false, false])];')
L.append('        tensor<int32, [4]> st = const()[val = tensor<int32, [4]>([1, 1, 1, 1])];')
L.append('        int32 ax1 = const()[val = int32(1)];')
L.append('        tensor<int32, [1]> rax = const()[val = tensor<int32, [1]>([1])];')
L.append('        bool kd = const()[val = bool(true)];')
outs = []
for i in range(ns):
    L.append(f'        tensor<fp16, {S}> cur{i} = read_state(input = kv{i})[name = string("cur{i}")];')
    L.append(f'        tensor<fp16, {S}> upd{i} = slice_update(x = cur{i}, begin = begin, end = end, begin_mask = bm, end_mask = em, squeeze_mask = sm, stride = st, update = x0)[name = string("upd{i}")];')
    L.append(f'        write_state(data = upd{i}, input = kv{i})[name = string("ws{i}")];')
    outs.append(f"upd{i}")
prev, shp = "x0", f"[1, {d1}, 1, 1]"
for k, op in enumerate(ops):
    nm = f"t{k}" if k < len(ops)-1 else "yout"
    if op in ("add","mul","sub","maximum"):
        L.append(f'        tensor<fp16, {shp}> {nm} = {op}(x = {prev}, y = {prev})[name = string("{nm}")];')
    elif op in ("relu","sigmoid","tanh"):
        L.append(f'        tensor<fp16, {shp}> {nm} = {op}(x = {prev})[name = string("{nm}")];')
    elif op.startswith("addc"):
        kk = int(op[4:] or 0)
        cv = ", ".join(["0.5"] * int(shp.split(",")[1]))
        L.append(f'        tensor<fp16, {shp}> cc{k} = const()[val = tensor<fp16, {shp}>([{cv}])];')
        L.append(f'        tensor<fp16, {shp}> {nm} = add(x = {prev}, y = cc{k})[name = string("{nm}")];')
    elif op == "softmax":
        L.append(f'        tensor<fp16, {shp}> {nm} = softmax(x = {prev}, axis = ax1)[name = string("{nm}")];')
    elif op == "rsum":
        shp = "[1, 1, 1, 1]"
        L.append(f'        tensor<fp16, {shp}> {nm} = reduce_sum(x = {prev}, axes = rax, keep_dims = kd)[name = string("{nm}")];')
    else:
        raise SystemExit("bad op "+op)
    prev = nm
if ops: outs.append(prev)
L.append(f"    }} -> ({', '.join(outs)});"); L.append("}")
print("\n".join(L))
