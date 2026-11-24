#!/usr/bin/env python3
# gen_p3model.py <outdir> [layers] — write a tiny synthetic Qwen3 checkpoint
# (config.json + model.safetensors, fp16) that `milc convert` accepts. It is
# the "/tmp/p3model" fixture of docs/spec/shape-flex-matrix.spec: matrix A's
# converted decoder, the model `predseg` loads as /tmp/p3/c_range.mlpackage.
#
# The original /tmp/p3model (2026-10-21) was never committed and is gone. This
# regenerates a model with the shapes `predseg` hard-codes: hidden 16, head_dim
# 8, and (with milc convert's default --max-kv 2048) a [1, 1, S, 2048] mask.
# The layout and weight pattern mirror upstream's own tiny_qwen3 test fixture
# (vendor/mil_spec/crates/milc/tests/seq_range_cli.rs), with 2 layers by
# default (writeup: "tiny-Qwen3, 2 layers, KV state").
#
# Size: ~12 KiB of weights; the converted KV state is (2*layers, 1, 2048, 8)
# fp16, 128 KiB at 2 layers. Deterministic: same args, same bytes.
import json
import os
import struct
import sys

HIDDEN, HEADS, KV_HEADS, HEAD_DIM, INTER, VOCAB = 16, 2, 1, 8, 32, 64


def tensors(layers: int) -> list[tuple[str, list[int]]]:
    out: list[tuple[str, list[int]]] = []
    for n in range(layers):
        l = f"model.layers.{n}"
        out += [
            (f"{l}.input_layernorm.weight", [HIDDEN]),
            (f"{l}.post_attention_layernorm.weight", [HIDDEN]),
            (f"{l}.self_attn.q_proj.weight", [HEADS * HEAD_DIM, HIDDEN]),
            (f"{l}.self_attn.k_proj.weight", [KV_HEADS * HEAD_DIM, HIDDEN]),
            (f"{l}.self_attn.v_proj.weight", [KV_HEADS * HEAD_DIM, HIDDEN]),
            (f"{l}.self_attn.o_proj.weight", [HIDDEN, HEADS * HEAD_DIM]),
            (f"{l}.self_attn.q_norm.weight", [HEAD_DIM]),
            (f"{l}.self_attn.k_norm.weight", [HEAD_DIM]),
            (f"{l}.mlp.gate_proj.weight", [INTER, HIDDEN]),
            (f"{l}.mlp.up_proj.weight", [INTER, HIDDEN]),
            (f"{l}.mlp.down_proj.weight", [HIDDEN, INTER]),
        ]
    out += [("model.norm.weight", [HIDDEN]), ("lm_head.weight", [VOCAB, HIDDEN])]
    return out


def main() -> None:
    if len(sys.argv) not in (2, 3):
        sys.exit("usage: gen_p3model.py <outdir> [layers]   (layers defaults to 2)")
    outdir = sys.argv[1]
    layers = int(sys.argv[2]) if len(sys.argv) == 3 else 2
    if layers < 1:
        sys.exit("gen_p3model.py: layers must be >= 1")
    os.makedirs(outdir, exist_ok=True)

    config = {
        "model_type": "qwen3",
        "hidden_size": HIDDEN,
        "num_hidden_layers": layers,
        "num_attention_heads": HEADS,
        "num_key_value_heads": KV_HEADS,
        "head_dim": HEAD_DIM,
        "intermediate_size": INTER,
        "vocab_size": VOCAB,
        "rms_norm_eps": 1e-6,
        "rope_theta": 1000000.0,
        "max_position_embeddings": 2048,
        "tie_word_embeddings": False,
    }
    with open(os.path.join(outdir, "config.json"), "w") as f:
        json.dump(config, f, indent=1)
        f.write("\n")

    # safetensors: u64 LE header length, JSON header, then the raw data.
    header: dict[str, dict] = {}
    data = bytearray()
    for name, shape in tensors(layers):
        n = 1
        for d in shape:
            n *= d
        off = len(data)
        for i in range(n):
            data += struct.pack("<e", 0.02 + (i % 7) * 0.01)
        header[name] = {"dtype": "F16", "shape": shape, "data_offsets": [off, len(data)]}
    hdr = json.dumps(header, separators=(",", ":")).encode()
    with open(os.path.join(outdir, "model.safetensors"), "wb") as f:
        f.write(struct.pack("<Q", len(hdr)))
        f.write(hdr)
        f.write(data)


if __name__ == "__main__":
    main()
