/*
 * The literature reference curves of the energy-resolution card's E (GeV) view: the two legend curves of
 * one figure, as data.
 *
 * Provenance. Martin supplied the figure "ECCE G4 simulation - Dual-Readout Inlay, 2.55 < eta < 3.98, with
 * models S1 and S2" on 2026-11-10. Its legend prints each curve as sigma/E = a/sqrt(E) (+) b, sigma/E in
 * percent, (+) the sum in quadrature; the two curves are transcribed here and nowhere else. The figure
 * names no source publication and prints no uncertainty for either parameter. The curves are fits to that
 * simulation's charged pions and electrons in its eta range, not to this dataset's detector. They are
 * documented point estimates: `interval` is null on the source and on every entry, and nothing here
 * derives one (CLAUDE.md section 2, the recorded exception for literature curves). The figure's Yellow
 * Report bands and its digitized points were left out on purpose (Martin's decision, 2026-11-10).
 * `resolution_references.md` is the source of record and `tests/test_resolution_refs.py` pins this file to
 * its Curves table.
 *
 * Printed decimals. `dp` counts the decimals the legend prints, so toFixed(dp) reproduces '27.2', '1.0',
 * '14.0' and '0.4' (a JS number drops the trailing zero).
 *
 * Pure data and three pure helpers: no imports, every export deep-frozen.
 */

function deepFreeze(value) {
  if (value !== null && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value)) deepFreeze(child);
  }
  return value;
}

/** Where the curves come from: the figure, its date, who supplied it, the record, and the scope. */
export const REFERENCE_SOURCE = deepFreeze({
  figure: 'ECCE G4 simulation — Dual-Readout Inlay, 2.55 < η < 3.98, with models S1 and S2',
  supplied: '2026-11-10',
  by: 'Martin',
  record: 'resolution_references.md',
  interval: null,
  scope: 'fits to that simulation\'s particles in its η range, not this dataset\'s detector',
});

/** The two curves, in the record's table order. a in %*sqrt(GeV), b in %. */
export const RESOLUTION_REFERENCES = deepFreeze([
  {
    key: 'pi', particle: 'π±', form: 'quadrature', a: 27.2, b: 1.0, dp: { a: 1, b: 1 },
    printed: 'π±: σ/E = 27.2/√E ⊕ 1.0', unitA: '%·√GeV', unitB: '%', interval: null,
  },
  {
    key: 'e', particle: 'e±', form: 'quadrature', a: 14.0, b: 0.4, dp: { a: 1, b: 1 },
    printed: 'e±: σ/E = 14.0/√E ⊕ 0.4', unitA: '%·√GeV', unitB: '%', interval: null,
  },
]);

export const REFERENCE_KEYS = deepFreeze(['pi', 'e']);

export const REFERENCE_BY_KEY = deepFreeze(Object.fromEntries(RESOLUTION_REFERENCES.map((r) => [r.key, r])));

/** The entry for a key, or null. */
export function referenceOf(key) {
  return Object.prototype.hasOwnProperty.call(REFERENCE_BY_KEY, key) ? REFERENCE_BY_KEY[key] : null;
}

/** sigma/E in % at an energy in GeV: sqrt(a^2/E + b^2); null for E <= 0 or a non-finite E. */
export function referenceValue(entry, energyGeV) {
  if (!entry || !Number.isFinite(energyGeV) || energyGeV <= 0) return null;
  return Math.sqrt((entry.a * entry.a) / energyGeV + entry.b * entry.b);
}

/** The equation with the printed decimals: "σ/E = 27.2%/√E ⊕ 1.0%". */
export function referenceEquation(entry) {
  return `σ/E = ${entry.a.toFixed(entry.dp.a)}%/√E ⊕ ${entry.b.toFixed(entry.dp.b)}%`;
}

/** The button label: "π± 27.2/√E ⊕ 1.0". */
export function referenceLabel(entry) {
  return `${entry.particle} ${entry.a.toFixed(entry.dp.a)}/√E ⊕ ${entry.b.toFixed(entry.dp.b)}`;
}
