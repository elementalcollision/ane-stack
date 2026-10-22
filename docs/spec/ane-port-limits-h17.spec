# ane-port-limits-h17: ANE resource budgets on h17 (M5), re-measured 2026-10-22.
# Asserts the model in docs/spec/ane-port-limits-h17.md (section numbers match):
#   1. execution io cap:  live_in + unique_out <= 127 (no floor)
#   2. frontend io cap:   declared_in + out <= 255 (validate AND compile)
#   3. states cost ports: +1 per state, +1 per exposed update; write_state is a
#                         liveness root (an input feeding only it still counts)
#   4. BAR pool:          every __FVMLIB segment is one BAR id, 55 ids in all;
#                         each state<> surface needs its own segment, so
#                         53 states fit with >=1 plain input and >=1 output,
#                         54 fit with no plain input; one more fails
#   5. binding records:   0x9344/0x934a/0x9442 are 12-byte buffer bindings whose
#                         slot word is a BAR ordinal; 0x9344 is not a 54-entry table
#   6. copy records:      tag = presence flags; stride = 8*min(ceil(log2 dim1),4)
#   7. state execution:   executes iff 64-B row padding needs no extra 16 KiB page
#                         (rows <= 256 is SUFFICIENT when d3 <= 32); state dtype
#                         fp16/int16/int8/uint8/bool ok, fp32/int32 rejected
#   8. h16g vs h17:       same compile-time caps and laws; 0x934a 1 vs 2 per
#                         self-add task (add(x, x)) (cross-compiled only)
# Rules: judge pass/fail by want_rc (a FAILING run also prints "step 0:"); anchor
# every count with $ ("records: 2" also matches 20-29). See docs/evidence/SPEC.md.
require_cmd  cargo
require_cmd  python3
require_hw   sysctl -n machdep.cpu.brand_string | grep -q '^Apple M'
require_file scripts/gen_live_ports.py
require_file scripts/gen_mix_ports.py
require_file scripts/gen_dup_returns.py
require_file scripts/gen_states.py
require_file scripts/gen_states_width.py
require_file scripts/gen_states_nd.py
require_file scripts/count_desc_records.py
require_file scripts/decode_slot_ordinals.py
require_file scripts/decode_copy_records.py
require_file scripts/hwx_layout.py
require_file scripts/state_exec_predict.py
require_file scripts/gen_state_dtype.py
require_file scripts/decode_block_trailers.py
require_file scripts/decode_copy_words.py
setup        cd vendor/mil_spec && cargo build --release -q -p milc
require_artifact vendor/mil_spec/target/release/milc

# provenance of this run (informational; the laws below were measured on
# Mac17,7 / macOS 26.7.1 25G241 — re-check them on any other build)
run  sysctl -n hw.model && sw_vers -productVersion && sw_vers -buildVersion
want_rc      0

# ============================================================================
# 1. Execution-time io cap: live_in + out <= 127. NO floor at 63.
#    (old claim out_cap = max(63, 127 - in) predicts PASS for every *_fail
#    line below with in > 64; all of them fail on hardware)
# ============================================================================
run  python3 scripts/gen_live_ports.py 1 126 > /tmp/pl_l1_126.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_l1_126.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_live_ports.py 1 127 > /tmp/pl_l1_127.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_l1_127.mil --steps 1 2>&1
want_rc      1
want_out     status=0x2 : statusType=0x9: Program Inference error

run  python3 scripts/gen_live_ports.py 32 95 > /tmp/pl_l32_95.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_l32_95.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_live_ports.py 32 96 > /tmp/pl_l32_96.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_l32_96.mil --steps 1 2>&1
want_rc      1
want_out     status=0x2 : statusType=0x9: Program Inference error

# past the old "floor": in = 65, 100, 127 with every input live
run  python3 scripts/gen_live_ports.py 65 62 > /tmp/pl_l65_62.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_l65_62.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_live_ports.py 65 63 > /tmp/pl_l65_63.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_l65_63.mil --steps 1 2>&1
want_rc      1
want_out     status=0x2 : statusType=0x9: Program Inference error

run  python3 scripts/gen_live_ports.py 100 27 > /tmp/pl_l100_27.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_l100_27.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_live_ports.py 100 28 > /tmp/pl_l100_28.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_l100_28.mil --steps 1 2>&1
want_rc      1
want_out     status=0x2 : statusType=0x9: Program Inference error

run  python3 scripts/gen_live_ports.py 126 1 > /tmp/pl_l126_1.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_l126_1.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_live_ports.py 127 1 > /tmp/pl_l127_1.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_l127_1.mil --steps 1 2>&1
want_rc      1
want_out     status=0x2 : statusType=0x9: Program Inference error

# dead inputs are free on the run path: gen_mix_ports 100 63 references only 63
# of its 100 inputs (this is where the old "floor at 63" came from)
run  python3 scripts/gen_mix_ports.py 100 63 > /tmp/pl_m100_63.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_m100_63.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

# outputs count UNIQUE returned tensors: one tensor returned 200 times runs
run  python3 scripts/gen_dup_returns.py 200 > /tmp/pl_dup200.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_dup200.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

# a count budget, not a byte budget: 16 KiB ports hit the same 127 boundary
run  python3 scripts/gen_live_ports.py 1 126 8192 > /tmp/pl_w1_126.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_w1_126.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_live_ports.py 1 127 8192 > /tmp/pl_w1_127.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_w1_127.mil --steps 1 2>&1
want_rc      1
want_out     status=0x2 : statusType=0x9: Program Inference error

# ============================================================================
# 2. Frontend io cap (validate/compile): DECLARED in + out <= 255.
# ============================================================================
run  python3 scripts/gen_mix_ports.py 127 128 > /tmp/pl_v127_128.mil && vendor/mil_spec/target/release/milc ane validate /tmp/pl_v127_128.mil --arch h17 2>&1
want_rc      0
want_out     status=0x0 rc=0

run  python3 scripts/gen_mix_ports.py 128 128 > /tmp/pl_v128_128.mil && vendor/mil_spec/target/release/milc ane validate /tmp/pl_v128_128.mil --arch h17 2>&1
want_rc      1
want_out     MaxLiveInLiveOutExceeded

# validate counts declared (dead) inputs: 254+1 ok, 255+1 rejected ...
run  python3 scripts/gen_mix_ports.py 254 1 > /tmp/pl_v254_1.mil && vendor/mil_spec/target/release/milc ane validate /tmp/pl_v254_1.mil --arch h17 2>&1
want_rc      0
want_out     status=0x0 rc=0

run  python3 scripts/gen_mix_ports.py 255 1 > /tmp/pl_v255_1.mil && vendor/mil_spec/target/release/milc ane validate /tmp/pl_v255_1.mil --arch h17 2>&1
want_rc      1
want_out     MaxLiveInLiveOutExceeded

# ... while the run path prunes them first: the same 255+1 file runs
run  python3 scripts/gen_mix_ports.py 255 1 > /tmp/pl_r255_1.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_r255_1.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

# the compile path enforces the same 255
run  rm -rf /tmp/pl_cc127 && vendor/mil_spec/target/release/milc ane compile /tmp/pl_v127_128.mil -o /tmp/pl_cc127 --arch h17 2>&1
want_rc      0
want_out     status=0x0 rc=0

run  rm -rf /tmp/pl_cc128 && vendor/mil_spec/target/release/milc ane compile /tmp/pl_v128_128.mil -o /tmp/pl_cc128 --arch h17 2>&1
want_rc      1
want_out     MaxLiveInLiveOutExceeded

# states count at the frontend too: 126 exposed states + 1 in + 1 out = 254 ok,
# 127 -> 256 rejected
run  python3 scripts/gen_states_nd.py 126 4 4 1 1 1 1 direct > /tmp/pl_fs126.mil && vendor/mil_spec/target/release/milc ane validate /tmp/pl_fs126.mil --arch h17 2>&1
want_rc      0
want_out     status=0x0 rc=0

run  python3 scripts/gen_states_nd.py 127 4 4 1 1 1 1 direct > /tmp/pl_fs127.mil && vendor/mil_spec/target/release/milc ane validate /tmp/pl_fs127.mil --arch h17 2>&1
want_rc      1
want_out     MaxLiveInLiveOutExceeded

# ============================================================================
# 3. States cost io ports: each state is 1 input port, each exposed (returned)
#    update is 1 output port. 53 states + 1 in + 53 exposed + 20 out = 127.
# ============================================================================
run  python3 scripts/gen_states_nd.py 53 4 4 1 1 1 20 direct > /tmp/pl_sp20.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_sp20.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_states_nd.py 53 4 4 1 1 1 21 direct > /tmp/pl_sp21.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_sp21.mil --steps 1 2>&1
want_rc      1
want_out     status=0x2 : statusType=0x9: Program Inference error

# updates not returned: a state costs one port (53 + 1 + 73 = 127)
run  python3 scripts/gen_states_nd.py 53 4 4 1 1 1 73 direct noupd > /tmp/pl_sn73.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_sn73.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_states_nd.py 53 4 4 1 1 1 74 direct noupd > /tmp/pl_sn74.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_sn74.mil --steps 1 2>&1
want_rc      1
want_out     status=0x2 : statusType=0x9: Program Inference error

# write_state is a liveness root: 100 inputs feed only the state update (u
# chain) and 24/25 outputs read x0..x23/x24. 100 + 3 + 24 = 127 runs, 128 fails.
# ("live = reachable from a returned output" would count 25 inputs and predict
# that OUT = 25 runs)
run  python3 scripts/gen_states_nd.py 3 4 4 1 1 100 24 noupd > /tmp/pl_ws24.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_ws24.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_states_nd.py 3 4 4 1 1 100 25 noupd > /tmp/pl_ws25.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_ws25.mil --steps 1 2>&1
want_rc      1
want_out     status=0x2 : statusType=0x9: Program Inference error

# so the old spec's "53 states + 32 in + 32 out" compiles but does not run
# (53 + 32 + 53 + 32 = 170 > 127)
run  python3 scripts/gen_states.py 53 32 32 > /tmp/pl_sio.mil && rm -rf /tmp/pl_siocc && vendor/mil_spec/target/release/milc ane compile /tmp/pl_sio.mil -o /tmp/pl_siocc --arch h17 2>&1
want_rc      0
want_out     status=0x0 rc=0

run  vendor/mil_spec/target/release/milc ane run /tmp/pl_sio.mil --steps 1 2>&1
want_rc      1
want_out     status=0x2 : statusType=0x9: Program Inference error

# ============================================================================
# 4. The BAR pool: 55 ids, one per __FVMLIB segment. A state surface always
#    owns a segment; non-state io packs into one shared data + one shared
#    const segment. So max states = 55 - (shared segments).
# ============================================================================
# 53 states + 1 in + 1 out: compiles, and the pool is exactly full
run  python3 scripts/gen_states.py 53 1 1 > /tmp/pl_s53.mil && rm -rf /tmp/pl_c53 && vendor/mil_spec/target/release/milc ane compile /tmp/pl_s53.mil -o /tmp/pl_c53 --arch h17 2>&1 && python3 scripts/hwx_layout.py /tmp/pl_c53/pl_s53.macho
want_rc      0
want_out     status=0x0 rc=0
want_out     segments=57 fvmlib=55 fvmlib_data=54 fvmlib_const=1

run  vendor/mil_spec/target/release/milc ane run /tmp/pl_s53.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_states.py 54 1 1 > /tmp/pl_s54.mil && rm -rf /tmp/pl_c54 && vendor/mil_spec/target/release/milc ane compile /tmp/pl_s54.mil -o /tmp/pl_c54 --arch h17 2>&1
want_rc      1
want_out     unable to allocate free BAR

# the run lane (e5rt compiles via aned) refuses the same 54-state program
run  vendor/mil_spec/target/release/milc ane run /tmp/pl_s54.mil --steps 1 2>&1
want_rc      1
want_out     ANECCompile() FAILED

# weights and lookup-table ops do not lower the cap: 53 states + an inline
# conv weight, or + a sigmoid, compile and run (the __KERN_0 segment is shed);
# 54 + conv still fail
run  python3 scripts/gen_states_nd.py 53 4 8 1 1 1 1 direct conv=1 > /tmp/pl_cv53.mil && rm -rf /tmp/pl_cv53c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_cv53.mil -o /tmp/pl_cv53c --arch h17 2>&1 && python3 scripts/hwx_layout.py /tmp/pl_cv53c/pl_cv53.macho && vendor/mil_spec/target/release/milc ane run /tmp/pl_cv53.mil --steps 1 2>&1
want_rc      0
want_out     fvmlib=55
want_out     kern=0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_states_nd.py 54 4 8 1 1 1 1 direct conv=1 > /tmp/pl_cv54.mil && rm -rf /tmp/pl_cv54c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_cv54.mil -o /tmp/pl_cv54c --arch h17 2>&1
want_rc      1
want_out     unable to allocate free BAR

run  python3 scripts/gen_states_nd.py 53 4 4 1 1 1 1 direct lut=sigmoid > /tmp/pl_lt53.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_lt53.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

# split vs packed layout: const+data sections <= 55 -> one segment each;
# 56 -> one shared const + one shared data segment
run  python3 scripts/gen_states.py 0 5 50 > /tmp/pl_sp50.mil && rm -rf /tmp/pl_sp50c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_sp50.mil -o /tmp/pl_sp50c --arch h17 >/dev/null 2>&1 && python3 scripts/hwx_layout.py /tmp/pl_sp50c/pl_sp50.macho
want_rc      0
want_out     fvmlib=55 fvmlib_data=50 fvmlib_const=5

run  python3 scripts/gen_states.py 0 5 51 > /tmp/pl_sp51.mil && rm -rf /tmp/pl_sp51c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_sp51.mil -o /tmp/pl_sp51c --arch h17 >/dev/null 2>&1 && python3 scripts/hwx_layout.py /tmp/pl_sp51c/pl_sp51.macho
want_rc      0
want_out     fvmlib=2 fvmlib_data=1 fvmlib_const=1 data_sections=51

# no plain input => no const segment => 54 states compile AND run; 55 fail.
# (refutes "53 states" as the cap itself)
run  python3 scripts/gen_states_nd.py 54 4 4 1 1 0 1 > /tmp/pl_z54.mil && rm -rf /tmp/pl_z54c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_z54.mil -o /tmp/pl_z54c --arch h17 2>&1 && python3 scripts/hwx_layout.py /tmp/pl_z54c/pl_z54.macho
want_rc      0
want_out     status=0x0 rc=0
want_out     segments=57 fvmlib=55 fvmlib_data=55 fvmlib_const=0

run  vendor/mil_spec/target/release/milc ane run /tmp/pl_z54.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_states_nd.py 55 4 4 1 1 0 1 > /tmp/pl_z55.mil && rm -rf /tmp/pl_z55c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_z55.mil -o /tmp/pl_z55c --arch h17 2>&1
want_rc      1
want_out     unable to allocate free BAR

# the cap is per segment, not per byte or per io port: big states + 32/32 io
# still pack to 53, and 54 still fail; state width does not move it either
run  python3 scripts/gen_states_nd.py 53 64 32 1 1 32 32 > /tmp/pl_b53.mil && rm -rf /tmp/pl_b53c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_b53.mil -o /tmp/pl_b53c --arch h17 2>&1
want_rc      0
want_out     status=0x0 rc=0

run  python3 scripts/gen_states_nd.py 54 64 32 1 1 32 32 > /tmp/pl_b54.mil && rm -rf /tmp/pl_b54c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_b54.mil -o /tmp/pl_b54c --arch h17 2>&1
want_rc      1
want_out     unable to allocate free BAR

run  python3 scripts/gen_states_width.py 54 64 > /tmp/pl_w64.mil && rm -rf /tmp/pl_w64c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_w64.mil -o /tmp/pl_w64c --arch h17 2>&1
want_rc      1
want_out     unable to allocate free BAR

run  python3 scripts/gen_states_width.py 53 256 > /tmp/pl_w256.mil && rm -rf /tmp/pl_w256c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_w256.mil -o /tmp/pl_w256c --arch h17 2>&1
want_rc      0
want_out     status=0x0 rc=0

# state dtype does not move the pool: int8 / int16 states hit the same 53/54
# with a plain input, and int8 the same 54/55 without one
run  python3 scripts/gen_state_dtype.py int8 53 > /tmp/pl_d8_53.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_d8_53.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_state_dtype.py int8 54 > /tmp/pl_d8_54.mil && rm -rf /tmp/pl_d8_54c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_d8_54.mil -o /tmp/pl_d8_54c --arch h17 2>&1
want_rc      1
want_out     unable to allocate free BAR

run  python3 scripts/gen_state_dtype.py int16 54 > /tmp/pl_d16_54.mil && rm -rf /tmp/pl_d16_54c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_d16_54.mil -o /tmp/pl_d16_54c --arch h17 2>&1
want_rc      1
want_out     unable to allocate free BAR

run  python3 scripts/gen_state_dtype.py int8 54 noin > /tmp/pl_d8n54.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_d8n54.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_state_dtype.py int8 55 noin > /tmp/pl_d8n55.mil && rm -rf /tmp/pl_d8n55c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_d8n55.mil -o /tmp/pl_d8n55c --arch h17 2>&1
want_rc      1
want_out     unable to allocate free BAR

# ============================================================================
# 5. Buffer bindings: 0x9344 (primary source) / 0x934a (more sources) /
#    0x9442 (destination) are 12-byte records; slot word = 0x2300 + 0x80*ordinal
#    of an __FVMLIB segment. 0x9344 is NOT a 54-entry state table.
# ============================================================================
run  python3 scripts/decode_slot_ordinals.py /tmp/pl_c53/pl_s53.macho && python3 scripts/count_desc_records.py /tmp/pl_c53/pl_s53.macho
want_rc      0
want_out     records=54 bars=55 max_ordinal=54 input_ordinal=54 format_ok=1
want_out_re  0x9344 records: 54$

# block framing: __text = 0x10-byte preamble + blocks [u16 idx][u16 size in u32
# words]; every block ends with a FLAT trailer [9344][934a]*[9442][1340][1341][1440].
# The ori page v1's "0x9344 record with sub-records at +0x0c/+0x18/+0x24/+0x30/
# +0x38/+0x40" is exactly that trailer laid end to end (h17: two 0x934a).
run  python3 scripts/decode_block_trailers.py /tmp/pl_c53/pl_s53.macho
want_rc      0
want_out     blocks=107 chain_ok=1
want_out     1x[9344,934a,934a,9442,1340,1341,1440]
want_out     first9344: block=0 9344@+0x00 934a@+0x0c 934a@+0x18 9442@+0x24 1340@+0x30 1341@+0x38 1440@+0x40 end@+0x48 nexthdr@+0x4c
want_out     nextblock: idx=1 size=39 prewords=1,30001,10001,1,1,4 frame=0x9361

# h16g has one 0x934a, so every later member moves 12 bytes up
run  python3 scripts/gen_states.py 53 1 1 > /tmp/pl_btg.mil && rm -rf /tmp/pl_btgc && vendor/mil_spec/target/release/milc ane compile /tmp/pl_btg.mil -o /tmp/pl_btgc --arch h16g >/dev/null 2>&1 && python3 scripts/decode_block_trailers.py /tmp/pl_btgc/pl_btg.macho
want_rc      0
want_out     first9344: block=0 9344@+0x00 934a@+0x0c 9442@+0x18 1340@+0x24 1341@+0x2c 1440@+0x34 end@+0x3c nexthdr@+0x3c

# v1's "u32 tail (1, 3, 1, 1, 1, 4)" is the NEXT block's pre-frame window and
# mirrors the copy record's header: dim1 = 9 -> stride class 5, last word 9
run  python3 scripts/gen_states_nd.py 3 4 9 1 1 1 1 direct > /tmp/pl_bd9.mil && rm -rf /tmp/pl_bd9c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_bd9.mil -o /tmp/pl_bd9c --arch h17 >/dev/null 2>&1 && python3 scripts/decode_block_trailers.py /tmp/pl_bd9c/pl_bd9.macho
want_rc      0
want_out     nextblock: idx=1 size=39 prewords=1,50001,10001,1,1,9 frame=0x9361

# a stateless program never has 0 records (v1 said 0): min(in, out) with a
# plain input; with none, exactly one special (fill) binding. That program
# compiles but does not run.
run  python3 scripts/gen_states.py 0 1 1 > /tmp/pl_z011.mil && rm -rf /tmp/pl_z011c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_z011.mil -o /tmp/pl_z011c --arch h17 >/dev/null 2>&1 && python3 scripts/count_desc_records.py /tmp/pl_z011c/pl_z011.macho && python3 scripts/hwx_layout.py /tmp/pl_z011c/pl_z011.macho
want_rc      0
want_out_re  0x9344 records: 1$
want_out     data_sections=1 const_sections=1

run  python3 scripts/gen_states.py 0 0 1 > /tmp/pl_z001.mil && rm -rf /tmp/pl_z001c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_z001.mil -o /tmp/pl_z001c --arch h17 >/dev/null 2>&1 && python3 scripts/count_desc_records.py /tmp/pl_z001c/pl_z001.macho && python3 scripts/decode_slot_ordinals.py /tmp/pl_z001c/pl_z001.macho
want_rc      0
want_out_re  0x9344 records: 1$
want_out     format_ok=1 special=1

run  vendor/mil_spec/target/release/milc ane run /tmp/pl_z001.mil --steps 1 2>&1
want_rc      1
want_out     e5_compiler_compile

# no plain input: raw 0x9344 = K + 1 at N = 1, K + 2 from N = 2 on
run  python3 scripts/gen_states.py 1 0 1 > /tmp/pl_i101.mil && rm -rf /tmp/pl_i101c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_i101.mil -o /tmp/pl_i101c --arch h17 >/dev/null 2>&1 && python3 scripts/count_desc_records.py /tmp/pl_i101c/pl_i101.macho
want_rc      0
want_out_re  0x9344 records: 2$

run  python3 scripts/gen_states.py 2 0 1 > /tmp/pl_i201.mil && rm -rf /tmp/pl_i201c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_i201.mil -o /tmp/pl_i201c --arch h17 >/dev/null 2>&1 && python3 scripts/count_desc_records.py /tmp/pl_i201c/pl_i201.macho
want_rc      0
want_out_re  0x9344 records: 4$

# with no plain input, one 0x9344 binds the fill source: bar_word 0x2080 is
# below 0x2300 (not an __FVMLIB segment) and is counted as special
run  python3 scripts/decode_slot_ordinals.py /tmp/pl_z54c/pl_z54.macho
want_rc      0
want_out     format_ok=1 special=1

# the old spec's own 53-state program has 85 0x9344 records and compiles
# (0x9344 = exposed states + max(1, min(in, out)) for gen_states.py)
run  python3 scripts/count_desc_records.py /tmp/pl_siocc/pl_sio.macho && python3 scripts/decode_slot_ordinals.py /tmp/pl_siocc/pl_sio.macho
want_rc      0
want_out_re  0x9344 records: 85$
want_out     bars=55 max_ordinal=54

# with no state update returned, 53 states have ONE 0x9344 record — and 54
# still fail: the cap does not live in a 0x9344 table
run  python3 scripts/gen_states_nd.py 53 4 4 1 1 1 1 direct noupd > /tmp/pl_nu53.mil && rm -rf /tmp/pl_nu53c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_nu53.mil -o /tmp/pl_nu53c --arch h17 >/dev/null 2>&1 && python3 scripts/count_desc_records.py /tmp/pl_nu53c/pl_nu53.macho
want_rc      0
want_out_re  0x9344 records: 1$

run  python3 scripts/gen_states_nd.py 54 4 4 1 1 1 1 direct noupd > /tmp/pl_nu54.mil && rm -rf /tmp/pl_nu54c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_nu54.mil -o /tmp/pl_nu54c --arch h17 2>&1
want_rc      1
want_out     unable to allocate free BAR

# __data sections = states + exposed updates + plain outputs; 0x9442 = one per
# __data section (outputs + 2N here, NOT 2N+1: 52 states + 50 out -> 154)
run  python3 scripts/gen_states.py 52 1 50 > /tmp/pl_m52.mil && rm -rf /tmp/pl_m52c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_m52.mil -o /tmp/pl_m52c --arch h17 >/dev/null 2>&1 && python3 scripts/count_desc_records.py /tmp/pl_m52c/pl_m52.macho 0x9442 && python3 scripts/hwx_layout.py /tmp/pl_m52c/pl_m52.macho
want_rc      0
want_out_re  0x9442 records: 154$
want_out     data_sections=154

run  python3 scripts/gen_states_nd.py 10 4 4 1 1 1 5 direct noupd > /tmp/pl_nu10.mil && rm -rf /tmp/pl_nu10c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_nu10.mil -o /tmp/pl_nu10c --arch h17 >/dev/null 2>&1 && python3 scripts/hwx_layout.py /tmp/pl_nu10c/pl_nu10.macho
want_rc      0
want_out     data_sections=15 const_sections=1

# ============================================================================
# 6. State-copy records. tag = 0x9261 + 0x100*[dim1!=1] + 4*[dim0!=1]
#    - [dim1==16]; stride word = 8*min(ceil(log2 dim1), 4). The update-row
#    record (0x9361 family) carries dim1 and stride: it is NOT a fixed template.
# ============================================================================
# old law min(2*dim1+8, 32) predicts 12 / 18 / 26 for dim1 = 2 / 5 / 9
run  python3 scripts/gen_states_nd.py 1 4 2 1 1 1 1 direct > /tmp/pl_cr2.mil && rm -rf /tmp/pl_cr2c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_cr2.mil -o /tmp/pl_cr2c --arch h17 >/dev/null 2>&1 && python3 scripts/decode_copy_records.py /tmp/pl_cr2c/pl_cr2.macho
want_rc      0
want_out     summary: records=1 long=0 short=1 dim0=4 dim1=2 stride=8 uniform=yes region=2097152

run  python3 scripts/gen_states_nd.py 1 4 5 1 1 1 1 direct > /tmp/pl_cr5.mil && rm -rf /tmp/pl_cr5c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_cr5.mil -o /tmp/pl_cr5c --arch h17 >/dev/null 2>&1 && python3 scripts/decode_copy_records.py /tmp/pl_cr5c/pl_cr5.macho
want_rc      0
want_out     summary: records=1 long=0 short=1 dim0=4 dim1=5 stride=24 uniform=yes region=5242880

run  python3 scripts/gen_states_nd.py 1 4 9 1 1 1 1 direct > /tmp/pl_cr9.mil && rm -rf /tmp/pl_cr9c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_cr9.mil -o /tmp/pl_cr9c --arch h17 >/dev/null 2>&1 && python3 scripts/decode_copy_records.py /tmp/pl_cr9c/pl_cr9.macho
want_rc      0
want_out     summary: records=1 long=0 short=1 dim0=4 dim1=9 stride=32 uniform=yes region=9437184

# the update-row ("read-side") record carries the shape too
run  python3 scripts/gen_states_nd.py 1 4 8 1 1 1 1 direct > /tmp/pl_cr8.mil && rm -rf /tmp/pl_cr8c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_cr8.mil -o /tmp/pl_cr8c --arch h17 >/dev/null 2>&1 && python3 scripts/decode_copy_records.py /tmp/pl_cr8c/pl_cr8.macho --reads
want_rc      0
want_out     kind=read compact=0 first=1 short=0 long=0 dim1=8 stride=24

# family tag is a presence-flag word: dim1 == 16, dim1 == 1, dim0 == 1
run  python3 scripts/gen_states_nd.py 1 4 16 1 1 1 1 direct > /tmp/pl_cr16.mil && rm -rf /tmp/pl_cr16c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_cr16.mil -o /tmp/pl_cr16c --arch h17 >/dev/null 2>&1 && python3 scripts/decode_copy_records.py /tmp/pl_cr16c/pl_cr16.macho --tags
want_rc      0
want_out_re  ^tags: 0x9360=1 0x9364=1$

run  python3 scripts/gen_states_nd.py 1 4 1 1 1 1 1 direct > /tmp/pl_cr1.mil && rm -rf /tmp/pl_cr1c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_cr1.mil -o /tmp/pl_cr1c --arch h17 >/dev/null 2>&1 && python3 scripts/decode_copy_records.py /tmp/pl_cr1c/pl_cr1.macho --tags
want_rc      0
want_out_re  ^tags: 0x9261=1 0x9265=1$

run  python3 scripts/gen_states_nd.py 1 1 8 1 1 1 1 direct > /tmp/pl_cre.mil && rm -rf /tmp/pl_crec && vendor/mil_spec/target/release/milc ane compile /tmp/pl_cre.mil -o /tmp/pl_crec --arch h17 >/dev/null 2>&1 && python3 scripts/decode_copy_records.py /tmp/pl_crec/pl_cre.macho --tags
want_rc      0
want_out_re  ^tags: 0x9361=2$

# exception: dim3 == 256 or dim2 == 256 (exactly) emits NO copy record, yet the
# program runs; 255 still emits them
run  python3 scripts/gen_states_nd.py 1 4 4 1 256 1 1 direct > /tmp/pl_nc256.mil && rm -rf /tmp/pl_nc256c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_nc256.mil -o /tmp/pl_nc256c --arch h17 >/dev/null 2>&1 && python3 scripts/decode_copy_records.py /tmp/pl_nc256c/pl_nc256.macho --tags && vendor/mil_spec/target/release/milc ane run /tmp/pl_nc256.mil --steps 1 2>&1
want_rc      0
want_out_re  ^tags: none$
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_states_nd.py 1 2 8 256 32 1 1 direct > /tmp/pl_nd256.mil && rm -rf /tmp/pl_nd256c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_nd256.mil -o /tmp/pl_nd256c --arch h17 >/dev/null 2>&1 && python3 scripts/decode_copy_records.py /tmp/pl_nd256c/pl_nd256.macho --tags
want_rc      0
want_out_re  ^tags: none$

run  python3 scripts/gen_states_nd.py 1 4 4 1 255 1 1 direct > /tmp/pl_nc255.mil && rm -rf /tmp/pl_nc255c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_nc255.mil -o /tmp/pl_nc255c --arch h17 >/dev/null 2>&1 && python3 scripts/decode_copy_records.py /tmp/pl_nc255c/pl_nc255.macho --tags
want_rc      0
want_out_re  ^tags: 0x9361=1 0x9365=1$

# state-out (0x9365) records, direct update source: SHORT layout only for the last one; region is
# rowbits << 16 (= dim1 MiB), the same in both layouts
run  python3 scripts/decode_copy_records.py /tmp/pl_c53/pl_s53.macho | tail -1
want_rc      0
want_out     summary: records=53 long=52 short=1 dim0=4 dim1=4 stride=16 uniform=yes region=4194304

# word-level fields (decode_copy_words.py, offsets from the 0x1041 marker):
# pitch = 64*ceil(d3/32) bytes = the padded row of the §7 page rule; slice =
# pitch*dim1 (the ori v2 page's "+0x33 flag byte 01 -> 02" is slice's 2nd byte);
# SHORT map 1M,RB,RB,RB|RB where the 1M word is ceil(d3/8) MiB
run  python3 scripts/decode_copy_words.py /tmp/pl_cr2c/pl_cr2.macho && python3 scripts/gen_states_nd.py 1 4 4 1 33 1 1 direct > /tmp/pl_cw33.mil && rm -rf /tmp/pl_cw33c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_cw33.mil -o /tmp/pl_cw33c --arch h17 >/dev/null 2>&1 && python3 scripts/decode_copy_words.py /tmp/pl_cw33c/pl_cw33.macho
want_rc      0
want_out     dim0=4 dim1=2 flagw=8028 pitch=64 slice=128 slice2=128 form=803c/0142 map=1M,RB,RB,RB|RB
want_out     dim0=4 dim1=4 flagw=8028 pitch=128 slice=512 slice2=512 form=803c/0142 map=0x00500000,RB,RB,RB|RB

# the ori v2 page's "+0x42 shape-class selector 0x42 -> 0x62" is the LONG form
# word (0x0162) of a non-last record, not a shape field: SHORT [4,4] vs SHORT
# [32,8] differ at exactly these 9 offsets (no 0x42)
run  python3 scripts/gen_states_nd.py 1 32 8 1 1 1 1 direct > /tmp/pl_cw328.mil && rm -rf /tmp/pl_cw328c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_cw328.mil -o /tmp/pl_cw328c --arch h17 >/dev/null 2>&1 && python3 scripts/gen_states_nd.py 1 4 4 1 1 1 1 direct > /tmp/pl_cw44.mil && rm -rf /tmp/pl_cw44c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_cw44.mil -o /tmp/pl_cw44c --arch h17 >/dev/null 2>&1 && python3 scripts/decode_copy_words.py /tmp/pl_cw44c/pl_cw44.macho --diff /tmp/pl_cw328c/pl_cw328.macho
want_rc      0
want_out_re  ^diff: 0x0a 0x0e 0x1c 0x33 0x4a 0x4e 0x52 0x5e 0x77$

# direct LONG layout (non-last state-out records of the 53-state program) and
# the SHORT first word at d3 = 9 (= ceil(9/8) = 2 MiB)
run  python3 scripts/decode_copy_words.py /tmp/pl_c53/pl_s53.macho | head -1 && python3 scripts/gen_states_nd.py 1 4 4 1 9 1 1 direct > /tmp/pl_cw9.mil && rm -rf /tmp/pl_cw9c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_cw9.mil -o /tmp/pl_cw9c --arch h17 >/dev/null 2>&1 && python3 scripts/decode_copy_words.py /tmp/pl_cw9c/pl_cw9.macho
want_rc      0
want_out     form=803e/0162 map=RB,1M,RB,RB,RB|2RB
want_out     pitch=64 slice=256 slice2=256 form=803c/0142 map=0x00200000,RB,RB,RB|RB

# the page rule's padded row IS the pitch word: head_dim 80 -> pitch 192
# (dim0 = 1, so the state-out record carries the update-row tag: use --last)
run  python3 scripts/gen_states_nd.py 1 1 85 1 80 1 1 direct > /tmp/pl_cw85.mil && rm -rf /tmp/pl_cw85c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_cw85.mil -o /tmp/pl_cw85c --arch h17 >/dev/null 2>&1 && python3 scripts/decode_copy_words.py /tmp/pl_cw85c/pl_cw85.macho --last
want_rc      0
want_out     pitch=192

# the two form words are independent: a one-state computed-source program with
# 2 inputs and 3 outputs has 803e/0142
run  python3 scripts/gen_states_nd.py 1 4 4 1 1 2 3 add > /tmp/pl_cwca.mil && rm -rf /tmp/pl_cwcac && vendor/mil_spec/target/release/milc ane compile /tmp/pl_cwca.mil -o /tmp/pl_cwcac --arch h17 >/dev/null 2>&1 && python3 scripts/decode_copy_words.py /tmp/pl_cwcac/pl_cwca.macho
want_rc      0
want_out     form=803e/0142

# no returned update => no state-out record at all
run  python3 scripts/decode_copy_records.py /tmp/pl_nu10c/pl_nu10.macho --tags
want_rc      0
want_out_re  ^tags: 0x9361=10$

# ============================================================================
# 7. State execution page rule: rows (d0*d1*d2) are padded to 64 B; the state
#    executes iff that padding needs no extra 16 KiB page. Compiles regardless.
# ============================================================================
run  python3 scripts/gen_states_nd.py 1 4 64 1 1 1 1 direct > /tmp/pl_pg64.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_pg64.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_states_nd.py 1 4 65 1 1 1 1 direct > /tmp/pl_pg65.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_pg65.mil --steps 1 2>&1
want_rc      1
want_out     status=0x1d : statusType=0x9: Program Inference error

run  python3 scripts/gen_states_nd.py 1 4 128 1 32 1 1 direct > /tmp/pl_pg128.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_pg128.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/state_exec_predict.py 4 65 1 1
want_rc      1
want_out     predicted=FAIL

# rows <= 256 is sufficient (d3 <= 32), not necessary: 300 rows of 31 run,
# 260 rows of 31 fail (the padding crosses a page in one case, not the other)
run  python3 scripts/gen_states_nd.py 1 1 300 1 31 1 1 direct > /tmp/pl_p300.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_p300.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_states_nd.py 1 1 260 1 31 1 1 direct > /tmp/pl_p260.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_p260.mil --steps 1 2>&1
want_rc      1
want_out     status=0x1d : statusType=0x9: Program Inference error

# d3 > 32 and not a multiple of 32 (head_dim 80): fails from 86 rows
run  python3 scripts/gen_states_nd.py 1 1 85 1 80 1 1 direct > /tmp/pl_p85.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_p85.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_states_nd.py 1 1 86 1 80 1 1 direct > /tmp/pl_p86.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_p86.mil --steps 1 2>&1
want_rc      1
want_out     status=0x1d : statusType=0x9: Program Inference error

# state dtype: int8 and bool states compile and run (io/compute stay fp16);
# fp32 and int32 states are rejected
run  python3 scripts/gen_state_dtype.py int8 > /tmp/pl_dt8.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_dt8.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_state_dtype.py bool > /tmp/pl_dtb.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_dtb.mil --steps 1 2>&1
want_rc      0
want_out_re  ^step 0: [0-9]

run  python3 scripts/gen_state_dtype.py fp32 > /tmp/pl_dtf.mil && rm -rf /tmp/pl_dtfc && vendor/mil_spec/target/release/milc ane compile /tmp/pl_dtf.mil -o /tmp/pl_dtfc --arch h17 2>&1
want_rc      1
want_out     CompilationFailure

run  python3 scripts/gen_state_dtype.py int32 > /tmp/pl_dti.mil && rm -rf /tmp/pl_dtic && vendor/mil_spec/target/release/milc ane compile /tmp/pl_dti.mil -o /tmp/pl_dtic --arch h17 2>&1
want_rc      1
want_out     status=0x1 rc=1

# ============================================================================
# 8. h16g (M4) vs h17 (M5), cross-compiled on this M5 host: same caps and
#    laws; 0x934a is emitted once per self-add task (add(x, x)) on h16g, twice
#    on h17 (+1 per add task, NOT +1 per program).
# ============================================================================
run  python3 scripts/gen_states.py 53 32 32 > /tmp/pl_aio.mil && rm -rf /tmp/pl_aio4 /tmp/pl_aio5 && vendor/mil_spec/target/release/milc ane compile /tmp/pl_aio.mil -o /tmp/pl_aio4 --arch h16g >/dev/null 2>&1 && vendor/mil_spec/target/release/milc ane compile /tmp/pl_aio.mil -o /tmp/pl_aio5 --arch h17 >/dev/null 2>&1 && echo "h16g: $(python3 scripts/count_desc_records.py /tmp/pl_aio4/pl_aio.macho 0x934a)  h17: $(python3 scripts/count_desc_records.py /tmp/pl_aio5/pl_aio.macho 0x934a)"
want_rc      0
want_out_re  ^h16g: 0x934a records: 32  h17: 0x934a records: 64$

run  python3 scripts/gen_states.py 53 1 1 > /tmp/pl_amm.mil && rm -rf /tmp/pl_am4 /tmp/pl_am5 && vendor/mil_spec/target/release/milc ane compile /tmp/pl_amm.mil -o /tmp/pl_am4 --arch h16g >/dev/null 2>&1 && vendor/mil_spec/target/release/milc ane compile /tmp/pl_amm.mil -o /tmp/pl_am5 --arch h17 >/dev/null 2>&1 && echo "h16g: $(python3 scripts/count_desc_records.py /tmp/pl_am4/pl_amm.macho 0x934a)  h17: $(python3 scripts/count_desc_records.py /tmp/pl_am5/pl_amm.macho 0x934a)" && python3 scripts/decode_slot_ordinals.py /tmp/pl_am4/pl_amm.macho
want_rc      0
want_out_re  ^h16g: 0x934a records: 1  h17: 0x934a records: 2$
want_out     records=54 bars=55 max_ordinal=54 input_ordinal=54 format_ok=1

run  python3 scripts/gen_states.py 54 1 1 > /tmp/pl_a54.mil && rm -rf /tmp/pl_a54c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_a54.mil -o /tmp/pl_a54c --arch h16g 2>&1
want_rc      1
want_out     unable to allocate free BAR

run  python3 scripts/gen_states_nd.py 1 4 5 1 1 1 1 direct > /tmp/pl_ag5.mil && rm -rf /tmp/pl_ag5c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_ag5.mil -o /tmp/pl_ag5c --arch h16g >/dev/null 2>&1 && python3 scripts/decode_copy_records.py /tmp/pl_ag5c/pl_ag5.macho
want_rc      0
want_out     summary: records=1 long=0 short=1 dim0=4 dim1=5 stride=24 uniform=yes region=5242880

run  python3 scripts/gen_mix_ports.py 128 128 > /tmp/pl_g128.mil && vendor/mil_spec/target/release/milc ane validate /tmp/pl_g128.mil --arch h16g 2>&1
want_rc      1
want_out     MaxLiveInLiveOutExceeded
