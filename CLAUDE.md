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
  - **Use when** the dataset cannot be shipped to a browser at all. The production file `hits_all_models.csv` is 24 GB / 24,161,893 hit rows across 20,325 events, with 99 columns: three coordinate frames and three networks' predictions and per-hit Grad-CAM / Shap-CAM maps; no client-side architecture can open it, which is why this half exists. It replaces `hits_with_gradcam_v37.csv` (7.4 GB, 29 columns), whose schema is retired; figures below credited to production v37 were measured on that file, whose lattice and incident kinematics the new one shares.
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
  - **A whisker encodes the uncertainty of an aggregate, never the dispersion of the sample.** A capped whisker on a plotted statistic is reserved for its standard error or a confidence interval built from it — at small $N$ the Student-$t$ interval $\bar x \pm t_{0.975,\,n-1}\,s/\sqrt{n}$, not a normal approximation, which understates the half-width by 2.2× at $N = 3$. Sample dispersion is a different quantity answering a different question and gets a different mark: an uncapped shaded range bar behind the marker, or nothing at all when the individual observations are already drawn. The two differ by $\sqrt{N}$, are indistinguishable by shape once a reader has seen both conventions, and so each must name its quantity in its tooltip.
* **Display Ranges Follow Robust Evidence**:
  - An axis range, a colour-scale bound or a histogram range is computed **only from the series that carry real statistical weight**. A fitted curve peaks at $1/(\sigma\sqrt{2\pi})$, so letting an under-powered slice set the scale flattens every well-measured series in service of the least reliable one. Measured on this panel: two 10-event slices peaked at 2.52 and 2.09 GeV⁻¹ against a robust maximum of 0.38, which would have compressed four well-measured slices into the bottom 15% of the canvas.
  - Under-powered estimates adapt to the established range. Where one overflows it, **clip it and say so**: an out-of-bounds indicator at the overflow, the true value in its tooltip, and a count in the panel footnote — the same disclosure discipline the percentile-clipping rule below demands.
  - A range taken from weak evidence because nothing stronger is present must be labelled **provisional** on the axis itself.
* **Density Estimation Needs Statistics**:
  - **Reported numbers and drawn marks are gated separately, because a table cell makes no claim about shape and a smooth curve does.** Conflating the two is what previously left a fourteen-event slice reporting em-dashes for a mean and width that were perfectly computable. Five thresholds, each justified on its own terms:

    | Floor | Gates | Why |
    |---|---|---|
    | $N \ge 2$ | $\mu$, $\sigma$, $\sigma/\mu$ **as reported numbers** | at $N = 2$ the sample width is one pairwise difference with a single degree of freedom — weak, not undefined, and labelled as such |
    | $N \ge 8$ | the continuous parametric density **curve** | below this a curve asserts a shape the sample cannot constrain |
    | $N \ge 15$ | the **density histogram** | the spike comb below |
    | $N \ge 15$ | the iterated $\pm 2.5\sigma$ **core refit** | it needs a populated tail to cut, and its truncation de-biasing must be applied *only* when the window actually excluded events |
    | $N \ge 20$ | the **robust width and Gaussian-shape verdict** | `np.percentile` on a handful of points interpolates between individual events, so the flag would fire at random. Below it the verdict is *untestable*, never a reassuring "Gaussian" |

  - **Scope of the $N \ge 8$ curve floor.** It governs a continuous density *estimated from a sample of per-event values*: a 1-D distribution whose shape the curve claims. It does not cover a **fixed-bandwidth spatial display reconstruction below the cell size**, such as the canonical Continuous Field (`calosrv/grid/kernel.py`): a Gaussian of $\sigma = 10$ mm (11.5 mm RMS per 20 mm accumulation bin, against a 48 mm cell) or the bilinear tent. That kernel's bandwidth is fixed by the accumulation grid rather than fitted to the events' values: one of two stated widths, chosen by a fixed $N$ gate, so it claims no shape the sample would have to constrain. It conserves energy and cannot raise any bin above the raw peak. It therefore runs at any $N$, with its kernel, $\sigma$ and $N$ gate stated on the panel. A small selection gets the provisional-range label and the kernel disclosure instead of a withheld picture.
  - A `density=True` histogram normalises by $N \times \text{bin width}$. Once the bins are finer than the spacing between events, each occupied bin holds exactly one event and reports a height of $1/(N \cdot w)$ — a comb of tall spikes whose height is set by the *binning*, not by the distribution. This argument is about the **histogram**, and it does not extend to the fit.
  - Below the histogram floor, draw the individual events plus the summary markers, and state which estimator produced the quoted numbers. **Never leave an event strip standing against an empty probability-density grid**: with no estimable density the axis is left unlabelled and the panel says so, rather than showing a 0–1 scale nothing on the plot is measured against.
  - Any mark placed on the density axis at a height that is **not** a density — an event strip, an error bar, a summary marker — lives in a tinted, captioned band with a rule along its top edge, and every tooltip in that band says its vertical position is a drawing offset. This is one axis with a reserved zone, not a second scale.
  - Below the core-refit floor, $\sigma$ must be quoted **with its own standard error and its asymmetric 95% interval**. At $N = 3$ the true $\sigma$ lies in $[0.52\hat\sigma,\ 6.29\hat\sigma]$, so a bare number with three decimals is the misleading presentation, not the honest one. Report the bias factor $c_4(N)$ too: $\text{ddof}=1$ makes the *variance* unbiased, not the standard deviation, which still runs 11.4% low at $N = 3$.
  - Above the histogram threshold, let the bin count follow the sample size (Rice rule, $\lceil 2N^{1/3} \rceil$, clamped to 8–120), driven by the **smallest slice whose histogram is drawn** so all slices can share one binning and still be comparable bin by bin.
  - Widths are the unbiased sample estimator, $\text{ddof} = 1$, in **both** architectures. The population form understates $\sigma$ by $\sqrt{1 - 1/N}$: 18% at $N = 3$, 6% at $N = 8$, below 0.3% above a few hundred events — so nothing at the scale the reference notebook worked at moves, and the small slices stop being quietly optimistic. `calosrv` additionally reports a $\text{ddof} = 0$ width so the notebook stays directly comparable, and a test asserts the two halves never quote different $\sigma$ for one sample.
* **Never Average a Circular Quantity**:
  - Azimuth $\phi$ wraps, so its arithmetic mean is meaningless. Measured on the production file, the mean resultant length $\bar R$ of `incoming_phi_A` is 0.012 over the full dataset, 0.042 for a 122-event momentum window, and 0.178 even for 7 events: the direction is near-uniform at every selection size reachable through the filters.
  - Therefore **never draw a single "average trajectory"**. It would point in an arbitrary direction while looking authoritative. Draw the individual per-event trajectories when few enough to read (≤ 50 events), and otherwise state $\bar R$ on the panel and draw nothing.
  - The same caution applies to any ensemble mean of a *position*: averaging the transverse centroid across a handful of showers that sit in different places has no common centre to converge on. The energy-weighted shower axis is an ensemble statistic and is only meaningful with many events.
  - **The one sanctioned exception is an averaged direction drawn after SE(3) co-registration into the centre-of-separation frame** (`calosrv/grid/frame.py`, `calosrv/query/ensemble.py`). Once every event is translated to the midpoint of its two back-projected entry points and rotated so the A→B separation lies along $+x'$, the directions become coherent: measured on the production file, the transverse mean resultant length $\bar R'$ is 0.78–0.82 for well-separated showers (D 2700–3000 mm) and 0.34 even for overlapping ones (D 20–40 mm), against 0.012 in the laboratory frame. That measurement, not the change of coordinates, is what licenses the mark. The drawn axis must carry its **dispersion band** (sample SD of the per-event slopes, an uncapped shaded wedge) and its **Student-$t$ 95% mean envelope** as two separate, named marks; $\bar R'$, the Rayleigh $p = \exp(-N \bar R'^2)$ and $N$ are always printed beside it, and an axis with $p > 0.05$ is drawn faded, never hidden. Numbers are reported from $N \ge 2$ and marks are gated as the low-N table in `README.md` / `plan.md` describes: a single event gets its own two lines labelled as such with no band; below $N = 20$ the coherence is labelled weak and the fitted ranges provisional. The lab-frame prohibition above is unchanged.
* **Perceptual Uniformity**:
  - Use strictly colorblind-safe palettes: **Viridis**, **Cividis**, **Plasma**, **Turbo**, or **ColorBrewer**.
  - **STRICTLY FORBIDDEN**: Rainbow, Jet, or non-monotonic spectral colormaps.
  - **A signed quantity takes a diverging ramp, symmetric about zero.** Shap-CAM attributions are signed: 11–64% of hits are negative, per network and frame, on the production file. A sequential ramp or a [0, 1] bound would fold every negative attribution into "no attention", and a logarithm cannot take a sign. Raw Shap-CAM is therefore drawn linear on [−1, +1] and its energy-weighted sum on a signed logarithmic ramp ±(10⁻³ … 1) of the selection's peak |value|, on the ColorBrewer **PuOr** diverging palette (orange negative, purple positive) and never on a sequential one. Bins with |value| below 10⁻³ of the peak are transparent and counted, as the density floor is; nothing is clipped.
    - **On the dark screen PuOr is folded; print keeps the standard scheme.** Measured against the `#1c2128` card, standard PuOr's strongest colours vanish (`#2d004b` at 1.07:1, `#7f3b08` at 1.95:1 WCAG contrast) and its `#f7f7f7` centre makes a bright halo round every near-zero bin. On screen each arm therefore runs from the card outwards through PuOr's own colours, brightness rising with |value| and hue alone giving the sign; the first 3:1 colour of each arm (`#b35806` 3.4:1, `#8073ac` 3.9:1) sits at 10^−2.5 of the peak, where the taper above the transparent band reaches full opacity, so nothing a reader is asked to see is drawn below 3:1. Raw Shap-CAM puts zero at border grey `#30363d`, so a populated zero stays distinct from an empty bin. Print keeps the standard 11-class scheme, whose light centre marks zero on white paper. Measure any new palette's anchors against the card before adopting it.
  - **Every rendered negative number is set with the minus sign U+2212**, never the ASCII hyphen: axis ticks, colour-scale ends, tooltips, captions, footnotes, server notices and exported SVG text (`static/js/format.js`, `calosrv/text.py`). JSON numbers are untouched.
* **Tuftean Data-Ink Optimization**:
  - Eliminate decorative chartjunk, 3D projections, heavy borders, redundant legends, and non-informative gridlines.
  - Maintain a high-contrast scientific dark theme: canvas `#0d1117` / `#161b22`, card panels `#1c2128`, borders `#30363d`, text `#e6edf3` / `#8b949e`.
* **Outlier Clipping for Readability**:
  - These datasets contain genuine outliers, and per-hit energies span ~15 decades. Fitting an axis or colour ramp to the full data range spends nearly all of it on a handful of extreme values.
  - Default display ranges (axis limits, histogram ranges, colour-scale bounds) to the **1st–99th percentile** rather than min/max.
  - This is a decision about the *displayed range only*: nothing is removed from any aggregation, and fitted $\mu$ / $\sigma$ must state which subset they were computed on.
  - **Disclosure is mandatory.** Always report how many values fall outside the visible range, via a payload field and a panel footnote. Silently discarding a tail violates the perceptual-integrity rules above; showing a readable range and naming what lies beyond it does not.
  - **Recorded exception: canonical-frame panel windows.** The X′Y′, Y′Z′ and X′Z′ crops of the centre-of-separation frame are **symmetric about the origin**, $x' \in [-\Delta_x, +\Delta_x]$ and $y' \in [-\Delta_y, +\Delta_y]$, not 1st–99th percentile windows. Each half-width is the larger excursion of the energy-weighted **0.1st–99.9th** percentile of that axis. It is never below 200 mm while the range is provisional ($N < 20$): the median single-shower $|y'|$ p98 of the entrance slab, one shower's own extent. Above that it is never below two cell footprints (100 mm), the physical resolution, because robust low-energy slices are narrower than one shower's p98: on production v37, $E_1, E_2 < 1$ GeV ($N = 468$) measures $y' \pm 80$ mm and $< 2$ GeV ($N = 691$) $\pm 160$ mm. It is snapped outward to whole 20 mm bins (`calosrv/query/window.py: symmetric_axis`).
    - **Why:** those panels do not draw below $10^{-3}\,\rho_\text{ref}$. On production v37 a 1–99 crop cut the shower halo where it was still **15–110× above that floor**, leaving 14–99% of the X′Y′ boundary bins above it, so the colour stopped at the window edge and looked like the edge of the shower. At 0.1–99.9, 2–11% of the boundary bins lie above the floor. Across seven production selections from $N = 3$ to the full 20 143 events, 0.12–0.33% of the X′Y′ energy falls outside the window.
    - **Why centred:** the origin is the midpoint of the two entry anchors, so a centred window keeps it in the middle of the panel.
    - **What does not change:** the disclosure duty. The energy outside each window is reported per panel, measured after display reconstruction, and the raw-grid figure travels beside it. The 1st–99th default still governs every other axis limit, histogram range and colour-scale bound.
  - **Recorded exception: the per-shower Translated and Local frames.** *Translated* moves every hit by its own shower's entry point P₀ — the energy-weighted (x, y) centroid of that shower's first populated layer, at that layer's z — without rotation; *Local* then rotates it by that shower's own R(θ, φ), so its incident direction lies along +w. Both superimpose the two showers of every event at the origin, and they take the canonical frame's rules rather than the laboratory's: panel windows symmetric about the origin at the energy-weighted 0.1st–99.9th percentile, with the same floors and 20 mm snapping; the Continuous Field kernel on the transverse axes only, under the scope stated above; footprint splatting instead of point binning — exact area-weighted box overlap in *Translated*, which does not rotate, and k × k × k_z sub-deposits (k ≥ 2, k_z = 2) over the 48.27 × 48.6 mm footprint and the 20.5 mm layer pitch, rotated by R(θ, φ), in *Local*; and the comb measured on every response on the raw, uncropped accumulation raster along both transverse axes, and along depth in *Local*. Depth is each shower's own native layers counted from its first in *Translated*, and a uniform grid at the layer pitch, binned and never smoothed, in *Local*. The accumulation grid is planned per dataset from the ingest-time energy-weighted 10⁻⁴ and 0.9999 quantiles plus half a footprint, and the energy outside it is counted.
    - **Why:** measured on production `hits_all_models.csv` over seven selections from N = 3 to 20,268: a 1–99 crop leaves 22–95% of the entrance-panel boundary bins above the 10⁻³ floor (up to 21 × the floor), 0.1–99.9 leaves 0–6.4%, with 0.15–0.31% of the energy outside. No comb is measured at any N: the worst transverse lag-1 is +0.14 (*Translated*, box overlap) and +0.05 (*Local*, k × k × 2), the worst depth lag-1 +0.11. At k_z = 1 the depth lag-1 falls to +0.0003 (N = 5), which is why k_z = 2 is kept.
    - **Why centred:** the origin is every shower's own entry point.
    - **What does not change:** D is the laboratory 3-D centroid distance `centroid_AB_distance` in every frame; `centroid_AB_distance_trans` / `_local` compare centroids expressed in two different frames and are never a separation, and the A–B offset of the superimposed centroids is labelled an offset. No ensemble direction is drawn in either frame: *Translated* keeps the laboratory azimuth (R̄ = 0.012), so it draws individual trajectories from the origin for ≤ 50 events and otherwise states R̄; in *Local* every incident direction is +w by construction, so an axis or a Rayleigh statistic would carry no information, and the panel says so. The mean centroid offset from P₀ has a common centre by construction and may be drawn, with its SD as an uncapped band and its Student-t 95% interval as capped whiskers, two separate marks, gated by the canonical low-N table. The disclosure duty is unchanged.
* **Irregular Detector Lattices**:
  - The transverse $x$ lattice of this detector is **not uniformly spaced**: 212 distinct cell positions arranged as tight pairs 4.4 mm apart, with the pitch between pair groups alternating 43.87 / 48.27 mm. ($y$ has 104 cells alternating 48.60 / 52.40 mm; $z$ is exactly uniform at 20.5 mm over 60 layers.)
  - Therefore **never convert a bin index to a position by multiplying a pitch.** Bin indices are ordinals over the measured cell coordinates; physical placement goes through the stored coordinate arrays.
  - Panels must be sized from **physical millimetre extents**, never from matrix shape. This is what preserves the isometric 1:1 requirement above when the matrix is 211 × 104 over a near-square region.
  - Re-binning to a coarser or finer display grid must use **area-weighted overlap** (splatting), or a **stated conservative kernel operator built from it** (box ⊗ Gaussian, tent; `calosrv/grid/kernel.py`). **Never** use point binning, which aliases against the lattice and produces a periodic empty-bin comb, or point interpolation, which samples the field instead of integrating it and so does not conserve energy.
    - **What qualifies a kernel:** every weight is a difference of one source bin's cumulative mass, $W[r,c] = G_c(d_{r+1}) - G_c(d_r)$. That makes it non-negative and conservative, and on a uniform source a partition of unity. A displayed bin is then a weighted mean of raw bins and can never exceed the raw peak.
    - **Rejected:** bicubic, whose negative lobes produce negative density and overshoot the peak.
    - **Stated** means the kernel, its width and its gate travel in the payload and are printed on the panel and in the figure.
    - **Uniform sources only:** the tent refuses a non-uniform source, so it can never be applied to the irregular lab lattice.
* **Staggered Transverse Lattice**:
  - One bin per cell removes empty bins on a *single* axis, but the XY plane is a product of two axes and the populated $(x, y)$ pairs are **not** the full product: adjacent x columns intersect different subsets of the y cells. Measured on the production file, adjacent native columns alternate between 46.2% and 42.3% occupancy (lag-1 autocorrelation of the detrended column profile: $-0.25$).
  - The resulting fine vertical comb is **detector segmentation, not shower structure**, and must never be presented without saying so. Area-weighted splatting to a coarser grid removes it (measured: $+0.05$ at $R = 150$, $+0.85$ at $R = 104$).
  - Do not assert that any binning scheme is artefact-free without measuring it on the actual data first.
  - **Rotating cell centres does not average the comb away.** Point-binning the co-registered cell centres of the canonical frame ($k = 1$, one deposit per cell on a 20 mm grid) was measured to leave a real footprint comb even over 20 143 events with near-uniform rotation angles ($\bar R(\psi) = 0.014$): lag-1 autocorrelation of the shower-core row $-0.26$ on the full production selection, $-0.47$ on a 221-event slice. Splatting each cell's energy as $k \times k$ sub-deposits over its measured physical footprint measures $+0.4$ to $+0.7$ from $k = 2$. Therefore $k \ge 2$ is mandatory (`MIN_SUBSAMPLE` in `grid/frame.py`), the comb statistic is measured on every canonical response with `stagger.detect` on the uncropped accumulation raster, and the payload names the value and the splat regime. The footprint itself is 48.27 × 48.6 mm, read from the populated $(ix, iy)$ occupancy — the pitch between adjacent cells sharing a row or a column — not from the sorted coordinate union, whose 4.4 mm "twins" are row-block offsets rather than cells. The 0.54 s that $k = 1$ would save on the full dataset does not buy an honest picture.
  - **Measure the comb before any display smoothing.** A smoothing kernel hides a comb without removing it. Smoothing hid a real $k = 1$ comb in **7 of 7** tests: the smoothed raster reported none where the raw accumulation raster had one.
    - The verdict is therefore always taken on the raw, uncropped accumulation raster, before any crop or display kernel. It is identical in every display mode, and the payload says where it was measured (`frame.comb.measured_on`).
    - The raw grid stays one click away as the Native Grid audit view, which shows a comb exactly as measured.
    - Never replace the measurement with one taken on the displayed field. In the canonical frame, never offer the Continuous Field kernel as a remedy for a measured comb: it hides the comb rather than removing it. (The laboratory frame's area-weighted re-binning to a coarser grid, above, is measured to remove its lattice comb, and keeps its advice.)

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
  - Display channel radio toggle, five options: "Average Hit Density (Summed Energy)", "Grad-CAM Model Attention", "Energy-weighted Grad-CAM", "Shap-CAM Attribution", "Energy-weighted Shap-CAM".
  - Reference frame radio toggle, four options: "Laboratory" (the cold-boot default), "Translated", "Local (shower-fixed)", "Canonical centre-of-separation". The separation vector D is drawn in the laboratory frame only; D is always the laboratory `centroid_AB_distance`.
  - Reconstruction model radio toggle: "Segmentation Model", "Energy Estimation Model", "Incident Angle Estimation Model" with dynamic contextual captions and metric summary cards. The selected model drives both the attention channels of the three spatial panels (its per-hit CAM columns in the selected frame; the canonical frame uses the absolute-frame networks) and the metric cards; plot 4 stays the segmentation reconstruction of the selected frame's segmentation network.