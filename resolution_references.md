# Literature reference curves for the energy-resolution card

The E (GeV) view of the Models page's energy-resolution card (`res-scaling`) can draw two literature
reference curves and divide its ratio panel by either one. This file is their source of record:
`calosrv/static/js/catalog/resolution_refs.js` is pinned to the table below by
`tests/test_resolution_refs.py`, and no other number of the figure is recorded anywhere in the repository.

## Provenance

Both curves are transcribed from the legend of the figure "ECCE G4 simulation — Dual-Readout Inlay,
2.55 < η < 3.98, with models S1 and S2", supplied by Martin on 2026-11-10.

- **Form.** The legend prints each curve as σ/E = a/√E ⊕ b, with σ/E in percent, so a is in %·√GeV and
  b in %. Here ⊕ is the sum in quadrature, √((a/√E)² + b²).
- **What the figure does not say.** It names no source publication for the curves and prints no
  uncertainty for either parameter.
- **What the curves describe.** They are fits to that simulation's charged pions and electrons in its η
  range. They do not describe this dataset's detector.
- **How the dashboard draws them.** As documented point estimates. No interval is reported, and none is
  derived: see CLAUDE.md §2, the recorded exception for transcribed literature reference curves.

Left out on purpose (Martin's decision, 2026-11-10):

- the figure's HCal and ECal Yellow Report requirement bands, whose parameters the figure does not print;
- its digitized π± and e± points.

## Curves

| key | particle | form | a (%·√GeV) | b (%) | as printed |
|---|---|---|---|---|---|
| pi | π± | quadrature | 27.2 | 1.0 | π±: σ/E = 27.2/√E ⊕ 1.0 |
| e | e± | quadrature | 14.0 | 0.4 | e±: σ/E = 14.0/√E ⊕ 0.4 |
