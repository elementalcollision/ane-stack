# docs/spec — our extensions to ANE_FRONTEND_SPEC.md

`vendor/mil_spec/ANE_FRONTEND_SPEC.md` is upstream's empirical grammar of the
ANE-eligible MIL dialect. **Do not edit it** — it is the record of what was
measured on `h16g` (M4).

Our extensions live here, alongside it:

- `ane-frontend-h17.md` — `PROBE-1`: the dialect re-probed on the current SoC.
  Highest-value new artifact available to us; nobody has published this.
- `shape-flex-matrix.md` — `PROBE-3`: fixed / EnumeratedShapes / ShapeRange ×
  compute units × execution lane, as an executable table.

Rule: every verdict in these files names the build it was measured on, and how.
A verdict without provenance is not a verdict.
