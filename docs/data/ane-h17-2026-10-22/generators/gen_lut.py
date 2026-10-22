#!/usr/bin/env python3
# WD-local generator (not in repo): gen_states_nd + extra op outputs.
# gen_lut.py N d0 d1 d2 d3 in out [add|direct] [noupd] [lut=sigmoid,tanh,exp,softmax] [cmul=K] [cadd=K] [deadin=K]
#   lut=...  : one extra plain output per listed op, applied to src (x0 or u)
#   cmul=K   : one extra plain output y = mul(src, const[1,d1,1,1] vector) (inline const tensor, K=count of such outputs)
#   cadd=K   : likewise add with const tensor
#   deadin=K : K extra declared plain inputs that nothing references
import sys
a=sys.argv[1:]
ns,d0,d1,d2,d3,ni,no=(int(x) for x in a[:7]); opts=a[7:]
mode="direct" if "direct" in opts else "add"; noupd="noupd" in opts
lut=[];cmul=0;cadd=0;deadin=0;nconv=0;xin=None;bigin=0;chainbig=0;sz=64;chain=0;schain=0;passthru=0;retcur=0;rdonly=0;wonly=0
for o in opts:
    if o.startswith("lut="): lut=o[4:].split(",")
    if o.startswith("cmul="): cmul=int(o[5:])
    if o.startswith("cadd="): cadd=int(o[5:])
    if o.startswith("deadin="): deadin=int(o[7:])
    if o.startswith("conv="): nconv=int(o[5:])
    if o.startswith("xin="): xin=o[4:]
    if o.startswith("bigin="): bigin=int(o[6:])
    if o.startswith("chainbig="): chainbig=int(o[9:]); bigin=1
    if o.startswith("sz="): sz=int(o[3:])
    if o.startswith("chain="): chain=int(o[6:])
    if o.startswith("passthru="): passthru=int(o[9:])
    if o.startswith("retcur="): retcur=int(o[7:])
    if o.startswith("rdonly="): rdonly=int(o[7:])
    if o.startswith("wonly="): wonly=int(o[6:])
    if o.startswith("schain="): schain=int(o[7:])
S=f"[{d0}, {d1}, {d2}, {d3}]"; U=f"[1, {d1}, {d2}, {d3}]"
L=["program(1.3)","{"]
params=[f"state<tensor<fp16, {S}>> kv{i}" for i in range(ns)]
params+=[f"tensor<fp16, {U}> x{i}" for i in range(ni)]
params+=[f"tensor<fp16, {U}> dead{i}" for i in range(deadin)]
if xin: params+=[f"tensor<{xin}, {U}> xe"]
if bigin: params+=[f"tensor<fp16, [1, {sz}, {sz}, {sz}]> xbig"]
L.append(f"    func main<ios18>({', '.join(params)}) {{")
L.append('        tensor<int32, [4]> begin = const()[val = tensor<int32, [4]>([0, 0, 0, 0])];')
L.append(f'        tensor<int32, [4]> end = const()[val = tensor<int32, [4]>([1, {d1}, {d2}, {d3}])];')
for nm in ("bm","em","sm"):
    L.append(f'        tensor<bool, [4]> {nm} = const()[val = tensor<bool, [4]>([false, false, false, false])];')
L.append('        tensor<int32, [4]> st = const()[val = tensor<int32, [4]>([1, 1, 1, 1])];')
if ni==0:
    L.append(f'        tensor<int32, [4]> ushape = const()[val = tensor<int32, [4]>([1, {d1}, {d2}, {d3}])];')
    L.append('        fp16 uval = const()[val = fp16(1.0)];')
    L.append(f'        tensor<fp16, {U}> u = fill(shape = ushape, value = uval)[name = string("u")];')
    src="u"
elif mode=="direct": src="x0"
elif ni==1:
    L.append(f'        tensor<fp16, {U}> u = add(x = x0, y = x0)[name = string("u")];'); src="u"
else:
    acc="x0"
    for k in range(1,ni):
        nm="u" if k==ni-1 else f"u_{k}"
        L.append(f'        tensor<fp16, {U}> {nm} = add(x = {acc}, y = x{k})[name = string("{nm}")];'); acc=nm
    src="u"
outs=[]
for i in range(ns):
    L.append(f'        tensor<fp16, {S}> cur{i} = read_state(input = kv{i})[name = string("cur{i}")];')
    L.append(f'        tensor<fp16, {S}> upd{i} = slice_update(x = cur{i}, begin = begin, end = end, begin_mask = bm, end_mask = em, squeeze_mask = sm, stride = st, update = {src})[name = string("upd{i}")];')
    L.append(f'        write_state(data = upd{i}, input = kv{i})[name = string("ws{i}")];')
    if not noupd: outs.append(f"upd{i}")
for j in range(no):
    s=f"x{j%ni}" if ni>0 else "u"
    L.append(f'        tensor<fp16, {U}> y{j} = add(x = {s}, y = {s})[name = string("y{j}")];'); outs.append(f"y{j}")
for j,op in enumerate(lut):
    if op=="softmax":
        L.append('        int32 sax = const()[val = int32(1)];')
        L.append(f'        tensor<fp16, {U}> l{j} = softmax(axis = sax, x = {src})[name = string("l{j}")];')
    else:
        L.append(f'        tensor<fp16, {U}> l{j} = {op}(x = {src})[name = string("l{j}")];')
    outs.append(f"l{j}")
vals="[[" + ", ".join(f"[[{((k*37)%100+1)/100:.2f}]]" for k in range(d1)) + "]]"
for j in range(cmul):
    L.append(f'        tensor<fp16, [1, {d1}, 1, 1]> cm{j} = const()[val = tensor<fp16, [1, {d1}, 1, 1]>({vals})];')
    L.append(f'        tensor<fp16, {U}> m{j} = mul(x = {src}, y = cm{j})[name = string("m{j}")];'); outs.append(f"m{j}")
for j in range(cadd):
    L.append(f'        tensor<fp16, [1, {d1}, 1, 1]> ca{j} = const()[val = tensor<fp16, [1, {d1}, 1, 1]>({vals})];')
    L.append(f'        tensor<fp16, {U}> p{j} = add(x = {src}, y = ca{j})[name = string("p{j}")];'); outs.append(f"p{j}")





if passthru: outs.append("x0")
for q in range(retcur): outs.append(f"cur{q}")
if schain:
    last="cur0"
    for q in range(schain):
        nm=f"sc{q}"; op=["add","mul","sub"][q%3]
        L.append(f'        tensor<fp16, {S}> {nm} = {op}(x = {last}, y = cur0)[name = string("{nm}")];'); last=nm
    outs.append(last)
if chain:
    last=src
    for q in range(chain):
        nm=f"ch{q}"; op=["add","mul","sub"][q%3]
        L.append(f'        tensor<fp16, {U}> {nm} = {op}(x = {last}, y = {src})[name = string("{nm}")];'); last=nm
    outs.append(last)
if xin:
    L.append(f'        string dt = const()[val = string("fp16")];')
    L.append(f'        tensor<fp16, {U}> xec = cast(dtype = dt, x = xe)[name = string("xec")];')
    L.append(f'        tensor<fp16, {U}> xo = add(x = xec, y = {src})[name = string("xo")];')
    outs.append("xo")
if bigin:
    BT=f"[1, {sz}, {sz}, {sz}]"
    L.append(f'        tensor<fp16, {BT}> xbo = add(x = xbig, y = xbig)[name = string("xbo")];')
    last="xbo"
    for q in range(chainbig):
        nm=f"xc{q}"
        op = ["add","mul","sub"][q%3]
        L.append(f'        tensor<fp16, {BT}> {nm} = {op}(x = {last}, y = xbig)[name = string("{nm}")];')
        last=nm
    outs.append(last)
if nconv:
    L.append('        tensor<string, []> pt = const()[val = string("valid")];')
    L.append('        tensor<int32, [2]> cst = const()[val = tensor<int32, [2]>([1, 1])];')
    L.append('        tensor<int32, [4]> pd = const()[val = tensor<int32, [4]>([0, 0, 0, 0])];')
    L.append('        tensor<int32, [2]> dl = const()[val = tensor<int32, [2]>([1, 1])];')
    L.append('        tensor<int32, []> gr = const()[val = int32(1)];')
for j in range(nconv):
    rows=[]
    for r in range(d1):
        rows.append("["+", ".join(f"[[{(((r*13+c*7+j*5)%41)-20)/100:.2f}]]" for c in range(d1))+"]")
    w="["+", ".join(rows)+"]"
    L.append(f'        tensor<fp16, [{d1}, {d1}, 1, 1]> w{j} = const()[val = tensor<fp16, [{d1}, {d1}, 1, 1]>({w})];')
    L.append(f'        tensor<fp16, {U}> cv{j} = conv(dilations = dl, groups = gr, pad = pd, pad_type = pt, strides = cst, weight = w{j}, x = {src})[name = string("cv{j}")];')
    outs.append(f"cv{j}")
L.append(f"    }} -> ({', '.join(outs)});"); L.append("}")
print("\n".join(L))
