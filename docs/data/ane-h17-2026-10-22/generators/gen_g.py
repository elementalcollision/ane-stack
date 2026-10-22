#!/usr/bin/env python3
"""gen_g.py -- general state<> + op-chain generator for the state-cap unit.

usage: gen_g.py NS D0 D1 IN OUT [key=value ...]
  NS states of shape [D0,D1,1,1]; IN plain inputs [1,D1,1,1] (all live: update source u = x0+..+x{IN-1}
  add-chain, or `src=x0` to feed x0 directly, or `src=const`); OUT passthrough outputs y_j = add(x_{j%IN}, x_{j%IN}).
  options:
    src=u|x0|const     update source for every slice_update   (default u; u needs IN>=1)
    chains=C len=L op=OP  C extra independent chains (each its own output z_c) of L ops of kind OP starting
                          from x_{c%IN}.   binary ops use (prev, prev); unary ops use prev.
    kinds=rsw|r|w|rw|... per-state kind pattern, comma list cycled over states (rsw = read+update+write,
                          r = read only -> output, w = write only (write_state of an input-derived value),
                          rs = read+slice_update, no write)
    fuse=0|1           (unused)
    noout=1            do not list upd_i among the program outputs (states only written)
"""
import sys

BIN = {"add", "mul", "sub", "maximum", "minimum"}
UN = {"relu", "sigmoid", "tanh", "exp", "abs", "sqrt", "rsqrt", "square"}


def main():
    ns, d0, d1, ni, no = (int(a) for a in sys.argv[1:6])
    kv = dict(a.split("=", 1) for a in sys.argv[6:])
    src = kv.get("src", "u")
    chains = int(kv.get("chains", 0))
    clen = int(kv.get("len", 1))
    op = kv.get("op", "add")
    kinds = kv.get("kinds", "rsw").split(",")
    noout = kv.get("noout", "0") == "1"
    expose = int(kv.get("expose", ns))
    S = f"[{d0}, {d1}, 1, 1]"
    U = f"[1, {d1}, 1, 1]"
    L = ["program(1.3)", "{"]
    params = [f"state<tensor<fp16, {S}>> kv{i}" for i in range(ns)]
    params += [f"tensor<fp16, {U}> x{i}" for i in range(ni)]
    L.append(f"    func main<ios18>({', '.join(params)}) {{")
    L.append('        tensor<int32, [4]> begin = const()[val = tensor<int32, [4]>([0, 0, 0, 0])];')
    L.append(f'        tensor<int32, [4]> end = const()[val = tensor<int32, [4]>([1, {d1}, 1, 1])];')
    for nm in ("bm", "em", "sm"):
        L.append(f'        tensor<bool, [4]> {nm} = const()[val = tensor<bool, [4]>([false, false, false, false])];')
    L.append('        tensor<int32, [4]> st = const()[val = tensor<int32, [4]>([1, 1, 1, 1])];')
    # update source
    if src == "const" or ni == 0:
        ones = ", ".join(["1.0"] * d1)
        L.append(f'        tensor<fp16, {U}> u = const()[val = tensor<fp16, {U}>([{ones}])];')
    elif src == "x0":
        L.append(f'        tensor<fp16, {U}> u = add(x = x0, y = x0)[name = string("u")];') if False else None
    if src == "u" and ni >= 1:
        if ni == 1:
            L.append(f'        tensor<fp16, {U}> u = add(x = x0, y = x0)[name = string("u")];')
        else:
            acc = "x0"
            for k in range(1, ni):
                nm = "u" if k == ni - 1 else f"u_{k}"
                L.append(f'        tensor<fp16, {U}> {nm} = add(x = {acc}, y = x{k})[name = string("{nm}")];')
                acc = nm
    usrc = src if (src.startswith("x") and ni >= 1) else "u"
    outs = []
    for i in range(ns):
        kind = kinds[i % len(kinds)]
        if kind == "rsw":
            L.append(f'        tensor<fp16, {S}> cur{i} = read_state(input = kv{i})[name = string("cur{i}")];')
            L.append(f'        tensor<fp16, {S}> upd{i} = slice_update(x = cur{i}, begin = begin, end = end, begin_mask = bm, end_mask = em, squeeze_mask = sm, stride = st, update = {usrc})[name = string("upd{i}")];')
            L.append(f'        write_state(data = upd{i}, input = kv{i})[name = string("ws{i}")];')
            if not noout and i < expose:
                outs.append(f"upd{i}")
        elif kind == "r":  # read only, expose as output
            L.append(f'        tensor<fp16, {S}> cur{i} = read_state(input = kv{i})[name = string("cur{i}")];')
            outs.append(f"cur{i}")
        elif kind == "rs":  # read + slice_update, output the updated tensor, no write_state
            L.append(f'        tensor<fp16, {S}> cur{i} = read_state(input = kv{i})[name = string("cur{i}")];')
            L.append(f'        tensor<fp16, {S}> upd{i} = slice_update(x = cur{i}, begin = begin, end = end, begin_mask = bm, end_mask = em, squeeze_mask = sm, stride = st, update = {usrc})[name = string("upd{i}")];')
            outs.append(f"upd{i}")
        elif kind == "w":  # write only: write_state of a full-size tensor built by concat of the input
            if i == 0 or True:
                if "cax" not in "".join(L):
                    L.append('        int32 cax = const()[val = int32(0)];')
                    L.append('        bool cil = const()[val = bool(false)];')
            vals = ", ".join([usrc] * d0)
            L.append(f'        tensor<fp16, {S}> full{i} = concat(values = ({vals}), axis = cax, interleave = cil)[name = string("full{i}")];')
            L.append(f'        write_state(data = full{i}, input = kv{i})[name = string("ws{i}")];')
        else:
            raise SystemExit("bad kind " + kind)
    for j in range(no):
        s = f"x{j % ni}" if ni > 0 else "u"
        L.append(f'        tensor<fp16, {U}> y{j} = add(x = {s}, y = {s})[name = string("y{j}")];')
        outs.append(f"y{j}")
    for c in range(chains):
        s = f"x{c % ni}" if ni > 0 else "u"
        prev = s
        for k in range(clen):
            nm = f"z{c}" if k == clen - 1 else f"z{c}_{k}"
            if op in BIN:
                L.append(f'        tensor<fp16, {U}> {nm} = {op}(x = {prev}, y = {s})[name = string("{nm}")];')
            else:
                L.append(f'        tensor<fp16, {U}> {nm} = {op}(x = {prev})[name = string("{nm}")];')
            prev = nm
        outs.append(f"z{c}")
    L.append(f"    }} -> ({', '.join(outs)});")
    L.append("}")
    print("\n".join(L))


if __name__ == "__main__":
    main()
