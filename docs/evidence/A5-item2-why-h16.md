# Evidence — A.5 item 2: why is H16 accepted on macOS 27.0?

Lane: **L-SCHED**. Work item: ADR-0002 A.5 item 2 ("Separates allowlist from
capability").

**Answer: capability, not allowlist. The loader keys on the compiled target, not
on a provenance label.** And it is not a signature check either — the artifacts
are ours, produced locally by `ANECCompile`.

Hosts: local macOS 26.7.1 (M5) compiles; `davids-mac-mini` macOS **27.0**
(26A428, M4 Pro) loads.

---

## 1. The naive read

H16 loads, H13/H14/H15/H17 fail. The obvious explanations were: an H16
**allowlist**, or H16 being the only arch this loader has **capability** for.
The two predict different behaviour for a *relabelled* image, so they are
separable by one experiment.

## 2. First, what actually differs between the two artifacts

The h16g-compiled (accepted) and h17-compiled (rejected) artifacts from the
same 13-op stateful model are **65536 bytes each, both compiled locally**, and:

- **1614 bytes** live in one 2048-byte region at offset 20480–22528, and are
  **entirely the compiler's own embedded command line** — `-t h16g` vs `-t h17`
  plus ~64 flags (`--fdram-allocator=ffreuse`, `--fsignature=ident`,
  `--max-kernel-section-size=134217728`, …) and the `-i`/`-o` paths.
- **14 bytes** elsewhere, in the compiled code region near the end of the file.
- The rest is byte-identical.

So the "arch difference" is mostly **a build-log string, not a structural
field**. That alone should reduce confidence in the allowlist story.

## 3. The experiment that separates them

Edit the embedded label to contradict the compiled code, keeping the file length
identical, then load on macOS 27.0:

| artifact | code target | embedded label | verdict on 27.0 |
|---|---|---|---|
| original `tl_h16g` | h16g | `-t h16g` | **LOAD_OK** |
| `fake_h17` | **h16g** | `-t h17` (2 bytes changed) | **LOAD_OK** |
| original `tl_h17` | h17 | `-t h17` | REFUSED (`0x13`) |
| `fake_h16g` | **h17** | `-t h16g` (2 bytes changed) | **REFUSED** (`0x13`) |

Both directions agree: **the label is ignored; the compiled target decides.**

`fake_h17` differs from the accepted original by exactly **2 bytes** and still
loads. `fake_h16g` differs from the refused original by exactly **2 bytes** and
still fails.

## 4. What this rules in and out

- **Capability, not allowlist.** If H16 were on a name allowlist, `fake_h17`
  would have been rejected for carrying the H17 label. It loaded.
- **Not a signing/provenance check.** All four artifacts are ours, compiled
  locally by `ANECCompile` in this session — including the two that load. Apple
  signs none of them, and two load anyway.
- **Not arch-*independent* either.** The H17-code artifacts are refused on 27.0
  even when labelled H16, so the loader really does resolve the target from the
  image and refuse what it cannot run.

So: macOS 27.0's `_ANEClient` precompiled loader can run **h16g-targeted**
images, cannot run h17-targeted ones, and reads the target from the compiled
program rather than from any label or signature.

## 5. Important limit on the conclusion

The 14 non-string differing bytes between h16g and h17 code were **not**
individually attributed. This experiment proves the *label* is not the
discriminator; it does not prove the discriminator is a single field among those
14 bytes. A byte-level bisection of that small region is the next step if a
precise field is wanted — cheap now that the label nuisance is removed, but not
done here.

Also: n=1 host on 27.0 (M4 Pro), n=1 on 26.7.1 (M5), so the OS×SoC confound
from A.5 item 4 still applies.

## 6. Cross-lane

- Method and artifacts: `/tmp/hw/{tl_h16g,tl_h17,fake_h17,fake_h16g}/*.macho`.
  Reproduced deterministically with the byte-based label swap shown above.
- **Request to L-PROBE:** "H16 is uniquely accepted on 27.0" belongs in
  `ANE_FRONTEND_SPEC.md` along with the ~52-port ceiling already requested, and
  the *mechanism* (target read from the image, label ignored) is a more useful
  statement than the bare verdict table.
- No vendor change, no patch, no manifest drift.
