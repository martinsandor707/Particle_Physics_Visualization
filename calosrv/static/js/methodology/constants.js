/* Every number the Methodology article quotes, with where it lives.
 *
 * The article states the dashboard's rules - its gates, widths, windows,
 * codes and thresholds - and a rule stated in prose drifts the moment the code
 * changes. So the prose never types one of these numbers: it reads it from
 * `C` below, and tests/test_methodology_constants.py resolves every `source`
 * against the live code and fails when the two disagree.
 *
 * `source` is one of:
 *
 * - `py:<module>:<expression>` - evaluated in that Python module's namespace
 *   (`calosrv.stats.gaussian:MIN_CURVE_SAMPLES`, `...:BINARY["threshold"]`);
 * - `js:<path under static/js>:<expression>` - evaluated under Node with that
 *   module's exports in scope (`scale.js:THEME.floorFadeDecades`);
 * - `text:<repository path>:<snippet>` - for a fact the code states only in
 *   prose or markup: the snippet must appear in the file, and the value must
 *   appear in the snippet.
 *
 * Measured figures (an R̄ on the production file, a lag-1 on a slice) are not
 * constants of the code and do not belong here: the article cites them with
 * their dataset and source.
 */

const entry = (value, source, meaning) => Object.freeze({ value, source, meaning });

export const CONSTANTS = Object.freeze({
  /* ------------------------------------------------ the low-N ladder -- */
  MIN_MOMENT_SAMPLES: entry(2, 'py:calosrv.stats.gaussian:MIN_MOMENT_SAMPLES',
    'Fewest events for which μ, σ and σ/μ are reported as numbers (one degree of freedom at N = 2).'),
  MIN_CURVE_SAMPLES: entry(8, 'py:calosrv.stats.gaussian:MIN_CURVE_SAMPLES',
    'Fewest events for which a parametric density curve is drawn.'),
  MIN_HISTOGRAM_SAMPLES: entry(15, 'py:calosrv.stats.histogram:MIN_HISTOGRAM_SAMPLES',
    'Fewest events for which a density histogram is drawn.'),
  MIN_CORE_SAMPLES: entry(15, 'py:calosrv.stats.gaussian:MIN_CORE_SAMPLES',
    'Fewest events for the iterated ±2.5σ core refit.'),
  MIN_ROBUST_SAMPLES: entry(20, 'py:calosrv.stats.gaussian:MIN_ROBUST_SAMPLES',
    'Fewest events for the robust (IQR) width and the Gaussian-shape verdict.'),
  PROVISIONAL_N: entry(20, 'py:calosrv.grid.frame:PROVISIONAL_N',
    'Below this many co-registered events a fitted display range is labelled provisional.'),
  PROFILE_PROVISIONAL_N: entry(20, 'py:calosrv.stats.profile:PROVISIONAL_N',
    'Below this many showers a profile band is weak and its y range provisional.'),
  MAX_TRAJECTORY_EVENTS: entry(50, 'py:calosrv.query.summary:MAX_TRAJECTORY_EVENTS',
    'Largest selection whose individual trajectories are drawn.'),
  GAUSSIAN_KERNEL_BELOW_N: entry(50, 'py:calosrv.grid.frame:GAUSSIAN_KERNEL_BELOW_N',
    'Below this many co-registered events the Continuous Field uses the Gaussian kernel, from here the tent.'),
  MIN_R_EVENTS: entry(3, 'py:calosrv.stats.jackknife:MIN_R_EVENTS',
    'Fewest events for which a correlation is quoted.'),
  MIN_FISHER_N: entry(4, 'text:calosrv/stats/metrics.py:Fisher-z interval needs N ≥ 4',
    'Fewest pairs for a Fisher-z interval.'),
  MIN_JACKKNIFE_GROUPS: entry(4, 'py:calosrv.stats.jackknife:MIN_JACKKNIFE_GROUPS',
    'Fewest event groups for a jackknife interval.'),
  MAX_GROUPS: entry(64, 'py:calosrv.stats.jackknife:MAX_GROUPS',
    'Most event groups a hit scan rolls its sums into.'),
  MIN_MARDIA_AZIMUTHS: entry(8, 'py:calosrv.stats.jackknife:MIN_MARDIA_AZIMUTHS',
    'Fewest distinct azimuths for which Mardia’s R is quoted.'),
  MIN_MARDIA_GROUPS: entry(5, 'py:calosrv.stats.jackknife:MIN_MARDIA_GROUPS',
    'Fewest groups for a jackknife SE of Mardia’s R.'),
  MIN_ORDER_N: entry(6, 'py:calosrv.stats.median:MIN_ORDER_N',
    'Fewest values for the distribution-free order-statistic interval of a median.'),
  MIN_BOOTSTRAP_N: entry(20, 'py:calosrv.stats.median:MIN_BOOTSTRAP_N',
    'Fewest values for a percentile bootstrap interval.'),
  MIN_CHI2_N: entry(2, 'py:calosrv.stats.rmse:MIN_CHI2_N',
    'Fewest residuals for the χ² interval of an RMSE.'),
  MIN_KDE_SAMPLES: entry(8, 'py:calosrv.stats.kde:MIN_KDE_SAMPLES',
    'Fewest values for a kernel density estimate.'),
  SHAPE_FLOOR_SHOWERS: entry(15, 'js:panels/distribution.js:SHAPE_FLOOR_SHOWERS',
    'Fewer showers than this draw a dashed outline: exact counts, not a distribution.'),
  WEAK_NODE_N: entry(20, 'py:calosrv.modelruns.views:WEAK_NODE_N',
    'Below this many rows a surrogate-tree node is weak and does not set the colour domain.'),

  /* --------------------------------------------------- the estimators -- */
  DDOF: entry(1, 'py:calosrv.stats.gaussian:DDOF', 'Degrees-of-freedom correction of every quoted width.'),
  CORE_SIGMA: entry(2.5, 'py:calosrv.stats.gaussian:CORE_SIGMA', 'Half-width of the core-refit window, in σ.'),
  CORE_ITERATIONS: entry(16, 'py:calosrv.stats.gaussian:CORE_ITERATIONS', 'Iteration cap of the core refit.'),
  CORE_TRUNCATION_FACTOR: entry(0.9365574133, 'py:calosrv.stats.gaussian:CORE_TRUNCATION_FACTOR',
    'k solving k = √f(2.5k): the truncated width over the true width at the refit’s fixed point.'),
  CORE_WINDOW_DRAWN: entry(2.3413935332499998, 'py:calosrv.stats.gaussian:CORE_WINDOW_DRAWN',
    'The ±2.5σ window in units of the drawn (de-biased) σ.'),
  CORE_WINDOW_COVERAGE: entry(0.9807880954122891, 'py:calosrv.stats.gaussian:CORE_WINDOW_COVERAGE',
    'Share of the drawn core Gaussian inside the window that selected its events.'),
  NON_GAUSSIAN_TOLERANCE: entry(0.15, 'py:calosrv.stats.gaussian:NON_GAUSSIAN_TOLERANCE',
    'Relative disagreement of the moment and robust widths above which a sample is flagged non-Gaussian.'),
  IQR_TO_SIGMA: entry(1.349, 'py:calosrv.stats.gaussian:IQR_TO_SIGMA', 'IQR over σ for a Gaussian.'),
  Z_975: entry(1.959963985, 'py:calosrv.stats.gaussian:_Z_975', 'Standard normal 97.5% point.'),
  T_975_DF1: entry(12.706, 'py:calosrv.stats.gaussian:_T_975[1]', 'Student-t 97.5% point, one degree of freedom.'),
  T_975_DF2: entry(4.303, 'py:calosrv.stats.gaussian:_T_975[2]', 'Student-t 97.5% point, two degrees of freedom.'),
  DEFAULT_BINS: entry(120, 'py:calosrv.stats.histogram:DEFAULT_BINS', 'Largest bin count (the reference notebook’s 120).'),
  MIN_BINS: entry(8, 'py:calosrv.stats.histogram:MIN_BINS', 'Smallest bin count worth drawing.'),
  CURVE_POINTS: entry(200, 'py:calosrv.stats.histogram:CURVE_POINTS', 'Points a fitted curve is drawn through.'),
  BOOTSTRAP_REPLICATES: entry(2000, 'py:calosrv.stats.median:BOOTSTRAP_REPLICATES', 'Bootstrap replicates B.'),
  BOOTSTRAP_SEED: entry(42, 'py:calosrv.stats.median:BOOTSTRAP_SEED', 'Seed of every bootstrap.'),
  SILVERMAN_FACTOR: entry(0.9, 'py:calosrv.stats.kde:SILVERMAN_FACTOR', 'Factor of Silverman’s bandwidth rule.'),
  KDE_TRUNCATION_H: entry(4.0, 'py:calosrv.stats.kde:TRUNCATION_H', 'Kernel truncation, in bandwidths.'),
  UNIFORM_P: entry(0.05, 'py:calosrv.stats.circular:UNIFORM_P',
    'Rayleigh p above which directions are consistent with a uniform circle.'),

  /* ------------------------------------------------ momentum classes -- */
  CALIBRATION_CENTRES_GEV: entry([1.0, 2.0, 5.0, 10.0, 15.0, 19.0], 'py:calosrv.stats.momentum:CALIBRATION_CENTRES_GEV',
    'Centres of the calibration notebook’s momentum windows.'),
  HALF_WIDTH_GEV: entry(0.5, 'py:calosrv.stats.momentum:HALF_WIDTH_GEV', 'Half-width of each momentum window.'),
  LABEL_THRESHOLD_GEV: entry(2.0, 'py:calosrv.stats.momentum:LABEL_THRESHOLD_GEV',
    'The aggregate’s binary momentum label: below against at or above this momentum.'),

  /* ------------------------------------------- frames and the display -- */
  CANONICAL_PITCH_MM: entry(20.0, 'py:calosrv.grid.frame:CANONICAL_PITCH_MM',
    'Transverse pitch of the co-registered accumulation grid.'),
  MIN_SUBSAMPLE: entry(2, 'py:calosrv.grid.frame:MIN_SUBSAMPLE', 'Smallest k of the k × k footprint splat.'),
  MAX_SUBSAMPLE: entry(6, 'py:calosrv.grid.frame:MAX_SUBSAMPLE', 'Largest k of the k × k footprint splat.'),
  LOCAL_K_Z: entry(2, 'text:calosrv/query/shower_frames.py:k_z = 2 by default',
    'Depth sub-deposits per cell of the Local frame’s ensemble splat.'),
  EVENT_LOCAL_K_Z: entry(4, 'py:calosrv.query.voxel_event:EVENT_LOCAL_K_Z',
    'Depth sub-deposits per cell of one event’s Local splat (3-D event view).'),
  ILL_CONDITIONED_D_MM: entry(80.0, 'py:calosrv.grid.frame:ILL_CONDITIONED_D_MM',
    'Below this entry separation the D-frame’s rotation ψ is effectively random.'),
  RAMP_DECADES: entry(3.0, 'py:calosrv.grid.frame:RAMP_DECADES', 'Decades of the co-registered relative colour ramp.'),
  SMOOTH_SIGMA_MM: entry(10.0, 'py:calosrv.grid.frame:SMOOTH_SIGMA_MM', 'σ of the Gaussian display kernel.'),
  WINDOW_LOW_PERCENTILE: entry(0.1, 'py:calosrv.grid.frame:WINDOW_LOW_PERCENTILE',
    'Lower energy-weighted percentile of a symmetric panel window.'),
  WINDOW_HIGH_PERCENTILE: entry(99.9, 'py:calosrv.grid.frame:WINDOW_HIGH_PERCENTILE',
    'Upper energy-weighted percentile of a symmetric panel window.'),
  SHOWER_RADIUS_MIN_MM: entry(200.0, 'py:calosrv.grid.frame:SHOWER_RADIUS_MIN_MM',
    'Smallest half-width of a provisional window.'),
  WINDOW_FLOOR_FOOTPRINTS: entry(2, 'py:calosrv.grid.frame:WINDOW_FLOOR_FOOTPRINTS',
    'Smallest half-width of a robust window, in cell footprints.'),
  KERNEL_TAIL_Z: entry(9.0, 'py:calosrv.grid.kernel:TAIL_Z', 'The Gaussian kernel’s tail is exactly zero beyond this many σ.'),
  COMB_THRESHOLD: entry(-0.1, 'py:calosrv.query.stagger:COMB_THRESHOLD', 'Lag-1 autocorrelation below which a profile is combed.'),
  COMB_EDGE_MARGIN: entry(0.15, 'py:calosrv.query.stagger:EDGE_MARGIN', 'Fraction of each axis end left out of the comb test.'),
  COMB_DETREND_WINDOW: entry(9, 'py:calosrv.query.stagger:DETREND_WINDOW', 'Bins of the moving average the comb test detrends with.'),
  WINDOW_AXIS_MM: entry(300, 'text:calosrv/query/window_axis.py:300 mm windows',
    'Width of the entry-position windows in which the absolute-frame ensemble axis was measured.'),
  LEAN_RATIO_MIN: entry(1.0, 'py:calosrv.query.window_axis:LEAN_RATIO_MIN',
    'The mean lean must reach this many SDs of the slopes for the windowed axis to be drawn in full.'),
  EVENT_WINDOW_MIN_HALF_MM: entry(150.0, 'py:calosrv.query.event_inspector:WINDOW_MIN_HALF_MM',
    'Smallest half-width of one event’s window.'),
  EVENT_WINDOW_SNAP_MM: entry(20.0, 'py:calosrv.query.event_inspector:WINDOW_SNAP_MM',
    'One event’s window is snapped outward to this many millimetres.'),
  MAX_VOXELS_PER_AXIS: entry(256, 'py:calosrv.query.voxel_event:MAX_VOXELS_PER_AXIS',
    'Most voxels per axis of one event’s 3-D splat.'),
  CLOUD_VOXEL_MERGE: entry(2, 'py:calosrv.query.voxels:MERGE',
    'The ensemble cloud’s voxels merge this many 20 mm bins per axis.'),
  NEG_DEPTH_THRESHOLD_MM: entry(1e-6, 'py:calosrv.query.negative_depth:THRESHOLD_MM',
    'A hit with w below minus this is behind its shower’s entry plane.'),

  /* ------------------------------------------------ payload and codes -- */
  RESPONSE_LIMIT: entry(100000, 'py:calosrv.query.density:RESPONSE_LIMIT',
    'Encoded-size ceiling, in bytes, the panel guard steers under (the 100 KB contract).'),
  RHO_UNIT: entry('GeV/mm^2/event', 'py:calosrv.query.density:RHO_UNIT', 'Unit of the ensemble-averaged density ⟨ρ⟩.'),
  EMPTY_CODE: entry(0, 'py:calosrv.encode.quantize:EMPTY_CODE', 'The colour code of a bin with no deposit.'),
  MIN_CODE: entry(1, 'py:calosrv.encode.quantize:MIN_CODE', 'First colour code of the Absolute-frame ramp.'),
  MAX_CODE: entry(255, 'py:calosrv.encode.quantize:MAX_CODE', 'Last colour code.'),
  LEVELS: entry(254, 'py:calosrv.encode.quantize:LEVELS', 'Usable steps of the Absolute-frame ramp.'),
  BELOW_CODE: entry(1, 'py:calosrv.encode.quantize:BELOW_CODE',
    'Co-registered panels: populated, but below the display floor (not drawn).'),
  SPLIT_CODE: entry(129, 'py:calosrv.encode.quantize:SPLIT_CODE', 'First code of the positive half of a signed-log ramp.'),
  SIGNED_MIN_CODE: entry(2, 'py:calosrv.encode.quantize:SIGNED_MIN_CODE', 'First code of a signed-log ramp.'),
  TOPK: entry(64, 'py:calosrv.encode.topk:DEFAULT_K', 'Brightest cells shipped with their exact values.'),
  TOPK_SIGNIFICANT: entry(7, 'py:calosrv.encode.topk:SIGNIFICANT',
    'Significant figures of an exact value: the float32 source’s precision.'),
  LAB_DECADES: entry(6.0, 'py:calosrv.encode.scale:DEFAULT_DECADES',
    'Decades of the Absolute-frame log ramp below the brightest cell.'),

  /* --------------------------------------------------- the detector -- */
  CORE_SHIFT_Z_MM: entry(3649.0, 'py:calosrv.db.ddl:CORE_SHIFT_Z_MM',
    'Display offset of depth below the front face; volumes, densities and centroids stay raw.'),
  FIRST_LAYER_Z_MM: entry(3662.4, 'text:calosrv/grid/lattice.py:3662.4', 'Raw z of the first layer.'),
  Z_PITCH_MM: entry(20.5, 'py:calodash.constants:Z_PITCH_MM', 'Longitudinal layer pitch.'),
  N_LAYERS: entry(60, 'py:calodash.constants:N_LAYERS', 'Layers along depth.'),
  X_CELLS: entry(212, 'text:calosrv/db/ddl.py:212 distinct values', 'Distinct transverse x cell positions.'),
  Y_CELLS: entry(104, 'text:calosrv/grid/lattice.py:104 cells', 'Distinct transverse y cell positions.'),
  CELL_X_MM: entry(48.27, 'text:calosrv/query/shower_frames.py:48.27 x 48.6 mm', 'Cell footprint along x.'),
  CELL_Y_MM: entry(48.6, 'text:calosrv/query/shower_frames.py:48.27 x 48.6 mm', 'Cell footprint along y.'),

  /* --------------------------------------------------- the XGBoost cards -- */
  KFOLD_SPLITS: entry(5, 'py:calosrv.modelruns.analysis:KFOLD["n_splits"]', 'Folds of the cross-validation (E1).'),
  TEST_SIZE: entry(0.2, 'py:calosrv.modelruns.analysis:TEST_SIZE', 'Hold-out share of the training split.'),
  SPLIT_SEED: entry(42, 'py:calosrv.modelruns.analysis:SPLIT_SEED', 'random_state of the notebooks’ split.'),
  CHECK_SEEDS_N: entry(99, 'py:calosrv.modelruns.analysis:len(CHECK_SEEDS)',
    'Other seeds the training-split check compares against.'),
  SPLIT_MARGIN_MOMENTUM: entry(1.05, 'py:calosrv.modelruns.analysis:SPLIT_MARGIN["momentum"]',
    'Margin by which seed 42 must clear the other seeds (momentum task).'),
  SPLIT_MARGIN_ANGLE: entry(1.6, 'py:calosrv.modelruns.analysis:SPLIT_MARGIN["angle"]',
    'Margin by which seed 42 must clear the other seeds (angle task).'),
  BINARY_THRESHOLD_GEV: entry(2.0, 'py:calosrv.modelruns.analysis:BINARY["threshold"]',
    'Threshold of the binary classification (E3).'),
  BINARY_CLASS_1_ABOVE_GEV: entry(10.0, 'py:calosrv.modelruns.analysis:BINARY["class_1_above"]',
    'Class 1 of E3’s sample is drawn from above this momentum.'),
  BINARY_TOTAL: entry(2000, 'py:calosrv.modelruns.analysis:BINARY["total"]', 'Rows of E3’s designed sample.'),
  BINARY_FRACTION_0: entry(0.99, 'py:calosrv.modelruns.analysis:BINARY["fraction_0"]', 'Designed share of class 0 (99 : 1).'),
  BINARY_FRACTION_1: entry(0.01, 'py:calosrv.modelruns.analysis:BINARY["fraction_1"]', 'Designed share of class 1.'),
  SURROGATE_MAX_DEPTH: entry(3, 'py:calosrv.modelruns.analysis:SURROGATE["max_depth"]', 'Depth of the surrogate tree (E4).'),
  LOW_FIDELITY_R2: entry(0.5, 'py:calosrv.modelruns.views:LOW_FIDELITY_R2',
    'Per-output surrogate fidelity below which the card warns (φ on the circular R²).'),
  TOP_N_FEATURES: entry(15, 'js:panels/xgb_importance.js:TOP_N', 'Features drawn on the gain-importance card (E5).'),

  /* ------------------------------------------------ on-screen display -- */
  FLOOR_FADE_DECADES: entry(0.5, 'js:scale.js:SCREEN_THEME.floorFadeDecades',
    'On screen, the decade above the display floor across which a ramp fades in.'),
  RAMP_CONTRAST: entry(3, 'js:scale.js:RAMP_CONTRAST', 'WCAG contrast every drawn colour must reach against the card.'),
  VIRIDIS_LEGIBLE_FROM: entry(0.376, 'js:panels/chart_panel.js:Number(legibleRamp("viridis").from.toFixed(3))',
    'Position on Viridis of its first colour with 3:1 contrast against the card.'),
  RESOLUTION_DEFAULT: entry(150, 'js:state.js:DEFAULTS.resolution', 'Default display resolution R.'),
  RESOLUTION_MIN: entry(50, 'text:calosrv/static/index.html:min="50" max="400" step="10"', 'Smallest display resolution R.'),
  RESOLUTION_MAX: entry(400, 'text:calosrv/static/index.html:min="50" max="400" step="10"', 'Largest display resolution R.'),
  READOUT_SHARE: entry(0.2, 'js:panels/tooltip.js:READOUT_SHARE',
    'Largest share of the hovered plot a pointer readout may cover.'),
});

/** The values alone, for the prose: `${C.MIN_CURVE_SAMPLES}`. */
export const C = Object.freeze(Object.fromEntries(Object.entries(CONSTANTS).map(([key, { value }]) => [key, value])));
