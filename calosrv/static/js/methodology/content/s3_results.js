/* §3 Results: a systematic perceptual and architectural audit of every
 * visualisation on the Physics page (/) and the Models page (/models).
 *
 * The section reports no dataset's findings. For each card it states what the
 * card encodes, why that mark, scale and aspect, which distortion the encoding
 * prevents, which statistical gates apply, and where the reader sees it live.
 * Measured figures appear only as the rationale of a design rule, with their
 * source. The mathematics lives in §2; this section cites its equations.
 *
 * Content model and rules: index.js.
 */

import { C } from '../constants.js';

/** A code span for the inline syntax, usable inside String.raw templates. */
const k = (name) => '\u0060' + name + '\u0060';
/** An integer with thousands separators, as the prose writes it. */
const n = (value) => Number(value).toLocaleString('en-US');
/** A share as a whole percentage. */
const pc = (share) => `${Math.round(share * 100)}%`;

const LADDER = `${C.MIN_MOMENT_SAMPLES} / ${C.MIN_CURVE_SAMPLES} / ${C.MIN_HISTOGRAM_SAMPLES} / ${C.MIN_ROBUST_SAMPLES}`;
const RATIO = `${Math.round(C.BINARY_FRACTION_0 * 100)} : ${Math.round(C.BINARY_FRACTION_1 * 100)}`;

/* ------------------------------------------------------------ the lead -- */

const TAXONOMY = {
  kind: 'table',
  id: 'tab-taxonomy',
  caption: String.raw`Every card of the Physics and Models pages: what it draws, how it encodes uncertainty, which sample-size gates govern its marks, and its colour. Gates are numbers of events, showers or rows as each card counts them; "ladder" is the low-$N$ ladder ${LADDER} of [[tab-low-n]]. Labels are the cards' identifiers in the dashboard's design; the spatial cards and plot 4 keep the names of the 2 × 2 diagnostic.`,
  head: ['Card', 'Label', 'Page', 'Mark', 'Uncertainty', 'Gate', 'Colour'],
  rows: [
    [k('xy'), '2 × 2, top-left', 'Physics', 'Entry-slab raster; centroid markers; separation vector $D$ (Absolute) or entry anchors (D-frame)', 'None on a raster; counts beyond the floor and outside the window disclosed; anchor SD bar (D-frame)', `Window provisional below ${C.PROVISIONAL_N}; kernel switch at ${C.GAUSSIAN_KERNEL_BELOW_N}`, 'Sequential log (Viridis default); folded PuOr for Shap-CAM'],
    [k('yz'), '2 × 2, top-right', 'Physics', 'Depth raster; trajectories, centre of deposited energy, windowed or D-frame ensemble axis', 'Axis: uncapped SD wedge and Student-t envelope, two marks', `Trajectories at ≤ ${C.MAX_TRAJECTORY_EVENTS} events; ladder for the axes`, 'As `xy`'],
    [k('xz'), '2 × 2, bottom-left', 'Physics', 'Depth raster, sharing the YZ colour scale', 'As `yz`', 'As `yz`', 'As `xy`'],
    [k('energy'), 'plot 4', 'Physics', 'Density histogram and core Gaussian per $D$ slice; event strip; isolated-reference rules and bands', 'Capped t whisker on the mean; uncapped SD bar; σ with SE, χ² interval and $c_4$ below the core floor', 'Ladder', 'Slice: ordered sequential stops; shower: line style'],
    ['Event Inspector', 'A1 / C2', 'Physics', '3 × 3 rasters: one shower of one event in three frames', 'None: one shower, every mark its own', `Shared window ≥ ${C.EVENT_WINDOW_MIN_HALF_MM} mm half-width`, 'Sequential, one ramp for nine panels'],
    ['Compare frames', 'A2 / C3', 'Physics', '3 × 3 rasters: three frames’ ensemble responses side by side', 'As the 2 × 2', 'As the 2 × 2', 'As the 2 × 2'],
    [k('profile-w'), 'C7', 'Physics', 'Per-shower mean step line; pooled ratio of sums dashed', 'Uncapped SD band; capped Student-t envelope, cluster-robust', `Band and envelope from ${C.MIN_MOMENT_SAMPLES}; provisional below ${C.PROFILE_PROVISIONAL_N}`, 'Accent'],
    [k('profile-r'), 'C7', 'Physics', `As \`profile-w\`, in ${C.PROFILE_R_BIN_MM} mm bins of ρ`, 'As `profile-w`', 'As `profile-w`', 'Accent'],
    [k('response-b1'), 'B1', 'Physics', 'Density histogram of the per-event sampling fraction; mean and 1/c verticals', 'Student-t (mean), cluster ratio interval (1/c); SD bar in the strip', `Histogram from ${C.MIN_HISTOGRAM_SAMPLES}`, 'Shower colours'],
    [k('response-b2'), 'B2', 'Physics', 'Mean per momentum bin; SD box; 1/c rule', 'Capped t whisker; uncapped SD box', `Weak and faded below ${C.MIN_ROBUST_SAMPLES}; one event an open circle`, 'Shower colours'],
    [k('response-res'), 'B3, σ/μ', 'Physics', 'σ/μ per momentum bin, two quantities', 'χ² whisker of σ over $\\hat\\mu$', `1 d.o.f. at ${C.MIN_MOMENT_SAMPLES}; weak below ${C.MIN_ROBUST_SAMPLES}`, 'Shower colours'],
    [k('response-b3'), 'B3', 'Physics', 'Small multiples by momentum, each on its own energy axis', 'As plot 4; momentum marker with t envelope', 'Ladder, per sub-plot', 'Shower colours; prediction dashed'],
    [k('distribution'), 'C4', 'Physics', 'Step outlines, one per momentum bin', 'Exact counts; $\\bar R$ and Rayleigh $p$ for φ', `Dashed below ${C.SHAPE_FLOOR_SHOWERS} showers`, 'Ordered sequential stops ≥ 3:1'],
    [k('correlation'), 'C8', 'Physics', 'Lower-triangle Pearson matrix', 'Grouped-jackknife Fisher-z interval (tooltip)', `$r$ from ${C.MIN_R_EVENTS}, interval from ${C.MIN_JACKKNIFE_GROUPS} groups; Mardia from ${C.MIN_MARDIA_AZIMUTHS} azimuths`, 'PuOr, linear on [−1, +1]; hatch for circular'],
    [k('statistics'), 'C1, C9', 'Physics', 'Table: unweighted and energy-weighted describe(); negative-depth counts', 'No SE of a hit mean; Wilson and cluster ratio intervals (C9)', 'Flag on rows from few hits', 'None'],
    [k('perf-bins'), 'E2', 'Models', 'Bars from zero at fixed offsets per momentum bin; a dot for one shower', 'RMSE: χ², then bootstrap; MAE and bias: t; median: order statistic, then bootstrap', `Interval floors per quantity; scale from ${C.MIN_CORE_SAMPLES}`, 'ColorBrewer qualitative, by input frame'],
    [k('pred-truth'), 'Prediction vs truth', 'Models', 'Square 1:1 count raster with the identity line', 'None (counts); pairs drawn below the floor', `Raster from ${C.MIN_HISTOGRAM_SAMPLES} pairs`, 'Sequential log count from its 3:1 colour'],
    [k('pred-residuals'), 'Residuals', 'Models', 'Freedman–Diaconis density histogram; core Gaussian; zero rule', 'Student-t hairlines; SD bar in the strip; circular statistics for φ', 'Ladder', 'Shower colours'],
    [k('xgb-cv'), 'E1', 'Models', 'Fold rings and mean diamond, one multiple per metric', 'Nadeau–Bengio corrected resampled t interval of the mean', `${C.KFOLD_SPLITS} folds`, 'Accent'],
    [k('xgb-binary'), 'E3', 'Models', 'Confusion counts; rate points on 0–100%', 'Wilson; Newcombe’s MOVER for balanced accuracy', 'Undefined rates not drawn', 'No ramp on counts; accent'],
    [k('xgb-surrogate'), 'E4', 'Models', `Depth-${C.SURROGATE_MAX_DEPTH} tree of node boxes`, 'Within-node SD, no whisker; per-output fidelity', `Weak below ${C.WEAK_NODE_N} rows; Rayleigh gate for φ`, 'Sequential node mean on its legible run; φ uncoloured'],
    [k('xgb-importance'), 'E5', 'Models', `Top ${C.TOP_N_FEATURES} bars from zero; fold dots; bracket`, 'Corrected resampled t interval of the fold mean', `Top ${C.TOP_N_FEATURES}, the rest counted`, 'ColorBrewer qualitative, by frame'],
    [k('feat-table'), 'D2', 'Models', 'Table per feature and momentum class', 'Mean’s t interval; σ’s SE, χ² interval and $c_4$ (tooltip)', `Cell flagged below ${C.MIN_ROBUST_SAMPLES} showers; 1 d.o.f. at ${C.MIN_MOMENT_SAMPLES}`, 'None'],
    [k('feat-corr'), 'D3', 'Models', 'Lower-triangle feature matrix', 'Fisher-z interval; faded where it contains 0', 'As C8', 'PuOr; hatch for azimuths'],
    [k('feat-hist'), 'D4', 'Models', 'Histograms and Gaussian KDEs per class', 'Event strip below the floor', `KDE from ${C.MIN_KDE_SAMPLES}, histogram from ${C.MIN_HISTOGRAM_SAMPLES}`, 'Ordered sequential stops'],
    [k('feat-hist2d'), 'D5', 'Models', '2-D count raster per class against deposited energy', 'None (counts); events drawn below the floor', `Raster from ${C.MIN_HISTOGRAM_SAMPLES}`, 'Sequential log count, shared scale'],
    [k('prim-rate'), 'C11', 'Models', 'Point per momentum bin; overall dotted rule', 'Capped asymmetric Wilson whisker', 'From one event', 'Accent'],
    [k('vox-event'), 'C5, C6', 'Models', 'Orthographic cubes of one event, beside three 2-D projections', 'None in 3-D; numbers on the projections', `Event window ≥ ${C.EVENT_WINDOW_MIN_HALF_MM} mm per axis`, 'Sequential, folded PuOr, or qualitative species'],
    [k('vox-ensemble'), '3-D ensemble', 'Models', 'Orthographic voxel cloud, beside three 2-D projections', 'None in 3-D; numbers on the projections', 'As the 2 × 2', 'The relative ramp of the 2-D panels'],
  ],
  note: String.raw`The paired projections of the 3-D cards (${k('vproj-xy')}, ${k('vproj-xz')}, ${k('vproj-yz')}, ${k('eproj-xy')}, ${k('eproj-yz')}, ${k('eproj-xz')}) follow their 2-D counterparts on the Physics page. Card ids are those of ${k('physics_section.js')} ${k('PHYSICS_CARDS')}, ${k('models_cards.js')} ${k('MODELS_CARDS')} and ${k('voxel_views.js')} ${k('VOXEL_CARDS')}.`,
};

const LEAD = [
  {
    kind: 'p',
    text: String.raw`This section audits the dashboard's encodings and reports no dataset's findings. Every card of the Physics page (${k('/')}) and the Models page (${k('/models')}) is examined for the quantity it encodes, the mark, scale and aspect chosen for it, the distortion that choice prevents, the gates that decide which marks may be drawn, and where the reader sees it live. A measured figure appears only as the rationale of a rule, with its source; the estimators are stated in [[sec-methods]] and cited by equation. Five rules recur on every card:`,
  },
  {
    kind: 'list',
    ordered: true,
    items: [
      String.raw`**Undistorted axes.** Bars, histograms and densities start at zero; detector geometry is 1:1 wherever the panel can hold it ([[eq-isometric]]); a truncated scale carries a break.`,
      String.raw`**Two marks, two quantities.** A capped whisker or thin envelope is the uncertainty of an aggregate; the spread of the sample is an uncapped band or bar, or nothing when the observations are drawn. They differ by $\sqrt{N}$, and each tooltip names its quantity.`,
      String.raw`**Ranges follow robust evidence.** Axis and colour ranges come from the series that carry statistical weight; a weaker series is clipped with a caret where it overflows, and a range taken from weak evidence is labelled provisional.`,
      String.raw`**Numbers and marks are gated separately** by the ladder of [[tab-low-n]]: a mean and width from $N = ${C.MIN_MOMENT_SAMPLES}$, a curve from ${C.MIN_CURVE_SAMPLES}, a histogram and the core refit from ${C.MIN_HISTOGRAM_SAMPLES}, a robust width from ${C.MIN_ROBUST_SAMPLES}.`,
      String.raw`**Nothing is dropped silently.** Values beyond a range, bins below a floor and energy outside a window are counted and stated in the card's Details drawer, which replaced the on-card footnotes and is the source of a figure's caption.`,
    ],
  },
  TAXONOMY,
  {
    kind: 'p',
    text: String.raw`Colour carries an ordered quantity only on a sequential ramp and a signed one only on a diverging ramp symmetric about zero; a nominal variable (an input frame, a species) takes ColorBrewer qualitative hues, each checked against the card. Table cards have no marks and no export, so their uncertainty lives in cells and tooltips.`,
  },
];

/* ------------------------------------------------------------ §3.1 -- */

const SPATIAL = {
  id: 'sec-spatial',
  title: 'Spatial projections',
  blocks: [
    {
      kind: 'p',
      text: String.raw`The 2 × 2 diagnostic is the dashboard's primary instrument: the entry slab (XY), with each shower's centroid and, in the Absolute (detector) frame, the separation vector $D$; two depth panels, YZ and XZ, sharing one colour scale; and plot 4 ([[sec-response]]). A raster bin holds the selected channel ([[eq-channels]]): the ensemble-averaged density $\langle\rho\rangle$ (${k(C.RHO_UNIT)}), or a Grad-CAM or Shap-CAM channel of the selected network. A panel of $W_{\mathrm{px}} \times H_{\mathrm{px}}$ pixels showing millimetre spans $L_{\mathrm c}$ and $L_{\mathrm r}$ is drawn at one scale on both axes and letterboxed:`,
    },
    {
      kind: 'eq',
      id: 'eq-isometric',
      tex: String.raw`\gamma = \min\left(\frac{W_{\mathrm{px}}}{L_{\mathrm c}},\ \frac{H_{\mathrm{px}}}{L_{\mathrm r}}\right)\ \mathrm{px\,mm^{-1}}, \qquad W'_{\mathrm{px}} = \gamma\,L_{\mathrm c}, \quad H'_{\mathrm{px}} = \gamma\,L_{\mathrm r}`,
    },
    {
      kind: 'p',
      text: String.raw`The spans are physical extents from the stored cell coordinates, never a matrix shape, since the ${C.X_CELLS} × ${C.Y_CELLS} transverse lattice is irregular ([[sec-discretisation]]). The entry panel is always 1:1, so $D$ can be measured off it. A depth panel is 1:1 when its span ratio lies in [${C.DEPTH_ISO_RATIO_MIN}, ${C.DEPTH_ISO_RATIO_MAX}] and the letterboxed plot fills at least ${pc(C.DEPTH_ISO_MIN_FILL)} of the card (${k('event_cells.js')} ${k('depthIsometric')}), a test the compact co-registered windows usually pass. The Absolute frame's depth panels never take it: they span about 5,200 mm against 1,210 mm of depth (${k('panels/projection.js')}), where 1:1 would leave a sliver, so they fill the card with true extents on the axes and the drawer states the aspect in force. One zoom scales both axes by one ratio, so isometry survives zooming, and the letterbox is recomputed on every container resize.`,
    },
    {
      kind: 'p',
      text: String.raw`In the D-frame (API ${k('canonical')}; [[sec-frames]]) the entry panel writes its horizontal axis as $D$, the signed $x'$ along the A→B separation, with open anchors at $D = \mp\langle D_{\mathrm{entry}}\rangle/2$, a faint bar for the SD of $D_{\mathrm{entry}}/2$ and a dashed rule for the mean separation. Co-registered windows are symmetric about the origin at the energy-weighted ${C.WINDOW_LOW_PERCENTILE}–${C.WINDOW_HIGH_PERCENTILE} percentiles ([[eq-window]]), at least ${C.SHOWER_RADIUS_MIN_MM} mm while provisional ($N < ${C.PROVISIONAL_N}$) and ${C.WINDOW_FLOOR_FOOTPRINTS} footprints after, snapped to ${C.CANONICAL_PITCH_MM} mm: a 1–99 crop cut the halo well above the display floor, so the colour stopped at the window edge and read as the shower's edge ([[sec-frames-windows]]).`,
    },
    {
      kind: 'p',
      text: String.raw`**The relative log ramp.** Co-registered panels paint $\ell$ on $[-${C.RAMP_DECADES}, 0]$ ([[eq-relative-log]]) in 8-bit codes ([[eq-quantise]]). A bin below $10^{-${C.RAMP_DECADES}}\rho_{\mathrm{ref}}$ takes its own code (${C.BELOW_CODE}), is transparent and is counted in the status bar's Clipped readout; folding it into the bottom colour painted the crop as a dark rectangle round the showers (${k('encode/scale.py')}). On screen the ramp fades in over the ${C.FLOOR_FADE_DECADES} decade above the floor, because a hard floor draws a violet rim round the halo; print keeps the hard contour its caption names. $\rho_{\mathrm{ref}}$ is the selection's peak or the dataset's (${k('rho_norm')}): relative to the dataset, a slice holding a tenth of the energy looks a tenth as bright. The Absolute frame locks a ${C.LAB_DECADES}-decade GeV ramp of ${C.LEVELS} codes to the experiment's brightest cell, folding and counting the cells below it, so a faint selection cannot render like the full dataset; Grad-CAM keeps fixed linear endpoints on [0, 1].`,
    },
    {
      kind: 'p',
      text: String.raw`**Native Grid and Continuous Field** ([[sec-discretisation]]). Native Grid is the audit view: one bin per cell (Absolute) or the raw ${C.CANONICAL_PITCH_MM} mm accumulation bins. Continuous Field applies a stated conservative operator ([[eq-kernel-operator]]): area-weighted re-binning at resolution $R$ (Absolute), or on the co-registered transverse axes a box ⊗ Gaussian of $\sigma_{\mathrm K} = ${C.SMOOTH_SIGMA_MM}$ mm below ${C.GAUSSIAN_KERNEL_BELOW_N} events and the bilinear tent from there; depth is never reconstructed. No displayed bin exceeds the raw peak ([[eq-raw-peak]]), so the choice changes resolution, not scale. The comb statistic ([[eq-lag1]]) is measured on the raw, uncropped raster before any kernel, so its verdict is the same in both displays; where it fires on the Absolute native entry panel, the panel itself says that the comb is detector segmentation, since the panel is what gets screenshotted.`,
    },
    {
      kind: 'p',
      text: String.raw`**Direction overlays.** The incident azimuth is near-uniform over the face ([[sec-frames-absolute]]), so the overlays differ by frame, as [[eq-resultant]] and [[eq-pointing]] set out:`,
    },
    {
      kind: 'list',
      ordered: false,
      items: [
        String.raw`*Absolute:* up to ${C.MAX_TRAJECTORY_EVENTS} events, each event's own trajectory from its centroid along $(\theta, \varphi)$; above that, $\bar R$ is printed and no average is drawn at full extent. A depth panel zoomed to a transverse window draws the mean trajectory of the events entering it, with an uncapped per-depth SD band and a thin Student-t envelope, faded when $|\bar\beta| < ${C.LEAN_RATIO_MIN}\,\operatorname{SD}(\beta)$ ([[eq-window-axis]]). It rests on a measured geometry: every shower points at the detector origin, and in ${C.WINDOW_AXIS_MM} mm entry windows the median $\bar R(\varphi)$ is 0.999 (production file).`,
        String.raw`*D-frame:* the two ensemble axes, each with an uncapped wedge for the SD of the per-event slopes and a thin Student-t envelope of the mean slope, two named marks; $\bar R'$, the Rayleigh $p$ and $N$ printed beside them, re-measured per response, and an axis with $p > ${C.UNIFORM_P}$ faded, never hidden.`,
        String.raw`*Local:* nothing, since every direction is $+w$ by construction; the legacy per-shower translated frame draws trajectories from the origin up to ${C.MAX_TRAJECTORY_EVENTS} events.`,
        String.raw`The per-layer energy centroid of the larger Absolute selections is named the *centre of deposited energy*: a property of the summed picture, never a direction.`,
      ],
    },
    {
      kind: 'p',
      text: String.raw`**Event Inspector and compare frames.** Both are the reference notebook's 3 × 3 figure, frames by projections. The Event Inspector draws one shower of one event in the original, per-shower translated and Local frames; every mark is that shower's own (its direction, first-layer plane, origin $P_0$), and its principal-axis tilt is printed, not drawn. Its nine panels share one window (energy-weighted ${C.WINDOW_LOW_PERCENTILE}–${C.WINDOW_HIGH_PERCENTILE} percentiles plus a footprint, at least ${C.EVENT_WINDOW_MIN_HALF_MM} mm, snapped to ${C.EVENT_WINDOW_SNAP_MM} mm) and one ramp, so all are isometric and comparable and a tilt reads at its true angle. The compare-frames view sets the Absolute, per-shower translated and Local ensemble responses side by side under the 2 × 2's rules.`,
    },
    {
      kind: 'p',
      text: String.raw`**Exports and tooltips.** An export is the plot canvas only, in ${k('#111827')} ink on ${k('#FFFFFF')} with the full ramp; the drawer's text is the caption. Tooltips sit on a fixed layer nothing clips; an explanation leaves the hovered plot, and a readout stays by the pointer only where it covers at most ${pc(C.READOUT_SHARE)} of the plot. A tip confined to its chart had covered a median 35% of the plot at 1600 × 900 and up to 98% at 1280 × 800 on the demonstration data (${k('panels/tooltip.js')}).`,
    },
    {
      kind: 'links',
      id: 'lnk-results-spatial',
      items: [
        { page: 'physics', panel: 'xy', label: 'Entry slab' },
        { page: 'physics', panel: 'yz', label: 'YZ depth panel' },
        { page: 'physics', panel: 'xz', label: 'XZ depth panel' },
        { page: 'physics', panel: 'xy', set: { frame: 'canonical' }, label: 'D–Y′ entry panel' },
        { page: 'physics', panel: 'yz', set: { frame: 'canonical' }, label: 'D-frame ensemble axes' },
        { page: 'physics', panel: 'compare-lab-xy', set: { compare: true }, label: 'Compare frames' },
        { page: 'models', panel: 'vox-event', label: 'One event, projected' },
      ],
    },
  ],
};

/* ------------------------------------------------------------ §3.2 -- */

const COLOUR = {
  id: 'sec-colour',
  title: 'Perceptual colorimetry, screen against print',
  blocks: [
    {
      kind: 'p',
      text: String.raw`Every colour is checked against its background with the WCAG 2.1 contrast ratio [[cite:wcag21]],`,
    },
    {
      kind: 'eq',
      id: 'eq-contrast',
      tex: String.raw`\begin{aligned} C_{\mathrm{WCAG}} &= \frac{\max(Y_1, Y_2) + 0.05}{\min(Y_1, Y_2) + 0.05}, \qquad Y = 0.2126\,\Lambda_{\mathrm R} + 0.7152\,\Lambda_{\mathrm G} + 0.0722\,\Lambda_{\mathrm B} \\ \Lambda &= \begin{cases} \Lambda_8/(255 \cdot 12.92), & \Lambda_8/255 \le 0.04045 \\ \left(\dfrac{\Lambda_8/255 + 0.055}{1.055}\right)^{2.4}, & \text{otherwise} \end{cases} \end{aligned}`,
    },
    {
      kind: 'p',
      text: String.raw`where $Y_1$ and $Y_2$ are the relative luminances of the two colours and each linear channel $\Lambda \in \lbrace \Lambda_{\mathrm R}, \Lambda_{\mathrm G}, \Lambda_{\mathrm B}\rbrace$ is decoded from its 8-bit value $\Lambda_8$ (${k('palette.js')} ${k('contrast')}), with the sRGB threshold 0.04045 (WCAG 2.1 prints 0.03928, which differs below $10^{-4}$). Anything a reader must see clears $C_{\mathrm{WCAG}} \ge ${C.RAMP_CONTRAST}$ against the card ${k('#1c2128')}.`,
    },
    {
      kind: 'p',
      text: String.raw`**Sequential ramps.** Viridis is the default because its lightness is monotone: on a multi-decade log ramp the eye orders decades by brightness before hue, which keeps a faint halo legible beside a bright core [[cite:crameri2020]]. Cividis serves colour-vision deficiency [[cite:nunez2018]]; Plasma is a third monotone ramp. Turbo [[cite:mikhailov2019]] is offered but never the default: its lightness is not monotone, so its hue transitions draw bright bands that read as structure [[cite:borland2007]]. On the dark screen every ramp starts at its first colour with $C_{\mathrm{WCAG}} \ge ${C.RAMP_CONTRAST}$, because Viridis' first colour is 1.06:1 on the dark card and up to 58% of an event's cubes vanished before the rule (CLAUDE.md). The run is found by scanning the palette's 256-entry table for the longest contiguous stretch that clears the floor (${k('panels/chart_panel.js')} ${k('legibleRamp')}, used by ${k('scale.js')} ${k('legibleSpan')}): Viridis from ${C.VIRIDIS_LEGIBLE_FROM}, Cividis from ${C.CIVIDIS_LEGIBLE_FROM}, Plasma from ${C.PLASMA_LEGIBLE_FROM}, and Turbo only between ${C.TURBO_LEGIBLE_FROM} and ${C.TURBO_LEGIBLE_TO}, its dark red top failing as well as its dark blue bottom. On a tapered ramp that colour sits where the taper turns opaque. Legend, raster and cubes share one remapped table, each drawer says where the ramp starts, and print keeps the full ramp.`,
    },
    {
      kind: 'figure',
      id: 'fig-ramps',
      exhibit: 'ramps',
      caption: String.raw`The four sequential palettes. Upper block: each ramp with the span the screen paints bracketed, from its first to its last colour at ${C.RAMP_CONTRAST}:1 or more against the card ${k('#1c2128')}; the screen draws nothing outside it. Lower block: the full print ramp on white. Viridis, Cividis and Plasma lose only their dark end on the card; Turbo loses both ends, and its brightness rises and falls along the ramp. Drawn from ${k('palette.js')}.`,
    },
    {
      kind: 'p',
      text: String.raw`**The signed ramp.** Shap-CAM and a Pearson $r$ are signed, so they take ColorBrewer PuOr [[cite:harrower2003]], orange negative and purple positive; on the production file 11–64% of hits carry negative Shap-CAM (CLAUDE.md), which a sequential ramp would fold into "no attention". Standard PuOr fails on the dark card: ${k('#2d004b')} reaches 1.07:1 and ${k('#7f3b08')} 1.95:1, and the ${k('#f7f7f7')} centre haloes every near-zero bin. The dark screen therefore folds it: each arm runs outwards from the card, brightness rising with $|\text{value}|$ and hue alone giving the sign; the anchors are placed by CIE lightness so both signs read equally bright; the first 3:1 colours, ${k('#b35806')} (3.3:1) and ${k('#8073ac')} (3.8:1), sit at $10^{-${C.RAMP_DECADES - C.FLOOR_FADE_DECADES}}$ of the peak ([[eq-signed-log]]), where the taper turns opaque; raw Shap-CAM puts zero at the border grey ${k('#30363d')}, so a populated zero differs from an empty bin. Print keeps the standard 11 classes, whose light centre marks zero on paper.`,
    },
    {
      kind: 'figure',
      id: 'fig-puor',
      exhibit: 'puor',
      caption: String.raw`Standard PuOr for print against the folded screen PuOr, each anchor labelled with its WCAG contrast against the card ${k('#1c2128')} and against white. The print scheme is brightest at zero; the screen scheme is darkest there and brightens outwards on both arms. Drawn from ${k('palette.js')}.`,
    },
    {
      kind: 'p',
      text: String.raw`**Typography.** Every rendered negative number uses the minus sign U+2212 (${k('format.js')}, ${k('calosrv/text.py')}). The dark screen theme is canvas ${k('#0d1117')} and ${k('#161b22')}, cards ${k('#1c2128')}, borders ${k('#30363d')}, text ${k('#e6edf3')} and ${k('#8b949e')}; the light screen theme is canvas ${k(C.LIGHT_CANVAS_HEX)}, cards ${k(C.LIGHT_CARD_HEX)}, borders ${k('#d0d7de')}, text ${k('#111827')} and ${k('#59636e')}; the exporter swaps either whole for ${k('#111827')} ink on ${k('#FFFFFF')}. A new palette is adopted only after its anchors are measured against the card.`,
    },
    {
      kind: 'p',
      text: String.raw`**The light screen.** A reader may switch the interface to a light theme (${k('theme.js')}). The toggle follows the operating system's setting until the reader chooses, and a choice lives in that browser alone: it is never written to a link, to a request or to the Admin defaults. The card is ${k(C.LIGHT_CARD_HEX)} on a page of ${k(C.LIGHT_CANVAS_HEX)}, and every rule above is measured against it unchanged: $C_{\mathrm{WCAG}} \ge ${C.RAMP_CONTRAST}$ for anything a reader must see and $C_{\mathrm{WCAG}} \ge ${C.TEXT_CONTRAST}$ for text. No ramp made for a dark ground or for paper survives a white one: Viridis' and Plasma's yellow ends vanish there, and a ramp turned round onto white fades in through them. So each colour-map slot draws a ramp made for white (${k('palette.js')}, ${k('scale.js')} ${k('screenPalette')}), from ColorBrewer colours interpolated in CIELAB, each running from a pale tint at the display floor to a deep tone at the peak, so contrast with the card rises with the value: the Viridis slot from ${k(C.LIGHT_RAMP_FLOOR_HEX)} through emerald-teal and azure to ${k(C.LIGHT_RAMP_PEAK_HEX)}, its lightness falling at every table entry from $L^* = ${C.LIGHT_RAMP_L_FLOOR}$ to $${C.LIGHT_RAMP_L_PEAK}$; the Cividis slot from ice-azure to navy in one hue; the Plasma slot from apricot to plum; and the Turbo slot, whose lightness, like Turbo's, is not monotone, from ice and pale sky through green and amber to garnet. A raster spans its ramp in full, because a bin sits among its neighbours and a faint halo should read faint, and on a logarithmic scale it is drawn through a transfer made for white (${k('scale.js')} ${k('LIGHT_FIELD_GAMMA')}): a bin a fraction $t$ of the way up the scale is drawn $t^{\gamma}$ of the way along the ramp, $\gamma = ${C.LIGHT_FIELD_GAMMA}$, so on the three-decade relative ramp the bottom decade takes the palest ${C.LIGHT_BOTTOM_DECADE_PCT}% of the ramp and the top decade the deepest ${C.LIGHT_TOP_DECADE_PCT}%. Taken linearly, a bin at 1% of the peak sat a third of the way to the deepest tone, and the faint spray round a shower flooded the card with mid-tones; through the transfer the bottom decade stays a pale tint on every slot, and the floor fades into the card over the ${C.LIGHT_FIELD_FADE_DECADES} decade above it. The colour bar is drawn through the same mapping, so a colour still reads off it at its own place. A mark that stands alone on the card, a cube, a series line, a histogram cell or a tree leaf, keeps the ramp's run at 3:1 or more (${k('panels/chart_panel.js')} ${k('legibleRamp')}): the Viridis slot's from ${C.LIGHT_MARK_VIRIDIS_FROM}, Cividis' from ${C.LIGHT_MARK_CIVIDIS_FROM}, Plasma's from ${C.LIGHT_MARK_PLASMA_FROM} and Turbo's longest from ${C.LIGHT_MARK_TURBO_FROM}. The overlay marks are drawn with nothing laid under them: a white casing under each, tried first, fused the anchors, bars and centroids of a narrow entrance strip into one white blob and banded the dashed axes through the core. An ensemble or windowed axis is one ${C.LIGHT_AXIS_PX} px dashed line; on a plot under ${C.STRIP_HEIGHT_PX} px tall, such as the entrance strip of a widely separated pair, the anchor rings are drawn at ${C.STRIP_ANCHOR_PX} px and the centroids at ${C.STRIP_CENTROID_PX} px, so the two showers' marks never meet; and each spatial card's Marks button hides every mark over the raster, so the core can be read unobstructed, and an export follows it. An ensemble axis's spread and 95% envelope are faint washes carried by their outlines, dashed for the spread and thin and solid for the envelope.`,
    },
    {
      kind: 'p',
      text: String.raw`PuOr keeps its standard direction on the light card, re-anchored by CIE lightness against it: each arm runs from the card outwards through the scheme's own colours, darkening with $|\text{value}|$, and equal $|\text{value}|$ of either sign reads equally dark. The first 3:1 colours, ${k(C.LIGHT_PUOR_NEG_FIRST)} and ${k(C.LIGHT_PUOR_POS_FIRST)}, sit at $10^{-${C.RAMP_DECADES - C.FLOOR_FADE_DECADES}}$ of the peak ([[eq-signed-log]]), where the taper turns opaque, as on the dark card; the arms end at ${k(C.LIGHT_PUOR_NEG_END)} and ${k(C.LIGHT_PUOR_POS_END)}, the purple stopped at the orange's lightness so that neither sign is the darker; and raw Shap-CAM and a Pearson $r$ put zero at ${k(C.LIGHT_PUOR_ZERO)}, the light theme's border grey, so a populated zero still differs from an empty bin. [[fig-ramps]] and [[fig-puor]] are drawn against the dark card in either theme, and an exported figure is identical whichever theme is on screen, because the exporter replaces the whole token set with the print theme before it draws.`,
    },
    {
      kind: 'links',
      id: 'lnk-results-colour',
      items: [
        { page: 'physics', panel: 'xy', set: { channel: 'shapcam_energy' }, label: 'Energy-weighted Shap-CAM' },
        { page: 'physics', panel: 'xy', set: { channel: 'shapcam' }, label: 'Raw Shap-CAM' },
        { page: 'physics', panel: 'correlation', label: 'Pearson matrix on PuOr' },
      ],
    },
  ],
};

/* ------------------------------------------------------------ §3.3 -- */

const PROFILES = {
  id: 'sec-profiles',
  title: 'Longitudinal and radial profiles (C7)',
  blocks: [
    {
      kind: 'p',
      text: String.raw`The profile cards draw the share of a shower's energy per centimetre: both from footprint-splatted sub-deposits: along the Local depth $w$ in bins of the ${C.Z_PITCH_MM} mm layer pitch, never smoothed, since nothing is measured between layers, and along $\rho = \sqrt{u^2 + v^2}$ in ${C.PROFILE_R_BIN_MM} mm bins. The $y$ axis is zero-based and set by the two lines; $w = 0$, the entry point, is a dashed rule. Four marks carry four quantities (${k('panels/profile.js')}): the per-shower mean, a solid step line; the uncapped SD band, where individual showers lie; the thin capped Student-t envelope of the mean, cluster-robust by event ([[eq-profile-se]]); and the notebook's pooled ratio of sums, dashed, energy-weighted and so a different number. A band that narrowed as $1/\sqrt{N}$ would claim that showers grow alike as more are selected; that is why the two are distinct marks.`,
    },
    {
      kind: 'p',
      text: String.raw`One shower is labelled "single shower, not an ensemble" and has no band; two showers carry one degree of freedom and say so; below ${C.PROFILE_PROVISIONAL_N} the label reads "weak" and the range is provisional. A band or interval leaving the axis, including a lower edge below zero, is cut with a caret, its values in the readout; energy beyond the window stays in the normalisers and its share is stated.`,
    },
    {
      kind: 'links',
      id: 'lnk-results-profiles',
      items: [
        { page: 'physics', panel: 'profile-w', label: 'Longitudinal profile' },
        { page: 'physics', panel: 'profile-r', label: 'Radial profile' },
      ],
    },
  ],
};

/* ------------------------------------------------------------ §3.4 -- */

const RESPONSE = {
  id: 'sec-response',
  title: 'Response, sampling fraction and resolution (plot 4, B1–B3)',
  blocks: [
    {
      kind: 'p',
      text: String.raw`**Plot 4** draws the reconstructed energy in slices of $D$: slice by colour (ordered stops visible as one-pixel lines), shower by line style (A solid, B dashed), so the broadening with $D$ reads as a progression. From ${C.MIN_HISTOGRAM_SAMPLES} events a slice is a density histogram from zero, binned by the Rice rule of the smallest drawn slice ([[eq-histogram]]), with its core Gaussian on the histogram's normalisation ([[eq-curve-area]]): where the ±${C.CORE_SIGMA}σ refit cut a tail, the curve's area is the core's share over the window's coverage ${C.CORE_WINDOW_COVERAGE.toFixed(4)}, so it stands below the bars by the tail it does not describe. From ${C.MIN_CURVE_SAMPLES} events the curve is thinner and fainter over the events; below, only events and summary marks. Every mark that is not a density sits in a tinted, captioned band at the foot: event ticks, the mean with its capped t whisker ([[eq-t-interval]]), the SD as an uncapped bar, and below the core floor σ with its SE [[eq-se-sigma]], its χ² interval [[eq-chi2-sigma]] and $c_4(N)$ [[eq-c4]]. The isolated references are a dotted rule at μ over a shaded μ ± σ band, A in the text colour and B muted, in their own legend: a stated ${pc(C.ISOLATED_RESOLUTION)} width at the selection's mean true momentum, not a fit and never a density.`,
    },
    {
      kind: 'p',
      text: String.raw`The density axis is set by slices of at least ${C.MIN_HISTOGRAM_SAMPLES} events. A curve peaks at $1/(\sigma\sqrt{2\pi})$, so a thin, under-powered slice would otherwise press every well-measured one into the bottom of the canvas ([[sec-statistics-gates]]). An overflowing thin curve is clipped with a caret; with no estimable density the axis is unlabelled and says so. The drawer's density explainer (${k('panel_notes.js')} ${k('DENSITY_EXPLAINER')}) states that a density is not a probability: its height in GeV⁻¹ exceeds 1 for any narrow peak and says nothing of how many events made it, which the ticks carry.`,
    },
    {
      kind: 'p',
      text: String.raw`**B1** is the per-event sampling fraction $E_{\mathrm{dep}}/p$, with two estimators as two verticals: the mean of ratios with its Student-t hairlines ([[eq-mean-of-ratios]]), and $1/c = \sum E_{\mathrm{dep}}/\sum p$, the calibration plot 4 applies ([[eq-calibration]]), with its cluster ratio interval ([[eq-ratio-se]]). The card exists to show that they differ. Below ${C.MIN_HISTOGRAM_SAMPLES} events a series moves to the reserved band with its capped mean, uncapped SD bar and a $1/c$ diamond. **B2** draws the mean per 1 GeV momentum bin with a capped t whisker over an uncapped, dashed SD box (A left, B right), and $1/c$ as a dotted rule. **σ/μ** carries the χ² interval of σ over $\hat\mu$, μ's error neglected and the delta-method SE beside it ([[eq-resolution-whisker]]), for two quantities: the calibrated energy and $E_{\mathrm{dep}}/p$, which divides out the in-bin momentum spread that alone gives σ/μ = 0.58 in the lowest bin (${k('query/response.py')}). **B3** is small multiples, one per window (${C.CALIBRATION_CENTRES_GEV.join(', ')} ± ${C.HALF_WIDTH_GEV} GeV), each on its own energy axis under plot 4's ladder, with the slice's mean momentum as a dotted rule and t envelope. Throughout, a bin below ${C.MIN_ROBUST_SAMPLES} is faded but never below 3:1, a one-event or one-d.o.f. bin is an open circle, a range without robust bins is provisional, and a mark beyond the axis is clipped, never rescaled.`,
    },
    {
      kind: 'links',
      id: 'lnk-results-response',
      items: [
        { page: 'physics', panel: 'energy', label: 'Plot 4' },
        { page: 'physics', panel: 'response-b1', label: 'B1' },
        { page: 'physics', panel: 'response-b2', label: 'B2' },
        { page: 'physics', panel: 'response-res', label: 'σ/μ' },
        { page: 'physics', panel: 'response-b3', label: 'B3' },
      ],
    },
  ],
};

/* ------------------------------------------------------------ §3.5 -- */

const DISTRIBUTIONS = {
  id: 'sec-distributions',
  title: 'Distributions, features and correlations (C1, C4, C8, C9, D1–D5)',
  blocks: [
    {
      kind: 'p',
      text: String.raw`**C4** overlays one step outline per momentum bin, since twenty filled histograms would hide one another, in ordered sequential stops that clear 3:1. Counts are exact; a series of fewer than ${C.SHAPE_FLOOR_SHOWERS} showers is dashed, its shape not a distribution. The linear axis starts at zero; the log axis omits empty bins and closes each run at its stated floor. Hit energy runs on a log axis over its 1st–99th percentiles with carets counting the rest; φ spans its full period, never averaged, with $\bar R$ and the Rayleigh $p$ per series. **C8**, the hit-level Pearson matrix, draws its lower triangle on PuOr linear on [−1, +1], each cell printing its $r$. Hits of one shower are not independent, so the interval is Fisher's $\zeta$ [[eq-fisher]] with an event-grouped jackknife [[eq-jackknife]], $n_{\mathrm{eff}}$ beside the hit count. An azimuth cell is hatched, off the colour scale, carrying Mardia's $R_{\mathrm M}$ from ${C.MIN_MARDIA_AZIMUTHS} azimuths ([[eq-mardia]]); a cell reads "—" below ${C.MIN_R_EVENTS} events.`,
    },
    {
      kind: 'p',
      text: String.raw`**C1** is a table: an unweighted ${k('describe()')} of the hits (ddof = ${C.DDOF}) beside energy-weighted means and quartiles, which say where the energy is rather than correct the others. No SE of a hit mean is quoted, since correlated hits would claim a precision the events lack. **C9** counts hits behind the entry plane, $w < -10^{${Math.log10(C.NEG_DEPTH_THRESHOLD_MM)}}$ mm: energy and hit shares with cluster ratio intervals, the share of events with any such hit with a Wilson interval ([[eq-wilson]]).`,
    },
    {
      kind: 'p',
      text: String.raw`**The feature explorer (D1–D5)**, D1 being the explorer itself (${k('GET /api/features')}, the aggregate's features in three frames), draws one shower at a time and never pools A and B; on an aggregate experiment it offers the Absolute, per-shower translated and Local frames, never the D-frame, which the producer's aggregate lacks. **D2** tabulates each feature per class as a median with quartiles, a mean ± SD (a spread, never an interval) or a range, with the mean's t interval and σ's SE, χ² interval and $c_4(N)$ in the tooltip, a flag below ${C.MIN_ROBUST_SAMPLES} showers, and a circular mean with $\bar R$ for an azimuth. **D3** fades a cell whose 95% interval contains zero: at $N = ${C.MIN_FISHER_N}$ the Fisher interval spans nearly [−1, 1], and full colour would claim an association the sample cannot tell from none; ${k('avg_phi')} is hatched with Mardia's $R_{\mathrm M}$ or $r_c$ ([[eq-rc]]), the notebook's linear $r$ kept as tooltip parity. **D4** draws histograms from ${C.MIN_HISTOGRAM_SAMPLES} showers and Gaussian KDEs from ${C.MIN_KDE_SAMPLES} ([[eq-silverman]]), with no linear kernel for an azimuth. **D5** replaces the notebook's 30,000-point scatter with a server-side 2-D count histogram per class on shared edges and one log scale: it keeps the payload under ${n(C.RESPONSE_LIMIT / 1000)} kB, hides no point under another, and gives way to the events themselves below ${C.MIN_HISTOGRAM_SAMPLES}.`,
    },
    {
      kind: 'links',
      id: 'lnk-results-distributions',
      items: [
        { page: 'physics', panel: 'distribution', label: 'C4' },
        { page: 'physics', panel: 'correlation', label: 'C8' },
        { page: 'physics', panel: 'statistics', label: 'C1 and C9' },
        { page: 'models', panel: 'feat-table', label: 'D2' },
        { page: 'models', panel: 'feat-corr', label: 'D3' },
        { page: 'models', panel: 'feat-hist', label: 'D4' },
        { page: 'models', panel: 'feat-hist2d', label: 'D5' },
      ],
    },
  ],
};

/* ------------------------------------------------------------ §3.6 -- */

const MODELS = {
  id: 'sec-models',
  title: 'Model evaluation, the surrogate tree and the 3-D views (E1–E5, C5, C6, C11)',
  blocks: [
    {
      kind: 'p',
      text: String.raw`**E2** draws each network's RMSE, MAE, median relative error or bias per 1 GeV momentum bin as bars from zero at fixed offsets, so the axis stays momentum in GeV and an empty bin is a gap; colour is the input frame on qualitative hues. The whisker is the interval of the bar's own statistic: for the RMSE a χ² interval below ${C.MIN_ROBUST_SAMPLES} showers and a seeded ${n(C.BOOTSTRAP_REPLICATES)}-replicate bootstrap from there ([[eq-rmse]]), never √ of a t interval of the MSE, whose lower end collapses at small $N$; Student-t for MAE and bias; the order-statistic interval of the median from ${C.MIN_ORDER_N} ([[eq-median-order]]). A bar without an interval is faded and its tooltip names the floor; one shower is a dot, an observation and not an aggregate; the range comes from points of at least ${C.MIN_CORE_SAMPLES} showers.`,
    },
    {
      kind: 'p',
      text: String.raw`**Prediction against truth** is a log-count raster per shower from its first 3:1 colour, so a count of one is seen and an empty bin is transparent. Truth and prediction share one range and unit, so each grid is square and the identity is the dashed diagonal; below ${C.MIN_HISTOGRAM_SAMPLES} pairs the pairs are drawn. **The residuals** take the Freedman–Diaconis width, the recorded exception to Rice ([[eq-histogram]]): on the relative XGBoost momentum residuals, (pred − true)/true, Rice put the whole core into one bin under a curve 3.5 times taller ([[sec-statistics-histograms]]). An azimuth residual is wrapped ([[eq-wrap]]) and drawn with no arithmetic mean, whisker or SD bar; its circular mean, $\bar R$ and circular SD are quoted.`,
    },
    {
      kind: 'p',
      text: String.raw`**The XGBoost cards** read analyses computed once on the whole experiment, so the selection does not apply, as each says. **E1** draws the ${C.KFOLD_SPLITS} folds as open rings and their mean as a diamond whose capped whisker is Nadeau and Bengio's corrected resampled t interval [[cite:nadeau2003]] at ${C.KFOLD_SPLITS - 1} d.o.f., since any two folds share three-quarters of their training rows; error metrics start at zero and an $R^2$ axis near 1 carries a break. **E3** thresholds at ${C.BINARY_THRESHOLD_GEV} GeV a designed sample of ${n(C.BINARY_TOTAL)} validation rows, ${RATIO} between $p < ${C.BINARY_THRESHOLD_GEV}$ GeV and $p > ${C.BINARY_CLASS_1_ABOVE_GEV}$ GeV. Its confusion matrix is counts without a ramp, which would only say class 0 is large; its rates are points on 0–100%, positions on a common scale, the encoding read most accurately [[cite:cleveland1984]], with Wilson intervals, balanced accuracy with Newcombe's MOVER interval [[cite:newcombe1998]]; and it states the realised ratio and that accuracy and the precisions depend on it while the recalls and balanced accuracy do not.`,
    },
    {
      kind: 'p',
      text: String.raw`**E4** is a depth-${C.SURROGATE_MAX_DEPTH} tree fitted to the booster's predictions [[cite:breiman1984]] [[cite:craven1996]]: boxes with the rule, the feature's frame, $n$, and mean ± within-node SD (ddof = ${C.DDOF}), a description and so without whiskers. Fidelity is per output, φ on the circular $R^2$ ([[eq-circular-r2]]), with a warning below ${C.LOW_FIDELITY_R2}; the average is never judged, since it would hide both outputs ([[sec-statistics-circular]]). Nodes below ${C.WEAK_NODE_N} rows are weak and do not set the colour domain; φ is never coloured and prints a circular mean with $\bar R$ only where the Rayleigh $p < ${C.UNIFORM_P}$. **E5** draws the top ${C.TOP_N_FEATURES} features by the shipped booster's normalised average split gain [[cite:chen2016]] as bars from zero, the five refits as dots on their own line and their mean in a capped bracket, so the bar is never read as the folds' mean; the total-gain share is in the tooltip and the rest are counted. **The training-split check** compares seed ${C.SPLIT_SEED} with ${C.CHECK_SEEDS_N} others; an unreproduced split is shown with its hazard. **C11** plots the share of events with no primary-tagged hit, events being the units, with capped asymmetric Wilson whiskers from one event on, on the full 0–100% axis; the overall share is a dotted rule whose interval is in its tooltip, so it cannot read as dispersion.`,
    },
    {
      kind: 'p',
      text: String.raw`**The 3-D views** (C5, C6, the ensemble cloud) are the one recorded exception to the rule against 3-D, because where energy sits in depth and around the axis is lost by two projections. They are held to strict terms (${k('voxels.js')}, ${k('voxel_views.js')}):`,
    },
    {
      kind: 'list',
      ordered: false,
      items: [
        String.raw`an orthographic camera and one millimetre scale on all three axes, 1:1:1, so no length is foreshortened;`,
        String.raw`measured cells of ${C.CELL_X_MM} × ${C.CELL_Y_MM} × ${C.Z_PITCH_MM} mm in the Absolute and per-shower translated frames; in Local and the D-frame, axis-aligned splat voxels of ${C.CANONICAL_PITCH_MM} mm for one event (coarser only where ${C.MAX_VOXELS_PER_AXIS} per axis cannot cover it) and ${C.CLOUD_VOXEL_MERGE * C.CANONICAL_PITCH_MM} mm for the cloud;`,
        String.raw`flat, unlit colour, because lighting modulates the luminance that encodes the value, on the 2-D panels' ramps from their first 3:1 colour;`,
        String.raw`per-axis energy-weighted ${C.WINDOW_LOW_PERCENTILE}–${C.WINDOW_HIGH_PERCENTILE} percentile windows, padded by one cell footprint (one layer pitch along depth), at least ${C.EVENT_WINDOW_MIN_HALF_MM} mm and snapped to ${C.EVENT_WINDOW_SNAP_MM} mm, so stray cells cannot stretch the box;`,
        String.raw`three paired 2-D projections beside each card, which carry the numbers and the export; the 3-D card has none, and at most two WebGL contexts per page.`,
      ],
    },
    {
      kind: 'p',
      text: String.raw`An event is coloured by energy density, Grad-CAM, signed Shap-CAM or segmentation error; on single-shower data C6 colours each cube by species on a qualitative palette that stays distinct under simulated deuteranopia and protanopia, with a halo on the most energetic primary-tagged cubes, the rest named in their tooltips. The ${C.TOPK} brightest cubes carry exact values; the rest are read from their 8-bit codes and labelled so.`,
    },
    {
      kind: 'links',
      id: 'lnk-results-models',
      items: [
        { page: 'models', panel: 'perf-bins', label: 'E2' },
        { page: 'models', panel: 'pred-truth', label: 'Prediction vs truth' },
        { page: 'models', panel: 'pred-residuals', label: 'Residuals' },
        { page: 'models', panel: 'xgb-cv', label: 'E1' },
        { page: 'models', panel: 'xgb-binary', label: 'E3' },
        { page: 'models', panel: 'xgb-surrogate', label: 'E4' },
        { page: 'models', panel: 'xgb-importance', label: 'E5' },
        { page: 'models', panel: 'prim-rate', label: 'C11' },
        { page: 'models', panel: 'vox-event', label: 'C5 / C6' },
        { page: 'models', panel: 'vox-ensemble', label: '3-D cloud' },
      ],
    },
  ],
};

export default {
  id: 'sec-results',
  title: 'Results: an audit of the visual encodings',
  blocks: LEAD,
  sections: [SPATIAL, COLOUR, PROFILES, RESPONSE, DISTRIBUTIONS, MODELS],
};
