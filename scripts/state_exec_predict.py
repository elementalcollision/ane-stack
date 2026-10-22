#!/usr/bin/env python3
# state_exec_predict.py <d0> <d1> <d2> <d3> — predict whether an fp16 ANE state
# state<tensor<fp16, [d0,d1,d2,d3]>> EXECUTES (it compiles regardless).
#
# Measured rule (h17, macOS 26.7.1; 190+ random shapes, N=1..53 states, 0 misses):
#   rows        = d0*d1*d2                      (everything except the innermost W axis)
#   true_bytes  = rows * d3 * 2                 (what the compiler sizes the buffer from)
#   padded      = rows * ceil(2*d3/64) * 64     (rows are laid out with a 64 B stride)
#   PASS  iff  ceil(true_bytes/16384) == ceil(padded/16384)     (16 KiB pages)
# otherwise execute_sync fails with "Program Inference error" (status 0x1d).
# Corollaries: d3 % 32 == 0 always passes (no padding); for d3 < 32 the state
# must satisfy d0*d1*d2 <= 256 (one 16 KiB page of 64 B rows).
# Prints one line; exit status 0 = predicted PASS, 1 = predicted FAIL.
import sys

PAGE = 16384
LINE = 64


def predict(d0: int, d1: int, d2: int, d3: int):
    rows = d0 * d1 * d2
    true_bytes = rows * d3 * 2
    padded = rows * (-(-2 * d3 // LINE)) * LINE
    pages = lambda b: -(-b // PAGE)
    return rows, true_bytes, padded, pages(true_bytes), pages(padded)


def main() -> None:
    d0, d1, d2, d3 = (int(a) for a in sys.argv[1:5])
    rows, tb, pb, pt, pp = predict(d0, d1, d2, d3)
    ok = pt == pp
    print(f"{d0}x{d1}x{d2}x{d3} rows={rows} true_bytes={tb} padded_bytes={pb} "
          f"pages_true={pt} pages_padded={pp} predicted={'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
