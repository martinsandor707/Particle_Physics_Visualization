/* The energy resolution against 1/√E: the `res-scaling` card of the Models page.
 *
 * `/api/resolution-scaling` (query/resolution_scaling.py) ships one series per
 * (estimator, shower): the detector's calibrated deposit c·E_dep, and where the
 * experiment has one the energy network of the selected frame or the XGBoost
 * momentum regressor on its validation split. Each series carries σ/E per
 * 1 GeV momentum window - s(R)/R̄ of the per-event ratio R = E_est / p, in
 * percent - and, for both window modes, four weighted least-squares fits: the
 * affine a/√E + b, the origin-pinned a₀/√E, the quadrature √(a²/E + b²) and
 * a/√E ⊕ b ⊕ c/E with its three squares held non-negative (`noise`).
 * Everything here is drawn from those fields; nothing is refitted or rescaled
 * in the browser, and the window mode and the shower choice only repaint.
 *
 * ## A reversed 1/√E axis that ends at the origin
 *
 * The stochastic term a/√E is a straight line through the origin in
 * x = 1/√E, and x = 0 is E → ∞. The bottom axis therefore runs from 0.5 at the
 * left to exactly 0 at the right border (`inverse`), and the y axis starts at
 * zero, so the bottom-right corner is the origin a pure stochastic term runs
 * into. A window below 4 GeV has x > 0.5 and lies off the axis: it is never
 * drawn, and the drawer lists it with its value.
 *
 * The top axis is a second x axis with the same range and direction whose
 * ticks sit at x = 1/√E for round energies, labelled E = 1/x², and ∞ at
 * x = 0. It is an exact relabelling of the bottom axis - a deterministic unit
 * conversion, the one kind of second axis CLAUDE.md section 2 allows - and no
 * series is plotted against it.
 *
 * ## The whisker is the uncertainty of the window's σ/E
 *
 * A window's marker carries a capped whisker, the χ²_{N−1} 95% interval of s
 * divided by R̄, only from N = 8 (the curve floor of the low-N table): it is
 * the uncertainty of the plotted aggregate, never the spread of the events.
 * The whisker is the series' colour on a casing, so it reads over the bands
 * and the lines behind it. From N = 2 to 7 the window is a faded hollow ring
 * with a dashed outline and no whisker, and its tooltip names the N = 8 floor.
 * A window below N = 20 is faded (`legibleOpacity`, never below 3:1 against
 * the card) and fitted only by a provisional fit, where a series has fewer
 * than two windows of N ≥ 20; it never sets the y range. A mark
 * beyond the server's range is clipped at the axis with a caret whose tooltip
 * gives the true value. Series whose windows share an x (a detector and a
 * network series read the same events) are set a few pixels apart.
 *
 * ## The fits are lines with their 95% confidence bands
 *
 * The affine fit is a line and the origin-pinned fit a thinner dotted one, each
 * with its 95% confidence band from the parameter covariance: ±1.96 √(gᵀΣg)
 * while the windows' own standard errors stand, ±t₀.₉₇₅,ν √(gᵀΣg) once the PDG
 * factor S = √(χ²/ν) > 1 scales Σ (S is then estimated from the fit's own ν;
 * the server ships the quantile). It is the uncertainty of the fitted line, not
 * the spread of the events, and the band's tooltip says so. The affine band is
 * a wash at `bandAlpha`, the pinned one at half of it. A band whose part inside
 * the axis covers `OUTLINE_SHARE` of it or more at some x of its fitted span is
 * drawn as its two thin edges instead, never as a wash: once
 * the windows alone set the range (Martin's decision of 2026-11-11), the three
 * anchors' ν = 1 affine bands, at t₀.₉₇₅,₁ = 12.71, washed over the whole
 * plot. Here the edges are solid along their whole length: this view marks no
 * extrapolation on its lines, and its dash is shower B's affine line, so a dash
 * beyond the span would give it a third meaning. The span only decides the
 * outline. It is the fitted windows' momentum edges (`span_gev`, the stretch
 * the E view draws solid) mapped by x = 1/√E (`xSpanOf`). A line and its band are
 * clipped to the plot: an affine fit with a negative intercept runs down to the
 * axis and stops there. The σ/E range is the server's and follows the windows
 * alone (Martin's decision of 2026-11-11): a fit summarises its windows and is
 * not more evidence, so no line or band sets it. One that leaves the top of the
 * plot is clipped and said so, as a weak window is: a caret where it leaves,
 * its true values in the caret's tooltip, and a count in the drawer. Two kinds
 * of fit are drawn faded, their lines at `PROVISIONAL_OPACITY` and their bands
 * at 0.6 of their strength (`faded`): a provisional fit (fewer than two windows
 * of N ≥ 20, so it runs through windows of N ≥ 8), and a fit whose form does not
 * describe its windows, the server's `misfit` (ν ≥ 1 and S = √(χ²/ν) above
 * `gates.misfit_scale`, 5: its residuals average more than five of the windows'
 * own errors). Each says why in its tooltip and the table's Status cell, and the
 * drawer names it. A fit whose iterated weights did not settle says so in its
 * tooltip, the table and the drawer. On this view the quadrature fit and
 * a/√E ⊕ b ⊕ c/E are never drawn; they are tabled (the latter's windows reach
 * below this view's 4 GeV edge). The E view draws a/√E ⊕ b ⊕ c/E (below).
 *
 * ## Colour is the series, fill and dash are the shower
 *
 * The detector series is drawn in ink (`THEME.text`), the neutral reference;
 * a model series takes the hue E2 gives its source (perf_bins.js
 * `sourceColours`, in the order absolute, translated, Local, XGBoost), so a
 * network keeps its colour across the cards. Shower A is a filled marker and a
 * solid affine line, shower B a hollow marker and a dashed affine line, so the
 * two read apart in greyscale too. Every mark of a series - markers, whiskers,
 * carets, lines and bands - carries the series' name, so its legend entry
 * shows and hides all of it.
 *
 * ## The fit table
 *
 * Under the plot, on screen only, the panel keeps a table of the fits of the
 * mode in force: one row group per series drawn, one row per fit (affine,
 * origin-pinned, quadrature, a/√E ⊕ b ⊕ c/E), each with its a, b and c (or the
 * undefined quadrature term with its standard error, or "0 (held)" for a term
 * the constraint holds at 0), χ²/ν with its p, the scale factor
 * S and its status; the series and the windows it fitted, with their
 * substitutions, span the group. Its text columns wrap, so it keeps to the
 * card's width. It is built with `createElement` and `textContent` only, from
 * the pure `fitTableRows`. The export is the chart alone.
 *
 * ## The E view: σ/E against E in GeV, with a ratio panel
 *
 * `opts.view === 'energy'` draws the same response a second way
 * (`energyViewOption`, Martin's decisions of 2026-11-10); every other view is
 * the 1/√E view above, whose option and table do not change. Nothing is
 * refitted: each window sits at E = 1/x² of the very x = ⟨1/√p⟩ the fits used,
 * one exact bijection, so a window on its line in one view is on its curve in
 * the other (its ⟨p⟩, larger by Jensen's inequality, is in its tooltip). The
 * axis is linear from 0 to `axis.energy.x.max`; the windows below 4 GeV, off
 * the 1/√E axis, are on it, those from 1 GeV fitted by a/√E ⊕ b ⊕ c/E alone
 * and the 0–1 GeV window as a point no fit uses. σ/E runs from zero to the
 * server's E-view top, which the windows alone set (from 2 GeV, never below);
 * a curve that leaves it is clipped, as on the 1/√E view.
 *
 * One fitted curve per series, with no band (Martin's directive of
 * 2026-11-15, replacing the two drawn fits of 2026-11-13 and every band of
 * this view), evaluated from its block's params alone (`fitCurveE`, held to
 * the server's `curve` rows by the tests): a/√E ⊕ b ⊕ c/E from 0 GeV wherever
 * the mode has a drawable one (`fits[mode].noise`, `noiseDrawable`); else the
 * origin-pinned a₀/√E ⊕ 0 from 4 GeV, its tooltip giving the server's
 * `noise_reason`; else no curve. Never a second fitted line beside the noise
 * curve: a₀/√E is then tabled only. The noise fit is fitted as (σ/E)² = A/E +
 * B + C/E² with A, B, C ≥ 0, a held term exactly 0, and the curve is √ of
 * that z. It rises without bound as E → 0 when A > 0 or C > 0: it is drawn
 * from where its line comes down through the top (C·u² + A·u + B = y.hi²,
 * u = 1/E), with one caret there (`noiseEntryTip`); a flat curve (A = C = 0)
 * is drawn from 0. The quadrature a/√E ⊕ b is tabled only, and the affine fit,
 * whose negative b would run below zero when extrapolated, stays on the 1/√E
 * view. The width is the form (1.6 px a/√E ⊕ b ⊕ c/E, 1 px the a₀/√E
 * fallback) and the dash is extrapolation: a curve is solid over its own
 * `span_gev`, the edges of the windows it was fitted to, dashed [6, 4] beyond
 * (a₀/√E from 4 GeV, a/√E ⊕ b ⊕ c/E from 0), to the axis end. So shower B,
 * hollow as ever, gives up its long dash here and draws its lines at 70%
 * strength, raised to 3:1 where the card needs it (E2's network hue reaches
 * 91% on the light card, where A and B would read alike); with both showers
 * drawn, a letter "A" or "B" at each curve's right end, in a column beside the
 * plot, names the shower instead: the shower's letter in ink (THEME.text),
 * led by a short key stroke in the curve's own colour, dash, width and
 * strength. A curve leaving the top gets one caret at
 * its first exit scanning up in E, its true value in the caret's tooltip, and
 * a curve that leaves before the axis end gets no end label. The a₀/√E
 * fallback falls with E, so where it starts above the top it comes down into
 * the plot at E = (a₀/y.hi)², with one caret there (`pinnedEntryTip`), and
 * never leaves later.
 *
 * No band round a fitted curve is drawn on either panel: no wash, no outline
 * edges, no band caret (CLAUDE.md section 2, "the E view's fitted curves carry
 * no band"). Two curves per series, each with its band and, where a band was
 * wide, its two edges, read as several competing lines. The fit's uncertainty
 * stays on the card: every window keeps its whisker, and the curve's tooltip
 * and the fit table give each term with its SE (scaled by S), χ²/ν, S and ρ.
 * A provisional fit, or one whose form does not describe its windows, is
 * drawn faded.
 *
 * Windows are not dodged on this view: a curve is steep at low E, so a few
 * pixels of offset would move a window visibly off its own curve, and flip a
 * small residual's sign. Every window sits at its exact E.
 *
 * The literature curves (catalog/resolution_refs.js, "no interval reported")
 * are drawn as the reader asks: either, both (the default) or neither
 * (`literature`, the card's π± | e± toggles; Martin's requests of
 * 2026-11-11). The ratio panel divides by the curve drawn; with both drawn,
 * by the one the windows lie farther from, "the one that needs scaling the
 * most" (`ratioReferenceChoice`); with neither, by each shower's deposit fit.
 * The other curve is drawn on the ratio panel too, divided by the reference
 * (e±/π± is one line, about 0.5). Each is dotted, in its identity colour (palette.js
 * `LITERATURE_COLOURS`, picked by the card's `THEME.qualitativePalette`): a
 * ColorBrewer qualitative hue of its own, π± a brown and e± a purple on every
 * card, measured apart from the deposit ink and E2's four hues, so it is never
 * a series hue and reads as the particle's without a hover. Its legend swatch
 * and its carets take the same colour; its end labels (its particle, in the
 * end column) are ink text (THEME.text), led by a key stroke in its own
 * colour, dotted at its own width. It never sets a range on either panel. A note band between the legend and the
 * plot, part of the canvas and the export, lists the windows above the top
 * and states the extrapolation rule; where the two would not fit side by side
 * they are stacked, so neither overprints the other and the rule's span is
 * never cut.
 *
 * The ratio panel underneath shares the E axis and a linked crosshair (no
 * zoom, no axis tooltip). It divides every window and each series' one curve
 * by the reference in force: each shower's deposit a/√E ⊕ b ⊕ c/E fit, defined
 * from 0 GeV, whose ratio marks start at the fit's own 1 GeV floor (a window
 * below it is counted in `belowNotDrawn`: no window below 1 GeV enters that
 * fit); or its a₀/√E where it has none, from 4 GeV, the server's
 * `noise_reason` said; or a literature curve over the whole axis. The
 * reference's own curve, 1 by construction, is not drawn, and no band is drawn
 * about 1 (Martin's directive of 2026-11-15). A noise fit's ratio is drawn
 * from 0 GeV and may come into the axis from beyond it as E rises, with a
 * caret there (`ratioEntry`); so may the a₀/√E fallback's, from 4 GeV. A ratio's interval is conditional on the
 * reference, which is held exact, and a literature curve has no interval
 * reported: every ratio mark against it says so. The axis is logarithmic and symmetric about 1 over
 * [1/k, k], so ×2 and ÷2 lie at equal distances and a linear axis's impossible
 * negative ratios never arise; its ticks below 1 read 1/x. k is the first
 * `RATIO_STEPS` value covering the robust ratio marks (`ratioRange`): the
 * windows alone, those of N ≥ 20 from 2 GeV, each against a reference that is
 * neither provisional nor a misfit (Martin's decisions of 2026-11-11); no fit
 * sets k. It is provisional without them, capped at the ladder's end and said
 * so, and marks beyond it, fits included, get carets. The faded fits are drawn
 * faded on both panels, as on the 1/√E view, their dashed extrapolations with
 * them. The panel's plot is
 * `ENERGY_VIEW_PX` tall where the view draws its two panels (`syncHeight`),
 * and its export keeps the two panels' proportions (`energyExportMetrics`).
 * `energyModel` decides all of it once, for the chart and the drawer.
 *
 * ## Three estimators, one per response
 *
 * The card's Estimator control (Martin's decisions of 2026-11-12) asks the
 * server for one of three per-window numbers, and the response names the one
 * it carries (`payload.estimator`, read by `estimatorOf`, which the panel
 * prefers to the control): the median relative error median |R − 1|, Model
 * Error vs. Incident Momentum's own number with its events, seed and interval
 * (the default; not a σ, so it is quoted, never converted); the robust σ/E
 * = IQR(R) / (1.349 · median R), reported from N = 20 only; and the sample
 * σ/μ described above. Only words change with it: the axis names are the
 * payload's, every fit, caption, note and tooltip names the plotted quantity
 * by `estimator.symbol`, a window's tooltip gives its interval by its own
 * `method`, its fit weight by `estimator.weight.method` (the bootstrap SE, its
 * κ and the series' pooled scale c of se = c·ŷ/√N, `weight_scale`; or the
 * delta-method SE) and the two estimators not plotted (`alt`). A window that
 * carries no fit weight (tied replicates, a withheld robust interval) and a
 * robust mode that declines to fit through one window say so by their cause,
 * never by N (brief-fix F3, F4, F7).
 * Every mark, colour, dash and gate is as above, the gates the payload's.
 * The literature curves stay drawable under all three (Martin's override):
 * under the median, with a curve on, the payload's disclosure
 * (`estimator.literature.warning`) is one more line of the note band and of
 * every literature-curve tooltip and every ratio-mark tooltip against a curve.
 *
 * ## The Deposit toggle, and the range of the series on show
 *
 * The calibrated deposit is a card toggle on both views, off by default
 * (Martin's decisions of 2026-11-17; `opts.deposit`, `shownSeries`). Hidden,
 * its windows, its fitted curve and its fit-table rows go together, since
 * `resolutionModel`, `energyModel` and `fitTableRows` all take their series
 * from `shownSeries`. A response whose only series is the deposit draws it
 * whatever the toggle says (`deposit.forced`): a card with nothing to draw
 * would say less than one with its benchmark. The y range follows the series
 * on show: a deposit's windows sit far above a network's on some files (on
 * `hits_all_models`, 2026-11-17, its 36.9% set the E view's 40% top against
 * the networks' 22.9% and 19.2%), so while it is hidden the range is the
 * server's second one over the model series alone (`axis.y_model`,
 * `axis.energy.y_model`), with its sentence as `y.basis`. Nothing is rescaled
 * here: both ranges are the server's, by the windows-alone rule. Where the
 * model series on show draw nothing, both views say so in one sentence and
 * name the toggle (`RES_DEPOSIT_HIDDEN_EMPTY`).
 *
 * ## E max: the E view's axis end
 *
 * The server's E axis runs to 80 GeV while every stored experiment's highest
 * window ends at 20 GeV, so three quarters of it was dashed extrapolation
 * (lead, 2026-11-17). The card's E max slider (Martin's decision of
 * 2026-11-17; `opts.eMax`, `res_axis.eMaxOf`) ends the axis from the data's
 * top edge, rounded up to 5 GeV, to the server's end, in 5 GeV steps; the 1/√E
 * view, whose right border is the origin, has none. `opts.eMax` undefined is
 * the server's axis exactly; anything else, null included (the slider's
 * lower end), sets `x.max`, its tick step and ticks (`eAxisTicks`, every
 * 5 GeV up to 40 GeV, every 10 GeV above, the server's own interval at its
 * own end), drawn on both x axes as custom values. Every curve grid,
 * literature grid, reference domain, caret and end label already derives from
 * `x.max`, so nothing is drawn beyond it on either panel; no fit is refitted,
 * and a curve whose fitted windows reach the new end is solid to it, so the
 * extrapolation rule is said only while a drawn curve keeps a dashed run.
 *
 * ## No reference: no ratio
 *
 * With the deposit hidden and no literature curve on, nothing on show can be
 * divided by (Martin's decision of 2026-11-17): the reference is 'none', no
 * window takes a ratio mark ("no reference is on show") and no curve a ratio.
 * The ratio panel keeps its frame and the shared E axis, so the figure's
 * layout does not jump, but its y axis carries no tick, label or name and no
 * 1.0 rule is drawn, since a scale and a rule would read as a reference. One
 * centred sentence says so; the screen adds how to draw one, which a printed
 * figure cannot act on. No hazard: nothing is drawn that needs one.
 *
 * ## What a switched-off entry takes with it
 *
 * A series switched off on the legend leaves with every mark of it, on screen
 * as in an export (Martin's decisions of 2026-11-17: a figure describes only
 * what is on show; `chart_panel.hiddenEntries`, set by a paint's `screenBuild`
 * and by export/figure.js). On screen its legend entry stays, greyed, so a
 * click brings it back; an export leaves the entry out too. The 1/√E view
 * needs nothing beyond the shared legend: every mark of a series carries its
 * name. The E view draws text of its own, so `energyViewOption` leaves out
 * every mark of a left-out name (`exportView`): its markers, whiskers, carets
 * and curves on both panels, its end labels (the end column is sized and the
 * labels spread without them), its values in the note band's off-scale list,
 * and a left-out literature curve's lines, carets and end labels. The
 * extrapolation rule then counts the dashed runs of the series still drawn.
 * Two things stay: the literature disclosure while a curve is on, since the
 * ratio may still divide by it, and a ratio axis name that says what the
 * visible marks are divided by.
 */

import { THEME, axisPadding, formatNumber, formatInt, typographic } from '../scale.js';
import { literatureColour } from '../palette.js';
import { measureText } from '../textfit.js';
import {
  REFERENCE_KEYS, referenceOf, referenceValue, referenceEquation, referenceLabel, REFERENCE_UNITS, literatureLegendName,
} from '../catalog/resolution_refs.js';
import { customWhiskers, customPolyline, customBand } from './marks.js';
import { tooltipOption } from './tooltip.js';
import {
  ChartPanel, baseOption, wrapTooltip, valueAxis, fitName, mutedLine, escapeHtml, caretSeries, clampInterval,
  withColour, wrappedLegend, legendTop, legibleOpacity, emptyChartOption, sigFigs, hiddenEntries, isPrintTheme, tickLabel,
} from './chart_panel.js';
import { SOURCE_ORDER, sourceColours } from './perf_bins.js';
import {
  isDepositSeries, depositShown, depositForced, eMaxRange, eMaxOf, eAxisTicks, eTickStep,
} from '../res_axis.js';

/** The window modes the card offers: the fits' anchors, or every eligible window. */
export const RES_WINDOW_MODES = Object.freeze(['anchors', 'all']);

/** The gates the payload states, as the server's constants (`gates`) default them. */
const DEFAULT_GATES = Object.freeze({
  report_n: 2, whisker_n: 8, fit_n: 20, e_min_gev: 4, anchor_low_gev: 5, n_anchors: 3, misfit_scale: 5, tail_min_n: 300,
});

/**
 * The estimators of a window (query/resolution_scaling.py `ESTIMATORS`, Martin's
 * decisions of 2026-11-12), the default first: the median relative error
 * median |R − 1| (Model Error vs. Incident Momentum's own number), the robust
 * σ/E = IQR(R) / (1.349 · median R), and the sample σ/μ = s(R)/R̄. A response
 * carries one (`payload.estimator`), which names the numbers it draws.
 */
export const RES_ESTIMATORS = Object.freeze(['median', 'robust', 'sample']);

/** The robust floor (CLAUDE.md section 2, `stats/robust_width.MIN_ROBUST_N`): no robust σ/E and no tail share below it. */
export const ROBUST_MIN_N = 20;

/** The cross-references a window's tooltip quotes, in this order, without the estimator plotted. */
const ALT_NAMES = Object.freeze([['robust', 'Robust σ/E'], ['sample', 'sample σ/μ'], ['median', 'median rel.']]);

/**
 * The estimator of a response, as the card words it: the payload's own
 * (`estimator`, which describes the numbers drawn), else the one asked for
 * (`asked`, the card's control), else the sample σ/μ (an older response,
 * `response_ratio`). {name, symbol (the plotted quantity in an equation:
 * "median rel." or "σ/E"), quantity (in prose: "median rel.", "robust σ/E",
 * "σ/E"), label, axisName, weight ('kappa' | 'delta'), warning (the literature
 * disclosure, under the median only, else null), calibration (per shower key:
 * {c_sum, c_median, n, n_zero_deposit})}.
 */
export function estimatorOf(payload, asked = null) {
  const est = payload?.estimator ?? null;
  let name = 'sample';
  if (RES_ESTIMATORS.includes(est?.name)) name = est.name;
  else if (!est && RES_ESTIMATORS.includes(asked)) name = asked;
  const symbol = typeof est?.symbol === 'string' && est.symbol ? est.symbol : (name === 'median' ? 'median rel.' : 'σ/E');
  return {
    name,
    symbol,
    quantity: { median: 'median rel.', robust: 'robust σ/E', sample: 'σ/E' }[name],
    label: typeof est?.label === 'string' ? est.label : null,
    axisName: typeof est?.axis_name === 'string' && est.axis_name ? est.axis_name : `${symbol} [%]`,
    weight: est?.weight?.method ?? (name === 'sample' ? 'delta' : 'kappa'),
    warning: name === 'median' && typeof est?.literature?.warning === 'string' && est.literature.warning
      ? est.literature.warning : null,
    calibration: est?.calibration?.showers ?? {},
  };
}

/** A window interval's name: its own `method`, else the estimator's. */
function intervalName(est, w) {
  if (w?.method === 'order_statistic') return 'order-statistic';
  if (w?.method === 'bootstrap_percentile') return 'bootstrap';
  if (w?.method === 'chi2_over_mu') return 'χ²';
  return est.name === 'sample' ? 'χ²' : 'bootstrap';
}

/**
 * A window's fit weight under the pooled-scale law of the median and robust
 * estimators (brief-fix F1, F3, F7): 'weighted' (a measured relative SE κ),
 * 'tied' (a bootstrap SE below 10⁻⁶ of its value: the replicates differ by
 * rounding alone), 'withheld' (a robust value whose interval, SE and κ are
 * withheld) or 'none'; null under the sample estimator, whose weight is the
 * delta method.
 */
export function weightState(est, w) {
  if ((est?.name ?? 'sample') === 'sample') return null;
  if (Number.isFinite(w?.se_rel) && w.se_rel > 0) return 'weighted';
  if (Number.isFinite(w?.se)) return 'tied';
  if (est.name === 'robust' && Number.isFinite(w?.value)) return 'withheld';
  return 'none';
}

/** Whether a window can enter a fit: N ≥ the fit gate, on the axis from 4 GeV, a value and, off sample, a fit weight. */
function fittableWindow(est, w, gates) {
  const weight = weightState(est, w);
  return (w.n ?? 0) >= gates.fit_n && !w.off_axis && (w.p_lo ?? 0) >= gates.e_min_gev && Number.isFinite(w.value)
    && (weight === null ? Number.isFinite(w.se_delta ?? w.se) : weight === 'weighted');
}

/**
 * The one fittable window a robust mode declines to fit (brief-fix F4: no
 * line through fewer than two), or null: under Robust σ (IQR), a mode that
 * fits no window while exactly one fittable window is in its pool (from
 * 5 GeV in the 3-anchor mode, from 4 GeV in the all-windows mode). `raw` is
 * the payload's series, `mf` its mode block.
 */
export function declinedWindow(est, raw, mf, mode, gates) {
  if (est?.name !== 'robust' || !raw || (mf?.points ?? []).length) return null;
  const floor = mode === 'anchors' ? gates.anchor_low_gev : gates.e_min_gev;
  const pool = (raw.windows ?? []).filter((w) => fittableWindow(est, w, gates) && (w.p_lo ?? 0) >= floor);
  return pool.length === 1 ? pool[0] : null;
}

/**
 * The empty state of a mode that draws nothing because Robust σ (IQR) declines
 * every series' one fittable window (brief-fix F4), or null: each declined
 * window named, and which mode draws it. `allName` is the all-windows button.
 */
function declinedEmptyText(model, allName) {
  const declined = model.series.map((s) => declinedWindow(model.estimator, s.raw, s.mf, model.mode, model.gates)).filter(Boolean);
  if (!declined.length || declined.length < model.series.length) return null;
  const drawsIt = model.mode === 'anchors' ? ` "${allName}" draws ${declined.length === 1 ? 'it' : 'them'}, unfitted.` : '';
  return `${declined.map((w) => declinedText(w)).join('; ')}: no fit, so ${model.mode === 'anchors' ? 'the 3-anchor mode draws nothing' : 'no line is drawn'}.${drawsIt}`;
}

/** The sentence a robust mode that declines its one fittable window says, in the empty state, the role line and the drawer. */
export function declinedText(w) {
  return `Robust σ (IQR) fits no line through fewer than two fittable windows, and only ${w.label ?? `bin ${w.bin}`} (N = ${formatInt(w.n)}) is fittable here`;
}

/** The reason `fitMissingReason` gives where neither a robust decline nor a missing pooled scale is the cause. */
const TOO_FEW_WINDOWS = 'too few windows';

/**
 * Why a series has no fit from 4 GeV (the affine, origin-pinned and
 * quadrature fits of a mode), from the payload alone (review-ui F2,
 * review-docs M3), in this order: Robust σ (IQR) declines its one fittable
 * window (`declinedWindow`); its `weight_scale` exists with c null, so no
 * window from 4 GeV carries a fit weight; otherwise too few windows. A window
 * of N ≥ 20 without a fit weight is never blamed on N (CLAUDE.md, the κ floor).
 * `raw` is the payload's series, `mf` its mode block.
 */
export function fitMissingReason(est, raw, mf, mode, gates = DEFAULT_GATES) {
  if (declinedWindow(est, raw, mf, mode, gates)) return 'Robust σ (IQR) fits no line through fewer than two fittable windows';
  const ws = raw?.weight_scale;
  if (ws && typeof ws === 'object' && !Number.isFinite(ws.c)) {
    return `no window from ${formatNumber(gates.e_min_gev)} GeV carries a fit weight, so this series has no pooled scale`;
  }
  return TOO_FEW_WINDOWS;
}

/** Why a nominal anchor was replaced or dropped, by the substitution's `cause`: never "too few events" unless N was the cause. */
function substitutionWhy(sub, symbol) {
  switch (sub?.cause) {
    case 'tied': return 'which carries no fit weight: its bootstrap SE is below 10⁻⁶ of its value (tied replicates)';
    case 'no_value': return `which reports no ${symbol}`;
    case 'withheld': return 'whose robust interval is withheld, so it carries no fit weight';
    case 'no_se': return 'which has no positive standard error, so it carries no fit weight';
    case 'off_axis': return 'which lies off the axis, below 4 GeV';
    default: return 'which holds too few events for this series';
  }
}

/**
 * The drawer's decomposition sentence (brief-fix, R-ui M3), verbatim, in the
 * Disclosures of both views under every estimator (models_notes.js): why the
 * three estimators of one window differ, without a payload number.
 */
export const RES_DECOMPOSITION = 'The three estimators differ for stated reasons: median|R − 1| is 0.6745 of a σ by definition and keeps the response\'s bias, which the two widths divide out by centring on the median; the sample width also counts the tails, which the robust width does not (each window\'s tooltip gives its share of events beyond 3 robust σ). Methodology §2.4 measures the three factors on one window.';

/** The fits drawn as lines; the quadrature form is tabled only. */
export const DRAWN_FORMS = Object.freeze(['affine', 'pinned']);

/** Marker radii (px): an anchor window of the series, and any other. */
const ANCHOR_PX = 4.4;
const MARKER_PX = 3.2;
/** The dot inside shower A's sub-floor ring (px). */
const CORE_PX = 1.2;
const CAP_PX = 3;
const CASING_PX = 3;
/** Horizontal pitch between series measured at one x (px). */
const SERIES_OFFSET_PX = 3.5;
/** Opacities asked of a weak window (N < 20) and a sub-floor one (N < 8); raised to 3:1 where needed. */
const WEAK_OPACITY = 0.6;
const SUB_FLOOR_OPACITY = 0.45;
/** Opacity asked of a faded fit's line: a provisional fit, or one whose form does not describe its windows. */
const PROVISIONAL_OPACITY = 0.55;
/** Shower B's affine dash, the pinned fit's dots, and a sub-floor ring's dash. */
const DASH_B = [6, 4];
const DASH_PINNED = [1.5, 3];
const DASH_RING = [2, 2];

const X_UNIT = 'GeV⁻¹ᐟ²';
const A_UNIT = '%·√GeV';
/** The unit of c in a/√E ⊕ b ⊕ c/E. */
const C_UNIT = '%·GeV';

/**
 * The E view's second curve (Martin's decisions of 2026-11-13): σ/E = a/√E ⊕
 * b ⊕ c/E, fitted as (σ/E)² = A/E + B + C/E² with A, B, C ≥ 0
 * (`stats/resolution_fit.FORM_NOISE`), its name as every string writes it.
 */
export const NOISE_FORM_NAME = 'a/√E ⊕ b ⊕ c/E';
/** The noise fit's window floor (GeV) where a payload does not state it (`query/resolution_scaling.NOISE_MIN_GEV`). */
const NOISE_MIN_GEV = 1;

const pct = (v) => (Number.isFinite(v) ? `${sigFigs(v, 3)}%` : '—');
/** "−12.3%" or "+4.5%": a signed percent, its minus the sign U+2212 (as the drawer writes a median response). */
const signedPct = (v) => (Number.isFinite(v) ? `${v > 0 ? '+' : ''}${sigFigs(v, 3)}%` : '—');
const sig = (v, d = 3) => sigFigs(v, d);
const plural = (n, word, many = `${word}s`) => `${formatInt(n)} ${n === 1 ? word : many}`;

/**
 * Whether a fit block's form does not describe its windows: the server's
 * `misfit` (ν ≥ 1 and S = √(χ²/ν) above `gates.misfit_scale`). The flag is the
 * server's alone; a block without it (an older payload) is not a misfit.
 */
export function isMisfit(fit) {
  return fit?.misfit === true;
}

/**
 * What a misfit's tooltip says: its χ²/ν and S, the RMS of its residuals in
 * units of the windows' own standard errors, against the gate.
 */
export function misfitText(fit, gates = DEFAULT_GATES) {
  return `Its form does not describe these windows: χ²/ν = ${sig(fit.chi2 / fit.ndf)}, so its residuals average `
    + `S = ${sig(fit.scale_factor)} times the windows' own errors (above ${formatNumber(gates.misfit_scale ?? DEFAULT_GATES.misfit_scale)}); `
    + 'drawn faded, it never sets the range.';
}

/** The mode in force: 'anchors' unless 'all' is asked for. */
export function windowMode(windows) {
  return windows === 'all' ? 'all' : 'anchors';
}

/** The mode as a reader names it. */
export function modeLabel(mode, gates = DEFAULT_GATES) {
  return mode === 'all'
    ? `every window from ${formatNumber(gates.e_min_gev)} GeV with N ≥ ${formatInt(gates.fit_n)}`
    : `the ${formatInt(gates.n_anchors)} anchor windows`;
}

/**
 * The series one shower choice and the Deposit toggle admit: one-shower data
 * admit theirs whatever is asked; `deposit === false` then drops the
 * calibrated deposit, unless it is the response's only series
 * (`res_axis.depositShown`: it is forced on there). Any other `deposit` keeps
 * it, as before the toggle.
 */
export function shownSeries(payload, shower = 'both', deposit = undefined) {
  const all = payload?.series ?? [];
  const nShowers = new Set(all.map((s) => s.shower).filter(Boolean)).size;
  const byShower = !shower || shower === 'both' || nShowers < 2 ? all : all.filter((s) => s.shower === shower);
  return depositShown(payload, deposit) ? byShower : byShower.filter((s) => !isDepositSeries(s));
}

/**
 * The Deposit toggle's state for a response (Martin's decision of
 * 2026-11-17): {shown, hidden, forced}. `forced` when hiding was asked but the
 * deposit is the response's only series, so it is drawn whatever the toggle says.
 */
export function depositState(payload, deposit = undefined) {
  const shown = depositShown(payload, deposit);
  return { shown, hidden: !shown, forced: deposit === false && depositForced(payload) };
}

/**
 * The y range of a view in force, `full` the server's range over every series
 * and `modelOnly` its range over the model series alone (`axis.y_model`,
 * `axis.energy.y_model`): the latter while the deposit is hidden and the
 * server shipped one, with its `note` as `basis`; else the former, `basis`
 * null (the range as before the toggle).
 */
function rangeInForce(full, modelOnly, hidden, estimator) {
  const useModel = hidden && modelOnly !== null && typeof modelOnly === 'object';
  const ya = (useModel ? modelOnly : full) ?? {};
  return {
    lo: 0, hi: ya.hi, interval: ya.interval, provisional: Boolean(ya.provisional),
    name: ya.name ?? estimator.axisName, n_clipped: ya.n_clipped ?? 0,
    basis: useModel ? (modelOnly.note ?? null) : null,
  };
}

/**
 * What both views say when the deposit is hidden and the model series on show
 * draw nothing, no point and no curve (brief res-emax section 5.6, verbatim).
 */
export const RES_DEPOSIT_HIDDEN_EMPTY = 'The calibrated deposit is hidden, and the model series have no window to draw in this selection; switch on Deposit to draw it.';

/**
 * The same state in print (review R2-4): an exported figure names no hidden series and gives no instruction a
 * printed page cannot act on, so it says only what is missing.
 */
export const RES_DEPOSIT_HIDDEN_EMPTY_PRINT = 'The model series have no window to draw in this selection.';

/**
 * The sentence the ratio panel shows with no reference on show (the deposit
 * hidden and no literature curve on), and what the screen adds to it.
 */
export const RATIO_NONE_TEXT = 'No ratio drawn: no reference is on show.';
export const RATIO_NONE_SCREEN_TEXT = ' Switch on π±, e± or the deposit to draw one.';

/** The ratio's reference with no reference on show: no fit, no value, no ratio mark. */
const NO_REFERENCE_REASON = 'no reference is on show';

/** Each series' colour: the detector in ink, a model in its E2 hue, measured against the card in force. */
export function seriesColours(series) {
  const slots = [...new Set(series.map((s) => s.colour_slot).filter((k) => k && k !== 'detector'))];
  // A known source keeps its E2 place (SOURCE_ORDER); sourceColours measures each hue against the card.
  const hues = sourceColours(slots.sort((a, b) => SOURCE_ORDER.indexOf(a) - SOURCE_ORDER.indexOf(b)));
  const out = {};
  for (const s of series) out[s.key] = s.colour_slot === 'detector' || !s.colour_slot ? THEME.text : (hues[s.colour_slot] ?? THEME.text);
  return out;
}

/** The label of window `bin` in a series, or of a nominal anchor from the payload. */
function binLabel(payload, series, bin) {
  const w = (series?.windows ?? []).find((x) => x.bin === bin);
  if (w?.label) return w.label;
  const nominal = payload?.anchors?.nominal_bins ?? [];
  const i = nominal.indexOf(bin);
  if (i >= 0 && payload.anchors.labels?.[i]) return payload.anchors.labels[i];
  return `bin ${bin}`;
}

/**
 * The polyline `points` ([x, y] pairs) cut to the horizontal strip lo ≤ y ≤ hi:
 * the runs inside it, each with at least two points. A run leaves the strip
 * where the line crosses an edge, so a line with a negative intercept stops at
 * the axis instead of running under it.
 */
export function clipPolyline(points, lo, hi) {
  const pts = (points ?? []).filter((p) => Number.isFinite(p?.[0]) && Number.isFinite(p?.[1]));
  const runs = [];
  let run = [];
  const flush = () => {
    if (run.length > 1) runs.push(run);
    run = [];
  };
  const add = (p) => {
    const last = run[run.length - 1];
    if (!last || last[0] !== p[0] || last[1] !== p[1]) run.push(p);
  };
  for (let i = 0; i + 1 < pts.length; i += 1) {
    const [x0, y0] = pts[i];
    const [x1, y1] = pts[i + 1];
    const dy = y1 - y0;
    let t0 = 0;
    let t1 = 1;
    if (dy === 0) {
      if (y0 < lo || y0 > hi) { t0 = 1; t1 = 0; }
    } else {
      const ta = (lo - y0) / dy;
      const tb = (hi - y0) / dy;
      t0 = Math.max(0, Math.min(ta, tb));
      t1 = Math.min(1, Math.max(ta, tb));
    }
    if (t0 > t1) { flush(); continue; }
    if (t0 > 0) flush();
    add([x0 + t0 * (x1 - x0), y0 + t0 * dy]);
    add([x0 + t1 * (x1 - x0), y0 + t1 * dy]);
    if (t1 < 1) flush();
  }
  flush();
  return runs;
}

/**
 * Where a fit leaves the top of the plot, or null where it stays inside:
 * `{at, lineAt, bandAt, peak}`. `lineAt` and `bandAt` are the x where the
 * line and the band's upper edge first rise above `hi`, scanning from x = 0
 * (null where one stays inside); `at` is where the caret goes, the line's exit
 * where the line leaves, else the band's; `peak` is the curve point
 * `[x, y, lo, hi]` whose band reaches highest, its true values.
 */
function cutAbove(curve, hi) {
  if (!Number.isFinite(hi) || !curve.length) return null;
  const exit = (index) => {
    for (let i = 0; i < curve.length; i += 1) {
      const v = curve[i][index];
      if (!(v > hi)) continue;
      if (i === 0) return curve[0][0];
      const before = curve[i - 1][index];
      const t = (hi - before) / (v - before);
      return curve[i - 1][0] + t * (curve[i][0] - curve[i - 1][0]);
    }
    return null;
  };
  const lineAt = exit(1);
  const bandAt = exit(3);
  if (lineAt === null && bandAt === null) return null;
  const peak = curve.reduce((a, c) => (c[3] > a[3] ? c : a), curve[0]);
  return { at: lineAt ?? bandAt, lineAt, bandAt, peak };
}

/**
 * A fit's span on the 1/√E view: its fitted windows' momentum edges `[lo, hi]`
 * (GeV, `span_gev`, the stretch the E view draws solid) mapped by x = 1/√E, so
 * `[1/√hi, 1/√lo]`; null without a span. The 1/√E view judges its bands
 * over it (`bandSpansShare`); the E view draws no band.
 */
export function xSpanOf(span) {
  if (!Array.isArray(span) || !(span[0] > 0) || !(span[1] > 0)) return null;
  return [1 / Math.sqrt(span[1]), 1 / Math.sqrt(span[0])];
}

/**
 * A fit's curve rows `[x, y, lo, hi]` with its line and band at the two span
 * edges added (from the block's params, `evalFitAt`), sorted by x: the band is
 * judged over the whole span however narrow, and its parts in and beyond the
 * span meet at a shared row.
 */
function withSpanEdges(curve, fit, span) {
  const extra = span.map((e) => {
    const v = evalFitAt(fit, e);
    return v ? [1 / Math.sqrt(e), v.y, v.lo, v.hi] : null;
  }).filter(Boolean);
  const rows = [...curve, ...extra].sort((a, b) => a[0] - b[0]);
  return rows.filter((r, i) => i === 0 || r[0] - rows[i - 1][0] > 1e-12);
}

/** What one window is in the mode in force: the role line(s) its tooltip states. */
function roleOf(payload, s, mf, mode, w, gates) {
  const est = estimatorOf(payload);
  const fitted = (mf?.points ?? []).includes(w.bin);
  const roles = [];
  const weight = weightState(est, w);
  if (fitted) {
    if (mode === 'anchors') {
      const sub = (mf.substitutions ?? []).find((x) => x.used === w.bin);
      roles.push(sub
        ? `anchor of this mode, standing in for the nominal anchor ${binLabel(payload, s, sub.nominal)}, ${substitutionWhy(sub, est.symbol)}`
        : 'anchor of this mode (a nominal anchor)');
    } else {
      roles.push('fitted in this mode');
    }
    if (mf.provisional) {
      roles.push(`part of a provisional fit: fewer than two windows reach N = ${formatInt(gates.fit_n)}, so the fit runs through windows of N ≥ ${formatInt(gates.whisker_n)}`);
    }
  } else if (w.n < gates.whisker_n) {
    roles.push(`below the whisker floor N = ${formatInt(gates.whisker_n)}: drawn as a faded ring, not fitted`);
  } else if (w.n < gates.fit_n) {
    roles.push(`not fitted because N < ${formatInt(gates.fit_n)}, the fit and range floor: drawn faded`);
  } else if (weight === 'tied') {
    roles.push('not fitted: its bootstrap SE is below 10⁻⁶ of its value (tied replicates), so it carries no fit weight; drawn in the all-windows mode only');
  } else if (weight === 'withheld') {
    roles.push('not fitted: its robust interval is withheld, so it carries no fit weight');
  } else if (declinedWindow(est, s, mf, mode, gates)?.bin === w.bin) {
    roles.push(`not fitted: ${declinedText(w)}`);
  } else {
    roles.push('not fitted in this mode');
  }
  const anchors = s.fits?.anchors?.points ?? [];
  if (mode === 'all' && anchors.includes(w.bin)) roles.push('an anchor of the 3-anchor mode (the larger marker)');
  return roles;
}

/**
 * Everything the chart, its tooltips, the table and the drawer need, decided
 * once. Pure. `opts` = {windows, shower, deposit (false hides the calibrated
 * deposit where a model series is left, `shownSeries`)}. Null without a
 * resolution payload.
 *
 * {mode, gates, estimator (`estimatorOf`), y: {lo, hi, interval, provisional, name, n_clipped,
 * basis (the server's `y_model.note` while the deposit is hidden and the
 * model series' range is in force, else null)}, nShowers,
 * series: [{key, label, raw, colour, isB, offsetPx, mf, provisional, points,
 * fits: {affine, pinned}, unreported}], clipped: {markers, whiskers, fits},
 * deposit {shown, hidden, forced} (`depositState`), nPoints, nLines}. A point is {w, x, value, lo, hi, n, whisker, weak,
 * subFloor, anchor, fitted, opacity, clip, over, roles}; a fit is {form, fit,
 * runs, band, provisional, misfit (`isMisfit`), faded (provisional or misfit:
 * drawn faded), span (its windows' momentum edges, GeV), xSpan (the same in x,
 * `xSpanOf`), outlined (its band spans `OUTLINE_SHARE` of the axis or more at
 * some x of `xSpan`, so it is drawn as its edges), edges ({solid, dashed} runs
 * of both edges, when outlined), cut, floorCut, converged}, `cut`
 * (`cutAbove`) where its line or band leaves the top of the plot, which no fit
 * sets; `unreported` the on-axis windows with no σ/E.
 */
export function resolutionModel(payload, opts = {}) {
  if (!payload || !Array.isArray(payload.series) || !payload.axis) return null;
  const mode = windowMode(opts.windows);
  const gates = { ...DEFAULT_GATES, ...(payload.gates ?? {}) };
  const estimator = estimatorOf(payload, opts.estimator);
  const deposit = depositState(payload, opts.deposit);
  // The range follows the series on show: the model series' own while the deposit is hidden (`axis.y_model`).
  const y = rangeInForce(payload.axis.y, payload.axis.y_model, deposit.hidden, estimator);
  const all = payload.series;
  const nShowers = new Set(all.map((s) => s.shower).filter(Boolean)).size;
  const shown = shownSeries(payload, opts.shower, opts.deposit);
  const colours = seriesColours(shown);
  const clipped = { markers: 0, whiskers: 0, fits: 0 };
  const hi = Number.isFinite(y.hi) ? y.hi : Infinity;

  const series = shown.map((s, k) => {
    const colour = colours[s.key];
    const isB = s.shower === 'b' && nShowers > 1;
    const mf = s.fits?.[mode] ?? null;
    const fittedBins = new Set(mf?.points ?? []);
    const anchorBins = new Set(s.fits?.anchors?.points ?? []);
    const onAxis = (s.windows ?? []).filter((w) => Number.isFinite(w.value) && !w.off_axis
      && Number.isFinite(w.x) && (w.p_lo ?? 0) >= gates.e_min_gev && (w.n ?? 0) >= gates.report_n);
    const drawn = mode === 'anchors' ? onAxis.filter((w) => fittedBins.has(w.bin)) : onAxis;
    const points = drawn.map((w) => {
      const ci = Array.isArray(w.ci95) && Number.isFinite(w.ci95[0]) && Number.isFinite(w.ci95[1]) ? w.ci95 : null;
      const whisker = Boolean(w.whisker) && ci !== null;
      const weak = (w.n ?? 0) < gates.fit_n;
      const subFloor = !whisker;
      const opacity = subFloor ? legibleOpacity(colour, SUB_FLOOR_OPACITY) : (weak ? legibleOpacity(colour, WEAK_OPACITY) : 1);
      const clip = whisker ? clampInterval(ci[0], ci[1], y.lo, hi) : null;
      const over = w.value > hi || w.value < y.lo;
      if (over) clipped.markers += 1;
      if (clip && (clip.cutLo || clip.cutHi)) clipped.whiskers += 1;
      return {
        w, x: w.x, value: w.value, lo: ci?.[0] ?? null, hi: ci?.[1] ?? null, n: w.n, whisker, weak, subFloor,
        anchor: anchorBins.has(w.bin), fitted: fittedBins.has(w.bin), opacity, clip, over,
        roles: roleOf(payload, s, mf, mode, w, gates),
      };
    });
    // Windows on the axis that report no value (one event, R̄ ≤ 0, or below the robust floor): never drawn, and named in the drawer.
    const unreported = (s.windows ?? []).filter((w) => !w.off_axis && (w.p_lo ?? 0) >= gates.e_min_gev
      && !((w.n ?? 0) >= gates.report_n && Number.isFinite(w.value)));
    const fits = {};
    for (const form of DRAWN_FORMS) {
      const fit = mf?.[form] ?? null;
      if (!fit || !Array.isArray(fit.curve) || !fit.curve.length) { fits[form] = null; continue; }
      const curve = fit.curve.filter((c) => Array.isArray(c) && c.every(Number.isFinite));
      const clampY = (v) => Math.min(Math.max(v, y.lo), hi);
      // No fit sets the range (the server's, from the windows alone): any line or band above it is cut and counted.
      const cut = cutAbove(curve, hi);
      if (cut) clipped.fits += 1;
      const provisional = Boolean(fit.provisional ?? mf.provisional);
      const misfit = isMisfit(fit);
      // The E view's span (the fitted windows' momentum edges), mapped by x = 1/√E: a band that spans half the
      // axis or more somewhere over it is drawn as its two edges, solid along their whole length on this view, whose
      // lines mark no extrapolation and whose dash is shower B's.
      const span = spanOf(mf, s);
      const xSpan = xSpanOf(span);
      const rows = xSpan ? withSpanEdges(curve, fit, span) : curve;
      const outlined = bandSpansShare(rows.map(([cx, , lo, up]) => [cx, lo, up]), xSpan, y.lo, hi);
      fits[form] = {
        form, fit,
        runs: clipPolyline(curve.map(([cx, cy]) => [cx, cy]), y.lo, hi),
        band: curve.map(([cx, , lo, up]) => [cx, clampY(lo), clampY(up)]),
        provisional, misfit, faded: provisional || misfit,
        span, xSpan, outlined,
        edges: outlined ? edgeRuns({ below: [], inside: rows, above: [] }, (pts) => clipPolyline(pts, hi * 1e-9, hi)) : null,
        cut,
        floorCut: curve.some((c) => c[2] < y.lo),
        converged: fit.converged !== false,
      };
    }
    return {
      key: s.key, label: s.label ?? s.key, raw: s, colour, isB,
      offsetPx: (k - (shown.length - 1) / 2) * SERIES_OFFSET_PX,
      mf, provisional: Boolean(mf?.provisional), points, fits, unreported,
    };
  });
  return {
    mode, gates, estimator, y, nShowers, series, clipped, deposit,
    nPoints: series.reduce((a, s) => a + s.points.length, 0),
    nLines: series.reduce((a, s) => a + DRAWN_FORMS.filter((f) => s.fits[f]).length, 0),
  };
}

/* ------------------------------------------------------------ tooltips -- */

/** The tooltip of one window of one series. */
export function pointTip(model, s, p) {
  return pointTipLines(model, s, p).join('<br/>');
}

/** The lines of `pointTip`, which the E view extends; its last line is the clipping note where one applies. */
function pointTipLines(model, s, p) {
  const { gates } = model;
  const w = p.w;
  const lines = [`<b>${escapeHtml(s.label)}</b>`];
  lines.push(`${escapeHtml(w.label ?? `bin ${w.bin}`)} · N = ${plural(w.n, 'event')}`);
  lines.push(`⟨p⟩ = ${formatNumber(w.p_mean, 2)} GeV · x = ⟨1/√p⟩ = ${formatNumber(w.x, 4)} ${X_UNIT}`);
  const est = model.estimator ?? estimatorOf(null);
  lines.push(valueLine(est, w, p));
  const se = seLine(est, s, w, gates);
  if (se) lines.push(mutedLine(se));
  if (Number.isFinite(w.c4)) lines.push(mutedLine(`bias factor c₄(N) = ${formatNumber(w.c4, 4)}: below N = 15 the sample SD runs low by this factor`));
  if (est.name === 'sample') {
    if (Number.isFinite(w.bias)) lines.push(mutedLine(`bias R̄ − 1 = ${pct(w.bias)}: the estimator's own bias, divided out of σ/E`));
  } else if (Number.isFinite(w.median_response) || Number.isFinite(w.bias)) {
    lines.push(mutedLine(`median response R̃ − 1 = ${signedPct(w.median_response)}; mean bias R̄ − 1 = ${signedPct(w.bias)}`));
  }
  if (Number.isFinite(w.momentum_spread)) {
    lines.push(mutedLine(`momentum spread σ_p/⟨p⟩ = ${pct(w.momentum_spread)} in the window, divided out event by event by R = E_est / p`));
  }
  if (w.dof_note) lines.push(mutedLine(String(w.dof_note)));
  for (const line of crossLines(est, s, w, gates)) lines.push(mutedLine(line));
  for (const role of p.roles) lines.push(`Role: ${escapeHtml(role)}`);
  let whiskerLine;
  if (p.whisker) whiskerLine = whiskerText(est, w);
  else if (weightState(est, w) === 'withheld') whiskerLine = 'No whisker: this window\'s robust interval is withheld (the note above says why); its value is drawn as a faded dashed ring.';
  else whiskerLine = `No whisker: N = ${formatInt(w.n)} is below the N = ${formatInt(gates.whisker_n)} floor for a drawn interval; ${est.quantity} is reported from N = ${formatInt(gates.report_n)}.`;
  lines.push(mutedLine(whiskerLine));
  if (p.over || p.clip?.cutLo || p.clip?.cutHi) {
    lines.push(mutedLine(`clipped at the ${model.y.provisional ? 'provisional ' : ''}axis (0 to ${pct(model.y.hi)}); the values above are the true ones`));
  }
  return lines;
}

/**
 * A window's value line, by estimator (brief section 4): "Median rel. = 8.52%,
 * 95% bootstrap interval [8.08%, 8.99%]" (or its order-statistic interval
 * below N = 20), "Robust σ/E = …, 95% bootstrap interval […]", or the sample
 * σ/E with its χ² interval, as ever. The interval is quoted where the window
 * reports one, drawn as a whisker or not.
 */
function valueLine(est, w, p) {
  const ci = Number.isFinite(p.lo) && Number.isFinite(p.hi) ? ` [${pct(p.lo)}, ${pct(p.hi)}]` : '';
  if (est.name === 'median') return `Median rel. = ${pct(w.value)}${ci ? `, 95% ${intervalName(est, w)} interval${ci}` : ''}`;
  if (est.name === 'robust') return `Robust σ/E = ${pct(w.value)}${ci ? `, 95% ${intervalName(est, w)} interval${ci}` : ''}`;
  return `σ/E = ${pct(w.value)}${ci ? `, 95% χ² interval${ci}` : ''}`;
}

/**
 * The fit weight's line, by `estimator.weight.method`: under median and robust
 * the bootstrap SE with its relative SE κ and the series' pooled scale c of
 * the weight se = c·ŷ/√N (brief-fix F1); a window below 4 GeV, which only
 * a/√E ⊕ b ⊕ c/E can fit, takes the same c without entering it (one pooled
 * scale, Martin's directive of 2026-11-15; any `c_low` an older payload
 * carries is never read); a tied window's SE, which carries no fit weight
 * (F3); the delta-method SE under sample, as ever. A withheld robust window
 * has no SE and no line: its `dof_note` says why (F7).
 */
function seLine(est, s, w, gates = DEFAULT_GATES) {
  if (est.weight === 'kappa') {
    if (!Number.isFinite(w.se)) return null;
    if (!(Number.isFinite(w.se_rel) && w.se_rel > 0)) {
      return `bootstrap SE ${pct(w.se)}: below 10⁻⁶ of the value (tied replicates), so no fit weight`;
    }
    const ws = s?.raw?.weight_scale ?? null;
    const c = ws?.c;
    const floor = Number.isFinite(gates?.e_min_gev) ? gates.e_min_gev : DEFAULT_GATES.e_min_gev;
    const pLo = Number.isFinite(w.p_lo) ? w.p_lo : (Number.isFinite(w.x) && w.x > 0 ? 1 / (w.x * w.x) : Infinity);
    const head = `bootstrap SE ${pct(w.se)} (κ = ${sig(100 * w.se_rel)}%)`;
    if (!Number.isFinite(c)) {
      return `${head}; no fit weight: no window of this series from ${formatNumber(floor)} GeV carries one, so it has no pooled scale c`;
    }
    if (pLo < floor) {
      return `${head}; fit weight se = c·ŷ/√N, c = ${sig(c)} for this series, pooled over its windows from ${formatNumber(floor)} GeV`;
    }
    return `${head}; fit weight se = c·ŷ/√N, c = ${sig(c)} for this series`;
  }
  return Number.isFinite(w.se_delta)
    ? `delta-method SE ${pct(w.se_delta)} (R̄'s error included): the fit weight 1/se², recomputed at the fitted value`
    : null;
}

/**
 * A window's cross-references (brief section 2.6): the two estimators not
 * plotted (`alt`; the deposit's median rel. under its median calibration c̃),
 * the share of events beyond 3 robust σ, and under the median where the
 * number comes from: Model Error vs. Incident Momentum's own for a model
 * series, c̃·E_dep for the deposit. Under the sample estimator the median
 * response R̃ − 1 leads them, its bias line being the old one.
 */
function crossLines(est, s, w, gates = DEFAULT_GATES) {
  const out = [];
  const shower = s.raw?.shower ?? 'a';
  const deposit = s.raw?.source === 'detector';
  const cal = est.calibration?.[shower] ?? null;
  if (est.name === 'sample' && Number.isFinite(w.median_response)) out.push(`median response R̃ − 1 = ${signedPct(w.median_response)}`);
  if (w.alt && typeof w.alt === 'object') {
    const parts = ALT_NAMES.filter(([key]) => key !== est.name).map(([key, name]) => {
      const v = w.alt[key];
      if (Number.isFinite(v)) {
        return key === 'median' && deposit && Number.isFinite(cal?.c_median)
          ? `${name} ${pct(v)} (c̃·E_dep, c̃ = ${sig(cal.c_median)})` : `${name} ${pct(v)}`;
      }
      if (key === 'robust' && (w.n ?? 0) < ROBUST_MIN_N) return `${name} not reported below N = ${formatInt(ROBUST_MIN_N)}, the robust floor`;
      return `${name} not reported`;
    });
    out.push(`Not plotted: ${parts.join('; ')}`);
  }
  const tailFloor = gates.tail_min_n ?? DEFAULT_GATES.tail_min_n;
  if (Number.isFinite(w.tail_share)) {
    out.push(`${pct(w.tail_share)} of events beyond 3 robust σ (0.27% for a large Gaussian sample)`);
  } else if ((w.n ?? 0) < tailFloor) {
    out.push(`share beyond 3 robust σ not reported below N = ${formatInt(tailFloor)}: a Gaussian sample of fewer events exceeds 0.27% by chance`);
  } else {
    out.push('share beyond 3 robust σ not reported: the window\'s IQR is 0, so there is no robust σ to measure it in');
  }
  if (est.name === 'median') {
    if (!deposit) out.push('the Median rel. of Model Error vs. Incident Momentum: the same events, seed and interval');
    else if (Number.isFinite(cal?.c_median)) {
      out.push(`c̃·E_dep with the median calibration c̃ = ${sig(cal.c_median)}${Number.isFinite(cal.c_sum) ? ` (the ratio of sums c = ${sig(cal.c_sum)})` : ''}`);
    }
  }
  return out;
}

/** What a drawn whisker is, by estimator: always the uncertainty of the aggregate, never the spread of the events. */
function whiskerText(est, w) {
  if (est.name === 'sample') {
    return 'Whisker: the 95% χ² interval of this window\'s σ/E (N − 1 degrees of freedom), the uncertainty of the aggregate, not the spread of its events.';
  }
  return `Whisker: the 95% ${intervalName(est, w)} interval of this window's ${est.quantity}, the uncertainty of the aggregate, not the spread of its events.`;
}

/** A fit's equation as written on the card, in the plotted quantity's symbol (`sym`). */
function equationOf(form, sym = 'σ/E') {
  if (form === 'affine') return `Affine fit ${sym} = a/√E + b`;
  if (form === 'pinned') return `Origin-pinned fit ${sym} = a₀/√E`;
  return `Quadrature fit ${sym} = √(a²/E + b²)`;
}

/** The χ² sentence of a fit: χ²/ν with p, or ν = 0 said. */
export function chi2Text(fit) {
  if (!fit) return '—';
  if (!(fit.ndf > 0) || !Number.isFinite(fit.p_value)) return 'ν = 0: no χ² test';
  return `χ²/ν = ${sig(fit.chi2)}/${formatInt(fit.ndf)}, p = ${sig(fit.p_value)}`;
}

/** The windows a fit ran through, by label, with the substitutions of the anchors mode. */
function windowsText(payload, s, mf) {
  if (!mf) return '—';
  const subs = mf.substitutions ?? [];
  const parts = (mf.points ?? []).map((bin) => {
    const sub = subs.find((x) => x.used === bin);
    const label = binLabel(payload, s, bin);
    return sub ? `${label} (for ${binLabel(payload, s, sub.nominal)})` : label;
  });
  for (const sub of subs.filter((x) => x.used === null || x.used === undefined)) {
    parts.push(`${binLabel(payload, s, sub.nominal)} dropped`);
  }
  return parts.length ? parts.join(', ') : 'none';
}

/** The tooltip of one fitted line. */
export function lineTip(model, s, f, payload = null) {
  const { fit, form } = f;
  const p = fit.params ?? {};
  const scaled = Number.isFinite(fit.scale_factor) && fit.scale_factor > 1;
  const sym = model.estimator?.symbol ?? 'σ/E';
  const lines = [`<b>${escapeHtml(s.label)}</b>`, escapeHtml(equationOf(form, sym))];
  if (form === 'affine') {
    lines.push(`a = ${sig(p.a)} ± ${sig(p.se_a)} ${A_UNIT}; b = ${sig(p.b)} ± ${sig(p.se_b)}%`
      + (Number.isFinite(p.rho_ab) ? `; ρ(a, b) = ${sig(p.rho_ab)}` : ''));
    if (scaled) lines.push(mutedLine(`errors scaled by S = ${sig(fit.scale_factor)} (PDG, χ²/ν > 1); unscaled SE(a) = ${sig(p.se_a_stat)}, SE(b) = ${sig(p.se_b_stat)}`));
  } else {
    lines.push(`a₀ = ${sig(p.a0)} ± ${sig(p.se_a0)} ${A_UNIT}`);
    if (scaled) lines.push(mutedLine(`error scaled by S = ${sig(fit.scale_factor)} (PDG, χ²/ν > 1); unscaled SE(a₀) = ${sig(p.se_a0_stat)}`));
  }
  lines.push(fit.ndf > 0 && Number.isFinite(fit.p_value)
    ? chi2Text(fit)
    : `${chi2Text(fit)}: the line passes through its ${formatInt(fit.n_points)} point${fit.n_points === 1 ? '' : 's'} exactly`);
  lines.push(`Windows fitted (${formatInt(fit.n_points)}): ${escapeHtml(windowsText(payload, s.raw, s.mf))}`);
  if (f.provisional) {
    lines.push(mutedLine(`Provisional: fewer than two windows reach N = ${formatInt(model.gates.fit_n)}, so the fit runs through windows of N ≥ ${formatInt(model.gates.whisker_n)}; drawn faded.`));
  }
  if (f.misfit) lines.push(mutedLine(misfitText(fit, model.gates)));
  if (form === 'affine' && (fit.negative_intercept || p.b < 0)) {
    lines.push(mutedLine('b < 0: the points fall faster than a/√E; the line runs down to the axis and stops there.'));
  }
  if (form === 'affine' && Number.isFinite(p.a) && p.a < 0) {
    lines.push(mutedLine(`a < 0: ${sym} rises with E here, which no stochastic term describes.`));
  }
  if (!f.converged) {
    lines.push(mutedLine(`Not converged: the iterated weights did not settle within ${formatInt(fit.iterations)} refits, so this is the last refit's line, not a fixed point.`));
  }
  if (f.cut) lines.push(mutedLine('It leaves the top of the plot: the caret there gives its true values.'));
  lines.push(mutedLine(f.outlined ? outlinedLine(fit) : 'The shaded band beside it is the line\'s 95% confidence band.'));
  return lines.join('<br/>');
}

/** The band's half-width as the card writes it: ±1.96 √(gᵀΣg), or ±t₀.₉₇₅,ν √(gᵀΣg) once S scales Σ. */
function bandRule(fit) {
  const scaled = Number.isFinite(fit.scale_factor) && fit.scale_factor > 1;
  const q = Number.isFinite(fit.band_quantile) ? fit.band_quantile : 1.96;
  return scaled
    ? `±t₀.₉₇₅,${formatInt(fit.ndf)} √(gᵀΣg) = ±${sig(q, 4)} √(gᵀΣg) from the parameter covariance scaled by S = ${sig(fit.scale_factor)}: S is estimated from the fit's own ν = ${formatInt(fit.ndf)}, so Student's t replaces 1.96`
    : '±1.96 √(gᵀΣg) from the parameter covariance';
}

/** The tooltip of one fit's band: its wash, or, where it is outlined, its solid edges. */
export function bandTip(s, f, est = null) {
  const name = f.form === 'affine' ? 'affine fit a/√E + b' : 'origin-pinned fit a₀/√E';
  const lines = [
    `<b>${escapeHtml(s.label)}</b>`,
    `95% confidence band of the ${name}: ${bandRule(f.fit)}`,
    mutedLine('The uncertainty of the fitted line, not the spread of the events.'),
  ];
  if (f.outlined) lines.push(mutedLine(outlinedLine(f.fit)));
  if (f.cut) lines.push(mutedLine('It leaves the top of the plot: the caret there gives its true values.'));
  if (f.floorCut) lines.push(mutedLine(`Its lower edge is cut at ${est?.symbol ?? 'σ/E'} = 0, the floor of the axis.`));
  return lines.join('<br/>');
}

/** "x = 0.354 GeV⁻¹ᐟ² (E = 8 GeV)": a place on the bottom axis with its energy. */
function placeText(x) {
  return `x = ${formatNumber(x, 3)} ${X_UNIT} (${x > 0 ? `E = ${sig(1 / (x * x))} GeV` : 'E → ∞'})`;
}

/** The tooltip of the caret where a fit's line or band leaves the top of the plot: its true values. */
export function fitCutTip(model, s, f) {
  const { cut } = f;
  const name = f.form === 'affine' ? 'affine fit a/√E + b' : 'origin-pinned fit a₀/√E';
  const [px, py, plo, pup] = cut.peak;
  const lines = [
    `<b>${escapeHtml(s.label)}</b>`,
    `The ${f.provisional ? 'provisional ' : ''}${name} leaves the top of the ${model.y.provisional ? 'provisional ' : ''}axis (0 to ${pct(model.y.hi)}):`
      + `${cut.lineAt !== null ? ` its line from ${placeText(cut.lineAt)},` : ''} its 95% band from ${placeText(cut.bandAt ?? cut.lineAt)}.`,
    `True values where the band reaches highest, at ${placeText(px)}: the line ${pct(py)}, the band [${pct(plo)}, ${pct(pup)}].`,
    mutedLine(rangeRuleText(model)),
  ];
  if (f.misfit) lines.push(mutedLine(misfitText(f.fit, model.gates)));
  return lines.join('<br/>');
}

/**
 * Why a fit is clipped at the top, as its caret says: the σ/E range follows the
 * windows alone (Martin's decision of 2026-11-11), so no line, curve or band
 * sets it. `floor` is the E view's lowest window edge that may set it ('2 GeV').
 */
function rangeRuleText(model, floor = null) {
  const n = formatInt(model.gates.fit_n);
  const from = floor ? ` from ${floor}` : '';
  // The E view (a `floor`) draws no band (Martin's directive of 2026-11-15), so its sentence names the curve alone.
  return model.y.provisional
    ? `Clipped, not rescaled: the provisional range follows the windows' markers, no window${from} reaching N = ${n}; no fit sets it.`
    : `Clipped, not rescaled: the range follows the windows of N ≥ ${n}${from} alone; a fit summarises its windows, so no ${floor ? 'fitted curve' : 'line, curve or band'} sets it.`;
}

/* --------------------------------------------------------------- marks -- */

/** The markers of one series: filled (A) or hollow (B); a dashed ring below the whisker floor. */
function markerSeries(model, s) {
  const { y } = model;
  const pts = s.points.filter((p) => !p.over);
  return {
    type: 'custom',
    id: `${s.key}|markers`,
    name: s.label,
    clip: true,
    z: 8,
    data: pts.map((p, index) => [p.x, p.value, index]),
    renderItem: (params, api) => {
      const p = pts[params.dataIndex];
      const c = api.coord([p.x, Math.min(p.value, y.hi)]);
      const cx = c[0] + s.offsetPx;
      const r = p.anchor ? ANCHOR_PX : MARKER_PX;
      if (p.subFloor) {
        const ring = {
          type: 'circle', shape: { cx, cy: c[1], r },
          style: { fill: THEME.card, stroke: s.colour, lineWidth: 1.2 * THEME.lineAxis, lineDash: DASH_RING, opacity: p.opacity },
        };
        if (s.isB) return ring;
        // Shower A keeps a dot at the centre, so its sub-floor ring is not taken for shower B's.
        return { type: 'group', children: [ring, { type: 'circle', shape: { cx, cy: c[1], r: CORE_PX }, style: { fill: s.colour, opacity: p.opacity } }] };
      }
      return {
        type: 'circle',
        shape: { cx, cy: c[1], r },
        style: s.isB
          ? { fill: THEME.card, stroke: s.colour, lineWidth: 1.4 * THEME.lineAxis, opacity: p.opacity }
          : { fill: s.colour, stroke: THEME.card, lineWidth: 0.6 * THEME.lineAxis, opacity: p.opacity },
      };
    },
    tooltip: { formatter: (prm) => pointTip(model, s, pts[prm.dataIndex]) },
  };
}

/** The legend swatch and item colour of a series: shower B's is hollow, as its markers are. */
function itemStyleOf(s) {
  return s.isB ? { color: THEME.card, borderColor: s.colour, borderWidth: 1.4 * THEME.lineAxis } : { color: s.colour };
}

/** Every mark of one series, each named after it, so its legend entry shows and hides all of them. */
function seriesMarks(model, s, payload) {
  const { y } = model;
  const out = [];
  const style = itemStyleOf(s);
  const named = (x) => ({ ...withColour(x, s.colour), name: s.label, itemStyle: { ...style } });

  // Markers first: the legend takes its swatch from the first series of a name.
  out.push(named(markerSeries(model, s)));

  const whiskers = s.points
    .filter((p) => p.whisker && p.clip && p.clip.lo !== null && p.clip.hi !== null && p.clip.hi > p.clip.lo)
    .map((p) => [p.x, p.clip.lo, p.clip.hi, { caps: p.clip.caps, opacity: p.opacity === 1 ? 1 : legibleOpacity(s.colour, WEAK_OPACITY), point: p }]);
  if (whiskers.length) {
    out.push(named({
      ...customWhiskers({
        name: s.label, points: whiskers, capPx: CAP_PX, color: s.colour, width: 1.2 * THEME.lineAxis,
        offsetPx: s.offsetPx, z: 7, casing: { color: THEME.canvas, width: CASING_PX },
        tooltip: (d) => pointTip(model, s, d.point),
      }),
      id: `${s.key}|whiskers`,
    }));
  }

  const carets = [];
  for (const p of s.points) {
    const tip = pointTip(model, s, p);
    if (p.value > y.hi || p.clip?.cutHi) carets.push({ at: [p.x, y.hi], dir: 'up', tooltip: tip });
    if (p.value < y.lo || p.clip?.cutLo) carets.push({ at: [p.x, y.lo], dir: 'down', tooltip: tip });
  }
  // A line or band that leaves the top of the plot: one caret where it leaves, with its true values.
  for (const form of DRAWN_FORMS) {
    const f = s.fits[form];
    if (f?.cut) carets.push({ at: [f.cut.at, y.hi], dir: 'up', tooltip: fitCutTip(model, s, f) });
  }
  if (carets.length) {
    out.push(named({ ...caretSeries({ name: s.label, carets, color: s.colour, offsetPx: s.offsetPx }), id: `${s.key}|carets` }));
  }

  for (const form of DRAWN_FORMS) {
    const f = s.fits[form];
    if (!f) continue;
    const affine = form === 'affine';
    // Faded: a provisional fit, or one whose form does not describe its windows.
    const opacity = f.faded ? legibleOpacity(s.colour, PROVISIONAL_OPACITY) : 1;
    f.runs.forEach((run, i) => {
      out.push(named({
        ...customPolyline({
          name: s.label, points: run, color: s.colour, opacity, z: 5,
          width: (affine ? 1.6 : 1) * THEME.lineAxis,
          dash: affine ? (s.isB ? DASH_B : null) : DASH_PINNED,
          tooltip: () => lineTip(model, s, f, payload),
        }),
        id: `${s.key}|${form}|line|${i}`,
      }));
    });
    // A band that spans half the axis or more over its fitted windows: its two edges, never a wash.
    if (f.outlined) {
      out.push(...bandEdges(f.edges, s.colour, `${s.key}|${form}`, () => bandTip(s, f, model.estimator)).map(named));
      continue;
    }
    out.push(named({
      ...customBand({
        name: s.label, points: f.band, color: s.colour, z: 2,
        opacity: (affine ? 1 : 0.5) * THEME.bandAlpha * (f.faded ? 0.6 : 1),
      }),
      id: `${s.key}|${form}|band`,
      silent: false,
      tooltip: { formatter: () => bandTip(s, f, model.estimator) },
    }));
  }
  return out;
}

/**
 * The empty state of a view whose deposit is hidden (Martin's decision of
 * 2026-11-17; brief res-emax section 5.6), or null: where the model series on
 * show draw nothing in that view (`empty`, the view's own test of its model:
 * no point and no curve, or no range), the one sentence that says the deposit
 * is hidden and how to draw it. A shower choice with no series at all, the
 * deposit included, keeps its own sentence; a forced deposit is shown, so its
 * view keeps its own empty states.
 */
function depositHiddenEmpty(payload, opts, model, empty = (m) => !m.nPoints || !(m.y.hi > 0), build = null) {
  if (!model?.deposit?.hidden) return null;
  if (!shownSeries(payload, opts?.shower).length) return null;
  if (!(!model.series.length || empty(model))) return null;
  // Only where the deposit would draw something (agent B's finding on the two-event baseline): else switching it on
  // changes nothing, and the view's own empty state says why nothing is drawn.
  const shown = typeof build === 'function' ? build({ ...opts, deposit: true }) : null;
  if (shown && (!shown.series.length || empty(shown))) return null;
  return isPrintTheme() ? RES_DEPOSIT_HIDDEN_EMPTY_PRINT : RES_DEPOSIT_HIDDEN_EMPTY;
}

/** "holds two events" at the report floor N = 2; "reaches N = 20" under the robust estimator's floor. */
function holdsText(gates) {
  return gates.report_n === 2 ? 'holds two events' : `reaches N = ${formatInt(gates.report_n)}`;
}

/** The top axis: the bottom one relabelled, E = 1/x², ticks at the payload's energies and ∞ at 0. */
function energyAxis(top, xMin, xMax) {
  const ticks = (top?.ticks ?? []).filter((t) => Number.isFinite(t.x) && t.x >= xMin && t.x <= xMax);
  const xs = ticks.map((t) => t.x);
  const labelOf = (v) => {
    const t = ticks.find((k) => Math.abs(k.x - v) < 1e-6);
    return t ? typographic(String(t.label)) : '';
  };
  const base = valueAxis({ name: top?.name ?? 'Energy (GeV) ⟶', min: xMin, max: xMax, nameGap: 1.8 * THEME.fontLabel + 4 });
  return {
    ...base,
    position: 'top',
    inverse: true,
    axisTick: { ...base.axisTick, customValues: xs },
    axisLabel: { ...base.axisLabel, customValues: xs, formatter: labelOf },
    splitLine: { show: false },
  };
}

/** The headroom the top axis's labels and name take above the plot (px). */
function topAxisPx() {
  return 3.6 * THEME.fontLabel;
}

/**
 * The card's option. Pure: `opts` = {view?: 'linear' | 'energy', windows:
 * 'anchors' | 'all', shower: 'a' | 'b' | 'both', reference?, deposit?, eMax?
 * (the E view's alone), palette, card, tooltipPosition?}; `metrics` = {width,
 * height}. `view: 'energy'` is the E view (`energyViewOption`); any other view
 * is the 1/√E view, whose export needs nothing beyond `chartLegend` and
 * `legendTop`: every mark of a series carries its name, so the legend's filter
 * leaves all of it out.
 */
export function resolutionScalingOption(payload, opts = {}, metrics = {}) {
  if (opts?.view === 'energy') return energyViewOption(payload, opts, metrics).option;
  const model = resolutionModel(payload, opts);
  if (!model) return emptyChartOption(opts, metrics, 'This response carries no energy-resolution series.');
  const hiddenEmpty = depositHiddenEmpty(payload, opts, model, undefined, (o) => resolutionModel(payload, o));
  if (hiddenEmpty) return emptyChartOption(opts, metrics, hiddenEmpty);
  if (!model.series.length) {
    return emptyChartOption(opts, metrics, 'No series of the chosen shower in this response.');
  }
  if (!model.nPoints || !(model.y.hi > 0)) {
    const { gates } = model;
    const offAxis = model.series.reduce((a, s) => a + (s.raw.windows ?? []).filter((w) => w.off_axis && Number.isFinite(w.value)).length, 0);
    const listed = offAxis ? ` ${plural(offAxis, 'window')} below ${formatNumber(gates.e_min_gev)} GeV ${offAxis === 1 ? 'is' : 'are'} listed in the Details drawer.` : '';
    // Windows that report a value (N ≥ report_n) but cannot anchor a fit (N < whisker_n): the anchors mode draws none of them.
    const reportable = model.series.reduce((a, s) => a + (s.raw.windows ?? []).filter((w) => !w.off_axis
      && (w.p_lo ?? 0) >= gates.e_min_gev && (w.n ?? 0) >= gates.report_n && Number.isFinite(w.value)).length, 0);
    const declined = declinedEmptyText(model, `All ≥ ${formatNumber(gates.e_min_gev)} GeV`);
    if (declined) return emptyChartOption(opts, metrics, `${declined}${listed}`);
    if (model.mode === 'anchors' && reportable && model.y.hi > 0) {
      return emptyChartOption(opts, metrics, `No window from ${formatNumber(gates.anchor_low_gev)} GeV reaches N = ${formatInt(gates.whisker_n)}, `
        + `the fewest an anchor fit runs through, so the 3-anchor mode draws nothing. "All ≥ ${formatNumber(gates.e_min_gev)} GeV" draws the `
        + `${plural(reportable, 'window')} from ${formatNumber(gates.e_min_gev)} GeV that report ${model.estimator.quantity} (N ≥ ${formatInt(gates.report_n)}).${listed}`);
    }
    const mode = model.mode === 'anchors' ? ' No series has a window its anchors fit can run through.' : '';
    return emptyChartOption(opts, metrics, `No momentum window from ${formatNumber(gates.e_min_gev)} GeV ${holdsText(gates)} in this selection, `
      + `so no ${model.estimator.quantity} can be drawn on this axis.${mode}${listed}`);
  }
  const pad = axisPadding();
  const width = metrics.width || 760;
  const height = metrics.height || 420;
  const plotWidthPx = Math.max(80, width - pad.left - pad.right);
  const axis = payload.axis;
  const xMin = axis.x?.min ?? 0;
  const xMax = axis.x?.max ?? 0.5;

  const series = [];
  const legend = [];
  for (const s of model.series) {
    const marks = seriesMarks(model, s, payload);
    if (!s.points.length && !DRAWN_FORMS.some((f) => s.fits[f])) continue;
    series.push(...marks);
    legend.push({ name: s.label, icon: 'circle' });
  }

  const top = legendTop(legend, plotWidthPx, { wrap: true }) + topAxisPx();
  const plotHeightPx = Math.max(60, height - top - pad.bottom);
  const yBase = model.y.name;
  const yName = fitName(model.y.provisional
    ? [`${yBase} — provisional, no window reaches N = ${formatInt(model.gates.fit_n)}`, `${yBase} — provisional`]
    : [yBase], plotHeightPx);
  const bottom = valueAxis({
    name: axis.x?.name ?? '⟵ 1/√E [GeV⁻¹ᐟ²]', min: xMin, max: xMax, interval: axis.x?.interval ?? 0.1,
  });
  return {
    ...baseOption(),
    tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
    grid: { left: pad.left, right: pad.right, top, bottom: pad.bottom },
    legend: wrappedLegend(legend, { left: pad.left, right: pad.right }),
    xAxis: [{ ...bottom, position: 'bottom', inverse: true }, energyAxis(axis.top, xMin, xMax)],
    yAxis: valueAxis({
      name: yName, min: 0, max: model.y.hi, interval: model.y.interval, split: true, nameGap: 3.6 * THEME.fontLabel,
    }),
    series,
  };
}

/* ---------------------------------------------------------- fit table -- */

/** The column heads of the fit table: one row per fit, the series and its windows spanning its rows. */
export const FIT_TABLE_COLUMNS = Object.freeze([
  'Series', 'Fit', `a ± SE [${A_UNIT}]`, 'b ± SE [%]', `c ± SE [${C_UNIT}]`, 'χ²/ν (p)', 'S', 'Windows fitted', 'Status',
]);

/** The left-aligned text columns; the rest are right-aligned numbers, each value kept whole by `NBSP`. */
export const FIT_TABLE_TEXT_COLUMNS = Object.freeze([0, 1, 7, 8]);

/**
 * The fits of one series, in the table's order, with the name its Fit cell
 * gives each in the 1/√E view. a/√E ⊕ b ⊕ c/E is tabled there: its windows
 * reach below that view's 4 GeV edge (Martin's decisions of 2026-11-13).
 */
const TABLE_FORMS = Object.freeze([
  ['affine', 'Affine a/√E + b'],
  ['pinned', 'Origin-pinned a₀/√E'],
  ['quadrature', 'Quadrature √(a²/E + b²), tabled only'],
  ['noise', `${NOISE_FORM_NAME}, tabled only: fitted to windows from 1 GeV, below this view's edge`],
]);

/** No-break space: a value and its SE, or p and its value, never split across lines as the table wraps. */
const NBSP = '\u00a0';

const pm = (v, se) => (Number.isFinite(v) ? `${sig(v)}${NBSP}±${NBSP}${sig(se)}` : '—');

/** A χ² cell: χ²/ν (p), or ν = 0 said. */
function chi2Cell(fit) {
  if (!fit) return '—';
  return fit.ndf > 0 && Number.isFinite(fit.p_value)
    ? `${sig(fit.chi2)}/${formatInt(fit.ndf)} (p${NBSP}=${NBSP}${sig(fit.p_value)})`
    : 'ν = 0: no χ² test';
}

/** The scale factor cell: S where it scaled the errors, 1 where they stand, — without a test. */
function scaleCell(fit) {
  if (!fit || !(fit.ndf > 0)) return '—';
  return Number.isFinite(fit.scale_factor) && fit.scale_factor > 1 ? sig(fit.scale_factor) : '1';
}

/** The units of the squares a², b² and c² of the quadrature and noise forms. */
const SQUARE_UNITS = Object.freeze({ a: '%²·GeV', b: '%²', c: '%²·GeV²' });

/**
 * Whether a term of the quadrature or noise form is printed as its square
 * (brief-fix m4): its delta-method SE, se(t²)/(2t), exceeds its value, so a
 * symmetric error would reach below 0 for a term that cannot; the square and
 * its own SE are printed instead ("b² = 0.04 ± 8.1 %²").
 */
export function termAsSquare(p, t) {
  const v = p?.[t];
  const se = p?.[`se_${t}`];
  return Number.isFinite(v) && Number.isFinite(se) && se > v && Number.isFinite(p?.[`${t}2`]);
}

/** A term's square with its SE and unit, as `termAsSquare` prints it; `space` between the parts. */
function squareText(p, t, space = ' ') {
  return `${t}²${space}=${space}${sig(p[`${t}2`])}${space}±${space}${sig(p[`se_${t}2`])}${space}${SQUARE_UNITS[t]}`;
}

/**
 * The a, b and c cells of one fit: the pinned b is zero by construction; an
 * undefined quadrature term is its square; a/√E ⊕ b ⊕ c/E writes a term the
 * constraint holds at 0 as "0 (held)"; a quadrature or noise term whose SE
 * exceeds its value is written as its square with its SE (`termAsSquare`,
 * brief-fix m4). c, the noise term c/E, belongs to that form alone, so the
 * other rows leave its cell empty.
 */
function termCells(fit) {
  if (!fit) return ['—', '—', '—'];
  const p = fit.params ?? {};
  const term = (t) => (termAsSquare(p, t) ? squareText(p, t, NBSP) : pm(p[t], p[`se_${t}`]));
  if (fit.form === 'noise') {
    const held = new Set(p.held ?? []);
    return ['a', 'b', 'c'].map((t) => (held.has(t) ? `0${NBSP}(held)` : term(t)));
  }
  if (fit.form === 'affine') return [pm(p.a, p.se_a), pm(p.b, p.se_b), '—'];
  if (fit.form === 'pinned') return [pm(p.a0, p.se_a0), '0 (through the origin)', '—'];
  const a = p.a_defined === false || !Number.isFinite(p.a)
    ? `A${NBSP}=${NBSP}${pm(p.a2, p.se_a2)}${NBSP}%²·GeV: a undefined`
    : term('a');
  const b = p.b_defined === false || !Number.isFinite(p.b)
    ? `B${NBSP}=${NBSP}${pm(p.b2, p.se_b2)}${NBSP}%²: b undefined`
    : term('b');
  return [a, b, '—'];
}

/**
 * The status of one fit: provisional, a form that does not describe its windows, not converged, a negative intercept, or N ≥ 20 throughout.
 * Without a fit, why (`missing`, `fitMissingReason`): "too few windows", or "no fit: <reason>" for any other cause.
 */
function statusCell(fit, mf, gates, missing = TOO_FEW_WINDOWS) {
  if (!fit) return missing === TOO_FEW_WINDOWS ? TOO_FEW_WINDOWS : `no fit: ${missing}`;
  const status = [];
  // The noise fit carries its own flag (the mode's, as its threshold is the mode's own).
  if (fit.form === 'noise' ? fit.provisional : mf?.provisional) status.push(`provisional (windows of N ≥ ${formatInt(gates.whisker_n)})`);
  if (isMisfit(fit)) status.push(`form does not describe its windows (S = ${sig(fit.scale_factor)} > ${formatNumber(gates.misfit_scale)})`);
  if (fit.converged === false) status.push(`not converged in ${formatInt(fit.iterations)} refits`);
  if (fit.form === 'affine' && fit.negative_intercept) status.push('b < 0');
  return status.length ? status.join('; ') : `N${NBSP}≥${NBSP}${formatInt(gates.fit_n)} throughout`;
}

/**
 * The fit table of the mode in force. Pure: {mode, caption, columns, rows:
 * [{key, label, windows, fits: [{form, cells: [string]}]}]}, one row group per
 * series the shower choice admits and one row per fit; `cells` are the Fit
 * column onwards except the windows, which span the group (`windows`). Every
 * cell is a string with U+2212 for a minus. Null without a payload.
 *
 * Four rows per series: affine, origin-pinned, quadrature and a/√E ⊕ b ⊕ c/E
 * (Martin's decisions of 2026-11-13), whose c column the others leave empty;
 * the windows cell adds a/√E ⊕ b ⊕ c/E's own windows, the low anchor named,
 * where they differ from the mode's.
 *
 * `opts.view === 'energy'` names the fits as the E view draws them, one curve
 * per series with no band (Martin's directive of 2026-11-15): a/√E ⊕ b ⊕ c/E
 * drawn, or not drawn with the server's reason; the origin-pinned a₀/√E ⊕ 0
 * drawn as the fallback where the series has no a/√E ⊕ b ⊕ c/E fit, else
 * table only (or not drawn without a fit); the quadrature a/√E ⊕ b table only;
 * the affine fit drawn in the 1/√E view. A caption says so, and the result
 * adds `view: 'energy'`. The rows, their order and every other cell are the
 * 1/√E view's.
 */
export function fitTableRows(payload, opts = {}) {
  if (!payload || !Array.isArray(payload.series)) return null;
  const mode = windowMode(opts?.windows);
  const gates = { ...DEFAULT_GATES, ...(payload.gates ?? {}) };
  const energy = resolutionView(opts?.view) === 'energy';
  const est = estimatorOf(payload, opts?.estimator);
  // The plotted quantity leads the caption under the median and robust estimators; the sample caption is unchanged.
  const of = est.name === 'sample' ? '' : ` of the ${est.quantity}`;
  const text = (c) => typographic(String(c));
  // The Deposit toggle hides the deposit's rows with its windows and curve (`shownSeries`).
  const rows = shownSeries(payload, opts?.shower, opts?.deposit).map((s) => {
    const mf = s.fits?.[mode] ?? null;
    // Why a fit from 4 GeV is missing, from the payload (review-ui F2, review-docs M3).
    const missing = fitMissingReason(est, s, mf, mode, gates);
    return {
      key: s.key,
      label: s.label ?? s.key,
      windows: text(tableWindowsText(payload, s, mf, mode)),
      fits: TABLE_FORMS.map(([form, name]) => {
        const fit = mf?.[form] ?? null;
        const [a, b, c] = termCells(fit);
        const cellName = energy ? energyTableName(form, fit, est.symbol, mf, missing) : name;
        const status = form === 'noise' && !fit ? noiseStatusCell(mf) : statusCell(fit, mf, gates, missing);
        return { form, cells: [cellName, a, b, c, chi2Cell(fit), scaleCell(fit), status].map(text) };
      }),
    };
  });
  // Above the gate S is the RMS of a fit's residuals in the windows' own errors, too large for its form.
  const misfitRule = `Above S = ${formatNumber(gates.misfit_scale)} a fit's form does not describe its windows, and a drawn one is faded.`;
  const noiseFloor = formatNumber(payload.gates?.noise_min_gev ?? NOISE_MIN_GEV);
  // One sentence in both views: the E view draws no band (Martin's directive of 2026-11-15).
  const noiseRule = `${NOISE_FORM_NAME} is fitted with a², b² and c² held non-negative, through ${mode === 'all'
    ? `every fittable window from ${noiseFloor} GeV` : `the anchors and the lowest fittable window from ${noiseFloor} GeV, the low anchor`}; `
    + 'a term the constraint holds at 0 is written "0 (held)". '
    + 'c, the noise term c/E, belongs to that form alone. '
    + `Where a term's SE exceeds its value, ${NOISE_FORM_NAME} and the quadrature form print its square with the square's SE `
    + '(b² = 0.04 ± 8.1 %²), never a symmetric error larger than a term that cannot be negative.';
  if (energy) {
    return {
      mode,
      view: 'energy',
      caption: typographic(`Fits${of} through ${modeLabel(mode, gates)}. This view draws one curve per series with no band: `
        + `${NOISE_FORM_NAME} from 0 GeV, or, where a series has none, the origin-pinned a₀/√E ⊕ 0 from ${formatNumber(gates.e_min_gev)} GeV, `
        + 'solid over the windows it was fitted to and dashed beyond; the other fits are tabled only, the affine a/√E + b drawn in the 1/√E view. '
        + `${noiseRule} `
        + 'S = √(χ²/ν) scales a fit\'s standard errors where χ²/ν > 1 (PDG); '
        + `S = 1 where the windows' own errors stand. ${misfitRule}`),
      columns: [...FIT_TABLE_COLUMNS],
      rows,
    };
  }
  return {
    mode,
    caption: typographic(`Fits${of} through ${modeLabel(mode, gates)}; the quadrature form is tabled, not drawn, and so is `
      + `${NOISE_FORM_NAME}, whose windows reach below this view's ${formatNumber(gates.e_min_gev)} GeV edge. ${noiseRule} `
      + 'S = √(χ²/ν) scales a fit\'s standard errors where χ²/ν > 1 (PDG), and its band then takes Student\'s t of its ν; '
      + `S = 1 where the windows' own errors stand. ${misfitRule}`),
    columns: [...FIT_TABLE_COLUMNS],
    rows,
  };
}

/**
 * The Fit cell of one form in the E view: what the view draws of it, and why
 * not where it does not. One curve per series (Martin's directive of
 * 2026-11-15): a/√E ⊕ b ⊕ c/E where drawable, else a₀/√E as the fallback, so
 * a₀/√E beside a drawn a/√E ⊕ b ⊕ c/E is table only. a/√E ⊕ b is table only
 * (Martin's decisions of 2026-11-13). An a₀/√E with nothing to draw says
 * why first, `missing` (`fitMissingReason`; review-ui F2), so a fit that was
 * never made is never called "table only".
 */
function energyTableName(form, fit, sym = 'σ/E', mf = null, missing = TOO_FEW_WINDOWS) {
  // A series with no fit from 4 GeV (robust declines, no pooled scale, too few windows) has no affine or quadrature
  // fit either: the cell gives the same cause as the pinned one, never "drawn in the 1/√E view" for a fit that is not.
  if (form === 'affine') return fit ? 'Affine a/√E + b — drawn in the 1/√E view' : `Affine a/√E + b — not fitted: ${missing}`;
  if (form === 'pinned') {
    if (!pinnedDrawable(fit)) return `Origin-pinned a₀/√E ⊕ 0 — not drawn: ${missing}`;
    if (noiseDrawable(mf?.noise)) return 'Origin-pinned a₀/√E ⊕ 0 — table only on this view';
    return `Origin-pinned a₀/√E ⊕ 0 — drawn: no ${NOISE_FORM_NAME} fit`;
  }
  if (form === 'noise') {
    if (noiseDrawable(fit)) return `${NOISE_FORM_NAME} — drawn`;
    return `${NOISE_FORM_NAME} — not drawn: ${noiseReasonClause(mf)}`;
  }
  if (!fit) return `Quadrature a/√E ⊕ b — not fitted: ${missing}`;
  const reason = quadratureReason(fit, sym);
  return `Quadrature a/√E ⊕ b — table only${reason ? `: ${reason}` : ''}`;
}

/** The Status cell of a mode with no noise fit: the server's reason, as a clause. */
function noiseStatusCell(mf) {
  return `no fit: ${noiseReasonClause(mf)}`;
}

/**
 * The windows cell of one series: the mode's windows (the affine, pinned and
 * quadrature fits), and, where a/√E ⊕ b ⊕ c/E ran through other windows (the
 * 1–4 GeV windows, the low anchor), its own list with the low anchor named.
 */
function tableWindowsText(payload, s, mf, mode) {
  const base = windowsText(payload, s, mf);
  const noise = mf?.noise ?? null;
  if (!noise) return base;
  const same = (noise.points ?? []).length === (mf.points ?? []).length
    && (noise.points ?? []).every((b) => (mf.points ?? []).includes(b));
  if (same && noise.low_anchor === null) return base;
  return `${base}. ${NOISE_FORM_NAME}: ${noiseWindowsText(payload, s, mf, mode)}`;
}

/* ======================================================= the noise fit == */

/*
 * The words of a/√E ⊕ b ⊕ c/E (brief section 8 and 11 of res-noise, verbatim
 * where the brief quotes them), exported for the drawer (models_notes.js).
 * "the noise term c/E" is written wherever c could be read as the calibration
 * constant c·E_dep or the pooled scale c of the fit weights.
 */

/** The constraint sentence: how the form is fitted, in the plotted quantity's symbol. */
export function noiseConstraintText(sym = 'σ/E') {
  return `Fitted as (${sym})² = A/E + B + C/E² by weighted least squares with A = a², B = b² and C = c² held non-negative, so every term is real.`;
}

/** The held phrase: "b = 0, held there by the constraint b² ≥ 0", its plural for two terms; '' with none. */
export function noiseHeldPhrase(held) {
  const h = [...(held ?? [])];
  if (!h.length) return '';
  if (h.length === 1) return `${h[0]} = 0, held there by the constraint ${h[0]}² ≥ 0`;
  const and = (xs) => (xs.length < 3 ? xs.join(' and ') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`);
  return `${and(h.map((t) => `${t} = 0`))}, held there by the constraints ${and(h.map((t) => `${t}² ≥ 0`))}`;
}

/**
 * The sentence every fitted curve's tooltip on the E view carries, verbatim
 * (Martin's directive of 2026-11-15): no band is drawn there, and where the
 * fit's uncertainty is instead.
 */
export const ENERGY_NO_BAND_TEXT = 'No band is drawn on this view: the standard errors above and the fit table carry the fit\'s uncertainty.';

/**
 * The share of the x axis from E = 0 below which an entry reads as the axis
 * line (brief-fix m7): a fixed fraction, so the output is deterministic.
 */
export const NOISE_AXIS_SHARE = 1e-3;

/** What the entry caret and the drawer add where a curve enters below `NOISE_AXIS_SHARE` of the axis (brief-fix m7, verbatim). */
export const NOISE_AXIS_LINE_TEXT = 'less than 0.1% of the axis from E = 0: the curve runs up along the axis line there.';

/** The floor sentence: why the noise fit uses windows from `floor` GeV (1). */
export function noiseFloorText(floor = NOISE_MIN_GEV) {
  return `It uses windows from ${formatNumber(floor)} GeV: below that a 1 GeV window reaches momenta near zero, so its average of 1/E² is far `
    + 'from what its plotted energy implies, and no single abscissa can carry the noise term c/E.';
}

/** The naming caveat: c is a fitted coefficient, not a measured noise level. */
export const NOISE_NAMING_CAVEAT = 'c/E is the calorimeter\'s conventional noise term. Here it takes up whatever grows like 1/E at low momentum '
  + '(for a network, its pull toward mid-range; under Median |rel. err.|, the response\'s bias as well), so c is a fitted coefficient, '
  + 'not a measured noise level.';

/**
 * The low-anchor sentence of the 3-anchor mode, the low anchor by its label.
 * `nAnchors` is the anchors it runs through besides the low anchor: three as a
 * rule, two on a table whose anchors coincide (the XGBoost recordings), so the
 * count is said as it is, as the drawer says it (N-notes).
 */
export function noiseLowAnchorText(label, floor = NOISE_MIN_GEV, nAnchors = 3) {
  const count = { 1: 'the one anchor', 2: 'the two anchors', 3: 'the three anchors' }[nAnchors] ?? `the ${formatInt(nAnchors)} anchors`;
  return `In the 3-anchor mode it runs through ${count} and the lowest fittable window from ${formatNumber(floor)} GeV (${label}), `
    + 'since anchors from 5 GeV cannot fix a 1/E term.';
}

/** The least |ρ| between two fitted squares that the card calls strong (the drawer's `STRONG_RHO`, N-notes). */
export const NOISE_STRONG_RHO = 0.7;

/**
 * The correlation line (brief section 11): the non-null correlations of the
 * fitted squares from `params.rho`, or null where none is (two terms held, so
 * no free pair). §11's sentence where the largest |ρ| reaches
 * `NOISE_STRONG_RHO` and every ρ is negative (the terms trade off); "strongly
 * correlated" without the trade-off where a strong ρ is positive; below it,
 * the largest |ρ|, never "strongly" (the single-shower recordings: |ρ| ≈ 0.3).
 */
export function noiseCorrelationText(rho) {
  const pairs = [['a2b2', 'ρ(a², b²)'], ['a2c2', 'ρ(a², c²)'], ['b2c2', 'ρ(b², c²)']].filter(([key]) => Number.isFinite(rho?.[key]));
  if (!pairs.length) return null;
  const list = pairs.map(([key, name]) => `${name} = ${sig(rho[key])}`).join(', ');
  const largest = Math.max(...pairs.map(([key]) => Math.abs(rho[key])));
  if (largest < NOISE_STRONG_RHO) {
    // Rounded as the list is, except where rounding would read as the threshold it lies below: 0.69999 is
    // truncated to 0.699, never shown as "0.7, below 0.7".
    const rounded = sig(largest);
    const shown = Number(rounded) >= NOISE_STRONG_RHO ? sig(Math.floor(largest * 1000) / 1000) : rounded;
    return `${list}: no pair of the fitted squares is strongly correlated here (largest |ρ| = ${shown}, below ${formatNumber(NOISE_STRONG_RHO)}).`;
  }
  if (pairs.every(([key]) => rho[key] < 0)) {
    return `${list}: the terms trade off against each other over the fitted windows, so the curve is better determined than its terms.`;
  }
  return `${list}: the fitted squares are strongly correlated over the fitted windows, so the curve is better determined than its terms.`;
}

/**
 * The entry caret's sentence: where the curve comes down into the plot, and
 * the term that makes it rise without bound as E → 0 (the noise term c/E when
 * C > 0, else the stochastic term a/√E).
 */
export function noiseEntryText(energy, term) {
  const through = term === 'c' ? 'noise term c/E' : 'stochastic term a/√E';
  return `It comes down into the plot at E = ${sig(energy)} GeV: ${NOISE_FORM_NAME} rises without bound as E → 0, through its ${through}.`;
}

/** The ratio panel's count of windows below the noise floor, under a deposit a/√E ⊕ b ⊕ c/E reference. */
export function noiseBelowText(n, floor = NOISE_MIN_GEV) {
  const f = formatNumber(floor);
  return `${plural(n, 'window')} below ${f} GeV ${n === 1 ? 'is' : 'are'} not drawn on the ratio panel: `
    + `no window below ${f} GeV enters the deposit's ${NOISE_FORM_NAME} fit.`;
}

/** A mode's noise_reason as a clause ("fewer than three windows …"), for the table and the reference's why. */
function noiseReasonClause(mf) {
  const reason = typeof mf?.noise_reason === 'string' && mf.noise_reason ? mf.noise_reason : 'no fit in this response';
  return reason.replace(/^No a\/√E ⊕ b ⊕ c\/E fit:\s*/u, '').replace(/\.$/u, '');
}

/** The windows a noise fit ran through, by label, the low anchor named, with the mode's substitutions. */
function noiseWindowsText(payload, s, mf, mode) {
  const noise = mf?.noise;
  if (!noise) return '—';
  const subs = mf.substitutions ?? [];
  const parts = (noise.points ?? []).map((bin) => {
    const sub = subs.find((x) => x.used === bin);
    const label = binLabel(payload, s, bin);
    if (bin === noise.low_anchor) return `${label} (the low anchor)`;
    return sub ? `${label} (for ${binLabel(payload, s, sub.nominal)})` : label;
  });
  const out = parts.length ? parts.join(', ') : 'none';
  return mode === 'anchors' && (noise.low_anchor === null || noise.low_anchor === undefined)
    ? `${out}; no low anchor: no other window from ${formatNumber(payload?.gates?.noise_min_gev ?? NOISE_MIN_GEV)} GeV is fittable` : out;
}

/** Whether a noise fit block can be drawn: its three squares finite and non-negative, one of them positive. */
export function noiseDrawable(fit) {
  const p = fit?.params ?? {};
  return fit?.form === 'noise' && [p.a2, p.b2, p.c2].every((v) => Number.isFinite(v) && v >= 0) && p.a2 + p.b2 + p.c2 > 0;
}

/** The term that dominates a noise curve as E → 0: 'c' when C > 0, 'a' when A > 0, else null (flat). */
function noiseTermAtZero(fit) {
  const p = fit?.params ?? {};
  if (p.c2 > 0) return 'c';
  if (p.a2 > 0) return 'a';
  return null;
}

/** The noise curve's lowest energy where it is not flat (GeV): its grid runs log-spaced from here to 4 GeV. */
const NOISE_E_MIN_GEV = 0.01;
/** The log-spaced steps of that grid below 4 GeV. */
const NOISE_LOG_STEPS = 96;

/**
 * The energies a noise curve is evaluated at: log-spaced from
 * `NOISE_E_MIN_GEV` to 4 GeV (the curve is steep there), the uniform
 * `E_GRID_STEP_GEV` steps to `max`, and `extra` (span edges, entries) inside
 * (0, max]; from exactly 0 for a flat curve (A = C = 0), which has a value there.
 */
function noiseGrid(fit, max, extra = []) {
  const flat = noiseTermAtZero(fit) === null;
  const out = flat ? [0] : [];
  const top = Math.min(4, max);
  for (let i = 0; i <= NOISE_LOG_STEPS; i += 1) out.push(NOISE_E_MIN_GEV * (top / NOISE_E_MIN_GEV) ** (i / NOISE_LOG_STEPS));
  out.push(...energyGrid(E_GRID_STEP_GEV, max));
  for (const e of extra) if (Number.isFinite(e) && e > 0 && e <= max) out.push(e);
  out.sort((a, b) => a - b);
  return out.filter((e, i) => i === 0 || e - out[i - 1] > 1e-9);
}

/**
 * Where a noise curve's line comes down through `hi` (%), from C·u² + A·u +
 * (B − hi²) = 0 with u = 1/E (the stable root 2(hi² − B)/(A + √(A² + 4C(hi² −
 * B)))): {E}, or {above: true} where it stays above the top over the whole
 * axis (B ≥ hi²), or null where it never rises above it (flat, B < hi²).
 */
function noiseLineEntry(fit, hi) {
  const p = fit.params;
  const H = hi * hi;
  if (!(p.a2 > 0) && !(p.c2 > 0)) return p.b2 > H ? { above: true } : null;
  if (p.b2 >= H) return { above: true };
  const u = (2 * (H - p.b2)) / (p.a2 + Math.sqrt(p.a2 * p.a2 + 4 * p.c2 * (H - p.b2)));
  return u > 0 ? { E: 1 / u } : { above: true };
}

/* ========================================================== the E view == */

/** The card's two views: σ/E against a reversed 1/√E axis, and against E in GeV with a ratio panel. */
export const RES_VIEWS = Object.freeze(['linear', 'energy']);

/** The view in force: 'energy' when asked for, 'linear' otherwise. */
export function resolutionView(view) {
  return view === 'energy' ? 'energy' : 'linear';
}

/** What the ratio panel divides by: each shower's deposit fit (the default), or a literature curve of the catalogue. */
export const RATIO_REFERENCES = Object.freeze(['deposit', ...REFERENCE_KEYS]);

/**
 * The literature curves the E view draws, in the catalogue's order: `literature`,
 * the card's π± | e± toggles (both by default; Martin's requests of 2026-11-11).
 * Unknown keys are dropped. Without the array, the older single-choice
 * `reference` draws that curve alone, and 'deposit' none, as the tests and the
 * golden still spell it.
 */
export function literatureDrawn(literature, reference = null) {
  const asked = Array.isArray(literature) ? literature : (REFERENCE_KEYS.includes(reference) ? [reference] : []);
  return REFERENCE_KEYS.filter((key) => asked.includes(key));
}

/**
 * What the ratio panel divides by, given the literature curves drawn (`keys`,
 * `literatureDrawn`): each shower's deposit fit when none is; the curve when
 * one is; with both, the one the windows on show lie farther from (Martin's
 * request of 2026-11-11: "the one which needs scaling the most"), by the
 * median over those windows of |ln(σ/E ÷ curve)|, the factor by which that
 * curve would have to be scaled to meet them. The windows are the robust ones
 * (N ≥ fit_n from `yMinGev`: the marks that set k), or every window on show
 * with a positive σ/E where none is robust; π±, the catalogue's first, on a
 * tie or with no window. `windows` [{E, value, n, pLo}]. Returns {key, rule
 * ('deposit' | 'single' | 'farther'), basis ('robust' | 'markers' | null), n,
 * scores [{key, factor (e^median, ≥ 1; null without a window), n}]}.
 */
export function ratioReferenceChoice(keys, windows, gates = DEFAULT_GATES, yMinGev = 2) {
  if (!keys.length) return { key: 'deposit', rule: 'deposit', basis: null, n: 0, scores: [] };
  if (keys.length === 1) return { key: keys[0], rule: 'single', basis: null, n: 0, scores: [] };
  const usable = (windows ?? []).filter((w) => Number.isFinite(w.value) && w.value > 0 && Number.isFinite(w.E) && w.E > 0);
  const robust = usable.filter((w) => (w.n ?? 0) >= gates.fit_n && w.pLo >= yMinGev);
  const set = robust.length ? robust : usable;
  const median = (values) => {
    const a = [...values].sort((p, q) => p - q);
    const m = Math.floor(a.length / 2);
    return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
  };
  const scores = keys.map((key) => {
    const lit = referenceOf(key);
    const logs = set.map((w) => Math.abs(Math.log(w.value / referenceValue(lit, w.E)))).filter(Number.isFinite);
    return { key, factor: logs.length ? Math.exp(median(logs)) : null, n: logs.length };
  });
  let best = scores[0];
  for (const sc of scores.slice(1)) {
    if (sc.factor !== null && (best.factor === null || sc.factor > best.factor * (1 + 1e-12))) best = sc;
  }
  return { key: best.key, rule: 'farther', basis: robust.length ? 'robust' : (usable.length ? 'markers' : null), n: set.length, scores };
}

/**
 * The windows a series draws on the E view in `mode`: every one on [0, x.max]
 * that reports σ/E; anchors: its fitted ones, the noise fit's low anchor among
 * them (a/√E ⊕ b ⊕ c/E runs through it, so it is drawn).
 */
function windowsOnShow(s, mode, gates, xMax) {
  const mf = s.fits?.[mode];
  const fitted = new Set([...(mf?.points ?? []), ...(mf?.noise?.points ?? [])]);
  const eligible = (s.windows ?? []).filter((w) => Number.isFinite(w.value) && Number.isFinite(w.x) && w.x > 0
    && (w.n ?? 0) >= gates.report_n && 1 / (w.x * w.x) <= xMax + 1e-9);
  return mode === 'anchors' ? eligible.filter((w) => fitted.has(w.bin)) : eligible;
}

/**
 * The half-ranges k of the log-symmetric ratio axis [1/k, k]: the first that
 * covers the robust marks. The ladder ends at 50: a robust mark beyond it is
 * clipped with a caret, and the axis name and the drawer say the axis is capped.
 */
export const RATIO_STEPS = Object.freeze([1.1, 1.25, 1.5, 2, 3, 4, 5, 8, 10, 20, 50]);

/** The step of the energies a curve is evaluated at (GeV). */
export const E_GRID_STEP_GEV = 0.25;

/** The plot's height in each view (px): the CSS height of the 1/√E view, and the E view's two panels. */
export const LINEAR_VIEW_PX = 420;
export const ENERGY_VIEW_PX = 600;

/**
 * The fits the E view can draw, in order of preference: one curve per series
 * (Martin's directive of 2026-11-15), a/√E ⊕ b ⊕ c/E from 0 GeV where the
 * series has a drawable one, else a₀/√E from 4 GeV. The affine fit stays on
 * the 1/√E view, and the quadrature a/√E ⊕ b is tabled in both.
 */
export const ENERGY_FORMS = Object.freeze(['noise', 'pinned']);

/** Why a₀/√E is not drawn beside a drawn a/√E ⊕ b ⊕ c/E: never two fitted lines for one series. */
const PINNED_TABLE_ONLY = `table only on this view: the ${NOISE_FORM_NAME} curve is drawn`;

/** The ratio panel's share of the two grids' height. */
const RATIO_SHARE = 0.26;
/**
 * The gap between the two grids (px): 1.4 label heights, so the main panel's
 * "0" and the ratio panel's top tick label never touch. Read where the layout
 * is built, so the print tokens apply in an export.
 */
function gridGapPx() {
  return Math.round(1.4 * THEME.fontLabel);
}
/** Shower B's line strength on this view, where the dash means extrapolation. */
const B_STRENGTH = 0.7;
/**
 * A 1/√E-view band that spans half its axis or more is drawn as its two edges: this width (× `lineAxis`)
 * and this asked opacity, raised to 3:1 where the card needs it.
 */
const EDGE_WIDTH = 0.8;
const EDGE_OPACITY = 0.5;
/** The end labels' gap from the plot's right border, and their least vertical pitch, as shares of `fontTip`. */
const END_LABEL_GAP = 0.5;
const END_LABEL_PITCH = 1.1;
/**
 * An end label is ink text (THEME.text: 4.5:1 or more on every card, CLAUDE.md
 * section 2), led by a key stroke in its curve's own colour, dash, width and
 * strength: a curve colour may sit near 3:1 (the literature hues on the dark
 * card, the network teal on white), which a mark may and text may not. The
 * stroke's length and its gap before the text, as shares of `fontTip`.
 */
const END_KEY_LENGTH = 1.2;
const END_KEY_GAP = 0.35;
/** A literature curve's dotted line width (× `lineAxis`): its hues sit near 3:1 on the dark card. */
const LITERATURE_WIDTH = 1.6;
/** An extrapolated part, and a literature curve. */
const DASH_EXTRAPOLATED = [6, 4];
const DASH_LITERATURE = [1.5, 3];
/** The band quantile of a fit block that carries none (the 1/√E view's affine and pinned bands). */
const DEFAULT_QUANTILE = 1.96;
/** A literature curve's legend swatch: three dots, as the curve is drawn. */
const LITERATURE_ICON = 'path://M0,4h2.4v2.4h-2.4zM5,4h2.4v2.4h-2.4zM10,4h2.4v2.4h-2.4z';
/** What the literature curves' tooltips and the drawer say of their provenance. */
export const LITERATURE_PROVENANCE = 'as printed in the legend of the supplied figure (ECCE G4 simulation, dual-readout '
  + `inlay, 2.55 < η < 3.98), ${REFERENCE_UNITS}; no interval reported; the figure does not state the energy range the curve was fitted over; `
  + 'it is drawn over the whole axis; it describes that simulation\'s particles, not this detector';

/* --------------------------------------------------------- evaluators -- */

/**
 * One fit block at one energy, in %, from its params alone, or null where the
 * fit has no value there. x = 1/√E and q the block's `band_quantile` (1.96
 * when absent).
 *
 * - pinned: {y, lo, hi, cutLo}, y = a₀·x, half-width q·SE(a₀)·x;
 * - affine: {y, lo, hi, cutLo}, y = a·x + b, half-width
 *   q·√((x·SE(a))² + 2ρ·x·SE(a)·SE(b) + SE(b)²);
 * - noise: {y} alone, y = √max(z, 0) with z = A·u + B + C·u², u = 1/E, the
 *   constrained fit's line. No band is computed for this form, conditional or
 *   otherwise (Martin's directive of 2026-11-15: the E view draws none, and
 *   `rfit.band` refuses the form). At E = 0 only a flat curve (A = C = 0) has
 *   a value.
 *
 * The affine and pinned half-widths are the 1/√E view's bands
 * (`withSpanEdges`); on the E view the a₀/√E fallback draws its line alone.
 * The SEs are the block's scaled ones and ρ its correlation (S cancels in it),
 * so the covariance is the server's (`stats/resolution_fit.band`).
 */
function evalFitAt(fit, energy) {
  if (!fit || !Number.isFinite(energy)) return null;
  const p = fit.params ?? {};
  const q = Number.isFinite(fit.band_quantile) ? fit.band_quantile : DEFAULT_QUANTILE;
  const num = (v) => (Number.isFinite(v) ? v : 0);
  if (fit.form === 'noise') {
    if (![p.a2, p.b2, p.c2].every(Number.isFinite)) return null;
    if (!(energy > 0) && (energy !== 0 || p.a2 > 0 || p.c2 > 0)) return null;
    const u = energy > 0 ? 1 / energy : 0;
    return { y: Math.sqrt(Math.max(p.a2 * u + p.b2 + p.c2 * u * u, 0)) };
  }
  if (!(energy > 0)) return null;
  const x = 1 / Math.sqrt(energy);
  if (fit.form === 'pinned') {
    if (!Number.isFinite(p.a0)) return null;
    const y = p.a0 * x;
    const half = q * num(p.se_a0) * x;
    return { y, lo: y - half, hi: y + half, cutLo: y - half < 0 };
  }
  if (fit.form === 'affine') {
    if (!Number.isFinite(p.a) || !Number.isFinite(p.b)) return null;
    const sa = num(p.se_a);
    const sb = num(p.se_b);
    const y = p.a * x + p.b;
    const half = q * Math.sqrt(Math.max((x * sa) ** 2 + 2 * num(p.rho_ab) * x * sa * sb + sb * sb, 0));
    return { y, lo: y - half, hi: y + half, cutLo: y - half < 0 };
  }
  return null;
}

/**
 * A fit's rows in % at `energies` (GeV), from the fit block alone
 * (`evalFitAt`): `[[E, y, lo, hi], …]` for the pinned and affine forms, and
 * `[[E, y], …]` for a/√E ⊕ b ⊕ c/E, its line alone, since no band is computed
 * for that form.
 */
export function fitCurveE(fit, energies) {
  const out = [];
  for (const e of energies ?? []) {
    const v = evalFitAt(fit, e);
    if (!v || !Number.isFinite(v.y)) continue;
    out.push(fit.form === 'noise' ? [e, v.y] : [e, v.y, v.lo, v.hi]);
  }
  return out;
}

/** Why a quadrature fit block has no curve (the fit table's E-view name): a term undefined, or no fit at all; null where both are defined. */
function quadratureReason(fit, sym = 'σ/E') {
  if (!fit) return 'too few windows';
  const p = fit.params ?? {};
  const reasons = [];
  if (p.a_defined !== true) reasons.push(`A ≤ 0: ${sym} rises with E`);
  if (p.b_defined !== true) reasons.push(`B ≤ 0: ${sym} falls faster than 1/√E, so there is no real constant term`);
  return reasons.length ? reasons.join('; ') : null;
}

/** Whether an origin-pinned fit block has a slope to draw. */
function pinnedDrawable(fit) {
  return Number.isFinite(fit?.params?.a0);
}

/**
 * Uniform `E_GRID_STEP_GEV` steps from `min` to `max`, `max` itself, and the
 * `extra` energies inside [min, max] (the span edges, so the solid and the
 * dashed part of a curve meet at a shared point), sorted and unique.
 */
export function energyGrid(min, max, extra = []) {
  if (!Number.isFinite(min) || !Number.isFinite(max) || max < min) return [];
  const steps = Math.floor((max - min) / E_GRID_STEP_GEV + 1e-9);
  const out = [];
  for (let i = 0; i <= steps; i += 1) out.push(Number((min + i * E_GRID_STEP_GEV).toFixed(9)));
  out.push(max);
  for (const e of extra ?? []) if (Number.isFinite(e) && e >= min && e <= max) out.push(e);
  out.sort((a, b) => a - b);
  return out.filter((e, i) => i === 0 || e - out[i - 1] > 1e-9);
}

/**
 * The ratio axis's half-range: `{k, provisional, capped}` with k the first of
 * `RATIO_STEPS` that covers the robust marks (1/k ≤ every value ≤ k, whiskers
 * included), the last step where none does: `capped` then counts the robust
 * marks that reach beyond it (0 otherwise), and they get carets. A mark is
 * `{value, lo?, hi?, robust?, marker?}`. Without a robust mark the range is
 * provisional and k covers the markers' values alone (`marker: true`); without
 * those, k = 2.
 */
export function ratioRange(marks) {
  const dev = (v) => (Number.isFinite(v) && v > 0 ? Math.max(v, 1 / v) : null);
  const reachOf = (mark, ends) => {
    let m = 1;
    for (const v of ends ? [mark.value, mark.lo, mark.hi] : [mark.value]) {
      const d = dev(v);
      if (d !== null) m = Math.max(m, d);
    }
    return m;
  };
  const reach = (list, ends) => list.reduce((m, mark) => Math.max(m, reachOf(mark, ends)), 1);
  const cap = RATIO_STEPS[RATIO_STEPS.length - 1];
  const step = (m) => RATIO_STEPS.find((s) => s >= m * (1 - 1e-9)) ?? cap;
  const robust = (marks ?? []).filter((m) => m?.robust && dev(m.value) !== null);
  if (robust.length) {
    return { k: step(reach(robust, true)), provisional: false, capped: robust.filter((m) => reachOf(m, true) > cap * (1 + 1e-9)).length };
  }
  const markers = (marks ?? []).filter((m) => m?.marker && dev(m.value) !== null);
  if (markers.length) return { k: step(reach(markers, false)), provisional: true, capped: 0 };
  return { k: 2, provisional: true, capped: 0 };
}

/**
 * The share of its axis a band of the 1/√E view must cover, at one x of its
 * fitted span (x = 1/√E, `xSpanOf`), to be drawn as its edges. Half: once the
 * windows alone set the range (Martin's decision of 2026-11-11), the three
 * anchors' ν = 1 affine bands (Student's t₀.₉₇₅,₁ = 12.71 once S scales them)
 * washed over the whole plot and fogged every mark under them (CLAUDE.md
 * section 5, the 1/√E view's wide bands). A band that spans half the axis says
 * the fit is barely constrained there; its two edges say as much, and leave
 * the windows legible. The E view draws no band (Martin's directive of
 * 2026-11-15).
 */
export const OUTLINE_SHARE = 0.5;

/**
 * Whether a band `[[x, lo, hi], …]` spans `OUTLINE_SHARE` of its axis
 * [floor, top] or more over its fitted span: at some x in the span, the part
 * of it inside the axis covers that share of the axis, on the scale the panel
 * draws (`log` for a log axis). Such a band is drawn as its two edges, never
 * as a wash that floods the panel. The 1/√E view's alone: the E view draws no
 * band (Martin's directive of 2026-11-15).
 */
export function bandSpansShare(rows, span, floor, top, log = false) {
  if (!span) return false;
  const scale = log ? (v) => (v > 0 ? Math.log(v) : -Infinity) : (v) => v;
  const [f, t] = [scale(floor), scale(top)];
  const need = OUTLINE_SHARE * (t - f);
  return rows.some(([e, lo, up]) => e >= span[0] - 1e-9 && e <= span[1] + 1e-9
    && Math.min(scale(up), t) - Math.max(scale(lo), f) >= need);
}

/**
 * Labels at `ys` (px, any order) spread to a least pitch `gap` within [lo, hi]
 * with the least displacement, their order kept: labels that would overlap are
 * merged into a block centred on the mean of their wanted places (less their
 * offsets in the block), blocks that then overlap are merged in turn, and a
 * block is held inside [lo, hi]. Returns the new positions, in the order given.
 */
export function spreadLabels(ys, gap, lo = -Infinity, hi = Infinity) {
  const order = ys.map((y, i) => [y, i]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const blocks = [];
  const place = (b) => {
    const n = b.want.length;
    const mean = b.want.reduce((a, w, i) => a + (w - i * gap), 0) / n;
    b.top = Math.min(Math.max(mean, lo), Math.max(lo, hi - (n - 1) * gap));
  };
  for (const [y] of order) {
    const block = { want: [y], top: y };
    place(block);
    blocks.push(block);
    while (blocks.length > 1) {
      const last = blocks[blocks.length - 1];
      const prev = blocks[blocks.length - 2];
      if (prev.top + prev.want.length * gap <= last.top + 1e-9) break;
      prev.want.push(...last.want);
      blocks.pop();
      place(prev);
    }
  }
  const out = blocks.flatMap((b) => b.want.map((_, i) => b.top + i * gap));
  const placed = new Array(ys.length);
  order.forEach(([, index], k) => { placed[index] = out[k]; });
  return placed;
}

/* ------------------------------------------------------------- model -- */

/** A fit's mode span [lo, hi] (GeV): the payload's `span_gev`, else its fitted windows' edges; null without. */
function spanOf(mf, s) {
  const span = mf?.span_gev;
  if (Array.isArray(span) && Number.isFinite(span[0]) && Number.isFinite(span[1])) return [span[0], span[1]];
  const chosen = new Set(mf?.points ?? []);
  const fitted = (s?.windows ?? []).filter((w) => chosen.has(w.bin) && Number.isFinite(w.p_lo) && Number.isFinite(w.p_hi));
  return fitted.length ? [Math.min(...fitted.map((w) => w.p_lo)), Math.max(...fitted.map((w) => w.p_hi))] : null;
}

/** "7–16 GeV". */
function spanText(span) {
  return span ? `${formatNumber(span[0])}–${formatNumber(span[1])} GeV` : 'no window';
}

/** Rows `[E, …]` split at a span: {below, inside, above}, each sharing its edge row with the next. */
function splitAtSpan(rows, span) {
  if (!span) return { below: [], inside: [], above: rows };
  const [lo, hi] = span;
  return {
    below: rows.filter((r) => r[0] <= lo),
    inside: rows.filter((r) => r[0] >= lo && r[0] <= hi),
    above: rows.filter((r) => r[0] >= hi),
  };
}

/**
 * A band's two edges as polyline runs, `parts` its {below, inside, above}
 * rows `[E, y, lo, hi]`: {solid (over the span), dashed (beyond it)}, each
 * edge cut to the plot by `clip` (points `[E, v]` to runs).
 */
function edgeRuns(parts, clip) {
  const both = (rows) => [...clip(rows.map((r) => [r[0], r[2]])), ...clip(rows.map((r) => [r[0], r[3]]))];
  return { solid: both(parts.inside), dashed: [...both(parts.below), ...both(parts.above)] };
}

/** Ratio points `[E, r]` cut to [1/k, k] in log r, the scale the panel draws them on. */
function clipLog(points, k) {
  const lk = Math.log(k);
  const runs = [];
  let chunk = [];
  const flush = () => {
    if (chunk.length > 1) runs.push(...clipPolyline(chunk, -lk, lk));
    chunk = [];
  };
  for (const [e, r] of points) {
    if (Number.isFinite(r) && r > 0) chunk.push([e, Math.log(r)]);
    else flush();
  }
  flush();
  return runs.map((run) => run.map(([e, l]) => [e, Math.min(k, Math.max(1 / k, Math.exp(l)))]));
}

/**
 * Where a ratio line, rows `[E, r]`, first leaves [1/k, k], scanning up in E,
 * or null: {at, dir, peak}, `peak` the row that deviates most (its true
 * values). A line alone: every caller passes one, since the E view draws no
 * band (Martin's directive of 2026-11-15).
 */
function ratioCut(rows, k) {
  const lk = Math.log(k);
  const dev = (v) => (Number.isFinite(v) && v > 0 ? Math.abs(Math.log(v)) : Infinity);
  const devRows = rows.map(([e, r]) => {
    const d = dev(r);
    return [e, d, d, d];
  });
  const cut = cutAbove(devRows, lk);
  if (!cut) return null;
  // The first row beyond the axis, where the caret's direction is read.
  const row = rows[Math.max(0, devRows.findIndex((d) => d[1] > lk))];
  return { at: cut.at, dir: row[1] > 1 ? 'up' : 'down', peak: rows[devRows.indexOf(cut.peak)] ?? row };
}

/**
 * Where a fitted curve's ratio line, rows `[E, r]`, comes into [1/k, k] from
 * outside as E rises from its first row (a noise fit's ratio is defined from
 * 0 GeV and often starts beyond the axis; the a₀/√E fallback's starts at
 * curveMin, review-ui F5): {entry, rest}. `entry` {at, dir, whole, peak} | null:
 * where the line comes in; `whole` where it stays outside over every row (its
 * caret then sits at the last row); `peak` the first row, its true values.
 * `rest` the rows from the entry on, `[E, r]`, which `ratioCut` then scans
 * for a later exit. The line alone: no band is drawn on this view (Martin's
 * directive of 2026-11-15).
 */
function ratioEntry(rows, k) {
  const lk = Math.log(k) * (1 + 1e-9);
  const lr = (v) => (Number.isFinite(v) && v > 0 ? Math.abs(Math.log(v)) : Infinity);
  const lineIn = (r) => lr(r[1]) <= lk;
  if (!rows.length) return { entry: null, rest: rows };
  const dirOf = (v) => (Number.isFinite(v) && v > 1 ? 'up' : 'down');
  const iLine = rows.findIndex(lineIn);
  if (iLine < 0) return { entry: { at: rows[rows.length - 1][0], dir: dirOf(rows[0][1]), whole: true, peak: rows[0] }, rest: [] };
  const rest = rows.slice(iLine);
  if (iLine > 0) {
    const [e0, r0] = rows[iLine - 1];
    const [e1, r1] = rows[iLine];
    const dir = dirOf(r0);
    const l0 = Math.log(r0);
    const edge = dir === 'up' ? Math.log(k) : -Math.log(k);
    const t = Number.isFinite(l0) ? (edge - l0) / (Math.log(r1) - l0) : 1;
    return { entry: { at: e0 + Math.min(1, Math.max(0, t)) * (e1 - e0), dir, whole: false, peak: rows[0] }, rest };
  }
  return { entry: null, rest };
}

/** Where a fitted curve's rows `[E, y]` first leave the top `hi`, scanning up in E, or null: {at, peak [E, y] (where it reaches highest)}. */
function lineCut(rows, hi) {
  const cut = cutAbove(rows.map(([e, yv]) => [e, yv, yv, yv]), hi);
  return cut ? { at: cut.at, peak: [cut.peak[0], cut.peak[1]] } : null;
}

/** Where a fitted curve's ratio rows `[E, r]` first leave [1/k, k], scanning up in E, or null: {at, dir, peak [E, r] (where it deviates most)}. */
function ratioLineCut(rows, k) {
  const cut = ratioCut(rows, k);
  return cut ? { at: cut.at, dir: cut.dir, peak: [cut.peak[0], cut.peak[1]] } : null;
}

/**
 * The E view's model of one a/√E ⊕ b ⊕ c/E fit block, drawn from 0 GeV, its
 * line alone (Martin's directive of 2026-11-15: no band on this view): the
 * shape of a drawn fit (`solid` over its `span_gev`, `dashed` below it to 0
 * and above it to x.max, `cut`, …) plus
 *
 * - `full`: rows `[E, y]` over the whole domain, from `NOISE_E_MIN_GEV` (0 for
 *   a flat curve), the ratio's source; `curve` the rows the main panel draws,
 *   from where the line comes down through the top;
 * - `entry` {at (the caret's E), lineAt, above (the line stays above the top
 *   over the whole axis), term ('c' | 'a' | null, the term that rises as
 *   E → 0), atAxis (`at` lies below `NOISE_AXIS_SHARE` of the axis from E = 0,
 *   brief-fix m7)} | null: where the line comes down into the plot
 *   (`noiseLineEntry`); `cut` any later exit, scanning up (`lineCut`);
 * - `held`, `points`, `lowAnchor`: its held terms, windows and low anchor.
 *
 * Without a drawable block: {form, fit, drawable: false, reason (the server's
 * noise_reason, as a clause), span: null, ratio: null, entry: null, cut: null}.
 */
function noiseFitModel(fit, mf, s, ref, x, hi) {
  if (!noiseDrawable(fit)) {
    return { form: 'noise', fit, drawable: false, reason: noiseReasonClause(mf), span: null, ratio: null, entry: null, cut: null };
  }
  const span = Array.isArray(fit.span_gev) && fit.span_gev.every(Number.isFinite) ? [fit.span_gev[0], fit.span_gev[1]] : null;
  const top = Number.isFinite(hi) ? hi : Infinity;
  const root = Number.isFinite(hi) ? noiseLineEntry(fit, hi) : null;
  // A line that comes down through the top beyond the axis end stays above it over the whole axis.
  const line = root?.E > x.max ? { above: true } : root;
  const grid = noiseGrid(fit, x.max, [...(span ?? []), line?.E]);
  const full = fitCurveE(fit, grid);
  // The main panel draws from where the line comes down through the top; above it nothing shows.
  const enteredAt = line?.E ?? 0;
  const curve = line?.above ? [] : full.filter((r) => r[0] >= enteredAt - 1e-9);
  const term = noiseTermAtZero(fit);
  let entry = null;
  if (line?.above) entry = { at: x.max, lineAt: null, above: true, term };
  else if (line?.E) entry = { at: line.E, lineAt: line.E, above: false, term };
  // An entry below NOISE_AXIS_SHARE of the axis from E = 0 reads as the axis line (brief-fix m7).
  if (entry) entry.atAxis = entry.at < x.max * NOISE_AXIS_SHARE;
  // Any exit above the entry, scanning up in E.
  const cut = line?.above ? null : lineCut(full.filter((r) => r[0] > enteredAt + 1e-9), hi);
  const parts = splitAtSpan(curve, span);
  const lineRuns = (rows) => clipPolyline(rows, 0, top);
  const isReference = Boolean(ref && !ref.reason && ref.series === s.key && ref.form === 'noise');
  let ratio = null;
  if (ref && !ref.reason && !isReference) {
    const rows = full.map(([e, yv]) => {
      const r = ref.valueAt(e);
      return r > 0 ? [e, yv / r] : null;
    }).filter(Boolean);
    ratio = rows.length ? { rows } : null;
  }
  const provisional = Boolean(fit.provisional);
  const misfit = isMisfit(fit);
  return {
    form: 'noise', fit, drawable: true, reason: null, span, domain: [curve[0]?.[0] ?? 0, x.max], curve, full,
    solid: lineRuns(parts.inside), dashed: [...lineRuns(parts.below), ...lineRuns(parts.above)],
    entry, cut, provisional, misfit, faded: provisional || misfit,
    converged: fit.converged !== false, isReference, ratio,
    held: [...(fit.params?.held ?? [])], points: [...(fit.points ?? [])], lowAnchor: fit.low_anchor ?? null,
  };
}

/** A series' short name on the canvas note: the shower letter (two showers only) and the estimator. */
function shortName(s, nShowers) {
  const source = { detector: 'deposit', network: 'network', xgb: 'XGBoost' }[s.source]
    ?? (s.colour_slot === 'detector' ? 'deposit' : 'network');
  return nShowers > 1 && s.shower ? `${String(s.shower).toUpperCase()} ${source}` : source;
}

/**
 * The ratio's reference for one shower under 'deposit' (Martin's decisions of
 * 2026-11-13): its detector series' a/√E ⊕ b ⊕ c/E fit, defined from 0 GeV,
 * whose ratio marks start at the noise fit's floor (`noiseMin`, 1 GeV: no
 * window below it enters that fit); else its a₀/√E from `curveMin`, as before,
 * its `why` giving the server's `noise_reason`. `floorGev` is the lowest
 * window edge that takes a ratio mark against it, and `floorBy` how a window is
 * held to it ('p_lo' for the noise fit, 'E' for a₀/√E, whose curve starts there).
 */
function depositReference(all, shower, mode, nShowers, curveMin, xMax, sym = 'σ/E', noiseMin = NOISE_MIN_GEV) {
  const owner = nShowers > 1 ? `shower ${String(shower).toUpperCase()}'s deposit` : 'the deposit';
  const det = all.find((s) => s.source === 'detector' && (s.shower ?? 'a') === shower) ?? null;
  // `interval` null: the reference is held exact and no band about 1 is drawn (Martin's directive of 2026-11-15).
  const base = {
    key: 'deposit', shower, literature: null, interval: null, series: det?.key ?? null, seriesLabel: det?.label ?? null,
    form: null, fit: null, span: null, provisional: false, misfit: false, why: null, valueAt: () => null,
    floorGev: null, floorBy: null, noiseReason: null,
  };
  if (!det) return { ...base, label: `${owner} fit`, reason: 'this shower has no calibrated-deposit series' };
  const mf = det.fits?.[mode] ?? null;
  const noise = noiseDrawable(mf?.noise) ? mf.noise : null;
  const pinned = mf?.pinned ?? null;
  const noiseReason = noise ? null : (mf?.noise_reason ?? null);
  if (noise) {
    const span = Array.isArray(noise.span_gev) ? [noise.span_gev[0], noise.span_gev[1]] : null;
    const valueAt = (e) => {
      if (!(e >= 0 && e <= xMax + 1e-9)) return null;
      const v = evalFitAt(noise, e);
      return v && v.y > 0 ? v.y : null;
    };
    return {
      ...base,
      label: `${owner} ${NOISE_FORM_NAME} fit`,
      why: `its ${NOISE_FORM_NAME} fit, drawn from 0 GeV; its ratio marks start at ${formatNumber(noiseMin)} GeV, the lowest window edge the fit uses`,
      form: 'noise', fit: noise, span, provisional: Boolean(noise.provisional), misfit: isMisfit(noise), valueAt,
      reason: null, floorGev: noiseMin, floorBy: 'p_lo', held: [...(noise.params?.held ?? [])],
    };
  }
  if (!pinnedDrawable(pinned)) {
    return {
      ...base, label: `${owner} fit`, noiseReason,
      reason: `${owner} series has no ${NOISE_FORM_NAME} or a₀/√E fit in this mode, so this shower has no ratio marks`,
    };
  }
  const span = spanOf(mf, det);
  const valueAt = (e) => {
    if (!(e >= curveMin - 1e-9 && e <= xMax + 1e-9)) return null;
    const v = evalFitAt(pinned, e);
    return v && v.y > 0 ? v.y : null;
  };
  return {
    ...base,
    label: `${owner} a₀/√E fit`,
    why: `its a₀/√E fit, since it has no ${NOISE_FORM_NAME} fit (${noiseReasonClause(mf)})`,
    form: 'pinned', fit: pinned, span, provisional: Boolean(pinned.provisional ?? mf?.provisional), misfit: isMisfit(pinned), valueAt,
    reason: null, floorGev: curveMin, floorBy: 'E', noiseReason,
  };
}

/** The ratio's reference for one shower under a literature curve: the same curve for every shower, over the whole axis. */
function literatureReference(entry, shower) {
  return {
    key: entry.key, shower, literature: entry, interval: null, series: null, seriesLabel: null, form: 'literature', fit: null,
    span: null, provisional: false, misfit: false, label: referenceLabel(entry), equation: referenceEquation(entry),
    why: `${referenceEquation(entry)}, ${LITERATURE_PROVENANCE}`, reason: null,
    valueAt: (e) => referenceValue(entry, e),
  };
}

/**
 * The ratio's reference for one shower with no reference on show (the deposit
 * hidden and no literature curve on; Martin's decision of 2026-11-17): no fit
 * and no value anywhere, so every window's ratio is undrawn with `reason`, and
 * no curve is divided by it.
 */
function noReference(shower) {
  return {
    key: 'none', shower, literature: null, interval: null, series: null, form: null, fit: null, span: null,
    provisional: false, misfit: false, label: 'no reference', why: null, reason: NO_REFERENCE_REASON, valueAt: () => null,
  };
}

/**
 * The 1/√E view's provisional role in the E view's words (brief-fix m2): on
 * this view windows of N ≥ 20 below 4 GeV can be drawn, so the fallback's
 * count is said of the windows from 4 GeV, where it is taken.
 */
function energyProvisionalRole(gates) {
  const from = `fewer than two windows from ${formatNumber(gates.e_min_gev)} GeV reach N = `;
  return (role) => role.replace(/^part of a provisional fit: fewer than two windows reach N = /u, `part of a provisional fit: ${from}`);
}

/** The roles of a window below the noise fit's floor (1 GeV): drawn as a point, never fitted. */
function belowRoles(w, gates, floor) {
  const roles = [`below ${formatNumber(floor)} GeV: no fit uses it; drawn as a point only`];
  if ((w.n ?? 0) < gates.whisker_n) roles.push(`below the whisker floor N = ${formatInt(gates.whisker_n)}: drawn as a faded ring`);
  else if ((w.n ?? 0) < gates.fit_n) roles.push(`N < ${formatInt(gates.fit_n)}: drawn faded`);
  return roles;
}

/**
 * The role lines of one window on the E view (Martin's decisions of
 * 2026-11-13: a/√E ⊕ b ⊕ c/E runs through windows from 1 GeV, so a window of
 * 1–4 GeV can be fitted): the 1/√E view's for a window the mode's other fits
 * use; "fitted by a/√E ⊕ b ⊕ c/E only" for one only the noise fit uses (the
 * low anchor named); for a window of 1–4 GeV the noise fit leaves out, why;
 * below 1 GeV, no fit.
 */
function energyRoles(payload, s, mf, mode, w, gates, curveMin, noiseMin) {
  const pLo = Number.isFinite(w.p_lo) ? w.p_lo : 1 / (w.x * w.x);
  if (pLo < noiseMin) return belowRoles(w, gates, noiseMin);
  const noise = mf?.noise ?? null;
  const inNoise = (noise?.points ?? []).includes(w.bin);
  const inMode = (mf?.points ?? []).includes(w.bin);
  const est = estimatorOf(payload);
  const lowOfAnchors = s.fits?.anchors?.noise?.low_anchor ?? null;
  const allNote = mode === 'all' && lowOfAnchors === w.bin && !inMode
    ? [`the low anchor of the 3-anchor mode's ${NOISE_FORM_NAME} fit (the larger marker)`] : [];
  if (inMode) {
    const roles = roleOf(payload, s, mf, mode, w, gates).map(energyProvisionalRole(gates));
    return inNoise ? roles : [...roles, `not in the ${NOISE_FORM_NAME} fit`];
  }
  if (inNoise) {
    // From 4 GeV a window the noise fit uses but a₀/√E does not is one Robust σ (IQR) declines there (brief-fix nit 1).
    const declined = pLo >= curveMin && declinedWindow(est, s, mf, mode, gates)?.bin === w.bin;
    let lead;
    if (noise.low_anchor === w.bin) {
      lead = `the low anchor of the ${NOISE_FORM_NAME} fit: the lowest fittable window from ${formatNumber(noiseMin)} GeV, `
        + 'since anchors from 5 GeV cannot fix a 1/E term; a₀/√E does not use it';
    } else if (declined) {
      lead = `fitted by ${NOISE_FORM_NAME} only; declined by a₀/√E: ${declinedText(w)}`;
    } else if (pLo >= curveMin) {
      lead = `fitted by ${NOISE_FORM_NAME} only: a₀/√E does not use it in this mode`;
    } else {
      lead = `fitted by ${NOISE_FORM_NAME} only: a₀/√E uses windows from ${formatNumber(curveMin)} GeV`;
    }
    const roles = [lead];
    if (noise.provisional) {
      roles.push(`part of a provisional fit: fewer than two windows from ${formatNumber(gates.e_min_gev)} GeV reach N = ${formatInt(gates.fit_n)}, so the fit runs through windows of N ≥ ${formatInt(gates.whisker_n)}`);
    }
    return [...roles, ...allNote];
  }
  // Not fitted by any form in this mode. From 4 GeV the noise fit's eligibility is the other fits', so the 1/√E
  // view's role says why (N, the fit weight, robust's decline); below it, say why by its cause.
  const below4 = pLo < curveMin;
  if (!below4) return [...roleOf(payload, s, mf, mode, w, gates).map(energyProvisionalRole(gates)), ...allNote];
  const where = `below ${formatNumber(curveMin)} GeV, the floor of a₀/√E; `;
  const weight = weightState(est, w);
  let why;
  if (w.n < gates.whisker_n) why = `below the whisker floor N = ${formatInt(gates.whisker_n)}: drawn as a faded ring, not fitted`;
  else if (w.n < gates.fit_n) why = `not fitted because N < ${formatInt(gates.fit_n)}, the fit and range floor: drawn faded`;
  else if (weight === 'tied') why = 'not fitted: its bootstrap SE is below 10⁻⁶ of its value (tied replicates), so it carries no fit weight; drawn in the all-windows mode only';
  else if (weight === 'withheld') why = 'not fitted: its robust interval is withheld, so it carries no fit weight';
  else if (!noise) why = `not fitted: ${mf?.noise_reason ? `no ${NOISE_FORM_NAME} fit (${noiseReasonClause(mf)})` : 'no fit runs through it in this mode'}`;
  else why = 'not fitted in this mode';
  const roles = [`${where}${why}`];
  if (mode === 'all' && (s.fits?.anchors?.points ?? []).includes(w.bin)) roles.push('an anchor of the 3-anchor mode (the larger marker)');
  return [...roles, ...allNote];
}

/**
 * Everything the E view's chart, its tooltips and the drawer need, decided
 * once. Pure. `opts` = {windows, shower, literature (the curves drawn,
 * `literatureDrawn`; the older single `reference` where it is absent),
 * deposit (false hides the calibrated deposit, `shownSeries`), eMax (the E
 * max slider's value: undefined keeps the server's axis end, anything else,
 * null included, is `res_axis.eMaxOf`'s)}. The ratio's reference follows
 * from them (`ratioReferenceChoice`).
 * Null without a resolution payload that carries `axis.energy`.
 *
 * The returned shape (models_notes.js builds the E view's drawer from it):
 *
 * - `view` 'energy', `mode`, `gates`, `estimator` (`estimatorOf`), `nShowers`, `payload`,
 *   `deposit` {shown, hidden, forced} (`depositState`);
 * - `x` {min, max, interval, name, serverMax (the server's axis end), ticks
 *   (the tick values under E max, `eAxisTicks`, else null), eMax (null
 *   without E max, else {value, min, max, step}: the slider's value and range)}
 *   and `y` {lo, hi, interval, provisional,
 *   name, n_clipped, basis (the server's `y_model.note` while the deposit is
 *   hidden and the model series' range is in force, else null)}: `axis.energy`'s
 *   (`y_model` while the deposit is hidden), the y range the server's 2 GeV rule;
 *   `curveMinGev` (no a₀/√E below it), `noiseMinGev` (the noise fit's window
 *   floor, 1 GeV), `yMinGev`, `dataMaxGev`, `rule` and
 *   `notes` (the server's sentences);
 * One fitted curve per series and panel, with no band anywhere on the view
 * (Martin's directive of 2026-11-15): a series' a/√E ⊕ b ⊕ c/E where it has a
 * drawable one, else its origin-pinned a₀/√E, else none.
 *
 * - `reference` {key: 'deposit' | 'pi' | 'e' | 'none' (the deposit hidden and
 *   no literature curve on: no ratio is taken, every byShower entry the
 *   reason "no reference is on show"), choice (`ratioReferenceChoice`:
 *   why this one; {key: 'none', rule: 'none', …} with none), label (the ratio axis's
 *   wording), literature: the catalogue entry or null, interval: null (the
 *   deposit's too: the reference is held exact and no band about 1 is drawn),
 *   flag: 'no interval reported' under a
 *   literature reference (else null), byShower: {a, b}}. Each shower's entry is {key, shower, label, form (
 *   'noise' | 'pinned' | 'literature' | null), fit, series (the deposit series' key),
 *   seriesLabel, span, provisional, misfit (its form does not describe the
 *   deposit's windows, said in the drawer), why (which fit and why), reason (null, or
 *   why that shower has no ratio marks), interval (null), valueAt(E) (the
 *   reference in %, null outside its domain), floorGev and floorBy (the lowest
 *   window edge that takes a ratio mark against it: 1 GeV by p_lo for 'noise',
 *   4 GeV by E for 'pinned'), noiseReason (the server's `noise_reason` where
 *   the deposit has no noise fit), held (a noise reference's held terms); a
 *   literature entry adds `equation`}. The reference's own curve is the curve
 *   its deposit series draws on the main panel; on the ratio panel it is 1 by
 *   construction and not drawn;
 * - `series`: [{key, label, short (the canvas note's name), raw, colour, isB,
 *   offsetPx (0: no dodge on this view), lineOpacity (the strength its lines
 *   take: shower B 70%, raised to 3:1 where the card needs it), mf,
 *   provisional, span, points, fits: {noise, pinned, quadrature (table only:
 *   never drawable, kept so a reader of the model can name it; the E view has
 *   no quadrature evaluator)}, drawnForm ('noise' | 'pinned' | null: the one
 *   curve the series draws), drawn (that fit's model, `fits[drawnForm]`, or
 *   null), unreported, reference (its shower's entry), noise {points,
 *   lowAnchor, span, held, reason (the server's noise_reason, or null)}}].
 *   Without an a₀/√E to draw, `fits.pinned` is {drawable: false, reason:
 *   `fitMissingReason`'s}, whatever the noise fit does; with one beside a
 *   drawable noise fit, {drawable: false, reason: "table only on this view:
 *   the a/√E ⊕ b ⊕ c/E curve is drawn"}; drawn as
 *   the fallback it adds `fallback: true`, `full` (its rows from curveMin, the
 *   ratio's source), `entry` (where it starts above the top: {at, lineAt,
 *   above, term 'a', atAxis false}, review-ui F5) and `noiseReason` (the server's
 *   noise_reason as a clause);
 * - a point: {w, E (= 1/x², x = ⟨1/√p⟩), x, value, ci, lo, hi, n, whisker,
 *   weak, subFloor, below4, belowNoise (p_lo below the noise floor), anchor
 *   (the 3-anchor mode's anchors and its noise low anchor: the larger
 *   marker), fitted (by the mode's other fits), noiseFitted, lowAnchor (this
 *   mode's), robust, opacity, clip, over, roles (`energyRoles`), ratio}; `ratio` {drawn, reason, ref (the reference in % at E),
 *   value, lo, hi (the whisker divided, null without one), robust (the
 *   window's, against a reference neither provisional nor a misfit: only
 *   these set k), clip, over};
 * - a drawn fit: {form, fit, drawable: true, reason: null, span, domain
 *   [from, x.max] (from curveMinGev for a₀/√E; for a/√E ⊕ b ⊕ c/E where its
 *   line comes into the plot, 0 for a flat one), curve [[E, y]] (its line, no
 *   band), solid (the runs over the span, clipped to [0, y.hi]), dashed (the
 *   runs beyond it), cut (where its curve leaves the top, which no fit sets,
 *   scanning up in E: {at, peak [E, y] where it reaches highest}),
 *   provisional, misfit (`isMisfit`), faded (provisional or misfit: its solid
 *   and dashed parts drawn faded on both panels), converged, isReference (the
 *   deposit reference itself: its ratio ≡ 1 is not drawn), ratio {rows
 *   [[E, ratio]], solid, dashed, cut (where it leaves [1/k, k], which no fit
 *   sets: {at, dir, peak [E, ratio] where it deviates most}), entry (where it
 *   comes into [1/k, k] as E rises from its first row, `ratioEntry`'s
 *   {at, dir, whole, peak}; null where it starts inside)} (null for the reference or
 *   without one); a noise fit adds `full` ([[E, y]] over its whole domain),
 *   `entry` ({at, lineAt, above, term, atAxis}), `held`, `points` and
 *   `lowAnchor` (`noiseFitModel`), and without a block it is {form, fit,
 *   drawable: false, reason (the server's noise_reason as a clause)}; a fit
 *   not drawn is {form, fit, drawable: false, reason, span, ratio: null,
 *   entry: null, cut: null};
 * - `literature`: the curves drawn (`literatureDrawn`), in the catalogue's
 *   order, [{key, entry, isReference (the ratio panel divides by it), label
 *   ("π±", its end label), legend, colour (its identity colour on the card in
 *   force, `literatureColour`), curve [[E, %]], runs, cut {at, peak} | null,
 *   ratio (beside a literature reference: {rows [[E, this/reference]], runs
 *   (clipped to [1/k, k]), cut (`ratioCut`, where it leaves the axis)}; else
 *   null)}];
 * - `ratio` {k, provisional, capped (the robust marks beyond the last
 *   `RATIO_STEPS` value, 0 when none), reference (key), clipped {markers,
 *   whiskers, fits (the curves' ratios that leave or come into the axis),
 *   literature (literature ratio lines that leave the axis), each with a
 *   caret}, belowNotDrawn (windows below the curve
 *   floor left off the ratio panel under the deposit reference), below
 *   ([{shower, form, floorGev, n}], those windows by shower and reference
 *   form: 'noise' at 1 GeV, `noiseBelowText`), noReference ([{shower, reason}]),
 *   none (true with no reference on show: no ratio mark, no curve ratio, k
 *   not provisional, nothing capped or counted below, noReference [])};
 * - `twoOnShow` (two showers drawn) and `endLabels` {main, ratio}: [{key,
 *   form, name (the legend entry that hides it), text ("A", "B", "π±"),
 *   colour (the series', or the literature curve's identity colour),
 *   literature, stroke, value (at x.max)}], one per drawn curve whose right
 *   end lies on the panel;
 * - `clipped` {markers, whiskers, fits, entries, literature, ratio}: the marks
 *   clipped at the main axis, each with a caret (`fits` the fits that
 *   leave the top as E rises, `entries` the curves that come down into the
 *   plot from the top as E rises, a/√E ⊕ b ⊕ c/E's from 0 and the a₀/√E
 *   fallback's from curveMin, or lie above it over the whole axis; `literature`: the drawn
 *   literature curves that cross its top), and the ratio panel's carets in
 *   total (markers + whiskers + fits + literature);
 * - `offScale`: [{label, E, entries: [{key, short, value, n}]}], the drawn
 *   windows above y.hi grouped by window, in E order;
 * - `spans` {shared, span, bySeries: [{key, label, form, span}]}: one entry
 *   per series with a curve, its fitted span, `shared` when they are one;
 * - `noteText` {offScale, extrapolation, warning}: the canvas note's strings
 *   before they are fitted to its width ('' where there is nothing to say;
 *   `extrapolation` only while a drawn curve has a dashed run on either panel);
 *   `warning` the literature disclosure, under the median estimator with a
 *   literature curve on;
 * - `nPoints`, `nLines` (the series with a curve).
 */
export function energyModel(payload, opts = {}) {
  if (!payload || !Array.isArray(payload.series) || !payload.axis?.energy) return null;
  const ea = payload.axis.energy;
  const mode = windowMode(opts.windows);
  const gates = { ...DEFAULT_GATES, ...(payload.gates ?? {}) };
  const estimator = estimatorOf(payload, opts.estimator);
  const deposit = depositState(payload, opts.deposit);
  const xa = ea.x ?? {};
  const serverMax = Number.isFinite(xa.max) ? xa.max : 80;
  const serverInterval = Number.isFinite(xa.interval) ? xa.interval : 10;
  const x = {
    min: Number.isFinite(xa.min) ? xa.min : 0, max: serverMax,
    interval: serverInterval, name: xa.name ?? 'Energy E [GeV]',
    serverMax, ticks: null, eMax: null,
  };
  // E max (Martin's decision of 2026-11-17): any `eMax` but undefined ends the axis on the slider's value, its
  // lower end for null; every curve grid, reference domain, end label and caret below derives from x.max.
  const eMax = opts.eMax === undefined ? null : eMaxOf(payload, opts.eMax);
  if (Number.isFinite(eMax)) {
    x.max = eMax;
    x.interval = eTickStep(eMax, serverMax, serverInterval);
    x.ticks = eAxisTicks(eMax, serverMax, serverInterval);
    x.eMax = { value: eMax, ...eMaxRange(payload) };
  }
  // The range follows the series on show: the model series' own while the deposit is hidden (`axis.energy.y_model`).
  const y = rangeInForce(ea.y, ea.y_model, deposit.hidden, estimator);
  const hi = Number.isFinite(y.hi) ? y.hi : Infinity;
  const curveMin = Number.isFinite(ea.curve_min_gev) ? ea.curve_min_gev : gates.e_min_gev;
  // The noise fit's floor: no window below it enters a/√E ⊕ b ⊕ c/E, or takes a ratio mark against the deposit's.
  const noiseMin = Number.isFinite(ea.noise_min_gev) ? ea.noise_min_gev : (Number.isFinite(gates.noise_min_gev) ? gates.noise_min_gev : NOISE_MIN_GEV);
  const yMinGev = Number.isFinite(ea.y_min_gev) ? ea.y_min_gev : 2;
  const all = payload.series;
  const nShowers = new Set(all.map((s) => s.shower).filter(Boolean)).size;
  const shown = shownSeries(payload, opts.shower, opts.deposit);
  const colours = seriesColours(shown);
  // The curves drawn, and what the ratio divides by: the one drawn, the farther of two, or the deposit fit; with the
  // deposit hidden and no curve on, nothing (Martin's decision of 2026-11-17: no ratio mark is drawn).
  const drawnKeys = literatureDrawn(opts.literature, opts.reference);
  const onShow = shown.flatMap((s) => windowsOnShow(s, mode, gates, x.max).map((w) => {
    const E = 1 / (w.x * w.x);
    return { E, value: w.value, n: w.n, pLo: Number.isFinite(w.p_lo) ? w.p_lo : E };
  }));
  const none = deposit.hidden && !drawnKeys.length;
  const choice = none
    ? { key: 'none', rule: 'none', basis: null, n: 0, scores: [] }
    : ratioReferenceChoice(drawnKeys, onShow, gates, yMinGev);
  const referenceKey = choice.key;
  const entry = referenceKey === 'deposit' || none ? null : referenceOf(referenceKey);
  // `fits` counts the fits that leave the top as E rises (a caret each); `entries` the curves that come down into the
  // plot from the top as E rises (a/√E ⊕ b ⊕ c/E from 0, the a₀/√E fallback from curveMin; one caret each).
  const clipped = { markers: 0, whiskers: 0, fits: 0, entries: 0, literature: 0, ratio: 0 };
  const energyOf = (w) => (Number.isFinite(w.x) && w.x > 0 ? 1 / (w.x * w.x) : (w.p_mean ?? w.p_lo ?? null));

  const byShower = {};
  for (const sh of new Set(shown.map((s) => s.shower ?? 'a'))) {
    if (none) byShower[sh] = noReference(sh);
    else byShower[sh] = entry ? literatureReference(entry, sh) : depositReference(all, sh, mode, nShowers, curveMin, x.max, estimator.symbol, noiseMin);
  }
  let belowNotDrawn = 0;
  // The windows left off the ratio panel below a deposit reference's floor, by shower and reference form.
  const below = new Map();

  const series = shown.map((s) => {
    const colour = colours[s.key];
    const isB = s.shower === 'b' && nShowers > 1;
    const mf = s.fits?.[mode] ?? null;
    const ref = byShower[s.shower ?? 'a'] ?? null;
    const fittedBins = new Set(mf?.points ?? []);
    const noiseBins = new Set(mf?.noise?.points ?? []);
    const lowAnchor = s.fits?.anchors?.noise?.low_anchor ?? null;
    // The larger marker: an anchor of the 3-anchor mode, its noise fit's low anchor included.
    const anchorBins = new Set([...(s.fits?.anchors?.points ?? []), ...(lowAnchor === null ? [] : [lowAnchor])]);
    // Every window on [0, x.max] that reports a value; the anchors mode draws its fitted ones only.
    const points = windowsOnShow(s, mode, gates, x.max).map((w) => {
      const E = 1 / (w.x * w.x);
      const ci = Array.isArray(w.ci95) && Number.isFinite(w.ci95[0]) && Number.isFinite(w.ci95[1]) ? w.ci95 : null;
      const whisker = Boolean(w.whisker) && ci !== null;
      const weak = (w.n ?? 0) < gates.fit_n;
      const subFloor = !whisker;
      const opacity = subFloor ? legibleOpacity(colour, SUB_FLOOR_OPACITY) : (weak ? legibleOpacity(colour, WEAK_OPACITY) : 1);
      const clip = whisker ? clampInterval(ci[0], ci[1], 0, hi) : null;
      const over = w.value > hi || w.value < 0;
      if (over) clipped.markers += 1;
      if (clip && (clip.cutLo || clip.cutHi)) clipped.whiskers += 1;
      const pLo = Number.isFinite(w.p_lo) ? w.p_lo : E;
      const below4 = pLo < curveMin;
      const robust = (w.n ?? 0) >= gates.fit_n && pLo >= yMinGev;
      // A ratio is robust only against a reference that is itself robust: a provisional deposit fit, or one whose
      // form does not describe its windows (a misfit, S above the gate), never sets k.
      const ratioRobust = robust && !ref?.provisional && !ref?.misfit;
      let ratio;
      if (!ref || ref.reason) {
        ratio = { drawn: false, reason: ref?.reason ?? 'no reference for this shower', ref: null, value: null, lo: null, hi: null, robust: ratioRobust };
      } else {
        // A deposit a/√E ⊕ b ⊕ c/E reference has a value from 0 GeV, but no window below its floor enters it.
        const belowFloor = ref.floorBy === 'p_lo' && pLo < ref.floorGev - 1e-9;
        const r = belowFloor ? null : ref.valueAt(E);
        if (!(r > 0)) {
          belowNotDrawn += 1;
          const floor = belowFloor ? ref.floorGev : curveMin;
          const group = `${ref.shower}|${ref.form}`;
          const g = below.get(group) ?? { shower: ref.shower, form: ref.form, floorGev: floor, n: 0 };
          g.n += 1;
          below.set(group, g);
          ratio = {
            drawn: false, ref: null, value: null, lo: null, hi: null, robust: ratioRobust,
            reason: belowFloor
              ? `below ${formatNumber(floor)} GeV: no window below ${formatNumber(floor)} GeV enters ${ref.label}`
              : `below ${formatNumber(curveMin)} GeV, where no fit is drawn, so ${ref.label} has no value there`,
          };
        } else {
          ratio = {
            drawn: true, reason: null, ref: r, value: w.value / r,
            lo: whisker ? ci[0] / r : null, hi: whisker ? ci[1] / r : null, robust: ratioRobust,
          };
        }
      }
      return {
        w, E, x: w.x, value: w.value, ci, lo: ci?.[0] ?? null, hi: ci?.[1] ?? null, n: w.n, whisker, weak, subFloor, below4,
        belowNoise: pLo < noiseMin, anchor: anchorBins.has(w.bin), fitted: fittedBins.has(w.bin),
        noiseFitted: noiseBins.has(w.bin), lowAnchor: mf?.noise?.low_anchor === w.bin, robust, opacity, clip, over,
        roles: energyRoles(payload, s, mf, mode, w, gates, curveMin, noiseMin),
        ratio,
      };
    });
    const unreported = (s.windows ?? []).filter((w) => {
      const e = energyOf(w);
      return Number.isFinite(e) && e <= x.max && !((w.n ?? 0) >= gates.report_n && Number.isFinite(w.value));
    });
    const span = spanOf(mf, s);
    const fits = {};
    // One curve per series (Martin's directive of 2026-11-15): a/√E ⊕ b ⊕ c/E where drawable, else a₀/√E, else none.
    fits.noise = noiseFitModel(mf?.noise ?? null, mf, s, ref, x, hi);
    const pinned = mf?.pinned ?? null;
    if (!pinnedDrawable(pinned)) {
      // No a₀/√E to draw: why, from the payload (review-ui F2, review-docs M3), whatever the noise fit does.
      fits.pinned = {
        form: 'pinned', fit: pinned, drawable: false, reason: fitMissingReason(estimator, s, mf, mode, gates),
        span, ratio: null, entry: null, cut: null,
      };
    } else if (fits.noise.drawable) {
      // Never a second fitted line beside the noise curve: a₀/√E stays in the model and the table only.
      fits.pinned = { form: 'pinned', fit: pinned, drawable: false, reason: PINNED_TABLE_ONLY, span, ratio: null, entry: null, cut: null };
    } else {
      // The fallback: the origin-pinned a₀/√E from curveMin, its line alone, the server's noise_reason said.
      // a₀/√E falls with E, so where it starts above the top it comes down into the plot at E = (a₀/y.hi)², and can
      // never leave the top later (review-ui F5): an entry, as the noise curve has, never a cut. Where that E lies
      // beyond the axis end it is above the top over the whole axis: one caret at x.max says so.
      const a0 = pinned.params.a0;
      const startsAbove = Number.isFinite(hi) && hi > 0 && a0 > 0 && a0 / Math.sqrt(curveMin) > hi;
      const enterE = startsAbove ? (a0 / hi) ** 2 : null;
      const above = startsAbove && enterE > x.max;
      const extra = [...(span ?? []), ...(startsAbove && !above ? [enterE] : [])];
      const full = fitCurveE(pinned, energyGrid(curveMin, x.max, extra)).map(([e, yv]) => [e, yv]);
      // The main panel draws from where the line comes down through the top; the ratio takes every row.
      const curve = above ? [] : (startsAbove ? full.filter((r) => r[0] >= enterE - 1e-9) : full);
      let entry = null;
      if (above) entry = { at: x.max, lineAt: null, above: true, term: 'a', atAxis: false };
      else if (startsAbove) entry = { at: enterE, lineAt: enterE, above: false, term: 'a', atAxis: false };
      const parts = splitAtSpan(curve, span);
      const lineRuns = (rows) => clipPolyline(rows, 0, hi);
      const isReference = Boolean(ref && !ref.reason && ref.series === s.key && ref.form === 'pinned');
      let ratio = null;
      if (ref && !ref.reason && !isReference) {
        const rows = full.map(([e, yv]) => {
          const r = ref.valueAt(e);
          return r > 0 ? [e, yv / r] : null;
        }).filter(Boolean);
        ratio = rows.length ? { rows } : null;
      }
      const provisional = Boolean(pinned.provisional ?? mf?.provisional);
      const misfit = isMisfit(pinned);
      fits.pinned = {
        form: 'pinned', fit: pinned, drawable: true, reason: null, fallback: true, noiseReason: noiseReasonClause(mf),
        span, domain: [curve[0]?.[0] ?? curveMin, x.max], curve, full,
        solid: lineRuns(parts.inside), dashed: [...lineRuns(parts.below), ...lineRuns(parts.above)],
        entry, cut: entry ? null : lineCut(curve, hi), provisional, misfit, faded: provisional || misfit,
        converged: pinned.converged !== false, isReference, ratio,
      };
    }
    const drawnForm = ENERGY_FORMS.find((form) => fits[form].drawable) ?? null;
    const drawn = drawnForm ? fits[drawnForm] : null;
    if (drawn?.cut) clipped.fits += 1;
    if (drawn?.entry) clipped.entries += 1;
    // a/√E ⊕ b is table only on this view now (Martin's decisions of 2026-11-13): kept in the model, never drawn.
    fits.quadrature = {
      form: 'quadrature', fit: mf?.quadrature ?? null, drawable: false, span,
      reason: `table only: ${NOISE_FORM_NAME} takes its place on this view`, ratio: null, entry: null, cut: null,
    };
    return {
      key: s.key, label: s.label ?? s.key, short: shortName(s, nShowers), raw: s, colour, isB,
      // No dodge on this view: a window sits at its exact E, on its own curve (the curves cannot be dodged with it).
      offsetPx: 0,
      // `faded`: a provisional fit, or one whose form does not describe its windows (a fit's `faded`).
      lineOpacity: (faded) => legibleOpacity(colour, (isB ? B_STRENGTH : 1) * (faded ? PROVISIONAL_OPACITY : 1)),
      mf, provisional: Boolean(mf?.provisional), span, points, fits, drawnForm, drawn, unreported, reference: ref,
      // The noise fit's windows and low anchor in this mode, or why it has none (the server's sentence).
      noise: {
        points: [...(mf?.noise?.points ?? [])], lowAnchor: mf?.noise?.low_anchor ?? null,
        span: Array.isArray(mf?.noise?.span_gev) ? [...mf.noise.span_gev] : null,
        held: [...(mf?.noise?.params?.held ?? [])], reason: mf?.noise ? null : (mf?.noise_reason ?? null),
      },
    };
  });

  // The ratio axis: k from the windows alone (Martin's decision of 2026-11-11, both views' vertical ranges): the
  // robust ratio marks are the windows of N ≥ fit_n from y_min_gev, whiskers included, each against a reference
  // that is neither provisional nor a misfit. No fit sets k: a fit's ratio that leaves [1/k, k] is clipped below,
  // with its caret, its true values and a count.
  const marks = [];
  for (const s of series) {
    for (const p of s.points) {
      if (!p.ratio.drawn) continue;
      marks.push(p.ratio.robust
        ? { value: p.ratio.value, lo: p.ratio.lo, hi: p.ratio.hi, robust: true, marker: true }
        : { value: p.ratio.value, marker: true });
    }
  }
  const { k, provisional: ratioProvisional, capped: ratioCapped } = ratioRange(marks);
  const ratioClipped = { markers: 0, whiskers: 0, fits: 0, literature: 0 };
  for (const s of series) {
    for (const p of s.points) {
      const r = p.ratio;
      if (!r.drawn) continue;
      r.over = r.value > k || r.value < 1 / k;
      r.clip = Number.isFinite(r.lo) && Number.isFinite(r.hi) ? clampInterval(r.lo, r.hi, 1 / k, k) : null;
      if (r.over) ratioClipped.markers += 1;
      if (r.clip && (r.clip.cutLo || r.clip.cutHi)) ratioClipped.whiskers += 1;
    }
    // The series' one curve divided by the reference, its line alone (no band about it, nor about 1).
    const f = s.drawn;
    if (!f?.ratio) continue;
    const parts = splitAtSpan(f.ratio.rows, f.span);
    const line = (rows) => clipLog(rows, k);
    f.ratio.solid = line(parts.inside);
    f.ratio.dashed = [...line(parts.below), ...line(parts.above)];
    // A curve's ratio can start outside [1/k, k] at its first row (a noise fit's as E → 0, the a₀/√E fallback's at
    // curveMin; review-ui F5): it enters there (`ratioEntry`, `whole` where it never comes in), and is cut beyond.
    const { entry, rest } = ratioEntry(f.ratio.rows, k);
    f.ratio.entry = entry;
    f.ratio.cut = ratioLineCut(rest, k);
    if (f.ratio.cut || f.ratio.entry) ratioClipped.fits += 1;
  }

  // The literature curves drawn (Martin, 2026-11-11), each in its identity colour on this card; none ever sets a
  // range. The one the ratio does not divide by is drawn on the ratio panel too, divided by the reference (one
  // line, the same for every shower).
  const literature = [];
  const literatureGrid = energyGrid(E_GRID_STEP_GEV, x.max);
  for (const key of drawnKeys) {
    const lit = referenceOf(key);
    if (!lit) continue;
    const curve = literatureGrid.map((e) => [e, referenceValue(lit, e)]).filter((c) => Number.isFinite(c[1]));
    let cut = null;
    for (let i = 0; i + 1 < curve.length && !cut; i += 1) {
      const [e0, v0] = curve[i];
      const [e1, v1] = curve[i + 1];
      if ((v0 > hi) !== (v1 > hi)) cut = { at: e0 + ((hi - v0) / (v1 - v0)) * (e1 - e0), peak: curve[0] };
    }
    if (!cut && curve.length && curve[0][1] > hi) cut = { at: curve[0][0], peak: curve[0] };
    if (cut) clipped.literature += 1;
    let ratio = null;
    if (entry && key !== referenceKey) {
      const rows = curve.map(([e, v]) => [e, v / referenceValue(entry, e)]).filter(([, r]) => Number.isFinite(r) && r > 0);
      const rcut = ratioCut(rows, k);
      if (rcut) ratioClipped.literature += 1;
      ratio = { rows, runs: clipLog(rows, k), cut: rcut };
    }
    literature.push({
      key, entry: lit, isReference: key === referenceKey, label: lit.particle, legend: literatureLegendName(lit),
      colour: literatureColour(key, THEME.qualitativePalette), curve, runs: clipPolyline(curve, 0, hi), cut, ratio,
    });
  }
  clipped.ratio = ratioClipped.markers + ratioClipped.whiskers + ratioClipped.fits + ratioClipped.literature;

  // Direct labels at the curves' right ends, in a column beside the plot: with two showers on show, the shower
  // letter of every drawn curve whose value at x.max lies on its panel (B's lines are at 70% strength or more, so
  // the letter names the shower where the strength cannot); and each literature curve's particle, on the main panel
  // and, beside a literature reference, on the ratio panel.
  // Each label is ink text led by a key stroke in its curve's colour, dash, width and strength (`endLabelSeries`).
  // A curve that leaves the plot before x.max has its caret and no label.
  const twoOnShow = nShowers > 1 && new Set(series.map((s) => s.raw.shower).filter(Boolean)).size > 1;
  const endLabels = { main: [], ratio: [] };
  const atEnd = (rows) => {
    const last = rows?.[rows.length - 1];
    return last && Math.abs(last[0] - x.max) < 1e-9 && Number.isFinite(last[1]) ? last[1] : null;
  };
  for (const s of twoOnShow ? series : []) {
    const text = String(s.raw.shower).toUpperCase();
    const f = s.drawn;
    if (!f) continue;
    // The key stroke draws the curve as it ends at x.max: dashed unless its fitted span reaches the axis end; its
    // width the form's (1.6 px a/√E ⊕ b ⊕ c/E, 1 px the a₀/√E fallback).
    const solidAtEnd = Array.isArray(f.span) && f.span[1] >= x.max - 1e-9;
    const label = {
      key: s.key, form: f.form, name: s.label, text, colour: s.colour, literature: false,
      stroke: { colour: s.colour, width: f.form === 'noise' ? 1.6 : 1, dash: solidAtEnd ? null : DASH_EXTRAPOLATED, opacity: s.lineOpacity(f.faded) },
    };
    const v = atEnd(f.curve);
    if (v !== null && v >= 0 && v <= hi) endLabels.main.push({ ...label, value: v });
    const r = f.ratio ? atEnd(f.ratio.rows) : null;
    if (r !== null && r >= (1 / k) * (1 - 1e-9) && r <= k * (1 + 1e-9)) endLabels.ratio.push({ ...label, value: r });
  }
  for (const lit of literature) {
    const label = {
      key: `literature|${lit.key}`, form: 'literature', name: lit.legend, text: lit.label, colour: lit.colour, literature: true,
    };
    const stroke = { colour: lit.colour, width: LITERATURE_WIDTH, dash: DASH_LITERATURE, opacity: 1 };
    const v = referenceValue(lit.entry, x.max);
    if (Number.isFinite(v) && v >= 0 && v <= hi) endLabels.main.push({ ...label, value: v, stroke });
    const r = lit.ratio ? atEnd(lit.ratio.rows) : null;
    if (r !== null && r >= (1 / k) * (1 - 1e-9) && r <= k * (1 + 1e-9)) endLabels.ratio.push({ ...label, value: r, stroke });
  }

  // The canvas note: the windows above the top by window, and the extrapolation rule.
  const groups = new Map();
  for (const s of series) {
    for (const p of s.points) {
      if (!(p.value > hi)) continue;
      const label = p.w.label ?? `bin ${p.w.bin}`;
      const g = groups.get(label) ?? { label, E: p.E, entries: [] };
      g.E = Math.min(g.E, p.E);
      g.entries.push({ key: s.key, short: s.short, value: p.value, n: p.n });
      groups.set(label, g);
    }
  }
  const offScale = [...groups.values()].sort((a, b) => a.E - b.E);
  const bySeries = series.filter((s) => s.drawn).map((s) => ({ key: s.key, label: s.label, form: s.drawnForm, span: s.drawn.span }));
  const same = (a, b) => (a === null && b === null) || (a && b && a[0] === b[0] && a[1] === b[1]);
  const shared = bySeries.length > 0 && bySeries.every((b) => same(b.span, bySeries[0].span));
  const noteText = {
    offScale: offScaleText(offScale),
    // Said only while a drawn curve has a dashed run on either panel (Martin's decision of 2026-11-17: at E max
    // = 20 GeV a curve fitted to 4–20 GeV is solid to the end), its span quoted where every drawn curve shares one.
    extrapolation: extrapolationText(series),
    // The literature disclosure (brief section 2.7, Martin's override of 2026-11-12): under the median, whenever a
    // literature curve is on, the payload's own sentence, verbatim, as one line of the note band.
    warning: estimator.warning && literature.length ? estimator.warning : '',
  };

  let refLabel;
  if (none) refLabel = 'no reference';
  else if (entry) refLabel = referenceLabel(entry);
  else refLabel = Object.keys(byShower).length > 1 ? 'each shower\'s deposit fit' : (Object.values(byShower)[0]?.label ?? 'the deposit fit');
  return {
    view: 'energy', mode, gates, estimator, nShowers, payload, x, y, deposit,
    curveMinGev: curveMin, noiseMinGev: noiseMin, yMinGev, dataMaxGev: ea.data_max_gev ?? null, rule: ea.rule ?? null, notes: [...(ea.notes ?? [])],
    reference: {
      key: referenceKey, choice, label: refLabel, literature: entry, interval: null,
      flag: entry ? 'no interval reported' : null, byShower,
    },
    series, literature,
    // With no reference on show (`none`) no window has a ratio mark and no curve a ratio, so the axis is no range.
    ratio: {
      k, provisional: none ? false : ratioProvisional, capped: ratioCapped, reference: referenceKey, clipped: ratioClipped, belowNotDrawn,
      below: [...below.values()],
      noReference: none ? [] : Object.values(byShower).filter((r) => r.reason).map((r) => ({ shower: r.shower, reason: r.reason })),
      none,
    },
    twoOnShow, endLabels,
    clipped, offScale,
    spans: { shared, span: shared ? bySeries[0].span : null, bySeries },
    noteText,
    nPoints: series.reduce((a, s) => a + s.points.length, 0),
    nLines: series.filter((s) => s.drawn).length,
  };
}

/** One window's group on the canvas note: "1–2 GeV — A network 79.1%, B network 77.6%". */
function offScaleGroupText(g) {
  return `${g.label} — ${g.entries.map((e) => `${e.short} ${pct(e.value)}`).join(', ')}`;
}

/** The canvas note's off-scale list of `groups` (`offScale`), or '' with none. */
function offScaleText(groups) {
  return groups.length ? `↑ off scale: ${groups.map(offScaleGroupText).join('; ')}` : '';
}

/**
 * The canvas note's extrapolation rule for `series` (the model's, or those an
 * export keeps), or '' where no drawn curve of theirs has a dashed run on
 * either panel: the rule describes drawn marks only (Martin's decision of
 * 2026-11-17). The span is quoted where every drawn curve of theirs shares one.
 */
function extrapolationText(series) {
  const drawn = series.filter((s) => s.drawn);
  const dashed = drawn.some((s) => (s.drawn.dashed ?? []).length || (s.drawn.ratio?.dashed ?? []).length);
  if (!dashed) return '';
  const same = (a, b) => (a === null && b === null) || (a && b && a[0] === b[0] && a[1] === b[1]);
  const shared = drawn.every((s) => same(s.drawn.span, drawn[0].drawn.span));
  return shared && drawn[0].drawn.span
    ? `dashed: fit extrapolated beyond its fitted windows (${spanText(drawn[0].drawn.span)})`
    : 'dashed: each fit extrapolated beyond its own fitted windows (Details)';
}

/* ------------------------------------------------------- E-view tips -- */

/** "plotted at E = 1/⟨1/√p⟩² = 5.49 GeV …; ⟨p⟩ = 5.5 GeV": where a window sits on this axis. */
function plottedAtLine(p) {
  return `plotted at E = 1/⟨1/√p⟩² = ${formatNumber(p.E, 2)} GeV (the 1/√E view's x mapped by E = 1/x²); `
    + `⟨p⟩ = ${formatNumber(p.w.p_mean, 2)} GeV`;
}

/** The tooltip of one window on the main panel: the 1/√E view's, with where it is plotted. */
export function energyPointTip(model, s, p) {
  const lines = pointTipLines(model, s, p);
  lines.splice(3, 0, escapeHtml(plottedAtLine(p)));
  return lines.join('<br/>');
}

/** The ratio axis's range as its ticks write it: "1/2 to 2". */
function ratioRangeText(model) {
  return `${ratioTickLabel(1 / model.ratio.k)} to ${ratioTickLabel(model.ratio.k)}${model.ratio.provisional ? ', provisional' : ''}`;
}

/** The tooltip of one window on the ratio panel: its ratio, named against its reference and said to be conditional. */
export function ratioPointTip(model, s, p) {
  const r = p.ratio;
  const ref = s.reference;
  const lines = pointTipLines(model, s, p);
  if (p.over || p.clip?.cutLo || p.clip?.cutHi) lines.pop();
  lines.splice(3, 0, escapeHtml(plottedAtLine(p)));
  let text = `Ratio to ${ref.label} = ${sig(r.value)}`;
  if (Number.isFinite(r.lo) && Number.isFinite(r.hi)) text += `, interval [${sig(r.lo)}, ${sig(r.hi)}]`;
  lines.splice(5, 0, `<b>${escapeHtml(text)}</b>`);
  const est = model.estimator ?? estimatorOf(null);
  lines.push(mutedLine(`The reference reads ${pct(r.ref)} at this E. The interval is conditional on the reference: it is this window's 95% ${intervalName(est, p.w)} interval divided by it, `
    + (ref.literature ? 'and the literature curve has no interval reported.' : 'and the reference fit\'s own uncertainty is not included.')));
  lines.push(...literatureWarningLines(model, Boolean(ref.literature)));
  if (ref.misfit) lines.push(mutedLine(referenceMisfitText(ref, model.gates)));
  if (r.over || r.clip?.cutLo || r.clip?.cutHi) {
    lines.push(mutedLine(`clipped at the ratio axis (${ratioRangeText(model)}); the values above are the true ones`));
  }
  return lines.join('<br/>');
}

/** A drawn fit's equation, in ⊕ notation, with its parameters (a/√E ⊕ b ⊕ c/E: the form alone; its terms follow on their own line). */
function energyEquation(f, sym = 'σ/E') {
  const p = f.fit.params ?? {};
  if (f.form === 'noise') return `${sym} = ${NOISE_FORM_NAME}`;
  return `Origin-pinned fit ${sym} = (${sig(p.a0)} ± ${sig(p.se_a0)})%/√E ⊕ 0 (b ≡ 0, through the origin)`;
}

/**
 * A drawn fit's χ²/ν line on the E view, as every curve tooltip writes it:
 * "χ²/ν = …, p = …; S = …" where ν ≥ 1 (S = 1 where the windows' own errors
 * stand), else the exact-pass sentence (review-ui N1, F4).
 */
function energyChi2Line(fit) {
  return fit.ndf > 0 && Number.isFinite(fit.p_value)
    ? `${chi2Text(fit)}; S = ${sig(Number.isFinite(fit.scale_factor) ? fit.scale_factor : 1)}`
    : `${chi2Text(fit)}: the curve passes through its ${plural(fit.n_points, 'point')} exactly`;
}

/** A drawn fit's name in a sentence: "a/√E ⊕ b ⊕ c/E fit", "origin-pinned fit a₀/√E ⊕ 0". */
function energyFitName(form) {
  if (form === 'noise') return `${NOISE_FORM_NAME} fit`;
  return 'origin-pinned fit a₀/√E ⊕ 0';
}

/**
 * The terms of a/√E ⊕ b ⊕ c/E, each with its SE and unit, the held phrase, or
 * its square with the square's SE where the term's SE exceeds it
 * (`termAsSquare`, brief-fix m4): "a = 30.2 ± 4.1 %·√GeV; b = 0, held there by
 * the constraint b² ≥ 0; the noise term c/E: c² = 0.04 ± 8.1 %²·GeV²".
 */
function noiseTermsText(p) {
  const held = new Set(p.held ?? []);
  const units = { a: A_UNIT, b: '%', c: C_UNIT };
  return ['a', 'b', 'c'].map((t) => {
    const lead = t === 'c' ? 'the noise term c/E: ' : '';
    if (held.has(t)) return `${lead}${noiseHeldPhrase([t])}`;
    if (termAsSquare(p, t)) return `${lead}${squareText(p, t)}`;
    return `${lead}${t} = ${sig(p[t])} ± ${sig(p[`se_${t}`])} ${units[t]}`;
  }).join('; ');
}

/** The windows of a noise fit for a tooltip: "4 windows, 3–16 GeV: 3–4 GeV (the low anchor), 7–8 GeV, …". */
function noiseWindowsLine(model, s, f) {
  const n = f.fit.n_points ?? f.points.length;
  return `Windows fitted (${formatInt(n)}, ${spanText(f.span)}): ${noiseWindowsText(model.payload, s.raw, s.mf, model.mode)}`;
}

/**
 * The literature disclosure as tooltip lines (brief section 2.7): the
 * payload's sentence under the median estimator, where `on` (a literature
 * curve is drawn, or is the ratio's reference); none otherwise.
 */
function literatureWarningLines(model, on = true) {
  const warning = model.estimator?.warning;
  return on && warning ? [mutedLine(warning)] : [];
}

/** The extrapolation sentence of a dashed part. */
function extrapolatedLine(f) {
  return `Extrapolated: beyond the windows this fit used (${spanText(f.span)}), where the fitted form is assumed to hold and no window supports it.`;
}

/**
 * Why a 1/√E-view fit's band is drawn as its edges: it spans half its axis or
 * more over its fitted windows, with the quantile that made it so (Student's t
 * at a small ν once S scales the covariance). The E view draws no band.
 */
function outlinedLine(fit) {
  const q = Number.isFinite(fit?.band_quantile) ? fit.band_quantile : DEFAULT_QUANTILE;
  const scaled = Number.isFinite(fit?.scale_factor) && fit.scale_factor > 1;
  const why = [
    scaled ? `S = ${sig(fit.scale_factor)}` : null,
    Number.isFinite(fit?.ndf) ? `ν = ${formatInt(fit.ndf)}` : null,
    `q = ${sigFigs(q, 4)}`,
  ].filter(Boolean).join(', ');
  return `Its 95% band spans half its axis or more over its fitted windows (${why}), so it is drawn as its edges, not as a wash.`;
}

/** What a literature reference adds to every ratio mark's tooltip: none of it carries an interval. */
const LITERATURE_NO_INTERVAL = 'The literature curve has no interval reported; none is derived.';

/** Shower B's strength as drawn (`faded` for a faded fit): 70% asked, raised to 3:1 where the card needs it; the end labels name the shower. */
function showerBLine(model, s, faded) {
  const strength = Math.round(100 * s.lineOpacity(faded));
  return `Shower B's lines are drawn at 70% strength, raised where the card needs it to keep 3:1 (this one at ${strength}%)`
    + `${model.twoOnShow ? ', so the end labels name the shower' : ''}: on this view the dash means extrapolation, not the shower.`;
}

/**
 * The tooltip of one drawn fit on the main panel; `part` 'solid' (over its
 * windows) or 'dashed'. a/√E ⊕ b ⊕ c/E has its own (`noiseFitTip`); a₀/√E is
 * drawn only as the fallback of a series with no a/√E ⊕ b ⊕ c/E fit, and says
 * so with the server's reason.
 */
export function energyFitTip(model, s, f, part = 'solid') {
  if (f.form === 'noise') return noiseFitTip(model, s, f, part);
  const { fit } = f;
  const p = fit.params ?? {};
  const scaled = Number.isFinite(fit.scale_factor) && fit.scale_factor > 1;
  const sym = model.estimator?.symbol ?? 'σ/E';
  const lines = [`<b>${escapeHtml(s.label)}</b>`, escapeHtml(energyEquation(f, sym))];
  lines.push(escapeHtml(`This series has no ${NOISE_FORM_NAME} fit (${f.noiseReason ?? noiseReasonClause(s.mf)}), `
    + `so its origin-pinned a₀/√E is drawn instead, from ${formatNumber(model.curveMinGev)} GeV.`));
  if (scaled) {
    lines.push(mutedLine(`error scaled by S = ${sig(fit.scale_factor)} (PDG, χ²/ν > 1); unscaled SE(a₀) = ${sig(p.se_a0_stat)}`));
  }
  lines.push(escapeHtml(energyChi2Line(fit)));
  lines.push(`Windows fitted (${formatInt(fit.n_points)}): ${escapeHtml(windowsText(model.payload, s.raw, s.mf))}`);
  lines.push(mutedLine(`Solid over the span of the windows it was fitted to (${spanText(f.span)}); dashed beyond, from ${formatNumber(model.curveMinGev)} to ${formatNumber(model.x.max)} GeV, where it extrapolates its form.`));
  if (part === 'dashed') lines.push(escapeHtml(extrapolatedLine(f)));
  if (f.provisional) {
    lines.push(mutedLine(`Provisional: fewer than two windows from ${formatNumber(model.gates.e_min_gev)} GeV reach N = ${formatInt(model.gates.fit_n)}, so the fit runs through windows of N ≥ ${formatInt(model.gates.whisker_n)}; drawn faded.`));
  }
  if (f.misfit) lines.push(mutedLine(misfitText(fit, model.gates)));
  if (!f.converged) {
    lines.push(mutedLine(`Not converged: the iterated weights did not settle within ${formatInt(fit.iterations)} refits, so this is the last refit's curve, not a fixed point.`));
  }
  if (s.isB) lines.push(mutedLine(showerBLine(model, s, f.faded)));
  if (f.entry) lines.push(mutedLine('It comes down into the plot from the top: the caret there says where.'));
  if (f.cut) lines.push(mutedLine('It leaves the top of the plot: the caret there gives its true value.'));
  lines.push(mutedLine(ENERGY_NO_BAND_TEXT));
  return lines.join('<br/>');
}

/**
 * The tooltip of an a/√E ⊕ b ⊕ c/E curve on the main panel (brief section 4.3
 * of res-noise): the equation; each term with its SE and unit, the held
 * phrase, or a term's square where its SE exceeds it (brief-fix m4); χ²/ν and
 * S; the windows fitted, the low anchor named; the correlation of the
 * squares; and that no band is drawn on this view (Martin's directive of
 * 2026-11-15). The floor sentence and the naming caveat are the drawer's
 * alone (brief-fix m6).
 */
function noiseFitTip(model, s, f, part = 'solid') {
  const { fit } = f;
  const p = fit.params ?? {};
  const sym = model.estimator?.symbol ?? 'σ/E';
  const scaled = Number.isFinite(fit.scale_factor) && fit.scale_factor > 1;
  const lines = [`<b>${escapeHtml(s.label)}</b>`, `<b>${escapeHtml(energyEquation(f, sym))}</b>`, escapeHtml(noiseTermsText(p))];
  lines.push(mutedLine(noiseConstraintText(sym)));
  if (scaled) {
    // A term printed as its square (brief-fix m4) gives its square's unscaled SE.
    const unscaled = ['a', 'b', 'c'].filter((t) => Number.isFinite(p[`se_${t}`]))
      .map((t) => (termAsSquare(p, t)
        ? `SE(${t}²) = ${sig(p[`se_${t}2`] / fit.scale_factor)}`
        : `SE(${t}) = ${sig(p[`se_${t}`] / fit.scale_factor)}`)).join(', ');
    lines.push(mutedLine(`errors scaled by S = ${sig(fit.scale_factor)} (PDG, χ²/ν > 1)${unscaled ? `; unscaled ${unscaled}` : ''}`));
  }
  lines.push(escapeHtml(energyChi2Line(fit)));
  lines.push(escapeHtml(noiseWindowsLine(model, s, f)));
  if (model.mode === 'anchors' && f.lowAnchor !== null) {
    const nAnchors = f.points.filter((b) => b !== f.lowAnchor).length;
    lines.push(mutedLine(noiseLowAnchorText(binLabel(model.payload, s.raw, f.lowAnchor), model.noiseMinGev, nAnchors)));
  }
  lines.push(mutedLine(`Solid over the span of the windows it was fitted to (${spanText(f.span)}); dashed beyond, from 0 to ${formatNumber(model.x.max)} GeV, where it extrapolates its form.`));
  if (part === 'dashed') lines.push(escapeHtml(extrapolatedLine(f)));
  const rho = noiseCorrelationText(p.rho);
  if (rho) lines.push(mutedLine(rho));
  if (f.provisional) {
    lines.push(mutedLine(`Provisional: fewer than two windows from ${formatNumber(model.gates.e_min_gev)} GeV reach N = ${formatInt(model.gates.fit_n)}, so the fit runs through windows of N ≥ ${formatInt(model.gates.whisker_n)}; drawn faded.`));
  }
  if (f.misfit) lines.push(mutedLine(misfitText(fit, model.gates)));
  if (!f.converged) {
    lines.push(mutedLine(`Not converged: the iterated weights did not settle within ${formatInt(fit.iterations)} refits, so this is the last refit's curve, not a fixed point.`));
  }
  if (s.isB) lines.push(mutedLine(showerBLine(model, s, f.faded)));
  if (f.entry) lines.push(mutedLine('It comes down into the plot from the top: the caret there says where.'));
  if (f.cut) lines.push(mutedLine('It leaves the top of the plot: the caret there gives its true value.'));
  lines.push(mutedLine(ENERGY_NO_BAND_TEXT));
  return lines.join('<br/>');
}

/**
 * The tooltip of the caret where an a/√E ⊕ b ⊕ c/E curve comes down into the
 * main panel: brief section 8's sentence alone (the lead's decision of
 * 2026-11-13; the drawer gives the same energy, from the same root), or, for a
 * line above the whole axis, what is so. The line alone: no band is drawn.
 */
function noiseEntryTip(model, s, f) {
  const e = f.entry;
  const at = (v) => `E = ${sig(v)} GeV`;
  const lines = [`<b>${escapeHtml(s.label)}</b>`];
  if (e.above) {
    lines.push(escapeHtml(`The ${f.provisional ? 'provisional ' : ''}${NOISE_FORM_NAME} fit lies above the top of the ${model.y.provisional ? 'provisional ' : ''}axis (0 to ${pct(model.y.hi)}) over the whole axis: at ${at(model.x.max)} it reads ${pct(evalFitAt(f.fit, model.x.max)?.y)}.`));
  } else if (e.term) {
    lines.push(escapeHtml(noiseEntryText(e.lineAt, e.term)));
  } else {
    lines.push(escapeHtml(`It comes down into the plot at ${at(e.lineAt)}.`));
  }
  if (e.atAxis) lines.push(mutedLine(NOISE_AXIS_LINE_TEXT));
  return lines.join('<br/>');
}

/**
 * The tooltip of the caret where the a₀/√E fallback comes down into the main
 * panel (review-ui F5, the lead's words verbatim): a₀/√E falls with E, so a
 * curve that starts above the top at curveMin enters at E = (a₀/y.hi)², or,
 * where that lies beyond the axis end, lies above the top over the whole axis.
 */
function pinnedEntryTip(model, s, f) {
  const e = f.entry;
  const top = `the top of the axis (0 to ${pct(model.y.hi)})`;
  const from = sig(model.curveMinGev);
  const text = e.above
    ? `The origin-pinned a₀/√E lies above ${top} at every energy from ${from} GeV: at ${sig(model.x.max)} GeV it reads ${pct(evalFitAt(f.fit, model.x.max)?.y)}.`
    : `The origin-pinned a₀/√E comes down into the plot at E = ${sig(e.lineAt)} GeV: it falls as 1/√E, so from ${from} GeV up to that energy it lies above ${top}.`;
  return [`<b>${escapeHtml(s.label)}</b>`, escapeHtml(text)].join('<br/>');
}

/**
 * The tooltip of the caret where a fit's ratio comes into the ratio panel from
 * outside as E rises from its first row, or stays outside it (`whole`): the
 * a/√E ⊕ b ⊕ c/E fit's from 0 GeV, the a₀/√E fallback's from curveMin.
 */
function ratioEntryTip(model, s, f) {
  const e = f.ratio.entry;
  const [pe, pr] = e.peak;
  const where = e.whole
    ? `stays ${e.dir === 'up' ? 'above' : 'below'} the ratio axis (${ratioRangeText(model)}) over the whole axis`
    : `comes into the ratio axis (${ratioRangeText(model)}) from ${e.dir === 'up' ? 'above' : 'below'} at E = ${sig(e.at)} GeV`;
  const lines = [
    `<b>${escapeHtml(s.label)}</b>`,
    escapeHtml(`The ratio of the ${energyFitName(f.form)} to ${s.reference.label} ${where}, scanning up in E from ${sig(pe)} GeV, where it reads ${sig(pr)}.`),
    mutedLine(`Clipped, not rescaled: the ratio range follows the windows of N ≥ ${formatInt(model.gates.fit_n)} from ${formatNumber(model.yMinGev)} GeV alone; `
      + 'a fit summarises its windows, so no fit ratio sets it.'),
  ];
  if (s.reference.literature) lines.push(mutedLine(LITERATURE_NO_INTERVAL));
  lines.push(...literatureWarningLines(model, Boolean(s.reference.literature)));
  return lines.join('<br/>');
}

/** The tooltip of the caret where a drawn fit's curve leaves the top of the main panel: its own values, no band. */
export function energyFitCutTip(model, s, f) {
  const { cut } = f;
  const name = energyFitName(f.form);
  const [pe, py] = cut.peak;
  const at = (e) => `E = ${sig(e)} GeV`;
  return [
    `<b>${escapeHtml(s.label)}</b>`,
    escapeHtml(`The ${f.provisional ? 'provisional ' : ''}${name} leaves the top of the ${model.y.provisional ? 'provisional ' : ''}axis (0 to ${pct(model.y.hi)}) `
      + `first at ${at(cut.at)}, scanning up in E.`),
    escapeHtml(`True values where it reaches highest, at ${at(pe)}: the curve ${pct(py)}.`),
    mutedLine(rangeRuleText(model, `${formatNumber(model.yMinGev)} GeV`)),
    ...(f.misfit ? [mutedLine(misfitText(f.fit, model.gates))] : []),
  ].join('<br/>');
}

/**
 * The tooltip of one drawn fit on the ratio panel: its line divided by the
 * reference, with no band (review-ui F4): below the title its terms with their
 * SEs (a/√E ⊕ b ⊕ c/E's terms, or a₀/√E's equation with ± SE(a₀)), its χ²/ν
 * line as the main tooltip writes it, the explanation, and that no band is
 * drawn on this view.
 */
export function ratioFitTip(model, s, f, part = 'solid') {
  const ref = s.reference;
  const noise = f.form === 'noise';
  const lines = [
    `<b>${escapeHtml(s.label)}</b>`,
    escapeHtml(`${noise ? `${NOISE_FORM_NAME} fit` : 'Origin-pinned fit a₀/√E ⊕ 0'} ÷ ${ref.label}`),
    escapeHtml(noise ? noiseTermsText(f.fit.params ?? {}) : energyEquation(f, model.estimator?.symbol)),
    escapeHtml(energyChi2Line(f.fit)),
    mutedLine('The fitted curve divided by the reference at each E, the reference held exact.'),
    mutedLine(ENERGY_NO_BAND_TEXT),
  ];
  if (part === 'dashed') lines.push(escapeHtml(extrapolatedLine(f)));
  if (f.misfit) lines.push(mutedLine(misfitText(f.fit, model.gates)));
  if (f.ratio?.entry?.whole) {
    lines.push(mutedLine('It stays beyond the ratio axis over the whole axis: the caret at the axis end says so.'));
  } else if (f.ratio?.entry) {
    lines.push(mutedLine(`It comes into the ratio axis from beyond it as E rises from ${noise ? '0' : `${formatNumber(model.curveMinGev)} GeV`}: the caret there says where.`));
  }
  if (f.ratio?.cut) lines.push(mutedLine('It leaves the ratio axis: the caret there gives its true value.'));
  if (ref.literature) lines.push(mutedLine(LITERATURE_NO_INTERVAL));
  lines.push(...literatureWarningLines(model, Boolean(ref.literature)));
  return lines.join('<br/>');
}

/** The tooltip of the caret where a fit's ratio leaves the ratio axis: its own values, no band. */
function ratioFitCutTip(model, s, f) {
  const cut = f.ratio.cut;
  const [pe, pr] = cut.peak;
  const name = energyFitName(f.form);
  const lines = [
    `<b>${escapeHtml(s.label)}</b>`,
    escapeHtml(`The ratio of the ${name} to ${s.reference.label} leaves the ratio axis (${ratioRangeText(model)}) first at E = ${sig(cut.at)} GeV, scanning up in E.`),
    escapeHtml(`True values where it deviates most, at E = ${sig(pe)} GeV: the ratio ${sig(pr)}.`),
    mutedLine(`Clipped, not rescaled: the ratio range follows the windows of N ≥ ${formatInt(model.gates.fit_n)} from ${formatNumber(model.yMinGev)} GeV alone; `
      + 'a fit summarises its windows, so no fit ratio sets it.'),
  ];
  if (s.reference.literature) lines.push(mutedLine(LITERATURE_NO_INTERVAL));
  lines.push(...literatureWarningLines(model, Boolean(s.reference.literature)));
  return lines.join('<br/>');
}

/**
 * The tooltip of the ratio panel's 1.0 rule. Under the deposit reference a shower whose deposit has no fit in this
 * mode is named with its reason; when no shower has one, the rule is the axis's centre with nothing to divide by.
 */
function unityTip(model) {
  const ref = model.reference;
  const missing = ref.literature ? [] : Object.values(ref.byShower ?? {}).filter((r) => r.reason);
  const none = missing.length > 0 && missing.length === Object.keys(ref.byShower ?? {}).length;
  const lines = [
    `<b>ratio = 1</b>`,
    escapeHtml(none
      ? 'The ratio axis\'s centre, with no reference to divide by, so the panel holds no ratio marks.'
      : `${model.estimator?.symbol ?? 'σ/E'} equal to the reference: ${ref.literature ? `${referenceEquation(ref.literature)} (${REFERENCE_UNITS})` : ref.label}.`),
    mutedLine(`A log axis symmetric about 1 (${ratioRangeText(model)}), so ×k and ÷k lie at equal distances from this rule.`),
  ];
  for (const r of missing) {
    lines.push(mutedLine(`${model.nShowers > 1 ? `Shower ${String(r.shower).toUpperCase()}` : 'The deposit'} has no ratio marks: ${r.reason}.`));
  }
  for (const r of Object.values(ref.byShower ?? {})) if (r.misfit) lines.push(mutedLine(referenceMisfitText(r, model.gates)));
  const why = referenceChoiceText(model);
  if (why) lines.push(mutedLine(why));
  if (ref.literature) lines.push(mutedLine(LITERATURE_NO_INTERVAL));
  lines.push(...literatureWarningLines(model, Boolean(ref.literature)));
  return lines.join('<br/>');
}

/**
 * What a ratio mark's tooltip and the 1.0 rule say of a deposit reference whose form
 * does not describe its windows (its fit's `misfit`): its S and χ²/ν, and that no ratio against it sets k.
 */
function referenceMisfitText(ref, gates) {
  const fit = ref.fit ?? {};
  return `The reference, ${ref.label}, does not describe its windows: S = ${sig(fit.scale_factor)} > ${formatNumber(gates.misfit_scale ?? DEFAULT_GATES.misfit_scale)} `
    + `(χ²/ν = ${sig(fit.chi2 / fit.ndf)}), so a ratio against it is not robust and never sets the ratio range.`;
}

/**
 * Why the ratio divides by the curve it does when both are drawn (`ratioReferenceChoice`), or null when one or
 * neither is, and with no reference on show (rule 'none'): the median factor between the windows and each curve,
 * over which windows.
 */
export function referenceChoiceText(model) {
  const c = model.reference.choice;
  if (c?.rule !== 'farther') return null;
  const name = (key) => referenceOf(key)?.particle ?? key;
  const ref = c.scores.find((sc) => sc.key === c.key);
  const other = c.scores.find((sc) => sc.key !== c.key);
  const head = `With both curves drawn the ratio divides by ${name(c.key)}, the curve the windows lie farther from `
    + 'and so the one that needs the most scaling';
  if (!c.basis || !(ref?.factor > 0) || !(other?.factor > 0)) {
    return `${head}: no window on show reports ${model.estimator?.quantity ?? 'σ/E'}, so it is ${name(c.key)}, the catalogue's first.`;
  }
  // With the deposit hidden the choice is judged on the model series' windows alone, the marks the ratio divides
  // (review R1-2): said, since showing the deposit can turn the choice to the other curve.
  const whose = model.deposit?.hidden ? ' of the model series (the deposit is hidden)' : '';
  const over = c.basis === 'robust'
    ? `the ${plural(c.n, 'window')}${whose} of N ≥ ${formatInt(model.gates.fit_n)} from ${formatNumber(model.yMinGev)} GeV`
    : `the ${plural(c.n, 'window')}${whose} on show, none of N ≥ ${formatInt(model.gates.fit_n)} from ${formatNumber(model.yMinGev)} GeV`;
  if (ref.factor <= other.factor * (1 + 1e-12)) {
    return `${head}: ${over} sit a median ×${sig(ref.factor)} from both, so it is ${name(c.key)}, the catalogue's first.`;
  }
  return `${head}: ${over} sit a median ×${sig(ref.factor)} from ${name(c.key)} and ×${sig(other.factor)} from ${name(other.key)} `
    + `(the median of |ln(${model.estimator?.symbol ?? 'σ/E'} ÷ curve)|, as a factor).`;
}

/**
 * The tooltip of a literature curve on the main panel: what it is, and what the
 * ratio panel does with it (divides by it, or draws it divided by the reference).
 */
export function literatureTip(model, lit) {
  const ref = model.reference.literature;
  const beside = model.literature.filter((l) => l.key !== lit.key).map((l) => l.entry.particle);
  const role = lit.isReference
    ? `The ratio panel divides by this curve${beside.length
      ? `; the ${beside.join(' and ')} curve drawn beside it is drawn there too, divided by it` : ''}.`
    : `Drawn beside the ratio's reference, the ${ref?.particle ?? 'other'} curve: the ratio panel draws it divided by that curve.`;
  const why = lit.isReference ? referenceChoiceText(model) : null;
  return [
    `<b>${escapeHtml(`${lit.entry.particle} literature curve`)}</b>`,
    escapeHtml(referenceEquation(lit.entry)),
    mutedLine(LITERATURE_PROVENANCE),
    mutedLine(role),
    ...(why ? [mutedLine(why)] : []),
    mutedLine('A reference, not a measurement: it never sets the range.'),
    ...literatureWarningLines(model),
  ].join('<br/>');
}

/** The tooltip of a literature curve on the ratio panel: it divided by the literature reference, at the axis's two ends. */
function literatureRatioTip(model, lit) {
  const ref = model.reference.literature;
  const rows = lit.ratio.rows;
  const [e0, r0] = rows[0];
  const [e1, r1] = rows[rows.length - 1];
  return [
    `<b>${escapeHtml(`${lit.entry.particle} literature curve ÷ ${ref.particle}`)}</b>`,
    escapeHtml(`${referenceEquation(lit.entry)} divided by ${referenceEquation(ref)} (in both, ${REFERENCE_UNITS}): ${sig(r0)} at E = ${sig(e0)} GeV, ${sig(r1)} at E = ${sig(e1)} GeV.`),
    mutedLine('Both curves are transcribed point estimates with no interval reported, so neither has one here; it never sets the ratio range.'),
    ...(lit.ratio.cut ? [mutedLine('It leaves the ratio axis: the caret there gives its true values.')] : []),
    ...literatureWarningLines(model),
  ].join('<br/>');
}

/** The tooltip of the caret where a literature curve's ratio leaves the ratio panel. */
function literatureRatioCutTip(model, lit) {
  const cut = lit.ratio.cut;
  const [pe, pr] = cut.peak;
  return [
    `<b>${escapeHtml(`${lit.entry.particle} literature curve ÷ ${model.reference.literature.particle}`)}</b>`,
    escapeHtml(`It leaves the ratio axis (${ratioRangeText(model)}) ${cut.dir === 'up' ? 'above' : 'below'} it first at E = ${sig(cut.at)} GeV, scanning up in E; at E = ${sig(pe)} GeV it reads ${sig(pr)}.`),
    mutedLine('Clipped, not rescaled: a literature curve never sets the ratio range.'),
    mutedLine(LITERATURE_NO_INTERVAL),
    ...literatureWarningLines(model),
  ].join('<br/>');
}

/** The tooltip of the caret where a literature curve crosses the top of the main panel. */
function literatureCutTip(model, lit) {
  const [pe, pv] = lit.cut.peak;
  return [
    `<b>${escapeHtml(`${lit.entry.particle} literature curve`)}</b>`,
    escapeHtml(`${referenceEquation(lit.entry)} (${REFERENCE_UNITS}) lies above the top of the axis (0 to ${pct(model.y.hi)}) below E = ${sig(lit.cut.at)} GeV; at E = ${sig(pe)} GeV it reads ${pct(pv)}.`),
    mutedLine('Clipped, not rescaled: a literature curve never sets the range.'),
    mutedLine(LITERATURE_NO_INTERVAL),
    ...literatureWarningLines(model),
  ].join('<br/>');
}

/* ------------------------------------------------------- E-view marks -- */

/** A series' markers at `items` ({p, at: [E, v]}): filled (A) or hollow (B); a dashed ring below the whisker floor. */
function energyMarkers(s, items, id, tip) {
  return {
    type: 'custom',
    id,
    name: s.label,
    clip: true,
    z: 8,
    data: items.map((it, index) => [it.at[0], it.at[1], index]),
    renderItem: (params, api) => {
      const { p, at } = items[params.dataIndex];
      const c = api.coord(at);
      const cx = c[0] + s.offsetPx;
      const r = p.anchor ? ANCHOR_PX : MARKER_PX;
      if (p.subFloor) {
        const ring = {
          type: 'circle', shape: { cx, cy: c[1], r },
          style: { fill: THEME.card, stroke: s.colour, lineWidth: 1.2 * THEME.lineAxis, lineDash: DASH_RING, opacity: p.opacity },
        };
        if (s.isB) return ring;
        return { type: 'group', children: [ring, { type: 'circle', shape: { cx, cy: c[1], r: CORE_PX }, style: { fill: s.colour, opacity: p.opacity } }] };
      }
      return {
        type: 'circle',
        shape: { cx, cy: c[1], r },
        style: s.isB
          ? { fill: THEME.card, stroke: s.colour, lineWidth: 1.4 * THEME.lineAxis, opacity: p.opacity }
          : { fill: s.colour, stroke: THEME.card, lineWidth: 0.6 * THEME.lineAxis, opacity: p.opacity },
      };
    },
    tooltip: { formatter: (prm) => tip(items[prm.dataIndex].p) },
  };
}

/**
 * Every mark of one series on both grids, each named after it, so its legend
 * entry shows and hides all of them: its windows, whiskers and carets, and its
 * one fitted curve (`s.drawn`) with its entry and exit carets, with no band
 * (Martin's directive of 2026-11-15).
 */
function energySeriesMarks(model, s) {
  const { y } = model;
  const k = model.ratio.k;
  const out = [];
  const style = itemStyleOf(s);
  const named = (x) => ({ ...withColour(x, s.colour), name: s.label, itemStyle: { ...style } });
  const onRatio = (x) => ({ ...x, xAxisIndex: 1, yAxisIndex: 1 });
  const whiskerOpacity = (p) => (p.opacity === 1 ? 1 : legibleOpacity(s.colour, WEAK_OPACITY));
  const casing = { color: THEME.canvas, width: CASING_PX };

  // ---- the main panel
  out.push(named(energyMarkers(s, s.points.filter((p) => !p.over).map((p) => ({ p, at: [p.E, p.value] })),
    `${s.key}|markers`, (p) => energyPointTip(model, s, p))));
  const whiskers = s.points
    .filter((p) => p.whisker && p.clip && p.clip.lo !== null && p.clip.hi !== null && p.clip.hi > p.clip.lo)
    .map((p) => [p.E, p.clip.lo, p.clip.hi, { caps: p.clip.caps, opacity: whiskerOpacity(p), point: p }]);
  if (whiskers.length) {
    out.push(named({
      ...customWhiskers({
        name: s.label, points: whiskers, capPx: CAP_PX, color: s.colour, width: 1.2 * THEME.lineAxis,
        offsetPx: s.offsetPx, z: 7, casing, tooltip: (d) => energyPointTip(model, s, d.point),
      }),
      id: `${s.key}|whiskers`,
    }));
  }
  const carets = [];
  for (const p of s.points) {
    if (!(p.value > y.hi || p.clip?.cutHi || p.value < 0 || p.clip?.cutLo)) continue;
    const tip = energyPointTip(model, s, p);
    if (p.value > y.hi || p.clip?.cutHi) carets.push({ at: [p.E, y.hi], dir: 'up', tooltip: tip });
    if (p.value < 0 || p.clip?.cutLo) carets.push({ at: [p.E, 0], dir: 'down', tooltip: tip });
  }
  // The series' one curve (`s.drawn`): a/√E ⊕ b ⊕ c/E, or the a₀/√E fallback; none where it has neither.
  const f = s.drawn;
  // The curve comes down into the plot from the top: one caret where its line enters (`noiseEntryTip`; the a₀/√E
  // fallback's `pinnedEntryTip`, review-ui F5), or at x.max where it lies above the whole axis.
  if (f?.entry) {
    carets.push({ at: [f.entry.at, y.hi], dir: 'up', tooltip: f.form === 'noise' ? noiseEntryTip(model, s, f) : pinnedEntryTip(model, s, f) });
  }
  if (f?.cut) carets.push({ at: [f.cut.at, y.hi], dir: 'up', tooltip: energyFitCutTip(model, s, f) });
  if (carets.length) {
    out.push(named({ ...caretSeries({ name: s.label, carets, color: s.colour, offsetPx: s.offsetPx }), id: `${s.key}|carets` }));
  }
  // The width is the form: a/√E ⊕ b ⊕ c/E at 1.6 px, the a₀/√E fallback at 1 px. A faded fit (provisional, or a
  // misfit) fades whole, its solid part and its dashed extrapolation, on both panels.
  const opacity = f ? s.lineOpacity(f.faded) : 1;
  const width = (f?.form === 'noise' ? 1.6 : 1) * THEME.lineAxis;
  const curveRuns = (part, runs, panel) => runs.map((run) => customPolyline({
    name: s.label, points: run, color: s.colour, opacity, z: 5, width,
    dash: part === 'dashed' ? DASH_EXTRAPOLATED : null,
    tooltip: panel === 'ratio' ? () => ratioFitTip(model, s, f, part) : () => energyFitTip(model, s, f, part),
  })).map((x, i) => ({ ...x, id: `${s.key}${panel === 'ratio' ? '|ratio' : ''}|${f.form}|${part}|${i}` }));
  if (f) {
    for (const [part, runs] of [['solid', f.solid], ['dashed', f.dashed]]) out.push(...curveRuns(part, runs, 'main').map(named));
  }

  // ---- the ratio panel
  const ratioPoints = s.points.filter((p) => p.ratio.drawn);
  const ratioShown = ratioPoints.filter((p) => !p.ratio.over);
  if (ratioShown.length) {
    out.push(named(onRatio(energyMarkers(s, ratioShown.map((p) => ({ p, at: [p.E, p.ratio.value] })),
      `${s.key}|ratio|markers`, (p) => ratioPointTip(model, s, p)))));
  }
  const ratioWhiskers = ratioPoints
    .filter((p) => p.ratio.clip && p.ratio.clip.hi > p.ratio.clip.lo)
    .map((p) => [p.E, p.ratio.clip.lo, p.ratio.clip.hi, { caps: p.ratio.clip.caps, opacity: whiskerOpacity(p), point: p }]);
  if (ratioWhiskers.length) {
    out.push(named(onRatio({
      ...customWhiskers({
        name: s.label, points: ratioWhiskers, capPx: CAP_PX, color: s.colour, width: 1.2 * THEME.lineAxis,
        offsetPx: s.offsetPx, z: 7, casing, tooltip: (d) => ratioPointTip(model, s, d.point),
      }),
      id: `${s.key}|ratio|whiskers`,
    })));
  }
  const ratioCarets = [];
  for (const p of ratioPoints) {
    const r = p.ratio;
    const up = r.value > k || r.clip?.cutHi;
    const down = r.value < 1 / k || r.clip?.cutLo;
    if (!up && !down) continue;
    const tip = ratioPointTip(model, s, p);
    if (up) ratioCarets.push({ at: [p.E, k], dir: 'up', tooltip: tip });
    if (down) ratioCarets.push({ at: [p.E, 1 / k], dir: 'down', tooltip: tip });
  }
  // The curve's ratio: where it comes into the axis as E rises from 0 (a noise fit), and where it leaves.
  const rEntry = f?.ratio?.entry ?? null;
  const rCut = f?.ratio?.cut ?? null;
  if (rEntry) ratioCarets.push({ at: [rEntry.at, rEntry.dir === 'up' ? k : 1 / k], dir: rEntry.dir, tooltip: ratioEntryTip(model, s, f) });
  if (rCut) ratioCarets.push({ at: [rCut.at, rCut.dir === 'up' ? k : 1 / k], dir: rCut.dir, tooltip: ratioFitCutTip(model, s, f) });
  if (ratioCarets.length) {
    out.push(named(onRatio({ ...caretSeries({ name: s.label, carets: ratioCarets, color: s.colour, offsetPx: s.offsetPx }), id: `${s.key}|ratio|carets` })));
  }
  // The curve divided by the reference; the reference's own curve (1 by construction) has no ratio and is not drawn.
  if (f?.ratio) {
    for (const [part, runs] of [['solid', f.ratio.solid], ['dashed', f.ratio.dashed]]) {
      out.push(...curveRuns(part, runs, 'ratio').map((x) => named(onRatio(x))));
    }
  }
  return out;
}

/**
 * A 1/√E-view band that spans half its axis or more, drawn as its two edges:
 * thin lines in `colour` at `EDGE_OPACITY` (raised to 3:1), solid along their
 * whole length, since that view's lines mark no extrapolation (`edges.dashed`
 * is empty there). The E view draws no band (Martin's directive of
 * 2026-11-15). `edges` {solid, dashed} runs, already clipped to the plot. Each
 * run is a series `${id}|edges|<solid|dashed>|<i>` whose tooltip is
 * `tip(part)`.
 */
function bandEdges(edges, colour, id, tip) {
  const opacity = legibleOpacity(colour, EDGE_OPACITY);
  const out = [];
  for (const [part, runs] of [['solid', edges?.solid ?? []], ['dashed', edges?.dashed ?? []]]) {
    runs.forEach((run, i) => {
      out.push({
        ...customPolyline({
          name: id, points: run, color: colour, opacity, z: 4, width: EDGE_WIDTH * THEME.lineAxis,
          dash: part === 'dashed' ? DASH_EXTRAPOLATED : null, tooltip: () => tip(part),
        }),
        id: `${id}|edges|${part}|${i}`,
      });
    });
  }
  return out;
}

/**
 * A drawn literature curve: dotted runs in its identity colour on the main
 * panel, or (`ratio`) its line divided by the literature reference on the
 * ratio panel, under one legend entry; its labels are in the end column.
 */
function literatureSeries(model, lit, ratio = false) {
  const width = LITERATURE_WIDTH * THEME.lineAxis;
  const runs = ratio ? lit.ratio.runs : lit.runs;
  return {
    type: 'custom',
    id: ratio ? `literature|${lit.key}|ratio` : `literature|${lit.key}`,
    name: lit.legend,
    ...(ratio ? { xAxisIndex: 1, yAxisIndex: 1 } : {}),
    clip: true,
    z: 4,
    silent: false,
    itemStyle: { color: lit.colour },
    data: [ratio ? (lit.ratio.rows[0] ?? [model.x.max, 1]) : (lit.curve[0] ?? [model.x.max, 0])],
    renderItem: (params, api) => ({
      type: 'group',
      children: runs.map((run) => ({
        type: 'polyline',
        shape: { points: run.map((pt) => api.coord(pt)) },
        style: { fill: 'none', stroke: lit.colour, lineWidth: width, lineDash: DASH_LITERATURE },
      })),
    }),
    tooltip: { formatter: () => (ratio ? literatureRatioTip(model, lit) : literatureTip(model, lit)) },
  };
}

/** The width of the end-label column beside the plot (px): the widest label and its gap; 0 without a label. */
function endColumnPx(model) {
  const labels = [...model.endLabels.main, ...model.endLabels.ratio];
  if (!labels.length) return 0;
  const font = THEME.fontTip;
  const widest = Math.max(...labels.map((l) => measureText(l.text, font, THEME.fontFamily)));
  return Math.ceil((END_LABEL_GAP + END_KEY_LENGTH + END_KEY_GAP) * font + widest);
}

/**
 * Where a panel's end labels sit: at the curves' right ends in the column
 * beside the plot, spread to a pitch of `END_LABEL_PITCH` × `fontTip` within
 * the panel, their order kept. `ends` [y at x.max of the panel's top, of its
 * floor]. Returns {x, ys} in px, `ys` in the order of `labels`.
 */
function endLabelPlaces(labels, model, api, ends) {
  const font = THEME.fontTip;
  const at = labels.map((l) => api.coord([model.x.max, l.value]));
  const [a, b] = ends.map((v) => api.coord([model.x.max, v])[1]);
  const half = font / 2;
  const ys = spreadLabels(at.map((c) => c[1]), END_LABEL_PITCH * font, Math.min(a, b) + half, Math.max(a, b) - half);
  const right = api.coord([model.x.max, ends[0]])[0];
  return { x: right + END_LABEL_GAP * font, ys };
}

/**
 * The end labels of one legend entry on one panel, as a series named after it
 * (so the legend hides them with it), drawn outside the plot (`clip: false`)
 * in the column `endColumnPx` reserves. Each renderer places every label of
 * its panel (`endLabelPlaces`) and draws its own, so labels of different
 * series clear each other. Null when the entry has no label there.
 */
function endLabelSeries(model, panel, name) {
  const labels = model.endLabels[panel];
  const own = labels.map((l, i) => [l, i]).filter(([l]) => l.name === name);
  if (!own.length) return null;
  const ratio = panel === 'ratio';
  const ends = ratio ? [model.ratio.k, 1 / model.ratio.k] : [model.y.hi, 0];
  const key = `${own[0][0].key}${ratio ? '|ratio' : ''}`;
  return {
    type: 'custom',
    id: `${key}|endlabels`,
    name,
    clip: false,
    silent: true,
    z: 9,
    ...(ratio ? { xAxisIndex: 1, yAxisIndex: 1 } : {}),
    data: [[model.x.max, own[0][0].value]],
    renderItem: (params, api) => {
      const place = endLabelPlaces(labels, model, api, ends);
      return {
        type: 'group',
        children: own.flatMap(([l, i]) => {
          const font = THEME.fontTip;
          const y = place.ys[i];
          const k = l.stroke ?? { colour: l.colour, width: 1, dash: null, opacity: 1 };
          return [
            {
              type: 'line',
              silent: true,
              shape: { x1: place.x, y1: y, x2: place.x + END_KEY_LENGTH * font, y2: y },
              style: { stroke: k.colour, lineWidth: k.width * THEME.lineAxis, lineDash: k.dash, opacity: k.opacity },
            },
            {
              type: 'text',
              silent: true,
              style: {
                x: place.x + (END_KEY_LENGTH + END_KEY_GAP) * font, y, text: l.text, fill: THEME.text, fontSize: font,
                fontFamily: THEME.fontFamily, textAlign: 'left', textVerticalAlign: 'middle',
              },
            },
          ];
        }),
      };
    },
  };
}

/**
 * The ratio axis's ticks: 1, k and 1/k, and each step of `RATIO_STEPS` below k
 * with its reciprocal where it clears its neighbours by 1.6 label heights on
 * a panel `heightPx` tall: symmetric, so ×s and ÷s sit at equal distances.
 */
export function ratioTicks(k, heightPx) {
  const minPx = 1.6 * THEME.fontLabel;
  const pxOf = (v) => (heightPx * Math.log(v)) / (2 * Math.log(k));
  const kept = [1, k];
  for (const s of [...RATIO_STEPS].filter((v) => v < k).reverse()) {
    if (kept.every((t) => Math.abs(pxOf(t) - pxOf(s)) >= minPx)) kept.push(s);
  }
  const up = kept.filter((t) => t > 1).sort((a, b) => a - b);
  return [...up.map((t) => 1 / t).reverse(), 1, ...up];
}

/**
 * The ratio axis's name at its height: "ratio to …", shortened to fit, "—
 * provisional" when it is, "— capped at ×50" when a robust mark lies beyond the
 * last step of `RATIO_STEPS`.
 */
function ratioAxisName(model, px) {
  const ref = model.reference;
  const lit = ref.literature;
  const one = Object.keys(ref.byShower).length === 1 ? Object.values(ref.byShower)[0] : null;
  const owner = model.nShowers > 1 ? (one ? `shower ${String(one.shower).toUpperCase()}'s` : 'each shower\'s') : 'the';
  const names = lit
    ? [`ratio to ${referenceLabel(lit)}`, `÷ ${referenceLabel(lit)}`, `÷ ${lit.particle} lit.`]
    : [`ratio to ${owner} deposit fit`, `÷ ${owner} deposit fit`, '÷ deposit fit'];
  let suffix = '';
  if (model.ratio.provisional) suffix = ' — provisional';
  else if (model.ratio.capped) suffix = ` — capped at ×${sigFigs(model.ratio.k, 3)}`;
  return fitName(names.map((n) => `${n}${suffix}`), px);
}

/** A ratio tick's label: decimal from 1 up, its reciprocal written 1/x below 1, so ÷3 reads "1/3" beside "3". */
export function ratioTickLabel(v) {
  const value = Number(v);
  if (!Number.isFinite(value) || value <= 0) return '';
  return value < 1 - 1e-9 ? `1/${sigFigs(1 / value, 3)}` : sigFigs(value, 3);
}

/**
 * The canvas note's lines at a width: the off-scale list (two lines at most,
 * then "+n more in Details") on the left, and the extrapolation rule on the
 * right, wrapped whole (its span "(4–20 GeV)" is never cut).
 *
 * Side by side, the rule keeps under half of `plotWidthPx` and the list the
 * rest. Where the list's widest token (one window and series, never broken)
 * would not fit beside the rule, or the rule needs more than two lines there,
 * the two blocks are stacked instead (`stacked`): the list first, over all of
 * `fullPx` (the canvas right of the y axis), then the rule right-aligned
 * beneath it, so the two never overprint. `height` reserves either layout.
 *
 * Under the median estimator with a literature curve on, the literature
 * disclosure (`noteText.warning`, brief section 2.7) is one more line of the
 * band, beneath both blocks over all of `fullPx`, wrapped at its spaces where
 * the canvas is too narrow for it (`warning`, its lines; `warnAt`, the lines
 * above it). Without it the layout is the one it always was.
 */
function noteLayout(model, plotWidthPx, fullPx = plotWidthPx) {
  const base = noteBlocks(model, plotWidthPx, fullPx);
  const text = model.noteText.warning;
  if (!text) return { ...base, warning: [], warnAt: 0 };
  const font = THEME.fontTip;
  const warning = packTokens(text.split(' '), Math.max(80, fullPx), font, THEME.fontFamily);
  const above = base.stacked ? base.left.length + base.right.length : Math.max(base.left.length, base.right.length);
  return {
    ...base, warning, warnAt: above,
    height: (above + warning.length) * base.lineH + Math.round(1.1 * font),
  };
}

/** The off-scale list and the extrapolation rule of the canvas note (`noteLayout`), as they always were. */
function noteBlocks(model, plotWidthPx, fullPx = plotWidthPx) {
  const font = THEME.fontTip;
  const family = THEME.fontFamily;
  const lineH = Math.ceil(1.35 * font);
  const width = (t) => measureText(t, font, family);
  const extrapolation = model.noteText.extrapolation;
  // Wrapped at its spaces, a parenthesised span "(4–20 GeV)" kept whole on one line.
  const wrapped = (room) => (!extrapolation ? []
    : (width(extrapolation) <= room ? [extrapolation] : packTokens(extrapolation.match(/\([^)]*\)|\S+/gu), room, font, family)));
  const heightOf = (lines) => (lines ? lines * lineH + Math.round(1.1 * font) : 0);
  if (!model.offScale.length) {
    const right = wrapped(Math.max(80, plotWidthPx));
    return { left: [], right, stacked: false, lineH, height: heightOf(right.length) };
  }
  // One token per window and series, so a line never breaks inside "7–8 GeV — A network 91.1%".
  const entries = model.offScale.flatMap((g) => g.entries.map((e, i) => ({
    text: i === 0 ? `${g.label} — ${e.short} ${pct(e.value)}` : `${e.short} ${pct(e.value)}`,
    end: i === g.entries.length - 1,
  })));
  const listIn = (room) => {
    let left = [];
    for (let keep = entries.length; keep >= 0; keep -= 1) {
      const more = entries.length - keep;
      const tokens = entries.slice(0, keep).map((x, i) => `${x.text}${i < keep - 1 || more ? (x.end ? ';' : ',') : ''}`);
      if (more) tokens.push(`+${formatInt(more)} more in Details`);
      tokens[0] = `↑ off scale: ${tokens[0]}`;
      left = packTokens(tokens, room, font, family);
      if (left.length <= 2) break;
    }
    return left;
  };
  const widestToken = Math.max(
    width(`↑ off scale: ${entries[0].text};`),
    ...entries.map((x) => width(`${x.text};`)),
    width(`+${formatInt(entries.length)} more in Details`),
  );
  const right = wrapped(Math.max(80, 0.45 * plotWidthPx));
  const rightW = right.length ? Math.max(...right.map(width)) : 0;
  const room = Math.max(80, plotWidthPx - rightW - (rightW ? 1.5 * font : 0));
  if (right.length <= 2 && widestToken <= room) {
    const left = listIn(room);
    return { left, right, stacked: false, lineH, height: heightOf(Math.max(left.length, right.length)) };
  }
  const left = listIn(Math.max(80, fullPx));
  const under = wrapped(Math.max(80, plotWidthPx));
  return { left, right: under, stacked: true, lineH, height: heightOf(left.length + under.length) };
}

/** `tokens` joined by spaces into lines no wider than `room`, never breaking inside a token. */
function packTokens(tokens, room, font, family) {
  const lines = [];
  let line = '';
  for (const t of tokens) {
    const candidate = line ? `${line} ${t}` : t;
    if (!line || measureText(candidate, font, family) <= room) {
      line = candidate;
    } else {
      lines.push(line);
      line = t;
    }
  }
  if (line) lines.push(line);
  return lines;
}

/**
 * The σ/E axis's tick interval at a plot `heightPx` tall: the server's,
 * widened by a round factor that still lands on the top when its labels would
 * crowd (a printed single-column figure), else the server's unchanged.
 */
function verticalInterval(top, interval, heightPx) {
  if (!(interval > 0) || !(top > 0)) return interval;
  const allowed = Math.max(2, Math.floor(heightPx / (1.8 * THEME.fontLabel)));
  for (const factor of [1, 2, 2.5, 5, 10]) {
    const n = top / (interval * factor);
    if (n <= allowed && Math.abs(n - Math.round(n)) < 1e-9) return interval * factor;
  }
  return interval;
}

/** The crosshair of both grids, linked: a line at the pointer's E, its label on the bottom axis only, never a tooltip. */
function crosshair(label) {
  return {
    show: true,
    type: 'line',
    snap: false,
    triggerTooltip: false,
    lineStyle: { color: THEME.muted, width: THEME.lineAxis, type: [3, 3] },
    label: label
      ? {
        show: true,
        formatter: (p) => {
          const v = typeof p === 'object' && p !== null ? p.value : p;
          return Number.isFinite(Number(v)) ? `E = ${sigFigs(Number(v), 3)} GeV` : '';
        },
        color: THEME.text, backgroundColor: THEME.labelBg, borderColor: THEME.border, borderWidth: 1,
        fontSize: THEME.fontSmall, fontFamily: THEME.fontFamily, padding: [2, 4],
      }
      : { show: false },
  };
}

/** What the E view says when it has nothing to draw. */
function energyEmptyText(model) {
  const { gates } = model;
  const reportable = model.series.reduce((a, s) => a + (s.raw.windows ?? [])
    .filter((w) => (w.n ?? 0) >= gates.report_n && Number.isFinite(w.value)).length, 0);
  const declined = declinedEmptyText(model, 'All windows');
  if (declined) return declined;
  if (model.mode === 'anchors' && reportable && model.y.hi > 0) {
    return `No window from ${formatNumber(gates.anchor_low_gev)} GeV reaches N = ${formatInt(gates.whisker_n)}, the fewest an anchor fit runs through, `
      + `so the 3-anchor mode draws nothing. "All windows" draws the ${plural(reportable, 'window')} that report ${model.estimator.quantity} `
      + `(N ≥ ${formatInt(gates.report_n)}), those below ${formatNumber(model.curveMinGev)} GeV as points only.`;
  }
  return `No momentum window ${holdsText(gates)} in this selection, so no ${model.estimator.quantity} can be drawn on this axis.`;
}

/**
 * Why the E view draws nothing for `model` (the empty state's sentence), or
 * null where it draws its two panels.
 */
function energyEmptyReason(model, opts = {}) {
  if (!model) return 'This response carries no energy-resolution series for the E view.';
  const empty = (m) => (!m.nPoints && !m.nLines) || !(m.y.hi > 0);
  const hiddenEmpty = depositHiddenEmpty(model.payload, opts, model, empty, (o) => energyModel(model.payload, o));
  if (hiddenEmpty) return hiddenEmpty;
  if (!model.series.length) return 'No series of the chosen shower in this response.';
  if (empty(model)) return energyEmptyText(model);
  return null;
}

/** Whether the E view draws its two panels for this payload and these options (else its empty state). */
export function energyDrawsPanels(payload, opts = {}) {
  return energyEmptyReason(energyModel(payload, opts), opts) === null;
}

/**
 * The E view's option. Pure but for the legend context (`hiddenEntries`: the
 * names switched off on the legend, on screen or in an export; null when none
 * is): `opts` = {windows, shower, literature
 * (or the older reference), estimator, deposit, eMax, palette, card,
 * tooltipPosition?}; `metrics` = {width, height}. Returns {option,
 * plotGrid}: two grids, the main panel over the ratio panel, on one E axis
 * (`plotGrid` their union for the tooltip placement), the canvas note
 * between the legend and the main panel, and the end-label column beside
 * both panels, which widens the grids' `right` where any curve is labelled.
 */
export function energyViewOption(payload, opts = {}, metrics = {}) {
  const model = energyModel(payload, opts);
  const empty = energyEmptyReason(model, opts);
  if (empty) return { option: emptyChartOption(opts, metrics, empty) };
  const pad = axisPadding();
  const f = THEME.fontLabel;
  const width = metrics.width || 760;
  const height = metrics.height || ENERGY_VIEW_PX;
  const gap = gridGapPx();
  // Every mark of a name switched off on the legend is left out, on screen and in an export (`hiddenEntries`):
  // its marks on both panels, its end labels and its off-scale values; with none switched off `view` is `model`.
  const off = hiddenEntries();
  const kept = (name) => !off?.has(name);
  const view = exportView(model, off);
  const right = pad.right + endColumnPx(view);
  const legendWidthPx = Math.max(80, width - pad.left - pad.right);
  const plotWidthPx = Math.max(80, width - pad.left - right);

  const series = [];
  const legend = [];
  for (const s of model.series) {
    if (!s.points.length && !s.drawn) continue;
    if (kept(s.label)) series.push(...energySeriesMarks(model, s));
    // Every entry is listed: on screen a left-out one is greyed; an export's legend drops it and marks it false
    // (chartLegend, legendTop).
    legend.push({ name: s.label, icon: 'circle' });
  }
  // The literature curves drawn: each one's line, caret, legend swatch and end label in its identity colour, and
  // beside a literature reference its line divided by it on the ratio panel, with its own caret.
  for (const lit of model.literature) {
    if (!kept(lit.legend)) {
      legend.push({ name: lit.legend, icon: LITERATURE_ICON, itemStyle: { color: lit.colour } });
      continue;
    }
    series.push(literatureSeries(model, lit));
    if (lit.cut) {
      series.push({
        ...caretSeries({ name: lit.legend, carets: [{ at: [lit.cut.at, model.y.hi], dir: 'up', tooltip: literatureCutTip(model, lit) }], color: lit.colour }),
        id: `literature|${lit.key}|caret`,
        itemStyle: { color: lit.colour },
      });
    }
    if (lit.ratio) {
      series.push(literatureSeries(model, lit, true));
      const cut = lit.ratio.cut;
      if (cut) {
        const k = model.ratio.k;
        series.push({
          ...caretSeries({ name: lit.legend, carets: [{ at: [cut.at, cut.dir === 'up' ? k : 1 / k], dir: cut.dir, tooltip: literatureRatioCutTip(model, lit) }], color: lit.colour }),
          xAxisIndex: 1,
          yAxisIndex: 1,
          id: `literature|${lit.key}|ratio|caret`,
          itemStyle: { color: lit.colour },
        });
      }
    }
    legend.push({ name: lit.legend, icon: LITERATURE_ICON, itemStyle: { color: lit.colour } });
  }
  // The end labels, one series per legend entry and panel, so the legend hides them with their curves; an export
  // places and spreads the labels it keeps alone (`view`).
  for (const panel of ['main', 'ratio']) {
    for (const name of new Set(view.endLabels[panel].map((l) => l.name))) {
      const labels = endLabelSeries(view, panel, name);
      if (labels) series.push(labels);
    }
  }

  const legendBottom = legendTop(legend, legendWidthPx, { wrap: true });
  const note = noteLayout(view, plotWidthPx, Math.max(80, width - pad.left - 2));
  const mainTop = legendBottom + note.height;
  const avail = Math.max(140, height - mainTop - pad.bottom - gap);
  const ratioH = Math.max(40, Math.round(RATIO_SHARE * avail));
  const mainH = Math.max(60, avail - ratioH);
  const grid = [
    { left: pad.left, right, top: mainTop, height: mainH },
    { left: pad.left, right, top: mainTop + mainH + gap, height: ratioH },
  ];
  const { k } = model.ratio;
  // With no reference on show the panel keeps its frame and the E axis but draws no 1.0 rule (Martin's decision
  // of 2026-11-17): a rule would read as a reference the ratio is taken against.
  if (!model.ratio.none) {
    series.push({
      type: 'custom',
      id: 'ratio|unity',
      name: 'ratio = 1',
      xAxisIndex: 1,
      yAxisIndex: 1,
      clip: true,
      z: 3,
      silent: false,
      data: [[model.x.min, 1]],
      renderItem: (params, api) => {
        const a = api.coord([model.x.min, 1]);
        const b = api.coord([model.x.max, 1]);
        return { type: 'line', shape: { x1: a[0], y1: a[1], x2: b[0], y2: b[1] }, style: { stroke: THEME.text, lineWidth: THEME.lineAxis } };
      },
      tooltip: { formatter: () => unityTip(model) },
    });
  }

  const xRange = { min: model.x.min, max: model.x.max, interval: model.x.interval };
  // Under E max both x axes tick at `x.ticks` (res_axis.eAxisTicks), from 0 to the slider's value; without it,
  // the server's interval as before.
  const drawn = drawnETicks(model.x.ticks, model.x.max, plotWidthPx);
  const ticked = (a) => (drawn
    ? { ...a, min: 0, max: model.x.max, axisTick: { ...a.axisTick, customValues: drawn }, axisLabel: { ...a.axisLabel, customValues: drawn } }
    : a);
  const top = ticked(valueAxis({ ...xRange, gridIndex: 0 }));
  const bottom = ticked(valueAxis({ ...xRange, gridIndex: 1, name: model.x.name }));
  const yBase = model.y.name;
  const yName = fitName(model.y.provisional
    ? [`${yBase} — provisional, no window from ${formatNumber(model.yMinGev)} GeV reaches N = ${formatInt(model.gates.fit_n)}`, `${yBase} — provisional`]
    : [yBase], mainH);
  const ticks = ratioTicks(k, ratioH);
  const ratio = valueAxis({
    type: 'log', gridIndex: 1, name: ratioAxisName(model, ratioH), min: 1 / k, max: k, nameGap: 3.6 * f,
    formatter: ratioTickLabel,
  });
  // No reference: the ratio axis is no scale, so it carries no tick, label, split line or name.
  const ratioAxis = model.ratio.none
    ? { ...valueAxis({ type: 'log', gridIndex: 1, name: '', min: 1 / k, max: k, labels: false }), logBase: 10 }
    : { ...ratio, logBase: 10, axisTick: { ...ratio.axisTick, customValues: ticks }, axisLabel: { ...ratio.axisLabel, customValues: ticks } };
  const noteTop = legendBottom + Math.round(0.2 * THEME.fontTip);
  const noteStyle = {
    fill: THEME.muted, fontSize: THEME.fontTip, fontFamily: THEME.fontFamily, lineHeight: note.lineH, textVerticalAlign: 'top',
  };
  const graphic = [];
  if (note.left.length) graphic.push({ type: 'text', silent: true, style: { ...noteStyle, x: pad.left, y: noteTop, text: note.left.join('\n') } });
  if (note.right.length) {
    // Beside the list at its top, or (stacked) beneath it; right-aligned at the plot's right border either way.
    const y = noteTop + (note.stacked ? note.left.length * note.lineH : 0);
    graphic.push({ type: 'text', silent: true, style: { ...noteStyle, x: width - right, y, text: note.right.join('\n'), textAlign: 'right' } });
  }
  if (note.warning.length) {
    // The literature disclosure under the median estimator: one line of the band, beneath the other two.
    graphic.push({
      type: 'text', silent: true,
      style: { ...noteStyle, x: pad.left, y: noteTop + note.warnAt * note.lineH, text: note.warning.join('\n') },
    });
  }
  if (model.ratio.none) {
    // One sentence centred in the ratio panel; the screen says how to draw a ratio, which a printed figure cannot.
    // It wraps inside the plot's width (`overflow: 'break'`), so its text stays the one sentence.
    graphic.push({
      type: 'text', silent: true,
      style: {
        x: pad.left + plotWidthPx / 2, y: grid[1].top + ratioH / 2, text: `${RATIO_NONE_TEXT}${isPrintTheme() ? '' : RATIO_NONE_SCREEN_TEXT}`,
        textAlign: 'center', textVerticalAlign: 'middle', width: Math.max(80, plotWidthPx - 8), overflow: 'break',
        fill: THEME.muted, fontSize: THEME.fontTip, fontFamily: THEME.fontFamily, lineHeight: 1.45 * THEME.fontTip,
      },
    });
  }
  return {
    option: {
      ...baseOption(),
      tooltip: wrapTooltip(tooltipOption(opts.tooltipPosition ?? null)),
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      grid,
      legend: wrappedLegend(legend, { left: pad.left, right: pad.right }),
      xAxis: [
        { ...top, name: '', axisLabel: { ...top.axisLabel, show: false }, axisPointer: crosshair(false) },
        { ...bottom, axisPointer: crosshair(true) },
      ],
      yAxis: [
        valueAxis({
          name: yName, min: 0, max: model.y.hi, interval: verticalInterval(model.y.hi, model.y.interval, mainH),
          split: true, nameGap: 3.6 * f, gridIndex: 0,
        }),
        ratioAxis,
      ],
      graphic,
      series,
    },
    plotGrid: grid,
  };
}

/**
 * The E axis's ticks as drawn on a plot `plotWidthPx` wide: `ticks` (res_axis.eAxisTicks), without the grid tick just
 * before an end off the step grid where the two labels would touch (review R3-9: at E max 75 a single-column figure
 * set '70' and '75' 0.2 px apart). The end stays ticked; null without ticks (the server's own axis).
 */
export function drawnETicks(ticks, max, plotWidthPx) {
  if (!Array.isArray(ticks) || ticks.length < 3 || !(max > 0) || !(plotWidthPx > 0)) return ticks ?? null;
  const end = ticks[ticks.length - 1];
  const prev = ticks[ticks.length - 2];
  const width = (v) => measureText(tickLabel(v), THEME.fontLabel, THEME.fontFamily);
  const gapPx = ((end - prev) / max) * plotWidthPx;
  return gapPx < (width(prev) + width(end)) / 2 + 0.5 * THEME.fontLabel ? [...ticks.slice(0, -2), end] : ticks;
}

/**
 * What the E view draws of its `model` with names switched off on the legend
 * (Martin's decisions of 2026-11-17: a figure describes only what is on show,
 * and the screen draws what its export would): with `off`, those names
 * (`hiddenEntries`, on screen or in an export), a copy whose series,
 * literature curves, end labels and off-scale list hold none of them, and
 * whose note text is recomputed from what is kept (the extrapolation rule from
 * the kept series' dashed runs). The literature disclosure stays while a curve
 * is on: the ratio may still divide by it. With none (`off` null or empty),
 * `model` itself.
 */
function exportView(model, off) {
  if (!off || !off.size) return model;
  const series = model.series.filter((s) => !off.has(s.label));
  const keys = new Set(series.map((s) => s.key));
  const offScale = model.offScale
    .map((g) => ({ ...g, entries: g.entries.filter((e) => keys.has(e.key)) }))
    .filter((g) => g.entries.length);
  const keep = (l) => !off.has(l.name);
  return {
    ...model,
    series,
    literature: model.literature.filter((lit) => !off.has(lit.legend)),
    endLabels: { main: model.endLabels.main.filter(keep), ratio: model.endLabels.ratio.filter(keep) },
    offScale,
    noteText: { ...model.noteText, offScale: offScaleText(offScale), extrapolation: extrapolationText(series) },
  };
}

/**
 * The E view's figure height at an export `width`: the legend and the canvas
 * note, the main panel at `aspect` of the plot width, the gap, and the ratio
 * panel at its share, so the figure keeps the screen's proportions.
 */
export function energyExportMetrics(payload, opts, width, aspect) {
  const pad = axisPadding();
  const plotWidth = Math.max(80, width - pad.left - pad.right);
  const { option } = energyViewOption(payload, opts, { width, height: ENERGY_VIEW_PX });
  const grids = [].concat(option.grid ?? []);
  const top = Number.isFinite(grids[0]?.top) ? grids[0].top : pad.top;
  const mainH = plotWidth * aspect;
  if (grids.length < 2) return { width, height: Math.round(top + pad.bottom + mainH) };
  const ratioH = (mainH * RATIO_SHARE) / (1 - RATIO_SHARE);
  return { width, height: Math.round(top + mainH + gridGapPx() + ratioH + pad.bottom) };
}

/* --------------------------------------------------------------- class -- */

export class ResolutionScalingPanel extends ChartPanel {
  /** `element` is the plot; the fit table goes after the card's `.plot-frame`. */
  constructor(elementOrId, { card = null, aspect } = {}) {
    super(elementOrId, { kind: 'res-scaling', aspect });
    this.card = card;
    this.tableHost = null;
    this.tableDoc = null;
  }

  buildOption({ payload, opts = {}, metrics }) {
    if (resolutionView(opts.view) === 'energy') return energyViewOption(payload, opts, metrics);
    return { option: resolutionScalingOption(payload, opts, metrics) };
  }

  /**
   * The plot's height for the view in force, set before ECharts measures:
   * `ENERGY_VIEW_PX` where the E view draws its two panels, cleared otherwise
   * (the 1/√E view, and the E view's one-sentence empty state) so the CSS
   * 420 px holds. True when it changed. It snaps, never animates (the chart's
   * ResizeObserver must see one size).
   */
  syncHeight() {
    if (!this.element?.style) return false;
    const twoPanels = resolutionView(this.lastOpts?.view) === 'energy' && energyDrawsPanels(this.lastPayload, this.lastOpts ?? {});
    const want = twoPanels ? `${ENERGY_VIEW_PX}px` : '';
    if ((this.element.style.height || '') === want) return false;
    this.element.style.height = want;
    return true;
  }

  render(payload, opts = {}) {
    this.lastPayload = payload;
    this.lastOpts = opts;
    // A view switch resizes the chart in the same call, so the option is laid out at the new height.
    if (this.syncHeight() && this.chart) this.chart.resize();
    super.render(payload, opts);
    this.renderTable();
  }

  relayout() {
    if (this.syncHeight() && this.chart) this.chart.resize();
    super.relayout();
  }

  /**
   * What the E view's ratio divides by now ('deposit', 'pi', 'e' or 'none'), or null off the E view: an export's
   * file name says it where the legend hides the curve drawn (review R3-10).
   */
  ratioReferenceKey() {
    if (!this.lastPayload || resolutionView(this.lastOpts?.view) !== 'energy') return null;
    return energyModel(this.lastPayload, this.lastOpts ?? {})?.reference?.key ?? null;
  }

  /** The E view's figure is two panels tall (`energyExportMetrics`); the 1/√E view's is the base figure. */
  exportMetrics(width) {
    if (!this.lastPayload || resolutionView(this.lastOpts?.view) !== 'energy') return super.exportMetrics(width);
    return energyExportMetrics(this.lastPayload, this.lastOpts ?? {}, width, this.aspect);
  }

  /** The table's host, created once after the card's plot frame; null outside a card. */
  ensureTableHost() {
    if (this.tableHost) return this.tableHost;
    const card = this.element?.closest?.('.card');
    const frame = card?.querySelector?.('.plot-frame');
    if (!frame) return null;
    const doc = frame.ownerDocument ?? globalThis.document;
    const host = doc.createElement('div');
    host.className = 'res-fit-table';
    frame.after(host);
    this.tableHost = host;
    this.tableDoc = doc;
    return host;
  }

  /**
   * Text nodes only: every label comes from a payload. One `tbody` per series:
   * its name (a row-group header) and the windows it fitted span its four
   * fit rows, each headed by the fit's name. Every cell wraps at its spaces;
   * text is left-aligned (`text`) and numbers right-aligned (`num`), a value
   * and its SE held together by no-break spaces.
   */
  renderTable() {
    const host = this.ensureTableHost();
    if (!host) return;
    const model = fitTableRows(this.lastPayload, this.lastOpts ?? {});
    if (!model || !model.rows.length) {
      host.replaceChildren();
      return;
    }
    const doc = this.tableDoc ?? host.ownerDocument ?? globalThis.document;
    const el = (tag, text, column = null) => {
      const node = doc.createElement(tag);
      if (text !== undefined && text !== null) node.textContent = text;
      if (column !== null) node.className = FIT_TABLE_TEXT_COLUMNS.includes(column) ? 'text' : 'num';
      return node;
    };
    const table = el('table');
    table.className = 'fit-table';
    table.append(el('caption', model.caption));
    const head = el('thead');
    const names = el('tr');
    model.columns.forEach((c, i) => {
      const th = el('th', c, i);
      th.setAttribute?.('scope', 'col');
      names.append(th);
    });
    head.append(names);
    table.append(head);
    for (const row of model.rows) {
      const body = el('tbody');
      row.fits.forEach((fit, k) => {
        const tr = el('tr');
        if (k === 0) {
          const series = el('th', row.label, 0);
          series.setAttribute?.('scope', 'rowgroup');
          series.setAttribute?.('rowspan', String(row.fits.length));
          tr.append(series);
        }
        // Fit, a, b, c, χ²/ν, S, then (once) the windows, then the status.
        const [name, a, b, c, chi2, scale, status] = fit.cells;
        const fitName = el('th', name, 1);
        fitName.setAttribute?.('scope', 'row');
        tr.append(fitName, el('td', a, 2), el('td', b, 3), el('td', c, 4), el('td', chi2, 5), el('td', scale, 6));
        if (k === 0) {
          const windows = el('td', row.windows, 7);
          windows.setAttribute?.('rowspan', String(row.fits.length));
          tr.append(windows);
        }
        tr.append(el('td', status, 8));
        body.append(tr);
      });
      table.append(body);
    }
    host.replaceChildren(table);
  }

  /** Forget the picture, the table and the E view's height, so a card shut or failed in that view is not left 600 px tall. */
  clear() {
    super.clear();
    if (this.element?.style) this.element.style.height = '';
    this.tableHost?.replaceChildren();
  }
}
