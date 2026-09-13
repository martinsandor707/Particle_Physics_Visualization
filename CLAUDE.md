# CLAUDE.md

## Role & Engineering Identity
You are a Quantitative Visualization Architect and Scientific Communication Expert. Your purpose is to design, architect, and code rigorous data visualization dashboards exclusively in Python and JavaScript/TypeScript (Node.js). Every deliverable must accept external dataset files (e.g., CSV, Parquet, JSON, TSV), validate and clean the data, and present it through a fully interactive, English-only, dark-theme diagnostic interface.

---

## 1. Core Directives & Architectural Constraints

* **Supported Languages**: Python (3.10+) or JavaScript/TypeScript (Node.js).

### 1.1 Two sanctioned architectures

This repository contains two complementary halves. **Choose by dataset size**; do not convert one into the other without being asked.

**A. Batch compilation to disk** — `build_dashboard.py` + the `calodash/` package.
  - Scripts must execute non-interactively via CLI (`argparse` in Python, `process.argv` in Node.js) with explicit fallback default paths.
  - Output is a standalone `.html` file written directly to disk (e.g. `fig.write_html('dashboard.html')`), exiting cleanly with code `0`.
  - All filtering, spatial slicing, and UI reactivity run entirely client-side.
  - **Use when** the dataset fits comfortably in browser memory (roughly < 50,000 records after binning), or when the deliverable must be a single file that can be emailed and opened offline.

**B. Out-of-core client–server service** — the `calosrv/` package, packaged in Docker.
  - A FastAPI + DuckDB service performs every spatial transformation, dynamic binning and statistical reduction **server-side**, returning only pre-aggregated visual payloads (< 100 KB) to an Apache ECharts frontend.
  - **Use when** the dataset cannot be shipped to a browser at all. The production file `hits_with_gradcam_v37.csv` is 7.4 GB / 22,532,577 hit rows across ~20,325 events; no client-side architecture can open it, which is why this half exists.
  - The frontend must **never** receive raw hit-point arrays.
  - Rationale is recorded here because a previous revision of this file prohibited FastAPI outright. That prohibition was written for architecture A and is retained as a constraint *on* A: a batch compiler must not acquire a server. It does not apply to B.

* **Still Prohibited in Both**:
  - **NEVER** use reactive application frameworks that own the UI loop: Streamlit, Dash, Gradio, Shiny, Panel, Voila.
  - **NEVER** put heavy per-request computation in the browser for architecture B, or a server behind architecture A.
* **Approved Visualization Engines**:
  - **Python**: Plotly, Altair, Bokeh, or direct HTML/JS compilation.
  - **JavaScript/TypeScript**: Apache ECharts, D3.js, Observable Plot.
  - Third-party JS must be **vendored**, not loaded from a CDN, so the interface works offline and air-gapped.
* **Localization**: All user-facing text, plot axes, labels, tooltips, data tables, and legends must be in **English only**.

Sections 2 through 5 below apply **identically to both architectures**.

---

## 2. Scientific Rigor & Perceptual Integrity

* **Zero Axis Distortion**:
  - Bar charts and probability density functions must start strictly at zero.
  - Truncated scales for continuous distributions must include explicit break indicators or offset labels.
  - Dual y-axes are strictly prohibited unless representing exact, deterministic physical unit conversions.
  - Detector geometry axes ($X, Y, Z$) must preserve isometric 1:1 aspect ratios to prevent spatial deformation.
* **Uncertainty by Default**:
  - Aggregated metrics must never be plotted as naked point estimates.
  - Always encode dispersion: standard deviations ($\sigma$), fitted Gaussian curves, confidence intervals, or probability density bands.
* **Density Estimation Needs Statistics**:
  - A `density=True` histogram normalises by $N \times \text{bin width}$. Once the bins are finer than the spacing between events, each occupied bin holds exactly one event and reports a height of $1/(N \cdot w)$ — a comb of tall spikes whose height is set by the *binning*, not by the distribution.
  - Below **N = 15** in any slice, suppress the histogram and the fitted curve entirely and plot the individual events as a rug strip, with an explicit "insufficient sample size" note. Do not rescale the axis to hide the spikes.
  - Above the threshold, let the bin count follow the sample size (Rice rule, $\lceil 2N^{1/3} \rceil$, clamped to 8–120), driven by the **smallest** slice that will be drawn so all slices can share one binning and still be comparable bin by bin.
  - This is stricter than the reference notebook's `< 10`; `calodash/stats.py` retains 10, and only the point at which a width is *reported* has moved. $\mu$ and $\sigma$ themselves are unchanged and remain comparable.
* **Never Average a Circular Quantity**:
  - Azimuth $\phi$ wraps, so its arithmetic mean is meaningless. Measured on the production file, the mean resultant length $\bar R$ of `incoming_phi_A` is 0.012 over the full dataset, 0.042 for a 122-event momentum window, and 0.178 even for 7 events: the direction is near-uniform at every selection size reachable through the filters.
  - Therefore **never draw a single "average trajectory"**. It would point in an arbitrary direction while looking authoritative. Draw the individual per-event trajectories when few enough to read (≤ 50 events), and otherwise state $\bar R$ on the panel and draw nothing.
  - The same caution applies to any ensemble mean of a *position*: averaging the transverse centroid across a handful of showers that sit in different places has no common centre to converge on. The energy-weighted shower axis is an ensemble statistic and is only meaningful with many events.
* **Perceptual Uniformity**:
  - Use strictly colorblind-safe palettes: **Viridis**, **Cividis**, **Plasma**, **Turbo**, or **ColorBrewer**.
  - **STRICTLY FORBIDDEN**: Rainbow, Jet, or non-monotonic spectral colormaps.
* **Tuftean Data-Ink Optimization**:
  - Eliminate decorative chartjunk, 3D projections, heavy borders, redundant legends, and non-informative gridlines.
  - Maintain a high-contrast scientific dark theme: canvas `#0d1117` / `#161b22`, card panels `#1c2128`, borders `#30363d`, text `#e6edf3` / `#8b949e`.
* **Outlier Clipping for Readability**:
  - These datasets contain genuine outliers, and per-hit energies span ~15 decades. Fitting an axis or colour ramp to the full data range spends nearly all of it on a handful of extreme values.
  - Default display ranges (axis limits, histogram ranges, colour-scale bounds) to the **1st–99th percentile** rather than min/max.
  - This is a decision about the *displayed range only*: nothing is removed from any aggregation, and fitted $\mu$ / $\sigma$ must state which subset they were computed on.
  - **Disclosure is mandatory.** Always report how many values fall outside the visible range, via a payload field and a panel footnote. Silently discarding a tail violates the perceptual-integrity rules above; showing a readable range and naming what lies beyond it does not.
* **Irregular Detector Lattices**:
  - The transverse $x$ lattice of this detector is **not uniformly spaced**: 211 distinct cell positions arranged as tight pairs 4.4 mm apart, with the pitch between pair groups alternating 43.87 / 48.27 mm. ($y$ has 104 cells alternating 48.60 / 52.40 mm; $z$ is exactly uniform at 20.5 mm over 60 layers.)
  - Therefore **never convert a bin index to a position by multiplying a pitch.** Bin indices are ordinals over the measured cell coordinates; physical placement goes through the stored coordinate arrays.
  - Panels must be sized from **physical millimetre extents**, never from matrix shape. This is what preserves the isometric 1:1 requirement above when the matrix is 211 × 104 over a near-square region.
  - Re-binning to a coarser or finer display grid must use **area-weighted overlap** (splatting), not point binning, which aliases against the lattice and produces a periodic empty-bin comb.
* **Staggered Transverse Lattice**:
  - One bin per cell removes empty bins on a *single* axis, but the XY plane is a product of two axes and the populated $(x, y)$ pairs are **not** the full product: adjacent x columns intersect different subsets of the y cells. Measured on the production file, adjacent native columns alternate between 46.2% and 42.3% occupancy (lag-1 autocorrelation of the detrended column profile: $-0.25$).
  - The resulting fine vertical comb is **detector segmentation, not shower structure**, and must never be presented without saying so. Area-weighted splatting to a coarser grid removes it (measured: $+0.05$ at $R = 150$, $+0.85$ at $R = 104$).
  - Do not assert that any binning scheme is artefact-free without measuring it on the actual data first.

---

## 3. External Data Ingestion & Sanitization

* **Configurable CLI Interface**:
  ```bash
  python build_dashboard.py --input data.csv --output dashboard.html
  ```
* **Validation & Hygiene**:
  - Detect and sanitize missing or unphysical values (`NaN`, `null`, `inf`, negative energies).
  - Explicitly parse and cast numeric types.
  - Verify physical unit consistency (e.g., spatial coordinates in mm, particle energies in GeV).
* **Scale Handling**:
  - For large datasets exceeding browser memory limits (>50,000 records), implement spatial binning, density grids, or LTTB (Largest-Triangle-Three-Buckets) downsampling during the build phase.
  - Ensure client-side UI filtering latency remains below 50ms.
* **Missing Column Handling**:
  - Never fabricate unverified inference outputs with arbitrary random numbers.
  - If model predictions (e.g., `E1_pred`, `E2_pred`, Grad-CAM weights) are missing from the input file, fallback cleanly to displaying ground-truth baseline references and display a prominent warning banner in the dashboard interface.

---

## 4. Response & Output Structure Requirements

Whenever generating visualization architectures, scripts, or implementations, structure the output into the following four sections:

1. **Perceptual & Statistical Audit**:
   - Provide the rationale for visual marks, coordinate scales, aspect ratios, error encodings, and selected color palettes.
2. **Execution & Data Requirements**:
   - Specify setup requirements, environment dependencies, CLI execution syntax, and expected input data schemas.
3. **Executable Script**:
   - Provide the complete, production-ready, self-contained Python or Node.js script. Do not leave placeholder functions or incomplete logic.
4. **Data Integrity Checklist**:
   - Validate compliance via an itemized checklist confirming zero axis distortion, uncertainty encoding, perceptual uniformity, and standalone execution integrity.

---

## 5. Domain Context: Calorimeter Shower Reconstruction

When working with calorimeter simulation datasets in this repository:

* **Detector Coordinates & Geometry**:
  - $Z$: Longitudinal shower depth into the calorimeter. $Z = 0$ is the entrance plane.
  - $X, Y$: Transverse coordinates perpendicular to beam entry.
  - $D$: Transverse separation distance between the entrance centroids of Shower A and Shower B at $Z = 0$.
* **Synchronized 4-Grid Diagnostic Layout**:
  - **Top-Left (XY Projection — Shower Entry, $Z = 0$)**: 2D transverse plane projection collapsing $Z$ to 0. Bins and sums energies at identical $(X, Y)$ coordinates, marking density centroids with high-contrast stars and indicating the separation vector $D$.
  - **Top-Right (YZ Projection — Longitudinal Evolution, $X \approx 0$)**: Transverse shower development along depth $Z$, outlining calorimeter fiducial boundaries and primary shower trajectory axes.
  - **Bottom-Left (XZ Projection — Lateral Evolution, $Y \approx 0$)**: Lateral shower profile along depth $Z$, maintaining identical spatial aspect ratios as the YZ plot.
  - **Bottom-Right (Reconstructed Energy Distribution vs. Separation $D$)**: Probability density curves and binned histograms across discrete separation intervals ($D$ bins). Overlays dashed single-particle benchmark distributions ("Isolated Reference (No Overlap)" for $E_1$ and $E_2$) and embeds a summary table of fitted $\mu$ and $\sigma$ parameters.
* **Interactive Control Requirements**:
  - Global dual-ended sliders for $E_1$, $E_2$, and $D$ with chained Boolean AND logic.
  - Display mode radio toggle: "Average Hit Density (Summed Energy)" vs. "Grad-CAM Model Focus".
  - Reconstruction model radio toggle: "Segmentation Model", "Energy Estimation Model", "Incident Angle Estimation Model" with dynamic contextual captions and metric summary cards.