# Evidence — A.5 item 4: no second macOS 27.0 host is available

Lane: **L-SCHED**. Work item: ADR-0002 A.5 item 4.

**Answer: cannot be done with current hardware.** Recorded so the gap is
explicit rather than implied by its absence.

---

## 1. What is on the tailnet

`tailscale status` at time of writing:

| host | OS | state |
|---|---|---|
| `daves-m5-macbook-pro` | macOS | online — **this machine, 26.7.1** |
| `davids-mac-mini` | macOS | idle — **the 27.0 box, M4 Pro** |
| `bev-imac-new` | macOS | **offline, last seen 55 days** |
| `nuc-amd-bos` | Windows | offline, 29 days |
| `badger-nas`, `glkvm` | Linux | offline |
| `iphone182` | iOS | offline, 200 days |
| `leonardo-newton-uat`, `hello.ts.net` | Linux | online, but not Apple Silicon |

So there is exactly **one macOS 27.0 host** (`davids-mac-mini`) and exactly one
other Mac, which is off.

## 2. What was tried for the offline Mac

- Direct ping to `100.112.106.25` → 100 % packet loss.
- Port 22 → closed.
- The tailnet still advertises it with a last-seen timestamp, so the node
  exists in the tailnet's memory but is unreachable — no wake attempt was made,
  because a 55-day-offline Mac is asleep/powered down and cannot be woken from
  here without a wake-on-LAN path or physical access.

**No hardware exists to satisfy this item at present.**

## 3. Consequence

ADR-0002's A.5 item 4 — "a second 27.0 host; the current data is n=1 per OS, and
one host is a machine configuration as much as an OS build" — **stays open and
is blocked on hardware, not on work.**

This matters for how the other A.5 results should be read. Everything measured
on 27.0 (the deploy gate opening for h16g images, the 16384-op artifact, the
`0x13`/`underlying=0x1` codes) is **one M4 Pro on one 27.0 build (26A428)**. The
local 26.7.1 host is an M5 — so the OS×SoC confound noted elsewhere is unresolved
and will remain so until a third host appears.

## 4. What would unblock it

Any of: power on `bev-imac-new`; another Apple Silicon Mac on macOS 27.x; or a
CI runner with macOS 27.x (none configured — checkout `.github/workflows/`).

Until then, treat "open on 27.0" as "**open on this one 27.0 M4 Pro**".

## 5. Cross-lane

- No vendor change, no patch, no manifest drift.
- **L-PROBE** is now also working; the `h17`-dialect probe reports should carry
  the same caveat if they were measured only on this one 27.0 host.
