/* §2.4 Estimators, uncertainty and epistemic gates.
 *
 * Follows calosrv/stats/ (gaussian, histogram, kde, rmse, median, metrics,
 * circular, jackknife, profile, describe, clip), query/response.py and
 * query/energy.py (calibration, the series ladder, curve area),
 * modelruns/analysis.py (circular_fidelity) and static/js/panel_notes.js.
 * Content model and rules: index.js. */

import { C } from '../constants.js';

/* TeX and code spans in one string. String.raw keeps TeX's backslashes; an
 * escaped backtick becomes the plain one the renderer reads as a code span. */
const md = (strings, ...values) =>
  String.raw({ raw: strings.raw.map((s) => s.replaceAll('\\`', '`')) }, ...values);

// Derived from the constants, never typed.
const KAPPA = C.CORE_TRUNCATION_FACTOR.toFixed(4);
const COVERAGE = C.CORE_WINDOW_COVERAGE.toFixed(4);
const T_OVER_Z = (C.T_975_DF2 / C.Z_975).toFixed(1);
const Z = C.Z_975.toFixed(3);

const calibration = {
  id: 'sec-statistics-calibration',
  title: 'Calibration and the sampling fraction',
  blocks: [
    { kind: 'p', text: md`A sampling calorimeter registers only a fraction of a particle's energy in its active cells; the summed deposit of a shower is of order 0.05 GeV while the incident momenta span 0.4–20 GeV (\`query/energy.py\`), so a deposit and a momentum never share an axis. Each shower $j \in \{A, B\}$ is calibrated by one constant, a ratio of sums over the events $i$ of the selection in which that shower deposited energy:` },
    { kind: 'eq', id: 'eq-calibration', tex: String.raw`c_j = \frac{\sum_i p_{ij}}{\sum_i E_{\mathrm{dep},ij}}, \qquad E_{\mathrm{reco},ij} = c_j\,E^{\mathrm{pred}}_{\mathrm{dep},ij}, \qquad f_j = \frac{100}{c_j}\ \%` },
    { kind: 'p', text: md`$E_{\mathrm{dep},ij}$ is the truth segmentation's share of the event's hit energy, $E^{\mathrm{pred}}_{\mathrm{dep},ij}$ the network's, and $f_j$ the sampling fraction the constant implies. Three choices are deliberate. The constant is fitted once per shower over the whole selection and never per momentum bin or per slice: a per-bin constant forces every bin onto its own truth and erases the response curve and the containment scatter the resolution exists to measure. A shower that deposited nothing says nothing about the sampling fraction, so it is left out of both sums and counted in a notice. And the sums are taken before dividing, which weights each event by its momentum. The notebook's estimator, drawn as B1's marker, is the mean of the per-event ratios instead, which weights every event alike:` },
    { kind: 'eq', id: 'eq-mean-of-ratios', tex: String.raw`\bar f_j = \frac{100}{N_j}\sum_i \frac{E_{\mathrm{dep},ij}}{p_{ij}}\ \%` },
    { kind: 'p', text: md`Because the fraction itself depends on the momentum (2.3% in the lowest bin of the electron file against about 3.1% from 5 GeV up), the two differ: 3.041% for [[eq-mean-of-ratios]] against 3.113% for [[eq-calibration]] on that file (\`query/response.py\`; README "Energy calibration"). Neither is *the* sampling fraction; B1 draws both, each with its own interval and its own name. The interval of a ratio of sums treats the event as the sampling unit, because the hits of one event share a shower and are not independent draws. With $y_i$ and $x_i$ the per-event numerator and denominator, the linearised (delta-method) variance over $n$ clusters [[cite:cochran1977]] is` },
    { kind: 'eq', id: 'eq-ratio-se', tex: String.raw`\hat Q = \frac{\sum_i y_i}{\sum_i x_i}, \qquad \widehat{\operatorname{SE}}{}^2(\hat Q) = \frac{\sum_i \left(y_i - \hat Q\,x_i\right)^2}{n\,(n-1)\,\bar x^2}, \qquad \hat Q \pm t_{0.975,\,n-1}\,\widehat{\operatorname{SE}}(\hat Q)` },
    { kind: 'p', text: md`computed from five sums the event table rolls up in one pass (\`stats/metrics.py\` \`ratio_estimate\`). Both $c_j$ and $f_j$ are ratios of non-negative sums, so the interval is clipped at zero and the clip is stated; the same estimator serves the segmentation metrics and the negative-depth shares of hits and energy, there clipped to $[0, 1]$.` },
    { kind: 'links', id: 'lnk-statistics-calibration', items: [
      { page: 'physics', panel: 'response-b1', label: 'B1 sampling fraction' },
      { page: 'physics', panel: 'response-b2', label: 'B2 response by momentum' },
    ] },
  ],
};

const moments = {
  id: 'sec-statistics-moments',
  title: 'Moments, widths and their intervals',
  blocks: [
    { kind: 'p', text: md`Every spectrum is described by its moments (\`stats/gaussian.py\` \`fit_gaussian\`), not by a least-squares fit to a histogram, which would make every quoted width depend on the bin count and, with the genuine low-side leakage tail of the spectra, describe neither the core nor the tail. For a sample $x_1, \ldots, x_N$,` },
    { kind: 'eq', id: 'eq-moments', tex: md`\hat\mu = \frac{1}{N}\sum_{i=1}^{N} x_i, \qquad s^2 = \frac{1}{N - ${C.DDOF}}\sum_{i=1}^{N}\left(x_i - \hat\mu\right)^2, \qquad s_{\mathrm{pop}} = s\,\sqrt{1 - \frac{1}{N}}` },
    { kind: 'p', text: md`Every quoted width is $s$, with ddof = ${C.DDOF}. The population form understates it by $\sqrt{1 - 1/N}$, 18% at $N = 3$ and 6% at $N = 8$, and is shipped beside it (\`sigma_population\`) only so the reference notebook stays directly comparable. The mean carries the Student-t interval [[cite:student1908]]:` },
    { kind: 'eq', id: 'eq-t-interval', tex: String.raw`\begin{aligned}
&\hat\mu \pm t_{0.975,\,N-1}\,\frac{s}{\sqrt N} \\
&t_{0.975,\,\nu} \approx z + \frac{z^3 + z}{4\nu} + \frac{5z^5 + 16z^3 + 3z}{96\,\nu^2}, \quad z = z_{0.975}, \quad \nu > 30
\end{aligned}` },
    { kind: 'p', text: md`The quantiles are tabulated to 30 degrees of freedom and continued by Fisher's expansion of Student's quantile in powers of $1/\nu$ [[cite:fisher1926]], a Cornish–Fisher series [[cite:cornishfisher1938]], within 0.1% of the true quantile there. The normal approximation cannot stand in at small $N$: $t_{0.975,2} = ${C.T_975_DF2}$ against $z_{0.975} = ${Z}$, so it would understate the half-width by a factor of ${T_OVER_Z} at $N = 3$. The width carries its own asymmetric interval, from the $\chi^2_{N-1}$ distribution of $(N-1)s^2/\sigma^2$, with the Wilson–Hilferty cube-root approximation [[cite:wilsonhilferty1931]] beyond the table:` },
    { kind: 'eq', id: 'eq-chi2-sigma', tex: String.raw`\begin{aligned}
&\left[\, s\,\sqrt{\frac{N-1}{\chi^2_{0.975,\,N-1}}},\ \ s\,\sqrt{\frac{N-1}{\chi^2_{0.025,\,N-1}}}\ \right] \\
&\chi^2_{q,\,\nu} \approx \nu\left(1 - \frac{2}{9\nu} + z_q\sqrt{\frac{2}{9\nu}}\right)^{3}, \quad \nu > 30
\end{aligned}` },
    { kind: 'p', text: md`ddof = ${C.DDOF} makes the *variance* unbiased, not the standard deviation: the square root is concave, so $s$ still runs low by the factor [[cite:gurland1971]]` },
    { kind: 'eq', id: 'eq-c4', tex: String.raw`c_4(N) = \frac{\mathbb E[s]}{\sigma} = \sqrt{\frac{2}{N-1}}\;\frac{\Gamma(N/2)}{\Gamma\left((N-1)/2\right)}` },
    { kind: 'p', text: md`which is 0.886 at $N = 3$ (11.4% low) and 0.940 at $N = 5$. The service ships it (\`sigma_bias_factor\`, with $s/c_4$ beside it) so the residual bias is visible, but keeps quoting $s$. The standard errors of the width and of the relative width $s/\hat\mu$ are` },
    { kind: 'eq', id: 'eq-se-sigma', tex: String.raw`\operatorname{SE}(s) = \frac{s}{\sqrt{2\,(N-1)}}, \qquad \operatorname{SE}\left(\frac{s}{\hat\mu}\right) = \left|\frac{s}{\hat\mu}\right|\sqrt{\frac{1}{2\,(N-1)} + \frac{s^2}{N\,\hat\mu^2}}` },
    { kind: 'p', text: md`the second by the delta method, with both estimates' uncertainties. The resolution panels (\`query/response.py\`) whisker $\sigma/\mu$ differently. A delta-method interval $s/\hat\mu \pm t\,\operatorname{SE}$ is symmetric and goes negative at small $N$, while the sampling distribution of $s$ is bounded below by zero and skewed upward. The whisker is therefore the $\chi^2$ interval of [[eq-chi2-sigma]] divided by $\hat\mu$:` },
    { kind: 'eq', id: 'eq-resolution-whisker', tex: String.raw`\left[\,\frac{\sigma_{\mathrm{lo}}}{\hat\mu},\ \frac{\sigma_{\mathrm{hi}}}{\hat\mu}\,\right], \qquad \hat\mu > 0` },
    { kind: 'p', text: md`with $\sigma_{\mathrm{lo}}, \sigma_{\mathrm{hi}}$ the limits of [[eq-chi2-sigma]]. It is never negative and is right-skewed exactly as the width's own uncertainty is. $\hat\mu$'s uncertainty is neglected: its relative standard error, $(s/\hat\mu)/\sqrt N$, is smaller than the width's, about $1/\sqrt{2N}$, by a factor of order $s/\hat\mu$ at every $N$. The panel says so, and the delta-method SE of [[eq-se-sigma]], which includes it, travels beside the whisker (\`se_delta\`) for the tooltip. Each shower has two resolution series: the calibrated energy $c_j E_{\mathrm{dep}}$, whose spread inside a 1 GeV momentum bin includes the spread of the momentum itself (a momentum uniform on 0–1 GeV alone gives $\sigma/\mu = 0.58$), and the response ratio $E_{\mathrm{dep}}/p$, which divides the momentum out; the momentum spread $\sigma_p/\langle p\rangle$ rides with both.` },
    { kind: 'callout', tone: 'rule', title: 'A whisker is the uncertainty of an aggregate', text: md`A capped whisker on a plotted statistic is reserved for its standard error or a confidence interval built from it. The dispersion of the sample is a different quantity answering a different question: it is drawn as an uncapped shaded band behind the marker, or not at all where the individual observations are drawn. The two differ by $\sqrt N$, cannot be told apart by shape, and so every tooltip names which one it is (CLAUDE.md §2). B1's whisker is the 95% Student-t interval at every $N$ and in every bin, so the mark never changes meaning along the axis; a metric card prints its interval below $N = ${C.MIN_CORE_SAMPLES}$ and its standard error above.` },
    { kind: 'links', id: 'lnk-statistics-moments', items: [
      { page: 'physics', panel: 'response-res', label: 'Energy resolution σ/μ' },
      { page: 'physics', panel: 'response-b1', label: 'B1 whisker and band' },
      { page: 'physics', panel: 'energy', label: 'Energy panel μ and σ table' },
    ] },
  ],
};

const core = {
  id: 'sec-statistics-core',
  title: 'The core refit and the curve’s area',
  blocks: [
    { kind: 'p', text: md`The reconstructed-energy spectra have a genuine low-side tail. The standard calorimetric response measurement separates the Gaussian core from it by re-taking the moments inside $\hat\mu \pm ${C.CORE_SIGMA}\,s$, iterated with the window recomputed from the new moments, until the width changes by less than one part in $10^{7}$ or for at most ${C.CORE_ITERATIONS} iterations. If a window would hold fewer than ${C.MIN_CORE_SAMPLES} events, the iteration stops at the last window that held ${C.MIN_CORE_SAMPLES} or more, and if even the first did not, the refit is not applied (\`core_refit\`). It is still pure moments, with no solver and no initial guess. Cutting the tails removes real variance, and because the window shrinks with the width, the iteration converges to a fixed point below the true width. For a Gaussian truncated at $\pm \tau\sigma$ the variance is $\sigma^2 f(\tau)$, and at the fixed point the window sits at ${C.CORE_SIGMA} *measured* widths:` },
    { kind: 'eq', id: 'eq-core-truncation', tex: md`\begin{aligned} f(\tau) &= 1 - \frac{2\tau\,\Phi'(\tau)}{2\Phi(\tau) - 1}, \qquad \kappa = \sqrt{f(${C.CORE_SIGMA}\,\kappa)} = ${KAPPA} \\ \hat\sigma_{\mathrm{core}} &= \begin{cases} s_{\mathrm{win}}/\kappa & \text{the window cut events} \\ s_{\mathrm{win}} & \text{otherwise} \end{cases} \end{aligned}` },
    { kind: 'p', text: md`Left uncorrected, the refit reports a width 6.3% low; a 40 × 200,000-sample Monte Carlo of the same iteration converges to 0.936856 ± 0.0018 (\`stats/gaussian.py\`). The correction is applied only when the window actually excluded events: applied to an untruncated sample it would inflate the width by 6.77% for a cut that never happened.` },
    { kind: 'p', text: md`**The drawn curve shares the histogram's normalisation.** A \`density=True\` histogram divides by the $n_{\mathrm{hist}}$ events inside its range, so each event carries area $1/n_{\mathrm{hist}}$. The core Gaussian is drawn with area $A$, the events it describes over that same count (\`gaussian.curve_area\`, \`described_events\`):` },
    { kind: 'eq', id: 'eq-curve-area', tex: md`A = \begin{cases} \dfrac{n_{\mathrm{core}}}{C_{\mathrm{w}}\,n_{\mathrm{hist}}} & n_{\mathrm{core}} < N \\ \dfrac{N}{n_{\mathrm{hist}}} & \text{otherwise} \end{cases}, \qquad C_{\mathrm{w}} = 2\,\Phi(${C.CORE_SIGMA}\,\kappa) - 1 = ${COVERAGE}, \qquad y(x) = \frac{A}{\hat\sigma_{\mathrm{core}}}\,\Phi'\left(\frac{x - \hat\mu_{\mathrm{core}}}{\hat\sigma_{\mathrm{core}}}\right)` },
    { kind: 'p', text: md`The coverage is $2\Phi(${C.CORE_SIGMA}\kappa) - 1$ and not $2\Phi(${C.CORE_SIGMA}) - 1$ because the window is ${C.CORE_SIGMA} *truncated* widths while the curve is drawn with the de-biased one. Without a histogram, below $N = ${C.MIN_HISTOGRAM_SAMPLES}$, no core refit runs and the curve keeps unit area. A unit-area curve beside a histogram over-claims: on the XGBoost momentum residuals, where 47 of 62 events lie in the core, it overstated the core's density by 1.27 times: in the recorded payload of that card (\`pred_density_xgb_energy\`), $47/${COVERAGE} = 47.9$ described events over the 61 the histogram holds give $A = 0.786$, and the curve's peak falls from 12.11 to 9.51 (README "Low statistics in plot 4"). The curve's tooltip names its area and the drawer states the rule (\`panel_notes.js\` \`CURVE_AREA_NOTE\`).` },
    { kind: 'p', text: md`**Is the spectrum Gaussian at all?** The interquartile width estimates $\sigma$ for a Gaussian, and the sample is flagged when the two widths disagree:` },
    { kind: 'eq', id: 'eq-robust', tex: md`\hat\sigma_{\mathrm{rob}} = \frac{\operatorname{IQR}}{${C.IQR_TO_SIGMA}}, \qquad \text{non-Gaussian} \iff \frac{\left|\hat\sigma_{\mathrm{rob}} - s\right|}{s} > ${C.NON_GAUSSIAN_TOLERANCE}, \qquad N \ge ${C.MIN_ROBUST_SAMPLES}` },
    { kind: 'p', text: md`The quartiles are linear interpolations between order statistics, and on a handful of points they interpolate between individual events, so the flag would fire or stay silent at random. Below $N = ${C.MIN_ROBUST_SAMPLES}$ the verdict is therefore *untestable* (\`non_gaussian = None\`), never a reassuring "Gaussian".` },
    { kind: 'links', id: 'lnk-statistics-core', items: [
      { page: 'physics', panel: 'energy', label: 'Energy vs. separation D' },
      { page: 'models', panel: 'pred-residuals', label: 'Prediction residuals' },
    ] },
  ],
};

const histograms = {
  id: 'sec-statistics-histograms',
  title: 'Histograms and density estimates',
  blocks: [
    { kind: 'p', text: md`A density histogram of $n_{\mathrm{in}}$ in-range values on bins of width $\delta$ reports, in bin $b$ holding $n_b$ of them,` },
    { kind: 'eq', id: 'eq-histogram', tex: md`\begin{aligned}
\hat p_b &= \frac{n_b}{n_{\mathrm{in}}\,\delta} \\
B_{\mathrm{Rice}} &= \operatorname{clip}\left(\left\lceil 2\,N_{\min}^{1/3}\right\rceil,\ ${C.MIN_BINS},\ ${C.DEFAULT_BINS}\right) \\
\delta_{\mathrm{FD}} &= \max_j\, 2\,\operatorname{IQR}_j\,N_j^{-1/3}, \qquad B_{\mathrm{FD}} = \operatorname{clip}\left(\left\lceil \frac{x_{\mathrm{hi}} - x_{\mathrm{lo}}}{\delta_{\mathrm{FD}}}\right\rceil,\ ${C.MIN_BINS},\ ${C.DEFAULT_BINS}\right)
\end{aligned}` },
    { kind: 'p', text: md`Once the bins are finer than the spacing between events, each occupied bin holds one event and reports $1/(n_{\mathrm{in}}\,\delta)$: a comb of tall spikes whose height is set by the binning, not by the distribution. With the notebook's ${C.DEFAULT_BINS} bins over an 18 GeV range that is 1.7 GeV⁻¹ at $N = 4$ (\`stats/histogram.py\`). No histogram is therefore drawn below $N = ${C.MIN_HISTOGRAM_SAMPLES}$; the individual events are drawn instead, in a tinted, captioned band whose tooltips say that their height is a drawing offset, not a density. Above the floor the bin count follows the Rice rule, driven by the smallest slice whose histogram is drawn, so every slice shares one binning and can be compared bin by bin. The prediction residuals of the Models page are the recorded exception: their heavy tails stretch the 1st–99th display range, and Rice's count then put the whole core into one bin — 8 bins of 0.25 against $\sigma_{\mathrm{core}} = 0.033$ on the recorded relative XGBoost momentum residuals, (pred − true)/true, now 87 bins of 0.023 (README) — so they take the widest Freedman–Diaconis width of the drawn showers [[cite:freedman1981]], whose interquartile range follows the core, and fall back to Rice when no shower has one. The payload names the rule and the width.` },
    { kind: 'p', text: md`A height on the density axis is not a probability: it carries GeV⁻¹ and exceeds 1 wherever the distribution is narrower than about 0.4 GeV, and it says nothing about how many events stand behind it (\`panel_notes.js\` \`DENSITY_EXPLAINER\`). Where a distribution is shown as a smooth curve estimated from the values themselves (the feature explorer's histograms, D4), it is a Gaussian kernel density estimate with Silverman's bandwidth [[cite:silverman1986]] [[cite:wand1995]] (\`stats/kde.py\`):` },
    { kind: 'eq', id: 'eq-silverman', tex: md`h = ${C.SILVERMAN_FACTOR}\,\min\left(s,\ \frac{\operatorname{IQR}}{${C.IQR_TO_SIGMA}}\right) N^{-1/5}, \qquad \hat p(x) = \frac{1}{N_{\mathrm{tot}}\,h}\sum_{i=1}^{N}\Phi'\left(\frac{x - x_i}{h}\right)` },
    { kind: 'p', text: md`It is drawn from $N = ${C.MIN_KDE_SAMPLES}$, the curve floor, scaled to expected counts per histogram bin. The sum is evaluated by linear binning onto a grid about $h/4$ apart (never coarser than $h/2$), with the kernel truncated at ${C.KDE_TRUNCATION_H} $h$, and the normaliser $N_{\mathrm{tot}}$ counts every finite value, so mass outside the drawn window stays missing rather than being renormalised away. A feature quantised on the lattice, a depth in whole layers for instance, takes only a few distinct values; a bandwidth below half that quantum would draw one spike per lattice value, and the curve is withheld with the reason stated. This bandwidth is fitted to the sample, which is why it takes the curve floor, unlike the fixed-width spatial kernels of [[sec-discretisation]].` },
    { kind: 'links', id: 'lnk-statistics-histograms', items: [
      { page: 'physics', panel: 'energy', label: 'Energy histograms and event strips' },
      { page: 'physics', panel: 'distribution', label: 'C4 (counts only, no curve)' },
      { page: 'models', panel: 'feat-hist', label: 'Feature histogram' },
    ] },
  ],
};

const errors = {
  id: 'sec-statistics-errors',
  title: 'Error metrics',
  blocks: [
    { kind: 'p', text: md`The momentum-bin performance card (E2) quotes the root-mean-square residual $\mathrm{RMSE} = \sqrt{n^{-1}\sum_i r_i^2}$ of each bin with an interval chosen by the bin's size (\`stats/rmse.py\`):` },
    { kind: 'eq', id: 'eq-rmse', tex: md`\mathrm{RMSE} \in \begin{cases} \left[\mathrm{RMSE}\sqrt{\dfrac{n}{\chi^2_{0.975,\,n}}},\ \mathrm{RMSE}\sqrt{\dfrac{n}{\chi^2_{0.025,\,n}}}\right] & ${C.MIN_CHI2_N} \le n < ${C.MIN_BOOTSTRAP_N} \\ \left[\,Q_{0.025},\ Q_{0.975}\,\right]\ \text{of}\ \left\{\mathrm{RMSE}^{*}_{k}\right\}_{k=1}^{${C.BOOTSTRAP_REPLICATES}} & n \ge ${C.MIN_BOOTSTRAP_N} \end{cases}` },
    { kind: 'p', text: md`Below $N = ${C.MIN_BOOTSTRAP_N}$ the interval assumes normal residuals centred on zero. Then $n\,\mathrm{RMSE}^2/\sigma^2$ is $\chi^2$ with $n$ degrees of freedom — $n$, not $n - 1$, because the RMSE is taken about zero, not about the sample mean — and the interval is exact; it is approximate otherwise, and with a bias, and its label says so. From $N = ${C.MIN_BOOTSTRAP_N}$ it is the percentile bootstrap [[cite:efron1979]] [[cite:davison1997]] with $B = ${C.BOOTSTRAP_REPLICATES}$ replicates, each series seeded from its own coordinates (seed ${C.BOOTSTRAP_SEED}, then frame, shower, bin and quantity), so an interval never depends on which other series a request computed. It replaces the square root of the Student-t interval of the mean squared residual, whose lower end collapses to zero at $N \le 8$ and whose coverage on squared residuals is poor; the Physics page's metric cards still use that older estimator (\`metrics.residual_summary\`). The mean absolute error and the bias take the Student-t interval of their means, the MAE's clipped at zero and saying so. A value is reported from $N = 1$ without an interval; a bin of one shower is drawn as a dot, an observation, never as a bar, and a point without an interval is faded, its tooltip naming the floor of its own quantity.` },
    { kind: 'links', id: 'lnk-statistics-errors', items: [
      { page: 'models', panel: 'perf-bins', label: 'E2 performance by momentum bin' },
      { page: 'models', panel: 'pred-residuals', label: 'Prediction residuals' },
    ] },
  ],
};

const proportions = {
  id: 'sec-statistics-proportions',
  title: 'Medians and proportions',
  blocks: [
    { kind: 'p', text: md`The median relative error is whiskered without a distributional assumption (\`stats/median.py\`). The number of values below the true median is $\operatorname{Bin}(n, 1/2)$, so with $F_n$ its distribution function` },
    { kind: 'eq', id: 'eq-median-order', tex: String.raw`\left[\,x_{(j)},\ x_{(n+1-j)}\,\right], \qquad j = \max\left\{\, j : F_n(j-1) \le 0.025 \,\right\}, \qquad \text{coverage } 1 - 2F_n(j-1) \ge 0.95` },
    { kind: 'p', text: md`exists from $N = ${C.MIN_ORDER_N}$, where $[x_{(1)}, x_{(6)}]$ covers 96.9%; at $N = 5$ even the full range covers less than 95%, and no interval is quoted. From $N = ${C.MIN_BOOTSTRAP_N}$ the whisker is the seeded percentile bootstrap, with the order-statistic interval kept beside it as a cross-check; below that the bootstrap distribution of a median sits on a few order statistics and under-covers. Each replicate's median is drawn from its exact sampling distribution instead of by resampling: the $m$-th order statistic of $n$ uniforms is $\operatorname{Beta}(m, n - m + 1)$, and resampling with replacement picks $x_{(\lceil nU\rceil)}$, the same distribution at $O(B)$ cost.` },
    { kind: 'p', text: md`A proportion $\hat p = k/n$ of independent units takes the Wilson score interval [[cite:wilson1927]] (\`metrics.wilson_interval\`):` },
    { kind: 'eq', id: 'eq-wilson', tex: String.raw`\frac{\hat p + \dfrac{z^2}{2n}}{1 + \dfrac{z^2}{n}} \ \pm\ \frac{z}{1 + \dfrac{z^2}{n}}\sqrt{\frac{\hat p\,(1 - \hat p)}{n} + \frac{z^2}{4n^2}}, \qquad z = z_{0.975}` },
    { kind: 'p', text: md`clipped to $[0, 1]$. The Wald interval $\hat p \pm z\sqrt{\hat p(1-\hat p)/n}$ collapses to a point at $k = 0$ or $k = n$ and leaves $[0, 1]$ at small $n$, which is where a bin of a few events sits. Wilson serves the primary-tag rate (the share of events without a primary-tagged hit, per momentum bin) and the share of units holding a hit behind the shower's entry plane. The unit must be independent: events always, showers only where each event contributes one, since the two showers of a two-shower event are not independent Bernoulli trials.` },
    { kind: 'links', id: 'lnk-statistics-proportions', items: [
      { page: 'models', panel: 'prim-rate', label: 'Primary-tag rate' },
      { page: 'models', panel: 'perf-bins', label: 'E2 median relative error' },
    ] },
  ],
};

const correlation = {
  id: 'sec-statistics-correlation',
  title: 'Correlation and clustered units',
  blocks: [
    { kind: 'p', text: md`Where every pair is one event, Pearson's $r$ is quoted from $N = ${C.MIN_R_EVENTS}$ events and its interval from $N = ${C.MIN_FISHER_N}$, on Fisher's $\zeta = \operatorname{atanh} r$ [[cite:fisher1921]]:` },
    { kind: 'eq', id: 'eq-fisher', tex: String.raw`\zeta = \operatorname{atanh} r, \qquad r \in \left[\,\tanh\left(\zeta - \frac{z_{0.975}}{\sqrt{N-3}}\right),\ \tanh\left(\zeta + \frac{z_{0.975}}{\sqrt{N-3}}\right)\right]` },
    { kind: 'p', text: md`The feature explorer fades every cell whose interval contains zero. A hit-level matrix (the Physics correlation card) is different: over millions of hits the pairs are not independent, because the incident momentum and angles take one value per shower, repeated on every hit, and the hits of one shower share its development. Fisher's interval with $N$ = hits would quote a standard error of 0.0003 on everything (\`query/correlations.py\`). The scan instead returns the count, $\sum v_i$ and $\sum v_i v_j$ per group of events, $G = \min(${C.MAX_GROUPS}, N_{\mathrm{events}})$ groups by event number modulo $G$ (one event per group up to ${C.MAX_GROUPS}), and leaves one group out at a time [[cite:quenouille1956]] [[cite:tukey1958]]:` },
    { kind: 'eq', id: 'eq-jackknife', tex: String.raw`\operatorname{SE}_J^2 = \frac{G-1}{G}\sum_{g=1}^{G}\left(\zeta_{(g)} - \bar\zeta_{(\cdot)}\right)^2, \qquad r \in \tanh\left(\zeta \pm t_{0.975,\,G-1}\operatorname{SE}_J\right), \qquad n_{\mathrm{eff}} = 3 + \frac{1}{\operatorname{SE}_J^2}` },
    { kind: 'p', text: md`from ${C.MIN_JACKKNIFE_GROUPS} groups (\`stats/jackknife.py\`). $n_{\mathrm{eff}}$ is the number of independent pairs the interval is worth, printed beside the naive count. Pairs of two per-shower values are aggregated from the event table, once weighted by each shower's hits, which reproduces the hit-level value exactly, and once with each shower counting once. The longitudinal and radial profiles face the same clustering: a profile is a per-shower fraction $f_e(b)$ in bin $b$, and the two showers of an event share its geometry. Their mean $\bar f(b)$ carries a cluster-robust standard error with the event as the cluster (\`stats/profile.py\`):` },
    { kind: 'eq', id: 'eq-profile-se', tex: String.raw`\operatorname{SE}^2\left(\bar f(b)\right) = \frac{G}{G-1}\;\frac{\sum_e F_e(b)^2 - 2\,\bar f(b)\sum_e M_e\,F_e(b) + \bar f(b)^2\sum_e M_e^2}{N^2}` },
    { kind: 'p', text: md`with $F_e(b)$ the summed fraction of event $e$'s $M_e$ showers, $N$ showers in $G$ events; it reduces to $s^2/N$ when every event holds one shower. The profile draws two marks: the sample SD of the per-shower fractions as an uncapped band, and $\bar f(b) \pm t_{0.975,G-1}\operatorname{SE}$ as the capped envelope of the mean.` },
    { kind: 'links', id: 'lnk-statistics-correlation', items: [
      { page: 'physics', panel: 'correlation', label: 'Hit-level correlation matrix' },
      { page: 'models', panel: 'feat-corr', label: 'Feature correlations' },
      { page: 'physics', panel: 'profile-w', label: 'Longitudinal profile' },
    ] },
  ],
};

const circular = {
  id: 'sec-statistics-circular',
  title: 'Circular statistics',
  blocks: [
    { kind: 'p', text: md`An azimuth wraps, so its arithmetic mean is meaningless: two showers at +179° and −179° average to 0°, the opposite of where both point. Every summary of an angle goes through the resultant of its unit vectors [[cite:mardia2000]] (\`stats/circular.py\`):` },
    { kind: 'eq', id: 'eq-resultant', tex: String.raw`\begin{aligned} \bar R &= \frac{\sqrt{C^2 + S^2}}{N}, \quad \bar\varphi = \operatorname{atan2}(S, C), \qquad C = \sum_i\cos\varphi_i, \ S = \sum_i\sin\varphi_i \\ \sigma_\circ &= \sqrt{-2\ln\bar R}, \quad P_{\mathrm{Ray}} \approx \exp\left(-N\bar R^2\right) \end{aligned}` },
    { kind: 'p', text: md`A mean direction is quoted only beside $\bar R$, and is faded as uninformative when the Rayleigh test [[cite:rayleigh1880]] gives $P_{\mathrm{Ray}} > ${C.UNIFORM_P}$. The incident azimuth of shower A is near-uniform over the whole production file ([[sec-frames-absolute]]), which is why the Absolute frame draws no average trajectory over the whole face: it draws each event's trajectory up to ${C.MAX_TRAJECTORY_EVENTS} events and states $\bar R$ above that. The two sanctioned exceptions, the D-frame's axis and the windowed axis of a zoomed depth panel, are licensed by their own measured $\bar R$ and lean ([[sec-frames]]). Residuals of an angle are wrapped onto $(-\pi, \pi]$,` },
    { kind: 'eq', id: 'eq-wrap', tex: String.raw`w(x) = x - 2\pi\left\lceil \frac{x - \pi}{2\pi}\right\rceil \in (-\pi, \pi]` },
    { kind: 'p', text: md`so a disagreement across the ±π seam counts the short way round, never as about $2\pi$; the MAE and RMSE of a predicted $\varphi$ are taken on wrapped residuals, and no linear R² is quoted for an azimuth. The surrogate tree of the XGBoost angle model (E4) is judged per output, and its $\varphi$ on a circular analogue of R² (\`modelruns/analysis.py\` \`circular_fidelity\`):` },
    { kind: 'eq', id: 'eq-circular-r2', tex: String.raw`R^2_\circ = 1 - \frac{\sum_i\left(1 - \cos\Delta_i\right)}{\sum_i\left(1 - \cos\left(\varphi_i - \bar\varphi\right)\right)}, \qquad \Delta_i = w\left(\tilde\varphi_i - \varphi_i\right)` },
    { kind: 'p', text: md`with $\varphi_i$ the booster's prediction, $\tilde\varphi_i$ the tree's and $\bar\varphi$ the circular mean of the booster's; it is 1 when the tree reproduces every direction and 0 when it does no better than the one mean direction. The wrapped MAE, the mean $|\Delta_i|$, stands beside it, the linear R² stays as notebook parity, and the low-fidelity warning fires per output below ${C.LOW_FIDELITY_R2}. The two outputs are never averaged: on electrons the linear R² of $\varphi$ is 0.978 and of $\theta$ 0.004, and their average, 0.49, would hide both. Two azimuths are correlated by the Jammalamadaka–SenGupta coefficient [[cite:jammalamadaka2001]]:` },
    { kind: 'eq', id: 'eq-rc', tex: String.raw`r_c = \frac{\sum_i \sin\left(\alpha_i - \bar\alpha\right)\sin\left(\beta_i - \bar\beta\right)}{\sqrt{\sum_i \sin^2\left(\alpha_i - \bar\alpha\right)\,\sum_i \sin^2\left(\beta_i - \bar\beta\right)}}` },
    { kind: 'p', text: md`which lies in $[-1, 1]$, is unchanged by rotating either angle (and so by where the ±π cut falls) and changes sign when one is reflected; a Pearson $r$ of two azimuths has neither property. A linear variable $x$ is correlated with an azimuth by Mardia's circular–linear coefficient [[cite:mardia1976]], the multiple correlation of $x$ on $(\cos\varphi, \sin\varphi)$:` },
    { kind: 'eq', id: 'eq-mardia', tex: String.raw`R_{\mathrm M}^2 = \frac{r_{xc}^2 + r_{xs}^2 - 2\,r_{xc}\,r_{xs}\,r_{cs}}{1 - r_{cs}^2}, \qquad \mathbb E\left[R_{\mathrm M}^2 \mid \text{no association}\right] = \frac{2}{N-1}` },
    { kind: 'p', text: md`with $r_{xc} = r(x, \cos\varphi)$, $r_{xs} = r(x, \sin\varphi)$ and $r_{cs} = r(\cos\varphi, \sin\varphi)$. An intercept and two slopes fit any three directions exactly, so $R_{\mathrm M} = 1$ whatever the data there: $R_{\mathrm M}$ is quoted only from ${C.MIN_MARDIA_AZIMUTHS} *distinct* azimuths, its jackknife SE only from ${C.MIN_MARDIA_GROUPS} groups, and the null expectation of $R_{\mathrm M}^2$ is printed beside it (\`stats/jackknife.py\`). The aggregate's \`avg_phi\` is the producer's arithmetic mean of the hits' $\varphi$. It is offered for parity with the producer's file and the XGBoost inputs only, never drawn as a direction, and its correlation cells are hatched and carry Mardia's $R_{\mathrm M}$, or $r_c$ with another azimuth, beside the notebook's linear $r$. The hit kinds add \`avg_phi_circ\`, $\operatorname{atan2}(\sum\sin\varphi, \sum\cos\varphi)$, which only per-hit sums can give.` },
    { kind: 'links', id: 'lnk-statistics-circular', items: [
      { page: 'models', panel: 'xgb-surrogate', label: 'E4 surrogate tree' },
      { page: 'models', panel: 'feat-corr', label: 'Hatched azimuth cells' },
      { page: 'physics', panel: 'correlation', label: 'Mardia’s R of φ' },
    ] },
  ],
};

const gates = {
  id: 'sec-statistics-gates',
  title: 'The low-N gates',
  blocks: [
    { kind: 'p', text: md`Reported numbers and drawn marks are gated separately, because a table cell makes no claim about shape and a smooth curve does. A slice of fourteen events once reported em-dashes for a mean and a width that were perfectly computable, because the floor of its *histogram* had been applied to its *moments*. [[tab-low-n]] lists every floor, each justified on its own terms; none is a proxy for another, and [[tab-intervals]] collects the estimators above with their gates.` },
    { kind: 'table', id: 'tab-low-n', caption: md`The low-N ladder: each threshold, what it gates, and why. Numbers are reported from the first rung; marks appear rung by rung.`,
      head: ['Threshold', 'Gates', 'Why'],
      rows: [
        [md`$N \ge ${C.MIN_MOMENT_SAMPLES}$`, md`$\hat\mu$, $s$, $s/\hat\mu$ as numbers, with their intervals; the RMSE's $\chi^2$ interval`, md`one pairwise difference, one degree of freedom: weak, not undefined, and labelled "1 d.o.f."`],
        [md`$N \ge ${C.MIN_R_EVENTS}$`, md`Pearson $r$`, md`at two points $r = \pm 1$ whatever the data`],
        [md`$N \ge ${C.MIN_FISHER_N}$`, md`Fisher-$\zeta$ interval; ${C.MIN_JACKKNIFE_GROUPS} groups for the jackknife`, md`$\operatorname{SE}(\zeta) = 1/\sqrt{N-3}$ needs $N > 3$`],
        [md`$N \ge ${C.MIN_ORDER_N}$`, md`order-statistic interval of a median`, md`below it even $[x_{(1)}, x_{(N)}]$ covers less than 95%`],
        [md`$N \ge ${C.MIN_CURVE_SAMPLES}$`, md`parametric density curve; KDE; Mardia's $R_{\mathrm M}$ (distinct azimuths)`, md`a curve asserts a shape; at $N = 8$ the width is known to $[0.66\,s, 2.04\,s]$`],
        [md`$N \ge ${C.MIN_HISTOGRAM_SAMPLES}$`, md`density histogram; iterated ±${C.CORE_SIGMA}σ core refit; the curve's histogram normalisation; evidence for the energy panel's, B3's and E2's display range`, md`the spike comb of [[eq-histogram]]; the refit needs a populated tail to cut`],
        [md`$N \ge ${C.MIN_ROBUST_SAMPLES}$`, md`robust width and Gaussian verdict; bootstrap intervals; evidence for a display range on the response cards (else provisional)`, md`percentiles of a handful of points interpolate between events`],
        [md`$N \le ${C.MAX_TRAJECTORY_EVENTS}$`, md`individual trajectories in the Absolute frame`, md`more lines than a reader can follow; $\bar R$ is stated instead`],
      ],
      note: md`Constants: \`stats/gaussian.py\`, \`stats/histogram.py\`, \`stats/median.py\`, \`stats/rmse.py\`, \`stats/jackknife.py\`, \`stats/kde.py\`, \`grid/frame.py\` \`PROVISIONAL_N\`, \`query/summary.py\` \`MAX_TRAJECTORY_EVENTS\`. The fixed-width spatial display kernels of [[sec-discretisation]] are not density estimates of a sample and run at any $N$.` },
    { kind: 'p', text: md`Below the core floor a width never travels alone: it carries its standard error ([[eq-se-sigma]]), its asymmetric $\chi^2$ interval ([[eq-chi2-sigma]]) and $c_4(N)$ ([[eq-c4]]). At $N = 3$ the true $\sigma$ lies in $[0.52\,s,\ 6.29\,s]$; we checked this against the code's own quantiles, $\chi^2_{0.975,2} = 7.378$ and $\chi^2_{0.025,2} = 0.0506$ in \`gaussian.chi2_quantile\`, which give 0.521 and 6.287. A bare width printed to three decimals is the misleading presentation there, not the honest one.` },
    { kind: 'p', text: md`**Display ranges follow robust evidence.** An axis range, a colour bound or a histogram range is computed only from the series that carry statistical weight: $N \ge ${C.MIN_ROBUST_SAMPLES}$ on the response cards, the series drawn as histograms ($N \ge ${C.MIN_HISTOGRAM_SAMPLES}$) on the energy panel and the B3 sub-plots, and $N \ge ${C.MIN_CORE_SAMPLES}$ on E2. A fitted curve peaks at $1/(\sigma\sqrt{2\pi})$, so an under-powered slice with a small, poorly determined width would set the scale for every well-measured one: two 10-event slices once peaked at 2.52 and 2.09 GeV⁻¹ against a robust maximum of 0.38, which would have compressed four well-measured slices into the bottom 15% of the canvas (CLAUDE.md §2). Weak series adapt to the established range; one that overflows it is clipped with a caret at the edge, its true value in the tooltip and a count in the drawer. Where nothing reaches the floor, the range is taken from what exists and labelled **provisional** on the axis itself, the label every co-registered panel also carries below $N = ${C.PROVISIONAL_N}$ events.` },
    { kind: 'table', id: 'tab-intervals', caption: md`Every interval the dashboard draws: the quantity, its estimator, its 95% interval, the sample size it needs, and the module that computes it.`,
      head: ['Quantity', 'Estimator', 'Interval', 'Gate', 'Module'],
      rows: [
        [md`mean`, md`$\hat\mu$`, md`Student-t, [[eq-t-interval]]`, md`$N \ge ${C.MIN_MOMENT_SAMPLES}$`, md`\`stats/gaussian.py\``],
        [md`width`, md`$s$, ddof ${C.DDOF}`, md`$\chi^2_{N-1}$, [[eq-chi2-sigma]]; SE and $c_4$`, md`$N \ge ${C.MIN_MOMENT_SAMPLES}$`, md`\`stats/gaussian.py\``],
        [md`resolution $\sigma/\mu$`, md`$s/\hat\mu$`, md`$\chi^2$ interval of $\sigma$ over $\hat\mu$, [[eq-resolution-whisker]]; delta SE beside`, md`$N \ge ${C.MIN_MOMENT_SAMPLES}$`, md`\`query/response.py\``],
        [md`core width`, md`±${C.CORE_SIGMA}σ refit, $\div\kappa$ if cut`, md`— (estimator stated)`, md`$N \ge ${C.MIN_CORE_SAMPLES}$`, md`\`stats/gaussian.py\``],
        [md`calibration, ratios of sums`, md`$\sum y/\sum x$`, md`linearised cluster t, clipped, [[eq-ratio-se]]`, md`$N \ge ${C.MIN_MOMENT_SAMPLES}$ events`, md`\`stats/metrics.py\``],
        [md`RMSE (E2)`, md`$\sqrt{\overline{r^2}}$`, md`$\chi^2_n$, then bootstrap, [[eq-rmse]]`, md`${C.MIN_CHI2_N} / ${C.MIN_BOOTSTRAP_N}`, md`\`stats/rmse.py\``],
        [md`MAE, bias`, md`mean`, md`Student-t, MAE clipped at 0`, md`$N \ge ${C.MIN_MOMENT_SAMPLES}$`, md`\`stats/metrics.py\``],
        [md`median`, md`sample median`, md`order statistics, then bootstrap, [[eq-median-order]]`, md`${C.MIN_ORDER_N} / ${C.MIN_BOOTSTRAP_N}`, md`\`stats/median.py\``],
        [md`proportion`, md`$k/n$`, md`Wilson, [[eq-wilson]]`, md`$n \ge 1$`, md`\`stats/metrics.py\``],
        [md`$r$ over events`, md`Pearson`, md`Fisher $\zeta$, [[eq-fisher]]`, md`${C.MIN_R_EVENTS} / ${C.MIN_FISHER_N}`, md`\`stats/metrics.py\``],
        [md`$r$ over hits`, md`Pearson from grouped sums`, md`jackknife on $\zeta$, $t_{G-1}$, [[eq-jackknife]]`, md`${C.MIN_R_EVENTS} events, ${C.MIN_JACKKNIFE_GROUPS} groups`, md`\`stats/jackknife.py\``],
        [md`profile mean`, md`mean fraction per bin`, md`cluster-robust t envelope, [[eq-profile-se]]`, md`$G \ge 2$; weak below ${C.PROFILE_PROVISIONAL_N}`, md`\`stats/profile.py\``],
        [md`mean direction`, md`$\operatorname{atan2}(S, C)$`, md`$\bar R$ and $P_{\mathrm{Ray}}$, [[eq-resultant]]`, md`$N \ge ${C.MIN_MOMENT_SAMPLES}$ for $P_{\mathrm{Ray}}$`, md`\`stats/circular.py\``],
        [md`Mardia's $R_{\mathrm M}$`, md`multiple $r$ on $(\cos, \sin)$`, md`grouped jackknife SE, [[eq-mardia]]`, md`${C.MIN_MARDIA_AZIMUTHS} azimuths, ${C.MIN_MARDIA_GROUPS} groups`, md`\`stats/jackknife.py\``],
      ] },
    { kind: 'links', id: 'lnk-statistics-gates', items: [
      { page: 'physics', panel: 'energy', label: 'Energy panel event strips and provisional range' },
      { page: 'physics', panel: 'response-b3', label: 'B3 response by momentum' },
      { page: 'physics', panel: 'statistics', label: 'Descriptive statistics' },
    ] },
  ],
};

export default {
  id: 'sec-statistics',
  title: 'Estimators, uncertainty and epistemic gates',
  blocks: [
    { kind: 'p', text: md`Every number the dashboard prints about a sample carries its uncertainty, and every mark it draws is gated by what the sample can support. This section states the estimators in the order a reader meets them, from the calibration that puts deposits on the momentum scale to the circular statistics of the azimuth, and ends with the ladder of sample-size gates that decides which of them are quoted and which marks are drawn. Two rules run through all of it. The sampling unit is the event, never the hit, because the hits of one shower share its development. And a statistic quoted at small $N$ is quoted with the interval that is honest at that $N$ — Student-t, $\chi^2$, order statistics or Wilson — rather than a normal approximation that is only valid at large $N$.` },
  ],
  sections: [calibration, moments, core, histograms, errors, proportions, correlation, circular, gates],
};
