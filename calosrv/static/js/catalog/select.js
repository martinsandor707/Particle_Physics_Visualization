/*
 * The benchmark catalogue's payloads: catalogPayload(card, { species, task }) builds the static payload of
 * one of the seven catalogue cards from catalog/benchmarks.js, the training report `models_performance.md`.
 *
 * Pure and DOM-free, no request. Every payload is a deep-frozen plain-JSON object. The filter selection
 * and the experiment never apply: the numbers are the report's documented point estimates, it prints no
 * interval for any of them, and nothing here derives one (Martin's recorded exception, 2026-11-05).
 *
 * Arguments. `card` is one of CATALOG_CARDS (a RangeError otherwise). `species` is one of SPECIES or 'all'
 * (null/undefined → 'all'); `task` is one of TASKS (null/undefined → 'energy'); anything else is a
 * RangeError. Under 'all' the species list is SPECIES in its order (proton, muon, electron, pion).
 *
 * Units. Stored values keep the report's unit; the payloads below are in the DISPLAY unit named by their
 * `unit` field: angles in mrad (the triad's radians × 1000, F4), energies in GeV, segmentation E-MAE and
 * R² unitless (''). A qualified scalar is { value, qualifier, bound? } as benchmarks.js documents.
 * Frame keys stay the report's: absolute | trans | local, drawn as Absolute | Per-shower translated | Local.
 *
 * ── Common fields (every card) ────────────────────────────────────────────────────────────────────────
 *   meta: { source: 'catalog', card, species: <requested: 'proton'…|'all'>, task, report: 'models_performance.md' }
 *   filtered: false                         no selection count (models_main.js updateStatus)
 *   card, task
 *   species: ['electron'] | SPECIES         the species drawn
 *   provenance: one sentence (the report, its proton date, point estimates, no intervals, nothing applies)
 *   frames: FRAMES, frameLabels: { absolute: 'Absolute', trans: 'Per-shower translated', local: 'Local' }
 *   speciesLabels: { proton: 'Proton', … }, taskLabels: { segmentation: 'Segmentation', … }
 *
 * ── 'distill-pysr' ─────────────────────────────────────────────────────────────────────────────────────
 *   cells: [{ task, frame, entries: [entry] }]    9 cells, task-major (TASKS × FRAMES); every task shown,
 *                                                 whatever `task` is
 *   entry: { species, formula: { source, ascii, tex, units: 'physical'|'standardised', absent },
 *            r2: qualified R²_PySR (to the network), netR2: qualified network R² to truth | null,
 *            tier: { tier, label, reasons: [sentence] }, features: [key] (the tree's top features),
 *            variables: [key] (the formula's variables, English keys; [] when absent),
 *            featureMapInferred: boolean (proton: Hungarian names mapped by inference),
 *            leaks: [flag] (gating.js leakFlags), caveats: [flag] ('oracle-separation' on angle/energy) }
 *   features: { key: FEATURES[key] }             every key a chip or a formula uses
 *   tiers: TIERS, tierLabels: TIER_LABELS, thresholds: { lawMinPysrR2, lawMinNetR2, partialMinPysrR2 }
 *   leakText: LEAK_TEXT
 *
 * ── 'distill-triangle' ─────────────────────────────────────────────────────────────────────────────────
 *   unit: 'mrad' | 'GeV' | ''                    the task's display unit
 *   rows: [{ species, frame,
 *            r2: { treeNet, pysrNet, treeTruth }  qualified or null (treeTruth: proton only; pysrNet is
 *                                                 the printed R² even where the formula is absent)
 *            formulaAbsent: boolean,
 *            mae: { netTruth, treeTruth, treeNet, formula }   display unit or null; formula = the PySR
 *                                                 formula's MAE to truth (ANGLE_FORMULA_VS_NET, angle only)
 *            maeSource: { netTruth: 'triad'|'accuracy'|null, formula: 'angle-formula-vs-net'|null },
 *            maeScope: 'voxel-sample' | 'validation'  (segmentation MAEs are voxel-sample, F5: never the E-MAE)
 *            leaks: [flag], leakSignal: boolean, leakSignalText: sentence | null,
 *            missing: [sentence]              what the report does not give for this row }]
 *   Rows run species-major (the requested species), then FRAMES.
 *
 * ── 'distill-curves' ───────────────────────────────────────────────────────────────────────────────────
 *   Energy formulas only, whatever `task` is; physical units and non-absent only.
 *   formulas: [{ species, frame, source, ascii, tex, variables: [key], tier: { tier, label, reasons },
 *                r2: qualified R²_PySR, netR2: qualified | null }]
 *   x: { key: 'E_sum', label, unit: 'GeV' }      p̂ [GeV] against E_sum [GeV]
 *   variables: { centroid_r, max_hit_frac, centroid_theta, rms_r }: each { key, label, unit, domain: [lo, hi],
 *              default (the domain midpoint), usedBy: [{ species, frame }] }
 *   note: the drawing choices (defaults = midpoints; conditional at stated values, not a marginal prediction)
 *   ceiling: { value: 20, unit: 'GeV', rule }
 *   domain: curveDomain(formulas, defaults)     the x range at the default values (see curveDomain)
 *   weakTruth: { <species>: { min, max, text } } species whose network R² to truth is below LAW_MIN_NET_R2
 *   absentOrExcluded: [{ species, frame, reason }]   energy formulas not drawn, and why
 *
 * ── 'perf-catalog' ─────────────────────────────────────────────────────────────────────────────────────
 *   facets: [{ key: 'segmentation', label, unit: '', metric: 'e-mae' }, { key: 'angle', unit: 'mrad' },
 *            { key: 'energy', unit: 'GeV' }, { key: 'energy-r2', unit: '' }]
 *   rows: ACCURACY rows of the shown species (species, task, frame, metric, unit, value, tta, rmse, bias,
 *         r2, coreMae, params, treeR2Net), each with n: { events, particles } (proton 4,065 / 8,130;
 *         the others 4,000 / 8,000, particles derived as 2 per combined event, nDerived: true)
 *   notReported: { tta: [species], rmse: [species], bias: [species] }   species with no such value at all
 *
 * ── 'perf-overlap' ─────────────────────────────────────────────────────────────────────────────────────
 *   unit: the task's display unit; bins: OVERLAP.bins
 *   series: [{ species, frame, level: 'hit'|'particle', all, values: [5] }]   ("all" is the overlap table's
 *           own total, not the headline metric)
 *   events: { <species>: { all, bins: [5], unbinned } | null }   null = "N not reported" (F2)
 *   starvation: [STARVATION] when the proton energy rows are shown, else []
 *   levels: { <species>: 'hit'|'particle' } for this task
 *
 * ── 'perf-momentum-bias' ───────────────────────────────────────────────────────────────────────────────
 *   Energy, Absolute frame, whatever `task` is.
 *   windows: [{ species, centre, window: [lo, hi], windowStated, mae, bias, n, oneSigned }]  (GeV)
 *   unit: 'GeV', frame: 'absolute', scope: 'all-exported', nConsistent: { <shown species>: boolean }
 *   notReported: ['proton'] when the proton is asked for, else []
 *   empty: sentence | null                       set when no shown species has windows
 *   note: MOMENTUM_SCOPE.note
 *
 * ── 'perf-diagnostics' ─────────────────────────────────────────────────────────────────────────────────
 *   indecision: INDECISION (scope 'proton'), throughput: THROUGHPUT (scope 'proton'),
 *   architecture: ARCHITECTURE (+ scope: 'all'), datasets: DATASETS of the shown species,
 *   caveats: [CAVEATS entry] whose scope matches the shown species and `task` (an absent scope key matches all)
 *   protonOnly: true, protonOnlyBlocks: ['indecision', 'throughput'], protonShown: boolean
 *
 * curveDomain(formulas, values) → { xMax, unit: 'GeV', ceiling: 20, bracket: [0, 10], frame,
 *   bySpecies: { <species>: { eSum, reached: 'crossed'|'at-origin'|'not-reached' } } }
 *   For each species' Absolute energy formula (any frame when a species has none), the E_sum where p̂
 *   reaches the 20 GeV ceiling at `values` (missing values take the defaults), by bisection on [0, 10] GeV;
 *   a formula already at the ceiling at E_sum = 0 gives 0, one that never reaches it gives 10. xMax is the
 *   largest, and 10 when that is 0 or nothing was found: always finite and positive.
 */

import {
  ACCURACY, ANGLE_FORMULA_VS_NET, ARCHITECTURE, CAVEATS, DATASETS, DISTILLATION, FEATURES, FRAMES,
  INDECISION, MOMENTUM_SCOPE, MOMENTUM_WINDOWS, OVERLAP, SOURCE, SPECIES, STARVATION, TASKS, THROUGHPUT,
} from './benchmarks.js';
import {
  LAW_MIN_NET_R2, LAW_MIN_PYSR_R2, LEAK_TEXT, PARTIAL_MIN_PYSR_R2, TIERS, TIER_LABELS, caveatFlags,
  leakFlags, tier,
} from './gating.js';
import { compileFormula, parseFormula, variables as formulaVariables } from './formula.js';
import { typographic } from '../format.js';

export const CATALOG_CARDS = Object.freeze([
  'distill-pysr', 'distill-triangle', 'distill-curves',
  'perf-catalog', 'perf-overlap', 'perf-momentum-bias', 'perf-diagnostics',
]);

export const FRAME_LABELS = Object.freeze({ absolute: 'Absolute', trans: 'Per-shower translated', local: 'Local' });
export const SPECIES_LABELS = Object.freeze({ proton: 'Proton', muon: 'Muon', electron: 'Electron', pion: 'Pion' });
export const TASK_LABELS = Object.freeze({ segmentation: 'Segmentation', angle: 'Angle', energy: 'Energy' });
export const DISPLAY_UNIT = Object.freeze({ segmentation: '', angle: 'mrad', energy: 'GeV' });

export const PROVENANCE = `From the training report (${SOURCE.file}; proton results dated ${SOURCE.protonDate}): documented point estimates, no intervals reported; the selection and the experiment do not apply.`;

export const CURVE_CEILING = Object.freeze({
  value: 20,
  unit: 'GeV',
  rule: 'The x axis runs from 0 to the E_sum at which a species\' Absolute energy formula reaches 20 GeV (the 0–20 GeV range of the datasets), the largest over the species shown.',
});

export const CURVE_BRACKET = Object.freeze([0, 10]);

export const CURVE_VARIABLES = Object.freeze({
  centroid_r: Object.freeze({ key: 'centroid_r', label: 'centroid_r', unit: 'mm', domain: Object.freeze([0, 5000]), default: 2500 }),
  max_hit_frac: Object.freeze({ key: 'max_hit_frac', label: 'max_hit_frac', unit: '', domain: Object.freeze([0, 1]), default: 0.5 }),
  centroid_theta: Object.freeze({ key: 'centroid_theta', label: 'centroid_theta', unit: 'rad', domain: Object.freeze([0, 1]), default: 0.5 }),
  rms_r: Object.freeze({ key: 'rms_r', label: 'rms_r', unit: 'mm', domain: Object.freeze([0, 300]), default: 150 }),
});

export const CURVE_NOTE = 'The secondary variables are drawing choices: each starts at the midpoint of its stated domain. The report gives no feature distributions, so a curve is conditional at the stated values, not a marginal prediction.';

function deepFreeze(value) {
  if (value !== null && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value)) deepFreeze(child);
  }
  return value;
}

/** A plain, independent, frozen copy (the catalogue's frozen objects are never handed out by reference). */
const freezeCopy = (value) => deepFreeze(JSON.parse(JSON.stringify(value)));

const num = (v) => typographic(String(v));

/** rad → mrad without binary noise (0.00046 rad → 0.46, not 0.45999999999999996). */
const toMrad = (rad) => (rad === null || rad === undefined ? null : Number((rad * 1000).toPrecision(12)));

const accuracyRow = (species, task, frame) => ACCURACY.find((r) => r.species === species && r.task === task && r.frame === frame) ?? null;
const distillRow = (species, task, frame) => DISTILLATION.find((r) => r.species === species && r.task === task && r.frame === frame) ?? null;
const netR2Of = (species, task, frame) => accuracyRow(species, task, frame)?.r2 ?? null;

function formulaVars(pysr) {
  if (pysr.absent || !pysr.ascii) return [];
  return formulaVariables(parseFormula(pysr.ascii));
}

function tierOf(row) {
  const t = tier({ pysr: row.pysr, netR2: netR2Of(row.species, row.task, row.frame), task: row.task, frame: row.frame });
  return { tier: t.tier, label: TIER_LABELS[t.tier], reasons: [...t.reasons] };
}

function resolveArgs(card, { species, task } = {}) {
  if (!CATALOG_CARDS.includes(card)) throw new RangeError(`unknown catalogue card "${card}"`);
  const sp = species ?? 'all';
  if (sp !== 'all' && !SPECIES.includes(sp)) throw new RangeError(`unknown species "${sp}"`);
  const tk = task ?? 'energy';
  if (!TASKS.includes(tk)) throw new RangeError(`unknown task "${tk}"`);
  return { species: sp, task: tk, shown: sp === 'all' ? [...SPECIES] : [sp] };
}

// ── distill-pysr ─────────────────────────────────────────────────────────────────────────────────────────

function pysrBody(shown) {
  const used = new Set();
  const cells = [];
  for (const task of TASKS) {
    for (const frame of FRAMES) {
      const entries = shown.map((species) => {
        const row = distillRow(species, task, frame);
        const vars = formulaVars(row.pysr);
        row.features.forEach((k) => used.add(k));
        vars.forEach((k) => { if (FEATURES[k]) used.add(k); });
        return {
          species,
          formula: { source: row.pysr.source, ascii: row.pysr.ascii, tex: row.pysr.tex, units: row.pysr.units, absent: row.pysr.absent },
          r2: row.pysr.r2,
          netR2: netR2Of(species, task, frame),
          tier: tierOf(row),
          features: row.features,
          variables: vars,
          featureMapInferred: Boolean(row.pysr.featureMapInferred),
          leaks: leakFlags({ task, frame }),
          caveats: caveatFlags({ task }),
        };
      });
      cells.push({ task, frame, entries });
    }
  }
  const features = {};
  for (const k of [...used].sort()) features[k] = FEATURES[k];
  return {
    cells,
    features,
    tiers: TIERS,
    tierLabels: TIER_LABELS,
    thresholds: { lawMinPysrR2: LAW_MIN_PYSR_R2, lawMinNetR2: LAW_MIN_NET_R2, partialMinPysrR2: PARTIAL_MIN_PYSR_R2 },
    leakText: LEAK_TEXT,
  };
}

// ── distill-triangle ─────────────────────────────────────────────────────────────────────────────────────

const qualified = (v) => (v === null || v === undefined ? null : { value: v, qualifier: null });
const inDisplay = (task, v) => (v === null || v === undefined ? null : task === 'angle' ? toMrad(v) : v);

function triangleRow(species, task, frame) {
  const row = distillRow(species, task, frame);
  const acc = accuracyRow(species, task, frame);
  const unit = DISPLAY_UNIT[task];
  const missing = [];
  const isProton = species === 'proton';

  let netTruth = null;
  let netSource = null;
  if (!isProton) {
    netTruth = inDisplay(task, row.netMaeTruth);
    netSource = 'triad';
  } else if (task !== 'segmentation') {
    netTruth = acc?.value ?? null; // validation MAE, already mrad / GeV
    netSource = netTruth === null ? null : 'accuracy';
  }
  const treeTruth = isProton ? null : inDisplay(task, row.treeMaeTruth);
  const treeNet = isProton ? null : inDisplay(task, row.treeMaeNet);
  const afn = task === 'angle' ? ANGLE_FORMULA_VS_NET.find((r) => r.species === species && r.frame === frame) : null;
  const formula = afn ? afn.formulaMae : null;

  if (isProton) {
    missing.push('The report gives no tree MAEs for the proton (neither to truth nor to the network); only the R² are drawn.');
    if (task === 'segmentation') {
      missing.push('The proton segmentation network\'s MAE is the validation E-MAE, not a voxel-sample MAE, so it is not drawn here (F5).');
    } else {
      missing.push('The proton network MAE is the validation MAE of the accuracy table.');
    }
  } else {
    missing.push('The report gives no tree R² to truth for this species.');
  }
  if (task === 'angle' && formula === null) missing.push('The report gives no PySR-formula MAE to truth for this model.');
  if (task !== 'angle') missing.push('The report gives a PySR-formula MAE to truth for the angle models only.');
  if (row.pysr.absent) missing.push('PySR gives no meaningful formula for this model; its printed R² is kept.');

  let leakSignal = false;
  let leakSignalText = null;
  if (treeTruth !== null && netTruth !== null && treeTruth < netTruth) {
    leakSignal = true;
    leakSignalText = `Tree→Truth MAE ${num(treeTruth)} is below the network's ${num(netTruth)}${unit ? ` ${unit}` : ''}: a depth-4 tree beating the network on truth is a leakage signal.`;
  } else if (isProton && task === 'segmentation' && row.treeR2Truth !== null && row.treeR2Truth > row.treeR2Net + 0.1) {
    leakSignal = true;
    leakSignalText = `The tree fitted to truth reaches R² ${num(row.treeR2Truth)} against ${num(row.treeR2Net)} to the network: the truth is easier for a depth-4 tree than the network's decisions, a leakage signal.`;
  }

  return {
    species,
    frame,
    r2: { treeNet: qualified(row.treeR2Net), pysrNet: row.pysr.r2, treeTruth: qualified(row.treeR2Truth) },
    formulaAbsent: row.pysr.absent,
    mae: { netTruth, treeTruth, treeNet, formula },
    maeSource: { netTruth: netSource, formula: formula === null ? null : 'angle-formula-vs-net' },
    maeScope: row.maeScope,
    leaks: leakFlags({ task, frame }),
    leakSignal,
    leakSignalText,
    missing,
  };
}

function triangleBody(shown, task) {
  const rows = [];
  for (const species of shown) for (const frame of FRAMES) rows.push(triangleRow(species, task, frame));
  return { unit: DISPLAY_UNIT[task], rows };
}

// ── distill-curves ───────────────────────────────────────────────────────────────────────────────────────

const CURVE_DEFAULTS = Object.freeze(Object.fromEntries(Object.entries(CURVE_VARIABLES).map(([k, v]) => [k, v.default])));

/** The E_sum [GeV] range of the energy curves; see the module header. */
export function curveDomain(formulas, values = {}) {
  const ceiling = CURVE_CEILING.value;
  const [lo, hi] = CURVE_BRACKET;
  const vars = { ...CURVE_DEFAULTS, ...values };
  const bySpecies = {};
  const list = Array.isArray(formulas) ? formulas : [];
  const speciesList = [...new Set(list.map((f) => f.species))];
  let frameUsed = 'absolute';
  for (const species of speciesList) {
    const own = list.filter((f) => f.species === species && f.ascii);
    const chosen = own.find((f) => f.frame === 'absolute') ?? own[0];
    if (!chosen) continue;
    if (chosen.frame !== 'absolute') frameUsed = 'mixed';
    const fn = compileFormula(chosen.ascii);
    const g = (x) => fn({ ...vars, E_sum: x }) - ceiling;
    const gLo = g(lo);
    const gHi = g(hi);
    if (Number.isFinite(gLo) && gLo >= 0) { bySpecies[species] = { eSum: lo, reached: 'at-origin', frame: chosen.frame }; continue; }
    if (!(Number.isFinite(gHi) && gHi >= 0)) { bySpecies[species] = { eSum: hi, reached: 'not-reached', frame: chosen.frame }; continue; }
    let a = lo;
    let b = hi;
    for (let i = 0; i < 80 && b - a > 1e-12; i += 1) {
      const m = 0.5 * (a + b);
      const gm = g(m);
      if (Number.isFinite(gm) && gm >= 0) b = m; else a = m;
    }
    bySpecies[species] = { eSum: b, reached: 'crossed', frame: chosen.frame };
  }
  const found = Object.values(bySpecies).map((s) => s.eSum);
  let xMax = found.length ? Math.max(...found) : hi;
  if (!(Number.isFinite(xMax) && xMax > 0)) xMax = hi;
  return { xMax, unit: 'GeV', ceiling, bracket: [lo, hi], frame: frameUsed, bySpecies };
}

function curvesBody(shown) {
  const formulas = [];
  const absentOrExcluded = [];
  for (const species of shown) {
    for (const frame of FRAMES) {
      const row = distillRow(species, 'energy', frame);
      if (row.pysr.absent) { absentOrExcluded.push({ species, frame, reason: 'PySR gives no meaningful formula.' }); continue; }
      if (row.pysr.units !== 'physical') { absentOrExcluded.push({ species, frame, reason: 'The formula uses standardised features, so it has no physical axis.' }); continue; }
      formulas.push({
        species,
        frame,
        source: row.pysr.source,
        ascii: row.pysr.ascii,
        tex: row.pysr.tex,
        variables: formulaVars(row.pysr),
        tier: tierOf(row),
        r2: row.pysr.r2,
        netR2: netR2Of(species, 'energy', frame),
      });
    }
  }
  const variables = {};
  for (const [key, spec] of Object.entries(CURVE_VARIABLES)) {
    variables[key] = { ...spec, usedBy: formulas.filter((f) => f.variables.includes(key)).map((f) => ({ species: f.species, frame: f.frame })) };
  }
  const weakTruth = {};
  for (const species of shown) {
    const nets = FRAMES.map((frame) => netR2Of(species, 'energy', frame)?.value).filter(Number.isFinite);
    if (nets.length && nets.some((v) => v < LAW_MIN_NET_R2)) {
      const min = Math.min(...nets);
      const max = Math.max(...nets);
      const r = (v) => num(Number(v.toFixed(3)));
      weakTruth[species] = { min, max, text: `describe the network: its R² to truth is ${r(min)}–${r(max)}` };
    }
  }
  return {
    formulas,
    x: { key: 'E_sum', label: 'E_sum', unit: 'GeV' },
    variables,
    note: CURVE_NOTE,
    ceiling: CURVE_CEILING,
    domain: curveDomain(formulas, CURVE_DEFAULTS),
    weakTruth,
    absentOrExcluded,
  };
}

// ── perf-catalog ─────────────────────────────────────────────────────────────────────────────────────────

function nOf(species) {
  const d = DATASETS[species];
  return { events: d.validationEvents, particles: d.validationParticles, nDerived: species !== 'proton' };
}

function catalogBody(shown) {
  const rows = ACCURACY.filter((r) => shown.includes(r.species)).map((r) => ({ ...r, n: nOf(r.species) }));
  const none = (field) => shown.filter((s) => rows.filter((r) => r.species === s).every((r) => r[field] === null));
  return {
    facets: [
      { key: 'segmentation', label: 'Segmentation E-MAE', unit: '', metric: 'e-mae', task: 'segmentation' },
      { key: 'angle', label: 'Angle MAE [mrad]', unit: 'mrad', metric: 'mae', task: 'angle' },
      { key: 'energy', label: 'Energy MAE [GeV]', unit: 'GeV', metric: 'mae', task: 'energy' },
      { key: 'energy-r2', label: 'Energy R² [0–1]', unit: '', metric: 'r2', task: 'energy' },
    ],
    rows,
    notReported: { tta: none('tta'), rmse: none('rmse'), bias: none('bias') },
  };
}

// ── perf-overlap ─────────────────────────────────────────────────────────────────────────────────────────

function overlapBody(shown, task) {
  const series = [];
  const events = {};
  const levels = {};
  for (const species of shown) {
    const block = OVERLAP[species];
    levels[species] = block.level[task];
    events[species] = block.events ? { all: block.events.all, bins: block.events.bins, unbinned: block.unbinned } : null;
    for (const frame of FRAMES) {
      const row = block.rows.find((r) => r.task === task && r.frame === frame);
      series.push({ species, frame, level: block.level[task], all: row.all, values: row.bins });
    }
  }
  const starvation = shown.includes(STARVATION.species) && task === STARVATION.task ? [STARVATION] : [];
  return { unit: DISPLAY_UNIT[task], bins: OVERLAP.bins, series, events, starvation, levels };
}

// ── perf-momentum-bias ───────────────────────────────────────────────────────────────────────────────────

function momentumBody(shown) {
  const windows = MOMENTUM_WINDOWS.filter((w) => shown.includes(w.species));
  const nConsistent = {};
  for (const s of shown) if (s in MOMENTUM_SCOPE.nConsistent) nConsistent[s] = MOMENTUM_SCOPE.nConsistent[s];
  const notReported = shown.filter((s) => MOMENTUM_SCOPE.notReported.includes(s));
  return {
    windows,
    unit: MOMENTUM_SCOPE.unit,
    frame: 'absolute',
    scope: MOMENTUM_SCOPE.scope,
    nConsistent,
    notReported,
    empty: windows.length ? null : 'The report gives no momentum windows for the proton.',
    note: MOMENTUM_SCOPE.note,
  };
}

// ── perf-diagnostics ─────────────────────────────────────────────────────────────────────────────────────

function caveatMatches(caveat, shown, task) {
  const s = caveat.scope ?? {};
  if (s.species && !s.species.some((sp) => shown.includes(sp))) return false;
  if (s.task && !s.task.includes(task)) return false;
  return true;
}

function diagnosticsBody(shown, task) {
  const datasets = {};
  for (const s of shown) datasets[s] = DATASETS[s];
  return {
    indecision: INDECISION,
    throughput: THROUGHPUT,
    architecture: { ...ARCHITECTURE, scope: 'all' },
    datasets,
    caveats: CAVEATS.filter((c) => caveatMatches(c, shown, task)),
    protonOnly: true,
    protonOnlyBlocks: ['indecision', 'throughput'],
    protonShown: shown.includes('proton'),
  };
}

const BODIES = {
  'distill-pysr': (shown) => pysrBody(shown),
  'distill-triangle': (shown, task) => triangleBody(shown, task),
  'distill-curves': (shown) => curvesBody(shown),
  'perf-catalog': (shown) => catalogBody(shown),
  'perf-overlap': (shown, task) => overlapBody(shown, task),
  'perf-momentum-bias': (shown) => momentumBody(shown),
  'perf-diagnostics': (shown, task) => diagnosticsBody(shown, task),
};

/** The frozen payload of one catalogue card; see the module header for every field. */
export function catalogPayload(card, options = {}) {
  const { species, task, shown } = resolveArgs(card, options ?? {});
  const body = BODIES[card](shown, task);
  return freezeCopy({
    meta: { source: 'catalog', card, species, task, report: SOURCE.file },
    filtered: false,
    card,
    task,
    species: shown,
    provenance: PROVENANCE,
    frames: FRAMES,
    frameLabels: FRAME_LABELS,
    speciesLabels: SPECIES_LABELS,
    taskLabels: TASK_LABELS,
    ...body,
  });
}
