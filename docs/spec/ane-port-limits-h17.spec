# port-limits-h17: the execution-time output cap, not a frontend constraint.
# Asserts the model in docs/spec/ane-port-limits-h17.md:
#   - the ANECCompile frontend accepts >>52 ports (no frontend constraint)
#   - the e5rt execution lane enforces out_cap(in) = max(63, 127 - in)
#   - the state<> budget IS a frontend constraint: 53 states compile, 54 fail
require_cmd  cargo
require_cmd  python3
require_file scripts/gen_mix_ports.py
require_file scripts/gen_states.py
require_file scripts/gen_states_width.py
require_file scripts/count_desc_records.py
require_file scripts/decode_9365.py

# --- Finding 1: the frontend does NOT reject at 52 (or 128) ---
run  python3 scripts/gen_mix_ports.py 26 26 > /tmp/pl52.mil && vendor/mil_spec/target/release/milc ane validate /tmp/pl52.mil --arch h17 2>&1
want_out  status=0x0 rc=0

run  python3 scripts/gen_mix_ports.py 64 64 > /tmp/pl128.mil && vendor/mil_spec/target/release/milc ane validate /tmp/pl128.mil --arch h17 2>&1
want_out  status=0x0 rc=0

# --- Finding 2: execution cap out_cap = max(63, 127 - in) ---
# under the cap: in=1 out=126 passes
run  python3 scripts/gen_mix_ports.py 1 126 > /tmp/pl_a.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_a.mil --steps 1 2>&1
want_out_re  step 0:

# over the cap: in=1 out=127 fails
run  python3 scripts/gen_mix_ports.py 1 127 > /tmp/pl_b.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_b.mil --steps 1 2>&1
want_out  Inference error

# the floor: in=64 out=63 passes, in=64 out=64 fails
run  python3 scripts/gen_mix_ports.py 64 63 > /tmp/pl_c.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_c.mil --steps 1 2>&1
want_out_re  step 0:

run  python3 scripts/gen_mix_ports.py 64 64 > /tmp/pl_d.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_d.mil --steps 1 2>&1
want_out  Inference error

# the sloped part: in=32 out=95 passes, in=32 out=96 fails
run  python3 scripts/gen_mix_ports.py 32 95 > /tmp/pl_e.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_e.mil --steps 1 2>&1
want_out_re  step 0:

run  python3 scripts/gen_mix_ports.py 32 96 > /tmp/pl_f.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_f.mil --steps 1 2>&1
want_out  Inference error

# --- Finding 2: the state<> budget is a FRONTEND constraint (53 pass, 54 fail) ---
# 53 independent state<> params compile
run  python3 scripts/gen_states.py 53 1 1 > /tmp/pl_s53.mil && rm -rf /tmp/pl_c53 && vendor/mil_spec/target/release/milc ane compile /tmp/pl_s53.mil -o /tmp/pl_c53 --arch h17 2>&1
want_out  status=0x0 rc=0

# 54 independent state<> params fail at ANECCompile with the BAR allocator error
run  python3 scripts/gen_states.py 54 1 1 > /tmp/pl_s54.mil && rm -rf /tmp/pl_c54 && vendor/mil_spec/target/release/milc ane compile /tmp/pl_s54.mil -o /tmp/pl_c54 --arch h17 2>&1
want_out  unable to allocate free BAR

# and 53 states actually run on the e5rt lane (not just compile)
run  python3 scripts/gen_states.py 53 1 1 > /tmp/pl_r53.mil && vendor/mil_spec/target/release/milc ane run /tmp/pl_r53.mil --steps 1 2>&1
want_out_re  step 0:

# plain io does NOT consume the state BAR table: 53 states + 32 in + 32 out still compile
run  python3 scripts/gen_states.py 53 32 32 > /tmp/pl_sio.mil && rm -rf /tmp/pl_siocc && vendor/mil_spec/target/release/milc ane compile /tmp/pl_sio.mil -o /tmp/pl_siocc --arch h17 2>&1
want_out  status=0x0 rc=0

# --- BAR characterization: the table is per-descriptor, not per-byte ---
# 54 states fails at width 4 AND width 64 (width doesn't move the boundary)
run  python3 scripts/gen_states_width.py 54 4 > /tmp/pl_w4.mil && rm -rf /tmp/pl_w4c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_w4.mil -o /tmp/pl_w4c --arch h17 2>&1
want_out  unable to allocate free BAR

run  python3 scripts/gen_states_width.py 54 64 > /tmp/pl_w64.mil && rm -rf /tmp/pl_w64c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_w64.mil -o /tmp/pl_w64c --arch h17 2>&1
want_out  unable to allocate free BAR

# and width does not let you fit more: 53 at width 256 still compiles
run  python3 scripts/gen_states_width.py 53 256 > /tmp/pl_w256.mil && rm -rf /tmp/pl_w256c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_w256.mil -o /tmp/pl_w256c --arch h17 2>&1
want_out  status=0x0 rc=0

# --- Mach-O structural model: __data segments = outputs + 2*states ---
# 53 states + 1 out -> 107 segments compiles; 54 states -> 109 segments fails.
# The decisive contrast: 52 states + 50 out = 154 segments PASSES (the cap is on
# the state COUNT, not the segment count).
run  python3 scripts/gen_states.py 52 1 50 > /tmp/pl_m52.mil && rm -rf /tmp/pl_m52c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_m52.mil -o /tmp/pl_m52c --arch h17 2>&1
want_out  status=0x0 rc=0

run  python3 scripts/gen_states.py 54 1 1 > /tmp/pl_m54.mil && rm -rf /tmp/pl_m54c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_m54.mil -o /tmp/pl_m54c --arch h17 2>&1
want_out  unable to allocate free BAR

# --- descriptor economy: 0x9344 record count is N+1, capped at 54 ---
# a 1-state program has exactly 2 descriptor-list records (1 state + 1 header)
run  python3 scripts/gen_states.py 1 1 1 > /tmp/pl_d1.mil && rm -rf /tmp/pl_d1c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_d1.mil -o /tmp/pl_d1c --arch h17 >/dev/null 2>&1 && python3 scripts/count_desc_records.py /tmp/pl_d1c/pl_d1.macho
want_out  0x9344 records: 2

# a 53-state program has exactly 54 records (53 states + 1 header = the table cap)
run  python3 scripts/gen_states.py 53 1 1 > /tmp/pl_d53.mil && rm -rf /tmp/pl_d53c && vendor/mil_spec/target/release/milc ane compile /tmp/pl_d53.mil -o /tmp/pl_d53c --arch h17 >/dev/null 2>&1 && python3 scripts/count_desc_records.py /tmp/pl_d53c/pl_d53.macho
want_out  0x9344 records: 54

# --- the 0x9365 state-copy record, decoded: shape + stride + region size ---
# a [4,4,1,1] state decodes to dim0=4 dim1=4 stride=16 region=4MiB
run  python3 scripts/gen_states.py 1 1 1 > /tmp/pl_dec.mil && rm -rf /tmp/pl_decc && vendor/mil_spec/target/release/milc ane compile /tmp/pl_dec.mil -o /tmp/pl_decc --arch h17 >/dev/null 2>&1 && python3 scripts/decode_9365.py /tmp/pl_decc/pl_dec.macho
want_out  dim0=4 dim1=4 stride=16 region=4194304
