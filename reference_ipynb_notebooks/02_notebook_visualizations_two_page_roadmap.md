# The other notebooks: visualization inventory and a two-page dashboard roadmap

What the seven remaining notebooks draw, which of it `calosrv` already serves,
how the rest could be built, and which database columns and tables that would
need. The companion document
`01_local_coords_vs_calosrv_se3_audit.md` covers the coordinate
transformations; this one refers to it where a figure depends on them.

Scope and method. Every notebook was read cell by cell (code, markdown and
printed outputs). The data they load are not in this repository: the
single-particle standalone files
(`{proton,pion,electron,muon}_standalone_N100000_M0_20GeV_reg_balanced_s{1,2}_v3.csv`,
21 columns, ~55 M hits each), the five fixed-energy ddsim proton files
(`ddsim_vertex0_{1,2,5,10,20}GeV_proton_N100000_*.csv`, 8 columns) and the
aggregated per-event files (`*_aggr_s{1,2}_v2.csv`, 29 columns). Nor is the
`core` / `robi.core` module they import, so two feature definitions below are
inferred from printed rows and said to be. The dashboard's data is the
two-shower `hits_all_models` schema (99 columns, `calosrv/db/ddl.py`).

The target layout the user asked for:

- **Page 1, Physics.** The existing 2 × 2 diagnostic (three spatial panels
  and the reconstructed-energy panel) plus the physics figures below.
- **Page 2, Model analysis.** The XGBoost-style model evaluation, the
  network comparisons, the feature explorer and every 3-D interactive view.

One concern to state before the plan. CLAUDE.md §2 lists "3D projections"
among the chartjunk to eliminate. That rule targets decorative depth (3-D
bars, extruded pies); the notebooks' 3-D event displays show genuinely
three-dimensional voxel data, which is the LFHCal "blue box" display the
physics group uses. The roadmap keeps them, under constraints that make them
data rather than decoration (§2.3): orthographic projection, 1:1:1 metric
aspect, one mark per cell, no perspective shading, always beside the 2-D
projections that carry the numbers, and never exported as the figure of
record. If the team reads the rule more strictly, §2.3 is the part to drop
and nothing else depends on it.

---

## 1. Inventory

Status: **exists** (served today), **partial** (the quantity exists, the
figure does not), **missing**. Page: P1 / P2. DB: what the figure needs
beyond today's tables (details in §3.4).

### 1.1 `coordinate_transformatioons/local-coords.ipynb` (see document 01)

| ID | Figure | Status | Page | DB |
|---|---|---|---|---|
| A1 | Per-event comparison: original / translated / local, 3 × 3 scatter with direction, first-layer plane, origin, principal-axis tilt | missing | P1 | none (document 01, §3.3) |
| A2 | Ensemble 3 × 3 energy-weighted 2-D histograms, global / translated / superimposed | exists as three frames, one at a time | P1 | none (side-by-side layout, document 01, §3.4) |

### 1.2 `sofiya_visualizations/CALIBRATION_proton_pion-v1.ipynb`

| ID | Figure | What it computes | Status | Page | DB |
|---|---|---|---|---|---|
| B1 | Sampling-fraction distribution per particle: histogram of `Σ E_dep / p_incident` per event (%), mean line, N, σ, scaling factor `1/mean` | per-event ratio, mean of ratios | partial: `energy.py` fits `c = Σp / ΣE_dep` over the selection (sum-before-divide, deliberately not the mean of ratios) and ships `sampling_fraction_a/b`; no distribution is drawn | P1 | none: `e_dep`, `e_a_true_*`, `e_b_true_*`, `e1`, `e2` are in the event table |
| B2 | Sampling fraction vs incident momentum: 1 GeV bins 0–20, mean ± SE error bars (`std/√n`), scaling factor per bin | per-bin mean of per-event ratios | missing | P1 | none |
| B3 | "Tamas' style" response grid: at p = 1, 2, 5, 10, 15, 19 ± 0.5 GeV, histogram of total visible energy, `curve_fit` Gaussian, stats box (entries, mean, std, χ²/ndf, prob, constant ± err, mean ± err, σ ± err) | least-squares Gaussian on 50 bins | partial: plot 4 is the same construction sliced by D instead of p, with moment fits and a core refit (no χ²) | P1 | none |

### 1.3 `sofiya_visualizations/High_energy_notebook_proton_pion-v5.ipynb`

| ID | Figure | Status | Page | DB |
|---|---|---|---|---|
| C1 | Comparative `describe()` table of `x_local, y_local, z_local, r_local, energy` per dataset (mean, std, min, quartiles, max), rendered as an image | missing; dataset-wide energy-weighted quantiles of `xt, yt, xl, yl, zl` exist in the registry (`frame_bounds`) but not per selection and not unweighted | P1 | none for a query-time version |
| C2 | = A1 (same function, plus particle type and momentum in the row label) | missing | P1 | none |
| C3 | = A2 | exists | P1 | none |
| C4 | Linear and log-y histograms of `x_local, y_local, z_local, energy, incoming_momentum, incoming_theta, incoming_phi` per `incoming_momentum_bin` (20 hues, 100 bins, 50 k-row sample), one subplot per dataset | missing | P1 | none: `e1_bin`/`e2_bin` and the hit columns exist |
| C5 | 3-D event display in the local frame, cells as squares coloured by energy (densest event by default) | missing; no 3-D series in the frontend, ECharts 5.6.0 only, no `echarts-gl` | P2 | none for the voxel payload |
| C6 | 3-D event display coloured by **secondary particle species**, primaries edged in black, legend of species | missing | P2 | **new hit columns**: `particle_type`, `is_secondary` (and `parent_type`, `daughter_type` if wanted) are not in the schema |
| C7 | Longitudinal profile (energy deposit per cm (%) vs depth `z_local`) and radial profile (vs `r_local = √(x′² + y′²)`), 20 mm / 10 mm bins, step lines | missing | P1 | none at query time; a per-(event, shower, layer) table recommended for per-event dispersion (§3.4) |
| C8 | Pearson correlation heatmap of `x_local, y_local, z_local, energy, incoming_momentum, incoming_theta, incoming_phi`, annotated, `coolwarm` | missing | P1 | none (`corr()` in DuckDB) |
| C9 | Negative `z_local` diagnostics: events with any hit at `z_local < −10⁻⁶ mm`, fraction of hits per event, energy fraction at negative depth, split by p < 1 GeV / p > 10 GeV; prints a table | missing; the Local grid's depth starts at the 10⁻⁴ energy quantile, so negative w is inside the grid and is not separately counted | P1 | none at query time; two cheap event-table columns make it free (§3.4) |
| C10 | Superimposed 3 × 3 for low (< 1 GeV) and high (> 10 GeV) energy subsets | exists through the E₁ / E₂ sliders | P1 | none |
| C11 | Mislabelling diagnostic: events with no primary-tagged hit (`is_secondary == 0` absent), 25–27% of events | missing; needs `is_secondary` | P2 | new hit column (as C6) |

### 1.4 `hit_level_analysis/features-by-events-class.ipynb`

The notebook derives 19 per-event features from raw hits (5 fixed-energy
proton datasets, "class" = incident energy 1 / 2 / 5 / 10 / 20 GeV) and
explores them. `core.process_event_data` is not available; the definitions
below are the markdown's, corrected where the printed rows contradict it.

| Feature | Definition (as inferred) | Check against printed row (event 2, 1 GeV) |
|---|---|---|
| `width`, `height` | `x_max − x_min`, `y_max − y_min` | 52.674 = 1541.746 − 1489.072; 101.0 ✓ |
| `depth` | **`z_max`** (depth reached; the markdown says `z_max − z_min`) | 190.4 with z ∈ {169.9, 190.4} ✓ |
| `depth_range` | `z_max − z_min` | 20.5 ✓ |
| `volume` | `width · height · depth` (bounding box; floored at 10⁻⁶ per side) | 52.674 × 101.0 × 190.4 = 1.0129 × 10⁶ ✓ |
| `num_hits` | rows after `drop_duplicates` on (event, x, y, z, energy) | 4 ✓ |
| `total_hit_energy` | Σ `hit_energy` | |
| `centroid_x/y/z` | **unweighted** arithmetic mean of hit positions (the dashboard's centroids are energy-weighted) | |
| `mean_r`, `std_r`, `max_r` | statistics of `r = √(x² + y² + z²)` of each hit from the detector origin after the z shift (3649 mm) | |
| `weighted_r_mean` | energy-weighted mean `r` | |
| `avg_theta`, `avg_phi` | mean polar / azimuth angle of the hit position vectors (mean θ ≈ 1.46 rad confirms position vectors, not incident directions); `avg_phi` is an arithmetic mean of a circular quantity | |
| `angular_spread` | not recoverable from the outputs (a dispersion of the hit angles); must be pinned at implementation | |
| `numerical_density`, `energy_density` | `num_hits / volume`, `total_hit_energy / volume` | |

| ID | Figure | Status | Page | DB |
|---|---|---|---|---|
| D1 | Feature table per event (19 features), one per energy class | missing | P2 | **new event-table columns** (§3.4) |
| D2 | `describe()` tables: count / mean / std / min / max / quartiles per feature and class | missing | P2 | as D1 |
| D3 | Pearson heatmap of the 19 features, one per class | missing | P2 | as D1 |
| D4 | Linear and log-x histograms with KDE of each feature, the 5 classes overlaid (50 k sample, 100 bins) | missing | P2 | as D1 |
| D5 | Scatter of each feature vs `total_hit_energy`, one subplot per class, hue and size by energy (30 k sample) | missing | P2 | as D1 |

### 1.5 `xgboost_model_visualization/XGBoost-Reg-{Proton,Pion,Electron,Muon}.ipynb`

The four notebooks are the same code on four inputs (diff checked: only the
input paths, row counts and printed numbers differ). Inputs: the aggregated
per-event files (the 19 features of §1.4 plus `incoming_momentum`,
`incoming_theta`, `incoming_phi`, `incoming_momentum_bin`, four `gnn_*`
columns and `energy`). Models: `XGBRegressor(objective='reg:squarederror',
n_estimators=100, learning_rate=0.1, random_state=42)`; target IM =
`incoming_momentum`, target IA = `[incoming_theta, incoming_phi]`
(multi-output).

| ID | Figure / table | Status | Page | DB |
|---|---|---|---|---|
| E1 | 5-fold CV table per seed and target: MAE, MSE, RMSE, R² per fold (momentum R² ≈ 0.88 proton, 0.87 pion, 0.96 electron, 0.22 muon; angle R² ≈ 0.95–0.98) | missing | P2 | **model-run tables** (§3.4) |
| E2 | Per-`incoming_momentum_bin` grouped bars on an 80/20 split: RMSE, MAE, mean relative error (%), two seeds side by side; for IM and for IA | missing as drawn; **the dashboard's analogue exists in the data today**: the energy and angle networks' per-shower predictions and `e1_bin`/`e2_bin` are in the event table, and `performance.py` already breaks the cards down by D slice | P2 | none for the networks; model-run tables for XGBoost |
| E3 | Binary performance on an asymmetric validation set: class 0 = p < 2 GeV, class 1 = p > 10 GeV, sampled 99 : 1 of 2 000 (printed 1 876 / 20 and 1 818 / 20), regression output thresholded at 2 GeV; accuracy, balanced accuracy, weighted precision / recall / F1, class counts | missing | P2 | model-run tables (predictions) |
| E4 | Surrogate `DecisionTreeRegressor(max_depth=3)` fitted to the XGBoost predictions, drawn with `plot_tree`; fidelity R² (0.90 momentum, 0.48 angle) and MAE vs the booster | missing | P2 | model-run tables (surrogate nodes) |
| E5 | Feature-importance bars ("Average Gain"), two seeds side by side, for IM and IA | missing | P2 | model-run tables (importances) |

None of the XGBoost work can run inside the dashboard as the notebooks run
it: training belongs to the analysis pipeline, and CLAUDE.md §3 forbids
fabricating model outputs. The AI page therefore **ingests model artefacts**
(§3.4) and draws them, and shows the baseline warning banner when none are
loaded.

---

## 2. Perceptual & Statistical Audit of the proposed panels

Each entry: marks, scales, uncertainty, palette, and the CLAUDE.md rule it
answers to. IDs refer to §1.

### 2.1 Page 1, Physics

**Longitudinal and radial profiles (C7).** Two step charts in the Local
frame: energy fraction per cm against depth w, and against radius
`r = √(u² + v²)` from the shower axis, both starting at zero. The notebook
draws one line of the pooled selection; the dashboard draws the pooled
profile as the line, the **sample SD of the per-event profiles** as an
uncapped shaded band, and the **Student-t 95% interval of the mean** as a
thin capped envelope, two marks, each named in its tooltip (§2 whisker rule).
The depth axis keeps the 20.5 mm layer pitch (never smoothed); the radial
axis uses 10 mm bins from the footprint-splatted accumulation, with the
energy outside the grid stated. Normalisation per cm and in percent as the
notebook. Pooled over both showers of an event, or per shower by the
existing A / B / Both control. Palette: one colour per shower from the
existing theme; no fill under the line.

**Response and resolution vs incident momentum (B1, B2, B3).** Three
linked views from the event table alone:

- B1: a density histogram of the per-event sampling fraction
  `E_dep,S / p_S` per shower, with the mean (capped t-whisker) and the
  fitted calibration constant `1/c_S` marked as a reference rule and
  labelled as the sum-before-divide estimator the energy panel uses, so the
  two definitions are visibly different numbers.
- B2: mean sampling fraction per 1 GeV momentum bin with the **t-interval
  of the mean** as the capped whisker (the notebook's `std/√n` normal
  interval understates it at small n) and the SD as a faint band; bar
  counts in the tooltip.
- B3: the notebook's response grid becomes the existing plot 4 with the
  slice axis switched from D to incident momentum (`slice_by=momentum`, with 1 GeV
  slices centred on the notebook's momenta, its ±0.5 GeV windows, or any
  edges the user sets): the same moment fit,
  core refit, low-N ladder and (μ, σ) table, plus a resolution summary
  `σ/μ vs p` with the σ χ² interval as its whisker. No χ²/ndf is quoted: the
  dashboard's estimator is moment-based by design (`stats/gaussian.py`), and
  the notebook's least-squares fit to 50 bins is the bin-count-dependent
  figure that design rejects. The notebook's Gaussian amplitude ("Constant")
  has no counterpart because the curve is unit-area.

**Distributions by momentum bin (C4).** Server-side histograms of the
per-hit `u, v, w`, hit energy, and the per-shower θ, φ, p, grouped by the
shower's momentum bin. Twenty ordered series on **Viridis** (ordered, so a
sequential ramp; Turbo is permitted but a 20-step categorical reading of it
is not needed). Linear and log-y toggle, with "log" written in the axis
title; bars start at zero; counts, not densities, so no density gate
applies. The 50 k-row sample of the notebook is replaced by exact counts
from DuckDB. Energy on a log-x axis with the 1st–99th percentile range and
the outside count disclosed.

**Correlation heatmap (C8).** Pearson r over the selection's hits, computed
by DuckDB's `corr()`, drawn on the **PuOr diverging ramp**, symmetric about
zero, with the value and the Fisher-z 95% interval in the tooltip and N in
the title; `coolwarm` is not in the permitted set. Note on the panel that
`φ` is circular and its linear correlations are not interpretable; the cell
is drawn hatched.

**Negative-depth diagnostics (C9).** A small card in the Local frame's
Details drawer and on the status bar: events with any hit at w < −10⁻⁶ mm,
the fraction of hits and of energy at negative w, overall and for the
current selection. Numbers only; no mark on the depth panels beyond the
existing w = 0 rule. The 10⁻⁶ mm tolerance is the notebook's and is stated.

**Selection statistics table (C1).** Per selection, per frame: count, mean,
SD, min, quartiles, max of each coordinate and of the hit energy, unweighted
as the notebook's `describe()`, beside the energy-weighted quantiles the
window fit already uses, labelled as two different weightings. Served as a
table, not an image.

**Event Inspector (A1, C2)** and **side-by-side frames (A2, C3)**: document
01, §3.3–3.4.

### 2.2 Page 2, Model analysis

**Per-momentum-bin error bars (E2), networks first.** For the energy and
angle networks (three frames each): RMSE, MAE and relative error per
`incoming_momentum_bin` of the shower, bars starting at zero, with the
**t-interval of the mean absolute residual** as capped whiskers and N per
bin in the tooltip. Relative error `|ŷ − y| / y` diverges as y → 0; report
the **median** relative error with a bootstrap interval, and say so, rather
than the notebook's mean. For the angle target the notebooks regress φ with
squared error across the ±π wrap; the dashboard reports θ (the networks
predict θ only) and, for imported runs that predict φ, wraps the residual to
(−π, π] before any statistic (§2 circular rule). Imported XGBoost runs appear
as further series on the same axes, labelled by run.

**Cross-validation table (E1).** A table per run: fold, MAE, MSE, RMSE, R²,
plus mean ± SD over folds. Numbers come from the artefact; nothing is
recomputed.

**Binary performance (E3).** The notebook's construction (threshold at
2 GeV, 99 : 1 class mix) recomputed from the imported predictions on the
server, with the class counts, the confusion matrix and Wilson intervals on
the rates; the mix and threshold are controls, their defaults the
notebook's, and the imbalance is stated beside every rate.

**Surrogate tree (E4).** A node-link diagram of the depth-3 surrogate from
the artefact's node table (feature, threshold, value, N per node), fidelity
R² and MAE against the booster in the title. Drawn with ECharts' `tree`
series; node fill encodes the predicted value on Viridis, node size the
sample count. The tree is an *explanation of a model*, not a measurement,
and the drawer says so.

**Feature importance (E5).** Horizontal bars from zero, one panel per run,
the importance type named ("gain", as xgboost's default and the notebook's
axis label). Where the artefact carries per-fold importances, the SD over
folds is the uncapped band and the t-interval the whisker.

**Prediction vs truth (new, enables E1–E3 to be read).** A 2-D density
(server-side `hist2d` of the per-shower predictions) with the identity line
and the residual histogram beneath; the per-event points themselves are not
shipped (20 000 events × 2 floats is over the contract and is a raw point
array in spirit). Available today for the six per-shower networks.

**Feature explorer (D1–D5).** Once the per-event features exist: D2 as a
table; D3 as the PuOr heatmap above; D4 as server-side histograms by energy
class (`e1_bin`, or an explicit class column for single-shower datasets)
with the KDE drawn only above the N ≥ 8 curve floor and the histogram above
N ≥ 15, per class; D5 as a 2-D density of feature vs total energy per class
instead of a 30 k-point scatter. Log-x for the features that span decades
(`volume`, densities, `total_hit_energy`), stated on the axis.

### 2.3 3-D interactive views (C5, C6, and two new ones)

Constraints, as stated at the top: orthographic camera, 1:1:1 metric aspect
locked, cells drawn as cubes of their measured footprint (48.27 × 48.6 ×
20.5 mm), no perspective or light-and-shade beyond a flat fill, rotation and
zoom only, Viridis / Cividis / Plasma for energy, PuOr for signed Shap-CAM,
and the 2-D projections of the same event drawn beside it as the
quantitative view. Export remains the 2-D panels.

- **Single-event voxels (C5).** One event, in the frame of the user's
  choice (Absolute, D-frame, Local, Per-shower translated): one cube per
  cell, coloured by energy on the event's own log ramp with the notebook's
  1st-percentile floor. Colour channel switchable to the selected network's
  Grad-CAM, Shap-CAM, or the **segmentation error** `|f_A,pred − f_A,true|`
  per cell, which is the AI-page reading of the same display. Payload: one
  row per cell (ordinals `ix, iy, iz` or 20 mm bin indices, shower code,
  quantised value), ≈ 5 bytes per cell before JSON; a 2 000-cell event is
  ≈ 15 KB. This is the finest payload the service will ever emit; it is a
  per-cell aggregate, capped at a stated cell count with the energy beyond
  the cap counted.
- **By particle species (C6)** needs `particle_type` and `is_secondary`
  per hit, which the schema lacks. With them: categorical colour from the
  ColorBrewer qualitative set, primaries outlined, a legend of species with
  counts. Without them the control is absent and the drawer says why.
- **Ensemble voxels (new).** The D-frame or Local accumulation grid as a
  sparse voxel cloud above the 10⁻³ display floor at 40 mm (merged 2 × 2 ×
  2 from the 20 mm grid; depth kept at the layer pitch). Capped at ≈ 15 000
  voxels (≈ 75 KB) by energy rank, with the energy fraction drawn stated,
  ρ_ref and N printed, and the provisional label below N = 20 as in 2-D.
- **Attention in 3-D (new).** The ensemble voxels coloured by the
  energy-weighted CAM channel of the selected network, with the same floor
  and the same per-event-normalisation caveat the 2-D channels carry.

Rendering: vendor `echarts-gl` (an ECharts-5-compatible release, pinned, ≈
1.3 MB, WebGL) for `scatter3D` / `bar3D` with `projection: 'orthographic'`;
when WebGL is unavailable the card shows the 2-D projections and a notice.
The alternative, a `custom` series with a client-side orthographic
projection of a few thousand cubes, needs no new vendor file and is worth a
day's spike before committing to GL.

---

## 3. Execution & Data Requirements

### 3.1 Two pages

Two entry points, one codebase:

- `/` stays the physics page: `static/index.html` and `js/main.js`, untouched
  in layout so every browser test and the admin defaults keep their meaning.
- `/models` serves `static/models.html` with its own bootstrap
  `js/models_main.js`, mounted by the same `app.py` route pattern (asset
  stamping, `no-cache`). A header tab on both pages links across.
- Shared: `state.js` (the hash carries `table_name`, the three filters,
  frame and model, so a link from one page opens the other on the same
  selection), `api.js`, `labels.js`, `palette.js`, `scale.js`, `format.js`,
  `shell.js` (sidebar, drawer), `panel_notes.js` (extended), `export/*`.
  The sidebar's filter block is shared markup; each page adds its own
  control blocks below it.
- Page 1 gains a second row of cards whose slots are chosen from a list
  (profiles, response, distributions, correlation, inspector, statistics);
  the default view stays the 2 × 2 grid, and the admin defaults may name
  the extra cards. Page 2 is a grid of the cards in §2.2–2.3.

A single-page tab switch was considered and rejected: it would put the new
cards' DOM under the existing ResizeObservers and tests (see the
snap-layout rule in `shell.js`), for no gain a link cannot give.

### 3.2 Vendoring

- `echarts-gl`, pinned, under `static/js/vendor/`, loaded only by
  `models.html`. Offline and air-gapped operation is unchanged.
- No other frontend dependency. No Python dependency for the AI page: the
  server reads artefacts, it does not train. (If the team later wants
  in-service training, `xgboost` and `scikit-learn` become optional
  extras behind an admin action; not in this roadmap.)

### 3.3 New API routes

All under the 100 KB response contract, filtered by the existing
`FilterDep`, served from the event table or a cached bundle unless noted.

| Route | Serves | Reads |
|---|---|---|
| `GET /api/profiles` | C7: longitudinal and radial profiles, pooled line, SD band, t-envelope, per shower | Local-frame bundle (longitudinal = column sums of the depth panels); radial from a new `GROUP BY floor(r/10)` scan, cached like a bundle; per-event dispersion from the per-layer table (§3.4) |
| `GET /api/response` | B1, B2, B3: sampling-fraction distribution, per-bin means, `slice_by=momentum` for the energy panel's machinery | event table |
| `GET /api/distributions` | C4: histograms by momentum bin | projection table (one grouped scan per quantity, cached) |
| `GET /api/correlations` | C8, D3: Pearson matrix with N and Fisher-z intervals | projection table (hit-level) or event table (features) |
| `GET /api/statistics` | C1: per-coordinate `describe()` per frame | projection table |
| `GET /api/event` | A1 / C2 inspector rasters and marks; C5 voxels (`format=voxels`) | projection + event tables; document 01, §3.3 |
| `GET /api/voxels` | ensemble voxel cloud, D-frame or Local, with the CAM channel | cached canonical / local bundle |
| `GET /api/model-performance?slice_by=momentum_bin` | E2 for the networks (extension of the existing route) | event table |
| `GET /api/model-runs`, `/api/model-runs/{id}` | E1, E3, E4, E5 and the prediction density for imported runs | model-run tables |
| `POST /api/model-runs` (admin) | artefact upload | writes the model-run tables |
| `GET /api/features` | D2, D4, D5 | event table (new columns) |

`GET /api/projections` is unchanged. The Local-frame diagnostics (C9) ride
in that route's `frame` block once the two event-table columns exist.

### 3.4 Database additions

The question asked: which of this needs new columns or tables. Four groups,
from none to a schema change.

**Group 0, no change (buildable now).** B1–B3, C1, C4, C7 (query-time), C8,
C10, A1/C2, A2/C3, C5 (energy / CAM / segmentation-error colouring), the
ensemble voxel views, E2 for the six per-shower networks, the prediction
density, and the per-momentum-bin cards. Everything they need is in the
event table (`e1, e2, e1_bin, e2_bin, theta_*, phi_*, e_dep, e_{a,b}_{true,pred}_*,
en_pred_*, th_pred_*, en_true_*, th_true_*, p0*, c*`) or the projection
table (`ix, iy, iz, xt, yt, kt, xl, yl, zl, energy, org`, the CAM and
segmentation columns).

**Group 1, cheap derived columns on the event table** (filled at ingest by
`derive_events.py`, appended by `registry.ensure_registry`-style migration;
per shower, suffix `_a` / `_b`):

| Column(s) | For | Definition |
|---|---|---|
| `w_neg_hits_{a,b}` BIGINT, `w_neg_energy_{a,b}` DOUBLE | C9 | hits and energy at `z_local < −10⁻⁶ mm` |
| `p0_def_residual_mm` DOUBLE (one per event, max over showers) | document 01 §3.5 | `|p0 − first-layer centroid|` |
| `anchor_residual_mm_{a,b}` DOUBLE | document 01 §3.2 | `|entry_S − P0_S|` in the transverse plane |
| `x_min/x_max/y_min/y_max/z_min/z_max_{a,b}` REAL | D1 `width, height, depth, depth_range, volume` | bounding box of the shower's cells |
| `n_cells_{a,b}` BIGINT | D1 `num_hits` (the notebook's count is of distinct cells after `drop_duplicates`) | distinct `cellID` per shower; today's `n_a_rows` counts rows |
| `cx_mean/cy_mean/cz_mean_{a,b}` REAL | D1 `centroid_*` (unweighted) | arithmetic mean of cell positions |
| `sum_r_{a,b}`, `sum_r2_{a,b}`, `max_r_{a,b}`, `sum_er_{a,b}` DOUBLE | D1 `mean_r, std_r, max_r, weighted_r_mean` | `r` from the detector origin as the notebook; `sum_er` = Σ E·r |
| `sum_theta_{a,b}`, `sum_theta2_{a,b}`, `sum_cos_phi_{a,b}`, `sum_sin_phi_{a,b}` DOUBLE | D1 `avg_theta, avg_phi, angular_spread` | per-cell position angles; φ stored as circular sums so the mean is a resultant, not an arithmetic mean; `angular_spread` pinned as the SD of θ unless the group recovers `core.process_event_data` |
| `sum_e_rl_{a,b}`, `sum_e_rl2_{a,b}` DOUBLE | C7 radial summary (energy-weighted mean and RMS radius about the shower axis) | Σ E·r_local, Σ E·r_local² |

`volume`, the two densities and every mean are derived at query time from
these sums, so the table stays additive and the metrics roll up over any
selection as the segmentation statistics do.

**Group 2, one new derived table** (recommended, not required):
`layers_<name>` with one row per (event, shower, own-shower layer `kt`):
`e_dep`, `n_cells`, Σ E·u, Σ E·v, Σ E·r_local, Σ E·r_local². About
20 000 × 2 × 60 = 2.4 M rows. It makes the per-event longitudinal profiles,
their SD band and the per-layer shower axis free, where today the
dispersion would need a 24 M-row scan per request.

**Group 3, model artefacts** (new tables, filled by an admin upload of a
JSON or Parquet bundle exported from the training notebooks; nothing is
ever computed from scratch here):

| Table | Columns |
|---|---|
| `model_run` | `run_id`, `name`, `library` (xgboost, …), `task` (momentum, angle, …), `target_columns`, `feature_columns` (list), `hyperparameters` (JSON), `dataset` (file name, particle, seed), `split` (JSON: CV folds or 80/20 seed), `fold_metrics` (JSON: E1), `surrogate` (JSON: max_depth, fidelity R², MAE), `created_at` |
| `model_prediction` | `run_id`, `event_number`, `shower` (A / B / single), `fold`, `y_true` (list), `y_pred` (list) — enables E2, E3 and the prediction density; keyed to this database's events only when the run was trained on an ingested experiment, otherwise carries its own event ids and is labelled external |
| `model_importance` | `run_id`, `fold` (nullable), `feature`, `importance_type`, `value` |
| `model_surrogate_node` | `run_id`, `node_id`, `parent_id`, `depth`, `feature`, `threshold`, `value`, `n_samples`, `is_leaf` |

The exporter on the notebook side is a short function the roadmap should
ship with the ingest format (feature lists, predictions per validation row,
`feature_importances_`, and the surrogate's `tree_` arrays).

**Group 4, hit-schema change (decision needed).** C6 and C11 need
`particle_type` (VARCHAR) and `is_secondary` (BOOLEAN) per hit, and the
notebooks' row labels use `parent_type` / `daughter_type`. These are not in
the 99-column schema, so adding them means a schema version 2 with the
header check, the Parquet reader, the archive and `derive_proj.py`
following. The species of showers A and B are also absent at the event
level; a per-event `particle_type_{a,b}` would be the minimum for any
"per particle" comparison (B1–B3 by species, E1 by species). Only the
producer of `hits_all_models` can supply these; until then the figures are
drawn without the species dimension and the drawer says so.

**Single-shower datasets.** The notebooks' standalone and fixed-energy
files are single-particle and will not pass the `hits_all_models` header
check. A second input schema ("single-shower hits": `event, x, y, z,
energy, θ, φ, p, bin[, particle_type, is_secondary]`) with its own derived
tables, frames computed in-DB (document 01, §3.1 and §3.6), no
segmentation or CAM planes, would let page 1's profiles, distributions,
response curves and the inspector, and page 2's feature explorer and
model-run views, run on the notebooks' own data. Scoped as its own phase.

### 3.5 Payload and performance notes

- Every new route measures itself with `density.wire_size` and degrades as
  the existing routes do (coarser histogram bins, fewer curve points,
  voxel cap), disclosing each step.
- Hit-level scans (C4, C8, C1, radial C7) are grouped DuckDB scans over
  the projection table, 0.3–1 s cold on the production table by the
  existing measurements for comparable scans, cached per selection as
  bundles are.
- The event table and the proposed `layers_` table answer everything else
  in milliseconds.

---

## 4. Implementation phases

| Phase | Content | Page | Needs |
|---|---|---|---|
| 1 | Page scaffold: `/models` entry point, header tabs, shared sidebar; `echarts-gl` vendored or the custom-series spike decided | both | none |
| 2 | Group-0 physics cards: response & resolution (B1–B3), profiles (C7, pooled), distributions (C4), correlation (C8), statistics (C1) | P1 | none |
| 3 | Per-momentum-bin network bars (E2), prediction density, cards extension | P2 | none |
| 4 | Event Inspector (A1/C2) and side-by-side frames (A2); single-event voxels (C5) with energy / CAM / segmentation-error colouring; ensemble voxels | P1 + P2 | document 01 §3.1–3.3 |
| 5 | Group-1 columns and the `layers_` table; C9 diagnostics; profiles with SD band and t-envelope; feature explorer (D2–D5) | P1 + P2 | ingest change, migration |
| 6 | Model-run tables, upload, exporter; E1, E3, E4, E5 | P2 | group 3 |
| 7 | Schema v2 with species columns (C6, C11, per-species comparisons) | P2 | producer's decision |
| 8 | Single-shower input schema | both | document 01 §3.6 |

Phases 2 and 3 are independent of each other and of phase 4; phase 5 can
start once phase 2's query-time versions have settled the definitions.

---

## 5. Data Integrity Checklist

- [x] No raw hit arrays: every new route ships histograms, rasters,
      per-cell aggregates of a single event, or event-level statistics; the
      single-event voxel list is the finest payload and is capped and
      disclosed.
- [x] Zero axis distortion: every histogram and bar chart starts at zero;
      log axes are written as such; 3-D views are orthographic at 1:1:1.
- [x] Uncertainty by default: profiles carry SD band and t-envelope as
      two marks; per-bin means carry t-intervals; correlation cells carry
      Fisher-z intervals; CV tables show the fold SD; rates on the binary
      table carry Wilson intervals.
- [x] Density gates: KDEs only above N ≥ 8, histograms above N ≥ 15, per
      class; the response panel inherits plot 4's low-N ladder.
- [x] Circular quantities: φ histograms are drawn, φ is never averaged
      arithmetically; `sum_cos_phi / sum_sin_phi` replace the notebook's
      `avg_phi`; angle residuals are wrapped before any statistic.
- [x] Palettes: Viridis / Cividis / Plasma for sequential, PuOr for
      signed (correlation, Shap-CAM), ColorBrewer qualitative for species;
      `coolwarm`, `tab20` and `turbo`-as-categorical are not carried over.
- [x] Clipping disclosed: percentile ranges on energy and feature axes
      state the outside counts; voxel caps state the energy not drawn.
- [x] No fabricated model output: XGBoost figures draw ingested artefacts
      only; with none loaded the AI page shows the warning banner and the
      network-based figures.
- [x] Definitions pinned: the per-event features follow §1.4's inferred
      definitions, with `depth = z_max` and `angular_spread` flagged as
      inferred; the drawer states each formula.
- [ ] Decisions pending for the team: the 3-D views under the §2 rule;
      schema v2 for species; the single-shower input schema.
