/*
 * The tiers of the training report's PySR formulas (catalog/benchmarks.js DISTILLATION[].pysr), and the
 * label-leakage flags the report itself raises.
 *
 * Pure and DOM-free. The thresholds are module constants; the Methodology article quotes them through
 * methodology/constants.js `js:catalog/gating.js:…` sources, so change them here only.
 *
 * What the two R² mean (the report's own definitions):
 *  - R²_PySR is the formula's fidelity to the network's own validation predictions, not to the truth;
 *  - R²_net is the network's R² against the truth (the summary table for the new species, the accuracy
 *    table for the proton's energy models); where the report prints none it is "not reported".
 * A formula is a physical law only when it describes the network faithfully AND the network predicts the
 * truth, in physical units, with no leak flag on its frame.
 *
 * tier() applies these rules in order; the first of 1–5 that matches wins:
 *  1. no formula (`absent`, or qualifier 'none')                       → not-law
 *  2. R²_PySR reported only as "< 0", or negative                       → not-law
 *  3. R²_PySR "≈ 0" (qualifier 'approx', value ≤ PARTIAL_MIN_PYSR_R2)   → not-law
 *  4. R²_PySR < PARTIAL_MIN_PYSR_R2                                     → not-law
 *  5. R²_net reported and < LAW_MIN_NET_R2                              → not-law
 *  6. R²_PySR ≥ LAW_MIN_PYSR_R2: standardised features → partial; any leak flag → partial;
 *     R²_net reported → law; otherwise → unverified
 *  7. otherwise (PARTIAL_MIN ≤ R²_PySR < LAW_MIN)                       → partial
 * Every reason is one English sentence with its numbers, negatives set with U+2212. A leak flag on a
 * not-law or partial formula is still named in the reasons, so the drawer can say it.
 */

import { typographic } from '../format.js';

export const LAW_MIN_PYSR_R2 = 0.75;
export const LAW_MIN_NET_R2 = 0.70;
export const PARTIAL_MIN_PYSR_R2 = 0.25;

export const TIERS = Object.freeze(['law', 'unverified', 'partial', 'not-law']);
export const TIER_LABELS = Object.freeze({
  law: 'Physical law',
  unverified: 'High fidelity, truth R² not reported',
  partial: 'Partial surrogate',
  'not-law': 'Not a law',
});

export const LEAK_FLAGS = Object.freeze(['local-true-angle', 'per-particle-frame', 'oracle-separation']);

/** One sentence per flag, faithful to the report's own caveats (CAVEATS in benchmarks.js). */
export const LEAK_TEXT = Object.freeze({
  'local-true-angle': 'The Local frame is rotated by the true incidence angle, so the angle can be read off the tilt of the layers: label leakage.',
  'per-particle-frame': 'The Per-shower translated and Local frames are defined per particle, so a segmentation input in them uses the label it is meant to predict: label leakage.',
  'oracle-separation': 'The angle and energy inputs are separated by the true particle_origin, so their accuracy assumes perfect segmentation.',
});

/** The flags that cap a formula's tier on (task, frame). `oracle-separation` is a global caveat, never a cap. */
export function leakFlags({ task, frame } = {}) {
  const flags = [];
  if (task === 'angle' && frame === 'local') flags.push('local-true-angle');
  if (task === 'segmentation' && (frame === 'trans' || frame === 'local')) flags.push('per-particle-frame');
  return Object.freeze(flags);
}

/** The caveats that apply to (task) without capping a tier. */
export function caveatFlags({ task } = {}) {
  return Object.freeze(task === 'angle' || task === 'energy' ? ['oracle-separation'] : []);
}

const num = (v) => typographic(String(v));

/** A qualified or plain R² as { value, qualifier, bound? }, or null when not reported. */
export function asQualified(r2) {
  if (r2 === null || r2 === undefined) return null;
  if (typeof r2 === 'number') return { value: r2, qualifier: null };
  return r2;
}

/** A qualified R² as text: "0.81", "≈ 0", "< 0", "not reported", "none". */
export function r2Text(r2) {
  const q = asQualified(r2);
  if (!q) return 'not reported';
  if (q.qualifier === 'none') return 'none';
  if (q.qualifier === 'lt') return `< ${num(q.bound ?? 0)}`;
  if (q.value === null || q.value === undefined) return 'not reported';
  if (q.qualifier === 'approx') return `≈ ${num(q.value)}`;
  if (q.qualifier === 'about') return `~${num(q.value)}`;
  return num(q.value);
}

function leakReasons(flags) {
  return flags.map((f) => LEAK_TEXT[f]);
}

/**
 * The tier of one formula: { tier, reasons }.
 * pysr: DISTILLATION[].pysr ({ r2, units, absent }); netR2: the network's R² to truth (qualified, plain or
 * null); task and frame give the leak flags.
 */
export function tier({ pysr, netR2 = null, task, frame } = {}) {
  const flags = leakFlags({ task, frame });
  const r2 = asQualified(pysr?.r2) ?? { value: null, qualifier: 'none' };
  const net = asQualified(netR2);
  const netValue = net && net.qualifier !== 'none' && net.qualifier !== 'lt' && Number.isFinite(net.value) ? net.value : null;
  const out = (name, reasons) => Object.freeze({ tier: name, reasons: Object.freeze([...reasons, ...leakReasons(flags)]) });

  // 1. No formula.
  if (!pysr || pysr.absent || r2.qualifier === 'none') {
    const printed = r2.qualifier === 'none' || (r2.value === null && r2.qualifier !== 'lt')
      ? '' : ` (the report prints R²_PySR ${r2Text(r2)} beside it)`;
    return out('not-law', [`PySR gives no meaningful formula for this model${printed}.`]);
  }
  // 2. R² below zero.
  if (r2.qualifier === 'lt' || (Number.isFinite(r2.value) && r2.value < 0)) {
    const shown = r2.qualifier === 'lt' ? 'is reported only as < 0' : `is ${num(r2.value)}`;
    return out('not-law', [`R²_PySR ${shown}: worse than predicting the mean.`]);
  }
  // 3. "≈ 0".
  if (r2.qualifier === 'approx' && Number.isFinite(r2.value) && r2.value <= PARTIAL_MIN_PYSR_R2) {
    return out('not-law', [`R²_PySR is ${r2Text(r2)}: the formula describes almost none of the network's behaviour.`]);
  }
  if (!Number.isFinite(r2.value)) {
    return out('not-law', ['R²_PySR is not reported, so the formula cannot be judged.']);
  }
  // 4. Low fidelity.
  if (r2.value < PARTIAL_MIN_PYSR_R2) {
    return out('not-law', [`R²_PySR is ${num(r2.value)}, below ${num(PARTIAL_MIN_PYSR_R2)}: the formula does not describe the network.`]);
  }
  // 5. The network itself does not predict the truth.
  if (netValue !== null && netValue < LAW_MIN_NET_R2) {
    return out('not-law', [`The formula describes a network that does not predict the truth: network R² to truth ${num(netValue)}, below ${num(LAW_MIN_NET_R2)} (R²_PySR ${num(r2.value)}).`]);
  }
  // 6. High fidelity.
  if (r2.value >= LAW_MIN_PYSR_R2) {
    if (pysr.units === 'standardised') {
      return out('partial', [`R²_PySR is ${num(r2.value)}, but the formula is written in standardised voxel features, not physical units.`]);
    }
    if (flags.length) {
      return out('partial', [`R²_PySR is ${num(r2.value)}, but a label-leakage flag on this frame caps it at a partial surrogate.`]);
    }
    if (netValue !== null) {
      return out('law', [`R²_PySR is ${num(r2.value)} (at least ${num(LAW_MIN_PYSR_R2)}) and the network's R² to truth is ${num(netValue)} (at least ${num(LAW_MIN_NET_R2)}), in physical units with no leak flag.`]);
    }
    return out('unverified', [`R²_PySR is ${num(r2.value)} (at least ${num(LAW_MIN_PYSR_R2)}), but the report gives no R² of the network to truth, so the law cannot be verified.`]);
  }
  // 7. Middle fidelity.
  const extra = pysr.units === 'standardised' ? '; the formula is written in standardised voxel features' : '';
  return out('partial', [`R²_PySR is ${num(r2.value)}, between ${num(PARTIAL_MIN_PYSR_R2)} and ${num(LAW_MIN_PYSR_R2)}: a partial description of the network${extra}.`]);
}
