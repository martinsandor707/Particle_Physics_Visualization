/* The energy-resolution card's E max slider, its E axis ticks and its deposit gate. DOM-free, so it runs under Node.
 *
 * Shared by the panel (panels/resolution_scaling.js) and the card shell
 * (models_cards.js), so the slider, the axis and the drawer read one rule.
 *
 * ## Why the slider starts at the data's top edge
 *
 * The server's E axis runs to 80 GeV (or to the dataset's top edge rounded up
 * to 10 GeV when that is higher), while every stored experiment's highest
 * momentum window ends at 20 GeV (18 GeV on two of them; lead, 2026-11-17):
 * three quarters of the axis is a fitted curve drawn dashed past every window.
 * E max cuts that extrapolation and nothing else. Its lower end is the data's
 * highest window edge (`data_max_gev`) rounded up to the slider's step, so no
 * measured window can ever leave the axis; its upper end is the server's axis
 * end, so the slider can only shorten what the server would draw. A response
 * without `data_max_gev` gets a slider whose two ends meet: nothing to cut.
 *
 * ## Why the tick steps
 *
 * Over a short axis (up to E_TICK_FINE_MAX_GEV = 40 GeV) a tick every 5 GeV
 * keeps four to eight labelled ticks; above it every 10 GeV, as the server's
 * own 80 GeV axis has. When the slider sits at the server's axis end the
 * server's own interval is kept, so that axis is exactly today's. An end that
 * is no multiple of the step (45, 75 GeV) is ticked too, so the axis always
 * ends on a labelled value.
 *
 * ## Why the deposit is forced on where it is the only series
 *
 * The calibrated deposit is a card toggle, off by default. A response whose
 * only series is the deposit (a single-shower experiment without an energy
 * network) would then draw nothing at all, and the error-scale range would
 * follow no series. There the deposit is drawn whatever the toggle says, and
 * the toggle is shut with its reason (`depositForced`).
 */

/** The E max slider's step, in GeV. */
export const E_MAX_STEP_GEV = 5;

/** E axis ticks every 5 GeV up to this end (GeV), every 10 GeV above it. */
export const E_TICK_FINE_MAX_GEV = 40;

/** Below this, two GeV values are the same tick (floating-point guard). */
const TICK_TOLERANCE = 1e-9;

/** Whether series `s` is the calibrated deposit: its source is 'detector', or it has none and its colour slot is. */
export function isDepositSeries(s) {
  if (!s || typeof s !== 'object') return false;
  if (s.source !== undefined && s.source !== null) return s.source === 'detector';
  return s.colour_slot === 'detector';
}

/** Whether the response carries any series that is not the deposit (a network, an XGBoost hold-out). */
export function hasModelSeries(payload) {
  return (payload?.series ?? []).some((s) => !isDepositSeries(s));
}

/** Whether the deposit is drawn: unless hiding it was asked (`asked === false`) and a model series is left to draw. */
export function depositShown(payload, asked) {
  if (asked !== false) return true;
  return !hasModelSeries(payload);
}

/** Whether the deposit is the response's only series, so no toggle can hide it. */
export function depositForced(payload) {
  return (payload?.series ?? []).length > 0 && !hasModelSeries(payload);
}

/** The E max slider's {min, max, step} in GeV: from the data's top edge, rounded up to the step, to the axis end; null without an axis end. */
export function eMaxRange(payload) {
  const energy = payload?.axis?.energy;
  const max = energy?.x?.max;
  if (!Number.isFinite(max)) return null;
  const step = E_MAX_STEP_GEV;
  const dataMax = energy?.data_max_gev;
  const min = Number.isFinite(dataMax)
    ? Math.min(max, Math.max(step, Math.ceil(dataMax / step) * step))
    : max;
  return { min, max, step };
}

/** The E max in force: `asked` clamped to the slider and snapped to its grid (half up); the lower end when `asked` is not a number; null without a slider. */
export function eMaxOf(payload, asked) {
  const range = eMaxRange(payload);
  if (!range) return null;
  const { min, max, step } = range;
  const value = asked === null || asked === undefined ? Number.NaN : Number(asked);
  if (!Number.isFinite(value)) return min;
  const clamp = (v) => Math.min(max, Math.max(min, v));
  const k = Math.floor((clamp(value) - min) / step + 0.5);
  return clamp(min + k * step);
}

/** The tick step of an E axis ending at `max`: the server's interval at its own end, else 5 GeV up to 40 GeV and 10 GeV above. */
export function eTickStep(max, serverMax = null, serverInterval = null) {
  if (Number.isFinite(serverMax) && max === serverMax && Number.isFinite(serverInterval) && serverInterval > 0) {
    return serverInterval;
  }
  return max <= E_TICK_FINE_MAX_GEV ? 5 : 10;
}

/** The tick values of an E axis from 0 to `max`, ascending: every multiple of the step, then `max` when it is none. */
export function eAxisTicks(max, serverMax = null, serverInterval = null) {
  if (!Number.isFinite(max) || max < 0) return [];
  const step = eTickStep(max, serverMax, serverInterval);
  const ticks = [];
  for (let i = 0; i * step <= max + TICK_TOLERANCE; i += 1) ticks.push(i * step);
  if (max - ticks[ticks.length - 1] > TICK_TOLERANCE) ticks.push(max);
  return ticks;
}
