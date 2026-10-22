# ane-port-limits-h17: ANE resource budgets on h17 (M5), re-measured 2026-10-22.
# Asserts the model in docs/spec/ane-port-limits-h17.md:
#   1. execution io cap:  live_in + unique_out (+ states, + exposed states) <= 127
#   2. frontend io cap:   declared_in + out (+ states, + exposed states)    <= 255
#   3. BAR pool:          every __FVMLIB segment is one BAR id, 55 ids in all;
#                         each state<> surface needs its own segment, so
#                         53 states fit with >=1 plain input and >=1 output,
#                         54 fit with no plain input; one more fails ("free BAR")
#   4. binding records:   0x9344/0x934a/0x9442 are 12-byte buffer bindings whose
#                         slot word is a BAR ordinal; 0x9344 is not a 54-entry table
#   5. copy records:      tag = presence flags; stride = 8*min(ceil(log2 dim1),4)
#   6. state execution:   a state executes iff 64-B row padding needs no extra
#                         16 KiB page (d3 < 32 => d0*d1*d2 <= 256)
#   7. h16g vs h17:       same caps and laws; 0x934a is 1 vs 2 per binary-add task
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
setup        cd vendor/mil_spec && cargo build --release -q -p milc
require_artifact vendor/mil_spec/target/release/milc

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

# ============================================================================
# 5. Buffer bindings: 0x9344 (primary source) / 0x934a (more sources) /
#    0x9442 (destination) are 12-byte records; slot word = 0x2300 + 0x80*ordinal
#    of an __FVMLIB segment. 0x9344 is NOT a 54-entry state table.
# ============================================================================
run  python3 scripts/decode_slot_ordinals.py /tmp/pl_c53/pl_s53.macho && python3 scripts/count_desc_records.py /tmp/pl_c53/pl_s53.macho
want_rc      0
want_out     records=54 bars=55 max_ordinal=54 input_ordinal=54 format_ok=1
want_out_re  0x9344 records: 54$

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

# state-out (0x9365) records: SHORT layout only for the last one; region is
# rowbits << 16 (= dim1 MiB), the same in both layouts
run  python3 scripts/decode_copy_records.py /tmp/pl_c53/pl_s53.macho | tail -1
want_rc      0
want_out     summary: records=53 long=52 short=1 dim0=4 dim1=4 stride=16 uniform=yes region=4194304

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

# ============================================================================
# 8. h16g (M4) vs h17 (M5), cross-compiled on this M5 host: same caps and
#    laws; 0x934a is emitted once per binary-add task on h16g, twice on h17
#    (+1 per add task, NOT +1 per program).
# ============================================================================
run  python3 scripts/gen_states.py 53 32 32 > /tmp/pl_aio.mil && rm -rf /tmp/pl_aio4 /tmp/pl_aio5 && vendor/mil_spec/target/release/milc ane compile /tmp/pl_aio.mil -o /tmp/pl_aio4 --arch h16g >/dev/null 2>&1 && vendor/mil_spec/target/release/milc ane compile /tmp/pl_aio.mil -o /tmp/pl_aio5 --arch h17 >/dev/null 2>&1 && echo "h16g: $(python3 scripts/count_desc_records.py /tmp/pl_aio4/pl_aio.macho 0x934a)  h17: $(python3 scripts/count_desc_records.py /tmp/pl_aio5/pl_aio.macho 0x934a)"
want_rc      0
want_out     h16g: 0x934a records: 32  h17: 0x934a records: 64

run  python3 scripts/gen_states.py 53 1 1 > /tmp/pl_amm.mil && rm -rf /tmp/pl_am4 /tmp/pl_am5 && vendor/mil_spec/target/release/milc ane compile /tmp/pl_amm.mil -o /tmp/pl_am4 --arch h16g >/dev/null 2>&1 && vendor/mil_spec/target/release/milc ane compile /tmp/pl_amm.mil -o /tmp/pl_am5 --arch h17 >/dev/null 2>&1 && echo "h16g: $(python3 scripts/count_desc_records.py /tmp/pl_am4/pl_amm.macho 0x934a)  h17: $(python3 scripts/count_desc_records.py /tmp/pl_am5/pl_amm.macho 0x934a)" && python3 scripts/decode_slot_ordinals.py /tmp/pl_am4/pl_amm.macho
want_rc      0
want_out     h16g: 0x934a records: 1  h17: 0x934a records: 2
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
