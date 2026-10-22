# port-limits-h17: the execution-time output cap, not a frontend constraint.
# Asserts the model in docs/spec/ane-port-limits-h17.md:
#   - the ANECCompile frontend accepts >>52 ports (no frontend constraint)
#   - the e5rt execution lane enforces out_cap(in) = max(63, 127 - in)
require_cmd  cargo
require_cmd  python3
require_file scripts/gen_mix_ports.py

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
