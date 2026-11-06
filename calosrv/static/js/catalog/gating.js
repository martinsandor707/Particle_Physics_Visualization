/*
 * The tiers of the training report's PySR formulas (catalog/benchmarks.js DISTILLATION[].pysr), and the
 * label-leakage flags the report itself raises.
 *
 * Pure and DOM-free. The thresholds are module constants; the Methodology article quotes them through
 * methodology/constants.js `js:catalog/gating.js:…` sources, so change them here only.
 *
 * What the two R² mean (the report's own definitions):
 *  - R² (PySR) is the formula's fidelity to the network's own validation predictions, not to the truth;
 *  - R²_net is the network's R² against the truth (the summary table for the new species, the accuracy
 *    table for the proton's energy models); where the report prints none it is "not reported".
 * The top tier is a law CANDIDATE (Martin's decision 5, 2026-11-05), never a physical law: the report
 * says so itself ("the tree and the formula explain the network's behaviour; they are not an independent
 * physical law"), and the rule below bounds the formula's fidelity to the network and the network's to the
 * truth, not the formula's own fit to the truth. Its reason quotes that sentence.
 *
 * tier() applies these rules in order; the first of 1–5 that matches wins:
 *  1. no formula (`absent`, or qualifier 'none')                       → not-law
 *  2. R² (PySR) reported only as "< 0", or negative                     → not-law
 *  3. R² (PySR) "≈ 0" (qualifier 'approx', value ≤ PARTIAL_MIN_PYSR_R2) → not-law
 *  4. R² (PySR) < PARTIAL_MIN_PYSR_R2                                   → not-law
 *  5. R²_net reported and < LAW_MIN_NET_R2                              → not-law
 *  6. R² (PySR) ≥ LAW_MIN_PYSR_R2: standardised features → partial; any leak flag → partial;
 *     R²_net reported → law (candidate); otherwise → unverified
 *  7. otherwise (PARTIAL_MIN ≤ R² (PySR) < LAW_MIN)                     → partial
 * Every reason is one English sentence with its numbers, negatives set with U+2212. A reported R² is set
 * by `fmt` (a qualified scalar → its digits): the default is the shortest form; catalog/select.js passes
 * its `printed` form, so a reason carries the report's own decimals (1.000 stays 1.000). The thresholds
 * print with THRESHOLD_DP decimals (0.70, never 0.7). A leak flag on a not-law or partial formula is still
 * named in the reasons, so the drawer can say it.
 */

import { typographic } from '../format.js';

export const LAW_MIN_PYSR_R2 = 0.75;
export const LAW_MIN_NET_R2 = 0.70;
export const PARTIAL_MIN_PYSR_R2 = 0.25;
/** The decimals a threshold prints with in a reason: one precision for the three of them. */
export const THRESHOLD_DP = 2;

export const TIERS = Object.freeze(['law', 'unverified', 'partial', 'not-law']);
export const TIER_LABELS = Object.freeze({
  law: 'Law candidate',
  unverified: 'High fidelity, truth R² not reported',
  partial: 'Partial surrogate',
  'not-law': 'Not a law',
});

/** The report's own sentence the top tier's reason quotes (Martin's decision 5). */
export const NOT_A_PHYSICAL_LAW = 'the tree and the formula explain the network\'s behaviour; they are not an independent physical law';

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

/** The default number formatter of tier(): a qualified scalar's value in its shortest form. */
export const shortestForm = (q) => num(q.value);

/** A threshold as a reason prints it: THRESHOLD_DP decimals. */
export const thresholdText = (v) => typographic(Number(v).toFixed(THRESHOLD_DP));

/** A qualified or plain R² as { value, qualifier, bound? }, or null when not reported. */
export function asQualified(r2) {
  if (r2 === null || r2 === undefined) return null;
  if (typeof r2 === 'number') return { value: r2, qualifier: null };
  return r2;
}

/**
 * A qualified R² as text: "0.81", "≈ 0", "< 0", "not reported", "none". `fmt` sets the number (a qualified
 * scalar → its digits; the shortest form by default).
 */
export function r2Text(r2, fmt = shortestForm) {
  const q = asQualified(r2);
  if (!q) return 'not reported';
  if (q.qualifier === 'none') return 'none';
  if (q.qualifier === 'lt') return `< ${fmt({ ...q, value: q.bound ?? 0 })}`;
  if (q.value === null || q.value === undefined) return 'not reported';
  if (q.qualifier === 'approx') return `≈ ${fmt(q)}`;
  if (q.qualifier === 'about') return `~${fmt(q)}`;
  return fmt(q);
}

function leakReasons(flags) {
  return flags.map((f) => LEAK_TEXT[f]);
}

/**
 * The tier of one formula: { tier, reasons }.
 * pysr: DISTILLATION[].pysr ({ r2, units, absent }); netR2: the network's R² to truth (qualified, plain or
 * null); task and frame give the leak flags; fmt: a qualified scalar → its printed digits (the shortest
 * form by default; select.js passes the report's printed decimals).
 */
export function tier({ pysr, netR2 = null, task, frame, fmt = shortestForm } = {}) {
  const flags = leakFlags({ task, frame });
  const r2 = asQualified(pysr?.r2) ?? { value: null, qualifier: 'none' };
  const net = asQualified(netR2);
  const netOk = net && net.qualifier !== 'none' && net.qualifier !== 'lt' && Number.isFinite(net.value);
  const netValue = netOk ? net.value : null;
  const out = (name, reasons) => Object.freeze({ tier: name, reasons: Object.freeze([...reasons, ...leakReasons(flags)]) });
  const R2 = () => fmt(r2);
  const NET = () => fmt(net);
  const T = thresholdText;

  // 1. No formula.
  if (!pysr || pysr.absent || r2.qualifier === 'none') {
    const printed = r2.qualifier === 'none' || (r2.value === null && r2.qualifier !== 'lt')
      ? '' : ` (the report prints R² (PySR) ${r2Text(r2, fmt)} beside it)`;
    return out('not-law', [`PySR gives no meaningful formula for this model${printed}.`]);
  }
  // 2. R² below zero.
  if (r2.qualifier === 'lt' || (Number.isFinite(r2.value) && r2.value < 0)) {
    const shown = r2.qualifier === 'lt' ? 'is reported only as < 0' : `is ${R2()}`;
    return out('not-law', [`R² (PySR) ${shown}: worse than predicting the mean.`]);
  }
  // 3. "≈ 0".
  if (r2.qualifier === 'approx' && Number.isFinite(r2.value) && r2.value <= PARTIAL_MIN_PYSR_R2) {
    return out('not-law', [`R² (PySR) is ${r2Text(r2, fmt)}: the formula describes almost none of the network's behaviour.`]);
  }
  if (!Number.isFinite(r2.value)) {
    return out('not-law', ['R² (PySR) is not reported, so the formula cannot be judged.']);
  }
  // 4. Low fidelity.
  if (r2.value < PARTIAL_MIN_PYSR_R2) {
    return out('not-law', [`R² (PySR) is ${R2()}, below ${T(PARTIAL_MIN_PYSR_R2)}: the formula does not describe the network.`]);
  }
  // 5. The network itself does not predict the truth.
  if (netValue !== null && netValue < LAW_MIN_NET_R2) {
    return out('not-law', [`The formula describes a network that does not predict the truth: network R² to truth ${NET()}, below ${T(LAW_MIN_NET_R2)} (R² (PySR) ${R2()}).`]);
  }
  // 6. High fidelity.
  if (r2.value >= LAW_MIN_PYSR_R2) {
    if (pysr.units === 'standardised') {
      return out('partial', [`R² (PySR) is ${R2()}, but the formula is written in standardised voxel features, not physical units.`]);
    }
    if (flags.length) {
      return out('partial', [`R² (PySR) is ${R2()}, but a label-leakage flag on this frame caps it at a partial surrogate.`]);
    }
    if (netValue !== null) {
      return out('law', [
        `R² (PySR) is ${R2()} (at least ${T(LAW_MIN_PYSR_R2)}) and the network's R² to truth is ${NET()} (at least ${T(LAW_MIN_NET_R2)}), in physical units with no leak flag: a law candidate, not a law.`,
        `The report: "${NOT_A_PHYSICAL_LAW}".`,
      ]);
    }
    return out('unverified', [`R² (PySR) is ${R2()} (at least ${T(LAW_MIN_PYSR_R2)}), but the report gives no R² of the network to truth, so the candidate cannot be checked against the truth.`]);
  }
  // 7. Middle fidelity.
  const extra = pysr.units === 'standardised' ? '; the formula is written in standardised voxel features' : '';
  return out('partial', [`R² (PySR) is ${R2()}, between ${T(PARTIAL_MIN_PYSR_R2)} and ${T(LAW_MIN_PYSR_R2)}: a partial description of the network${extra}.`]);
}
