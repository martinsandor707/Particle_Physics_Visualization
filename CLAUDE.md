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
  - **The data arrive as Parquet.** Every CSV left the repository on 2026-10-27. The production data are now ZSTD-compressed Parquet: `ingest/hits_all_models.parquet` (2.9 GB, level 3), converted from the CSV above. The suite and the image seed from `hits_all_models_dummy.parquet`.
  - **Three input schemas, three pages.**
    - The service ingests three schemas, as CSV or Parquet, from the drop folder or the Admin upload:
      - `hits_all_models` v1: two showers, 99 columns;
      - `standalone_hits` v3: one shower, one row per cell, 21 columns;
      - `standalone_events` v3: the 59-column event-level aggregate of `core.calc_all_features_v3`.
    - What each kind serves is decided in one place, `calosrv/query/capabilities.py`. Every card a kind cannot serve says why.
    - Page 1 (`/`, Physics) holds the 4-grid diagnostic of §5 and the physics section below it. Page 2 (`/models`, Models) holds the network and XGBoost analysis, the feature explorer and the 3-D views. Both read one API and one URL hash.
    - Page 3 (`/methodology`, Methodology) is one journal-style article on how every panel of the other two is computed and drawn. It carries the same hash and writes no view key of its own; see §5.
  - **XGBoost runs in the service, never in the browser.**
    - The notebooks' regressors live in `xgboost_models/`, one per species, task and seed; the s1 models are used. A folder scan (`CALOSRV_MODEL_DIR`) finds them and pairs each with the aggregate experiment of the same species and seed.
    - A background job reproduces the notebooks' analyses and stores the results in DuckDB: the hold-out predictions, the 5-fold refit, the thresholded classification, the depth-3 surrogate tree and the gain importance.
    - `/api/xgboost` serves pre-aggregated views of them under the same 100 KB rule.
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
  - Under-powered estimates adapt to the established range. Where one overflows it, **clip it and say so**: an out-of-bounds indicator at the overflow, the true value in its tooltip, and a count in the panel's Details drawer (the former footnote) — the same disclosure discipline the percentile-clipping rule below demands.
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
    - **Recorded exception: prediction residuals take the Freedman–Diaconis width.**
      - **Where:** the Models page's residual cards (`calosrv/stats/histogram.py` `freedman_diaconis_bins`).
      - **The rule:**
        - the widest Freedman–Diaconis width among the drawn showers, within the same 8–120 clamp;
        - Rice again when no shower has an interquartile range.
      - **Why:** a residual's heavy tail stretches the 1st–99th display range. Rice's count then put the whole Gaussian core into one bin under a curve 3.5× taller. Measured on the XGBoost momentum residuals: 8 bins of 0.25, against σ_core = 0.033.
      - **Disclosure:** the payload names the rule (`residual.axis.bin_rule`, `bin_width`), and the drawer states the exception.
  - **A curve drawn over a histogram shares its normalisation.**
    - **The rule:** the core Gaussian's area is the number of events it describes, divided by the count the histogram normalises by (`calosrv/query/energy.py` `build_series`).
      - When the iterated ±2.5σ window cut events, that number is n_core / (2Φ(2.5k) − 1). The window sits at 2.5 *truncated* widths, while the curve is drawn with the de-biased σ, so the coverage is 0.98078, not 2Φ(2.5) − 1.
      - Otherwise it is n / n_in_range.
    - **Without a histogram**, the curve keeps unit area.
    - **Why:** a unit-area curve over a histogram of every event overstated the core's density by 1.32× on the XGBoost momentum residuals, where 47 of 62 events are in the core.
    - **Disclosure:** the curve's tooltip names its area, and the drawers say so.
  - Widths are the unbiased sample estimator, $\text{ddof} = 1$, in **both** architectures. The population form understates $\sigma$ by $\sqrt{1 - 1/N}$: 18% at $N = 3$, 6% at $N = 8$, below 0.3% above a few hundred events — so nothing at the scale the reference notebook worked at moves, and the small slices stop being quietly optimistic. `calosrv` additionally reports a $\text{ddof} = 0$ width so the notebook stays directly comparable, and a test asserts the two halves never quote different $\sigma$ for one sample.
* **Never Average a Circular Quantity**:
  - Azimuth $\phi$ wraps, so its arithmetic mean is meaningless. Measured on the production file, the mean resultant length $\bar R$ of `incoming_phi_A` is 0.012 over the full dataset, 0.042 for a 122-event momentum window, and 0.178 even for 7 events: the direction is near-uniform at every selection size reachable through the filters.
  - Therefore **never draw a single "average trajectory"**. It would point in an arbitrary direction while looking authoritative. Draw the individual per-event trajectories when few enough to read (≤ 50 events), and otherwise state $\bar R$ on the panel and draw nothing.
  - The same caution applies to any ensemble mean of a *position*: averaging the transverse centroid across a handful of showers that sit in different places has no common centre to converge on. The energy-weighted shower axis is an ensemble statistic and is only meaningful with many events.
  - **The one sanctioned exception is an averaged direction drawn after SE(3) co-registration into the Separation-Aligned (D-Frame), API `canonical` — the centre-of-separation frame, hereafter the D-frame** (`calosrv/grid/frame.py`, `calosrv/query/ensemble.py`). Once every event is translated to the midpoint of its two back-projected entry points and rotated so the A→B separation lies along $+x'$, the directions become coherent: measured on production `hits_all_models.csv`, the transverse mean resultant length $\bar R'$ is 0.78–0.82 for well-separated showers (D 2700–3000 mm, N = 500) and 0.12 for overlapping ones (D 20–40 mm, N = 950, every event below the 80 mm ill-conditioning threshold; Rayleigh $p \approx 5 \times 10^{-7}$), against 0.012 in the absolute (detector) frame. (On v37 the overlapping figure was 0.34.) That measurement, not the change of coordinates, is what licenses the mark, and it is re-measured on every response. The drawn axis must carry its **dispersion band** (sample SD of the per-event slopes, an uncapped shaded wedge) and its **Student-$t$ 95% mean envelope** as two separate, named marks; $\bar R'$, the Rayleigh $p = \exp(-N \bar R'^2)$ and $N$ are always printed beside it, and an axis with $p > 0.05$ is drawn faded, never hidden. Numbers are reported from $N \ge 2$ and marks are gated as the low-N table in `README.md` / `plan.md` describes: a single event gets its own two lines labelled as such with no band; below $N = 20$ the coherence is labelled weak and the fitted ranges provisional. The absolute-frame prohibition above is unchanged.
  - **Recorded exception: the windowed ensemble axis of the absolute frame** (`calosrv/query/window_axis.py`, `GET /api/window-axis`). The azimuth is uniform over the face but not random. Measured on production `hits_all_models.csv`: every shower's incident direction points at the detector origin — its azimuth equals the azimuth of its own position, φ = atan2(y, x) with R̄ = 1.000, and tan θ · z = r (the 3-D centroid's r / tan θ is 3,860 mm against its own z of 3,892 mm), residual 1.8° SD against that radial line (`summary.pointing`, reported on every lab and D-frame response). The azimuth is uniform only because the entry positions are, so the showers entering one window share a direction: in 300 mm windows of the entry position (262 windows with N ≥ 20) the median R̄(φ) is 0.999 and the mean lean over the depth is 346 mm against a 33 mm dispersion band. Therefore, when a depth panel is zoomed to a transverse window narrower than the detector, the mean trajectory of the selected events whose back-projected entry point lies in that window is drawn, with the sample SD of their per-event trajectories at each depth as an uncapped band and the Student-$t$ 95% interval of the mean as a thin envelope, two separate named marks. The gate is the lean against the fan, $|\bar s| \ge \text{SD}(s)$, drawn faded otherwise with the reason stated; the Rayleigh test is reported but not used as the gate, because a strip across the face flips the azimuth while the projected slope stays coherent. The low-N table applies unchanged. Nothing of the kind is drawn at full extent, where the prohibition above stands, and the per-layer energy centroid the depth panels draw for larger selections is named *centre of deposited energy*, a property of the summed picture, never a direction. Part of the D-frame band is this geometry, and its drawer says so.
  - **The aggregate's `avg_phi` is not a direction.** In `standalone_events` v3 and in the XGBoost inputs, it is `core.calc_all_features_v3`'s *arithmetic* mean of the hits' φ.
    - It is offered for parity with the producer's file and the models only.
    - It is flagged circular and never drawn as a direction.
    - Its correlation cells are hatched. They carry Mardia's circular–linear R, or r_c with another azimuth, beside the notebook's linear r.
    - The hit kinds offer `avg_phi_circ`, the mean direction atan2(Σ sin φ, Σ cos φ), which only per-hit sums can give. They also offer `angular_spread_circ` beside core's `angular_spread`, whose linear SD of φ the ±π cut inflates.
    - The angle model's predicted φ is never coloured or averaged linearly on the XGBoost surrogate card. Its boxes print a circular mean, with R̄, behind a Rayleigh gate.
* **Perceptual Uniformity**:
  - Use strictly colorblind-safe palettes: **Viridis**, **Cividis**, **Plasma**, **Turbo**, or **ColorBrewer**.
  - **STRICTLY FORBIDDEN**: Rainbow, Jet, or non-monotonic spectral colormaps.
  - **A signed quantity takes a diverging ramp, symmetric about zero.** Shap-CAM attributions are signed: 11–64% of hits are negative, per network and frame, on the production file. A sequential ramp or a [0, 1] bound would fold every negative attribution into "no attention", and a logarithm cannot take a sign. Raw Shap-CAM is therefore drawn linear on [−1, +1] and its energy-weighted sum on a signed logarithmic ramp ±(10⁻³ … 1) of the selection's peak |value|, on the ColorBrewer **PuOr** diverging palette (orange negative, purple positive) and never on a sequential one. Bins with |value| below 10⁻³ of the peak are transparent and counted, as the density floor is; nothing is clipped.
    - **On the dark screen PuOr is folded; print keeps the standard scheme.** Measured against the `#1c2128` card, standard PuOr's strongest colours vanish (`#2d004b` at 1.07:1, `#7f3b08` at 1.95:1 WCAG contrast) and its `#f7f7f7` centre makes a bright halo round every near-zero bin. On screen each arm therefore runs from the card outwards through PuOr's own colours, brightness rising with |value| and hue alone giving the sign; the first 3:1 colour of each arm (`#b35806` 3.3:1, `#8073ac` 3.8:1) sits at 10^−2.5 of the peak, where the taper above the transparent band reaches full opacity, so nothing a reader is asked to see is drawn below 3:1. The arms' other anchors are placed by CIE lightness, so equal |value| of either sign reads equally bright (mirrored codes agree to 15% in contrast on the signed log, 9% on the linear ramp). Raw Shap-CAM puts zero at border grey `#30363d`, so a populated zero stays distinct from an empty bin. Print keeps the standard 11-class scheme, whose light centre marks zero on white paper. Measure any new palette's anchors against the card before adopting it.
    - **On the light screen PuOr keeps its standard direction, re-anchored** (`palette.js` `puor_light`, `puor_light_linear`).
      - **Why:** on the `#ffffff` card the standard order already raises contrast with |value|, but its pastels sit below 3:1 over the lower two decades of the signed log.
      - **How:** each arm runs from the card outwards through PuOr's own colours in their standard order.
        - Its first 3:1 colour (`#d37610` 3.30:1, `#9287b9` 3.29:1, points on PuOr's path at one L*) sits at 10^−2.5 of the peak, as on the dark card.
        - It ends at `#7f3b08` and `#603b91`, both L* 33.3. The purple arm stops short of `#2d004b`, which would break the mirror.
        - Anchors are placed by CIE lightness: mirrored codes agree within 1.5% in contrast on the signed log and 1.8% on the linear ramp.
      - **Zero:** raw Shap-CAM and the correlation matrix put it at the light border `#d0d7de` (1.45:1, as `#30363d` is 1.33:1 on the dark card), so a populated zero stays distinct from an empty bin.
  - **On the dark screen, every sequential ramp is drawn on its 3:1 run against the card.**
    - **Why:** Viridis' own first colour is 1.06:1 on the `#1c2128` card. A populated bin, or a floating 3-D cube, at the bottom of the ramp would vanish while being drawn: up to 58% of an event's cubes did.
    - **Where:** every on-screen sequential ramp, and its legend:
      - both pages' spatial rasters and the Event Inspector;
      - the Models page's paired projections, 3-D cubes, 2-D histograms and surrogate tree;
      - the ordered series colours (`seriesStops`).
    - **How:** each is painted on its palette's longest run at ≥ 3:1 against the card (`static/js/scale.js` `legibleSpan`, built on `chart_panel.legibleRamp`).
      - Viridis runs from t = 0.376 to 1.
      - A tapered relative ramp reaches the run's first colour at the taper's full-opacity point.
      - Raw Shap-CAM cubes start each arm at 3:1.
    - **Print and the exporter** keep the full ramp in the palette's standard direction, from either screen theme.
    - **Disclosure:** the drawers say where the screen ramp starts.
  - **On the light screen each colour-map slot draws a ramp made for white** (`palette.js` `viridis_light`, `cividis_light`, `plasma_light`, `turbo_light`; `scale.js` `screenPalette`; Martin's directive, 2026-10-30).
    - **Why:** no dark-ground or paper ramp survives a white card.
      - Viridis' and Plasma's yellow ends vanish there (1.26:1 and 1.15:1).
      - Turned round onto white, they fade in through a yellow fringe round every shower, and Cividis muddies to khaki-grey.
      - Cut to its 3:1 run, Turbo keeps only its orange end.
    - **The ramps:** ColorBrewer colours, evenly spaced and interpolated in CIELAB.
      - Each runs from a pale tint at the display floor to a deep tone at the peak, so contrast with the card rises with the value: Martin's "contrast rises with value" of 2026-10-30, by construction.
      - **Viridis slot:** aqua, emerald-teal, azure, indigo. L* 95.8 to 13.4.
      - **Cividis slot:** ice-azure to navy in one hue. L* 95.5 to 7.6.
      - **Plasma slot:** apricot, coral-red, plum. L* 95.4 to 12.7.
      - **Turbo slot:** pale sky through cerulean, emerald, amber and vermilion to garnet. Like Turbo its lightness is not monotone, so it is never the default and never colour-vision-safe. Its peak is 13.2:1.
      - The three monotone ramps lose lightness at every table entry.
      - The directive's emerald `#2ca25f` was left out of the Viridis slot: at L* 59.2 against `#1d91c0`'s 56.4, either spacing gave a lightness rise or a hue contour.
    - **A continuous raster spans its ramp in full** (`field: true`: the 2 × 2, compare frames, the Event Inspector, the paired projections).
      - Its floor takes the palest tint and fades into the card over the bottom half decade.
      - Its peak takes the deepest tone.
      - A bin sits among its neighbours, and a faint halo should read faint.
    - **The 3:1 rule still governs every mark that stands alone on the card:** a 3-D cube, a series line or bar, a 2-D histogram cell, a surrogate-tree leaf, text.
      - Each takes its slot ramp's run at ≥ 3:1: Viridis slot from t = 0.537, Cividis 0.384, Plasma 0.420, Turbo's longest 0.675–1.
    - **Overlays on the deep core:**
      - **A white casing** sits under the overlay marks drawn on a raster: anchor and origin rings, ensemble and windowed axes, centroids, the D vector, the separation rule, P0 and its lines, the centre of deposited energy (`THEME.markCasing`; `canonical_overlays.overlayCasing`). Individual per-event trajectories stay uncased: they are many, and drawn faint on purpose.
      - **An ensemble axis's two wedges** are faint washes carried by their outlines (`THEME.wedgeAlpha` 0.05 against the dark card's 0.18, scaled 0.6 and 1.4 as there):
        - the spread at 0.03 with dashed long sides;
        - the 95% envelope of the mean, which at N = 2 spans the panel, at 0.07 with thin solid ones.
    - **Print and the exporter** keep the standard ramps, with no casing.
    - **Disclosure:** the drawers name the slot's light ramp and say a raster spans it in full; the colour-map options say what each slot draws on the light theme.
  - **Every rendered negative number is set with the minus sign U+2212**, never the ASCII hyphen: axis ticks, colour-scale ends, tooltips, captions, footnotes, server notices and exported SVG text (`static/js/format.js`, `calosrv/text.py`). JSON numbers are untouched.
* **Tuftean Data-Ink Optimization**:
  - Eliminate decorative chartjunk, 3D projections, heavy borders, redundant legends, and non-informative gridlines.
  - **Recorded exception: the orthographic 3-D views of the Models page** (`static/js/voxels.js`, `voxel_views.js`; data from `query/voxel_event.py` and `query/voxels.py`).
    - **What may be drawn in 3-D.** One event's cells and the selection's co-registered cloud. Where the energy sits in depth and around the axis is what a reader looks for there, and two projections lose it.
    - **How it is held:**
      - an orthographic camera, never perspective;
      - one scale on all three axes, 1:1:1 in millimetres, with the box proportional to the physical spans;
      - in the Absolute and per-shower translated frames, cubes that are measured cells: one per cell, sized by the measured footprint and the layer pitch;
      - in Local and the D-frame, where a tilted cell cannot be drawn as a cube, axis-aligned voxels of a stated splat grid: 20 mm sub-deposit voxels for one event (coarser only where 256 voxels per axis cannot cover the shower), 40 mm voxels merged about the origin for the cloud;
      - flat shading, with no lights;
      - colour scales and display floors stated as on the 2-D panels;
      - an opening zoom fitted to the card, so no axis title leaves the canvas.
    - **Why.** Occlusion and foreshortening make a 3-D view unreadable as a measurement. It orients, and the numbers live elsewhere:
      - every 3-D card stands beside its three paired 2-D projections, which carry the quantities and are the exportable figures;
      - the 3-D card has no export;
      - a page holds at most two WebGL contexts, and the card says so where WebGL is unavailable.
  - Maintain a high-contrast scientific dark theme: canvas `#0d1117` / `#161b22`, card panels `#1c2128`, borders `#30363d`, text `#e6edf3` / `#8b949e`.
  - **An optional light theme sits beside it** (the header toggle, §5).
    - **Tokens:** canvas `#f6f8fa` / `#ffffff`, card panels `#ffffff`, borders `#d0d7de`, text `#111827` / `#59636e`, the showers `#a3186b` / `#0b5fbe`.
    - **Where they live:** the `css/tokens.css` light block (inside `@media screen`) and `scale.js` `SCREEN_LIGHT`, which a test keeps equal.
    - **The rules:** every rule of this section holds on its card as on the dark one, measured against it. Text clears 4.5:1 on every ground it is drawn on. One exception: a continuous raster spans its slot's white-grounded ramp in full, its floor a pale tint, while every mark that stands alone keeps 3:1 (the light-screen ramp rule above).
    - **Dark mode does not move:** `tests/test_js_dark_golden.py` records every dark output as it was before the light theme.
    - **Exports:** an export is the same figure from either theme, because print overrides every screen token.
* **Outlier Clipping for Readability**:
  - These datasets contain genuine outliers, and per-hit energies span ~15 decades. Fitting an axis or colour ramp to the full data range spends nearly all of it on a handful of extreme values.
  - Default display ranges (axis limits, histogram ranges, colour-scale bounds) to the **1st–99th percentile** rather than min/max.
  - This is a decision about the *displayed range only*: nothing is removed from any aggregation, and fitted $\mu$ / $\sigma$ must state which subset they were computed on.
  - **Disclosure is mandatory.** Always report how many values fall outside the visible range, via a payload field and the panel's Details drawer (the former footnote). Silently discarding a tail violates the perceptual-integrity rules above; showing a readable range and naming what lies beyond it does not.
  - **Event windows.**
    - **Which panels:** one event's panels, meaning the Event Inspector, and the Models page's 3-D event with its three paired projections.
    - **The window:**
      - the energy-weighted 0.1st–99.9th percentile range of the event's cells;
      - padded by one cell footprint (one layer pitch along depth);
      - snapped outward to 20 mm;
      - never below 150 mm.
    - **Disclosure:** the cells outside are counted and named in the window rule.
    - **The Event Inspector** shares one half-width across its nine panels, so they stay square and directly comparable.
    - **The Models page** takes one half-width per axis (`/api/event?window=per_axis`, the default for the 3-D cubes). Otherwise a shower with a few far stray cells would be drawn in a box metres deeper than the detector.
    - **Either way**, the axes stay 1:1, and 1:1:1 in 3-D.
  - **Recorded exception: D-frame panel windows.** The X′Y′ (drawn as D–Y′), Y′Z′ and X′Z′ crops of the Separation-Aligned (D-Frame), API `canonical` — the centre-of-separation frame — are **symmetric about the origin**, $x' \in [-\Delta_x, +\Delta_x]$ and $y' \in [-\Delta_y, +\Delta_y]$, not 1st–99th percentile windows. Each half-width is the larger excursion of the energy-weighted **0.1st–99.9th** percentile of that axis. It is never below 200 mm while the range is provisional ($N < 20$): the median single-shower $|y'|$ p98 of the entrance slab, one shower's own extent. Above that it is never below two cell footprints (100 mm), the physical resolution, because robust low-energy slices are narrower than one shower's p98: on production v37, $E_1, E_2 < 1$ GeV ($N = 468$) measures $y' \pm 80$ mm and $< 2$ GeV ($N = 691$) $\pm 160$ mm. It is snapped outward to whole 20 mm bins (`calosrv/query/window.py: symmetric_axis`).
    - **Why:** those panels do not draw below $10^{-3}\,\rho_\text{ref}$. On production v37 a 1–99 crop cut the shower halo where it was still **15–110× above that floor**, leaving 14–99% of the X′Y′ boundary bins above it, so the colour stopped at the window edge and looked like the edge of the shower. At 0.1–99.9, 2–11% of the boundary bins lie above the floor. Across seven production selections from $N = 3$ to the full 20 143 events, 0.12–0.33% of the X′Y′ energy falls outside the window.
    - **Why centred:** the origin is the midpoint of the two entry anchors, so a centred window keeps it in the middle of the panel.
    - **What does not change:** the disclosure duty. The energy outside each window is reported per panel, measured after display reconstruction, and the raw-grid figure travels beside it. The 1st–99th default still governs every other axis limit, histogram range and colour-scale bound.
  - **Recorded exception: the per-shower frames — Separation-Aligned (D-Frame), Local (API `local`) and the legacy per-shower translated frame (API `trans`).** *Per-shower translated* (never plain "Translated", which now names the D-frame) moves every hit by its own shower's entry point P₀ — the energy-weighted (x, y) centroid of that shower's first populated layer, at that layer's z — without rotation; *Local* then rotates it by that shower's own R(θ, φ), so its incident direction lies along +w. Both superimpose the two showers of every event at the origin, and they take the D-frame's rules rather than the absolute frame's: panel windows symmetric about the origin at the energy-weighted 0.1st–99.9th percentile, with the same floors and 20 mm snapping; the Continuous Field kernel on the transverse axes only, under the scope stated above; footprint splatting instead of point binning — exact area-weighted box overlap in *Per-shower translated*, which does not rotate, and k × k × k_z sub-deposits (k ≥ 2, k_z = 2) over the 48.27 × 48.6 mm footprint and the 20.5 mm layer pitch, rotated by R(θ, φ), in *Local*; and the comb measured on every response on the raw, uncropped accumulation raster along both transverse axes, and along depth in *Local*. Depth is each shower's own native layers counted from its first in *Per-shower translated*, and a uniform grid at the layer pitch, binned and never smoothed, in *Local*. The accumulation grid is planned per dataset from the ingest-time energy-weighted 10⁻⁴ and 0.9999 quantiles plus half a footprint, and the energy outside it is counted.
    - **Why:** measured on production `hits_all_models.csv` over seven selections from N = 3 to 20,268: a 1–99 crop leaves 22–95% of the entrance-panel boundary bins above the 10⁻³ floor (up to 21 × the floor), 0.1–99.9 leaves 0–6.4%, with 0.15–0.31% of the energy outside. No comb is measured at any N: the worst transverse lag-1 is +0.14 (*Per-shower translated*, box overlap) and +0.05 (*Local*, k × k × 2), the worst depth lag-1 +0.11. At k_z = 1 the depth lag-1 falls to +0.0003 (N = 5), which is why k_z = 2 is kept.
    - **Why centred:** the origin is every shower's own entry point.
    - **What does not change:** D is the absolute-frame 3-D centroid distance `centroid_AB_distance` in every frame; `centroid_AB_distance_trans` / `_local` compare centroids expressed in two different frames and are never a separation, and the A–B offset of the superimposed centroids is labelled an offset. No ensemble direction is drawn in either frame: *Per-shower translated* keeps the absolute-frame azimuth (R̄ = 0.012), so it draws individual trajectories from the origin for ≤ 50 events and otherwise states R̄; in *Local* every incident direction is +w by construction, so an axis or a Rayleigh statistic would carry no information, and the panel says so. The mean centroid offset from P₀ has a common centre by construction and may be drawn, with its SD as an uncapped band and its Student-t 95% interval as capped whiskers, two separate marks, gated by the D-frame's low-N table. The disclosure duty is unchanged.
* **Irregular Detector Lattices**:
  - The transverse $x$ lattice of this detector is **not uniformly spaced**: 212 distinct cell positions arranged as tight pairs 4.4 mm apart, with the pitch between pair groups alternating 43.87 / 48.27 mm. ($y$ has 104 cells alternating 48.60 / 52.40 mm; $z$ is exactly uniform at 20.5 mm over 60 layers.)
  - Therefore **never convert a bin index to a position by multiplying a pitch.** Bin indices are ordinals over the measured cell coordinates; physical placement goes through the stored coordinate arrays.
  - Panels must be sized from **physical millimetre extents**, never from matrix shape. This is what preserves the isometric 1:1 requirement above when the matrix is 212 × 104 over a near-square region.
  - Re-binning to a coarser or finer display grid must use **area-weighted overlap** (splatting), or a **stated conservative kernel operator built from it** (box ⊗ Gaussian, tent; `calosrv/grid/kernel.py`). **Never** use point binning, which aliases against the lattice and produces a periodic empty-bin comb, or point interpolation, which samples the field instead of integrating it and so does not conserve energy.
    - **What qualifies a kernel:** every weight is a difference of one source bin's cumulative mass, $W[r,c] = G_c(d_{r+1}) - G_c(d_r)$. That makes it non-negative and conservative, and on a uniform source a partition of unity. A displayed bin is then a weighted mean of raw bins and can never exceed the raw peak.
    - **Rejected:** bicubic, whose negative lobes produce negative density and overshoot the peak.
    - **Stated** means the kernel, its width and its gate travel in the payload and are printed on the panel's Details drawer.
    - **Uniform sources only:** the tent refuses a non-uniform source, so it can never be applied to the irregular lab lattice.
* **Staggered Transverse Lattice**:
  - One bin per cell removes empty bins on a *single* axis, but the XY plane is a product of two axes and the populated $(x, y)$ pairs are **not** the full product: adjacent x columns intersect different subsets of the y cells. Measured on the production file, adjacent native columns alternate between 46.2% and 42.3% occupancy (lag-1 autocorrelation of the detrended column profile: $-0.25$).
  - The resulting fine vertical comb is **detector segmentation, not shower structure**, and must never be presented without saying so. Area-weighted splatting to a coarser grid removes it (measured: $+0.05$ at $R = 150$, $+0.85$ at $R = 104$).
  - Do not assert that any binning scheme is artefact-free without measuring it on the actual data first.
  - **Rotating cell centres does not average the comb away.** Point-binning the co-registered cell centres of the canonical frame ($k = 1$, one deposit per cell on a 20 mm grid) was measured to leave a real footprint comb even over 20 143 events with near-uniform rotation angles ($\bar R(\psi) = 0.014$): lag-1 autocorrelation of the shower-core row $-0.26$ on the full production selection, $-0.47$ on a 221-event slice. Splatting each cell's energy as $k \times k$ sub-deposits over its measured physical footprint measures $+0.4$ to $+0.7$ from $k = 2$. Therefore $k \ge 2$ is mandatory (`MIN_SUBSAMPLE` in `grid/frame.py`), the comb statistic is measured on every canonical response with `stagger.detect` on the uncropped accumulation raster, and the payload names the value and the splat regime. The footprint itself is 48.27 × 48.6 mm, read from the populated $(ix, iy)$ occupancy — the pitch between adjacent cells sharing a row or a column — not from the sorted coordinate union, whose 4.4 mm "twins" are row-block offsets rather than cells. The 0.54 s that $k = 1$ would save on the full dataset does not buy an honest picture.
  - **Measure the comb before any display smoothing.** A smoothing kernel hides a comb without removing it. Smoothing hid a real $k = 1$ comb in **7 of 7** tests: the smoothed raster reported none where the raw accumulation raster had one.
    - The verdict is therefore always taken on the raw, uncropped accumulation raster, before any crop or display kernel. It is identical in every display mode, and the payload says where it was measured (`frame.comb.measured_on`).
    - The raw grid stays one click away as the Native Grid audit view, which shows a comb exactly as measured.
    - Never replace the measurement with one taken on the displayed field. In the Separation-Aligned (D-Frame), API `canonical`, never offer the Continuous Field kernel as a remedy for a measured comb: it hides the comb rather than removing it. (The absolute (detector) frame's area-weighted re-binning to a coarser grid, above, is measured to remove its lattice comb, and keeps its advice.)

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
    - **The z convention is raw z.** Every file, the Parquet archive and every derived table keep the detector's raw z, on the one 212 × 104 × 60 lattice both hit schemas share: the first layer is at 3662.4 mm, then 60 layers at 20.5 mm. The producer's aggregate was computed on raw z.
    - `core.SHIFT_Z = 3649` mm (`ddl.CORE_SHIFT_Z_MM`) is only a display offset. It applies where a card quotes depth below the front face, labelled `z − 3649 mm` there.
    - Volumes, densities and `centroid_z` stay raw.
    - In the per-shower frames, z = 0 is each shower's own first populated layer.
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
  - Reference frame control, two tiers with one stored value: a primary radio "Absolute (detector coordinates)" (API `lab`, the cold-boot default) or "Separation-Aligned (D-Frame)", and under the latter a nested radio "Translated" (API `canonical`, the D-frame) or "Local (shower-fixed)" (API `local`). The legacy per-shower translated frame (API `trans`) has no radio: a `#frame=trans` link or a saved default opens it and reveals a hidden "Per-shower translated (legacy)" sub-option while it is active. The stored value, the URL hash (`#frame=lab|canonical|local|trans`) and the admin `default_coord_system` stay the flat four-value key; `js/labels.js` `FRAME_TREE` is the one definition. The separation vector D is drawn in the Absolute frame only; D is always the absolute-frame `centroid_AB_distance`. The D-frame's entry panel writes its horizontal axis as D — the signed x′ coordinate along the A→B separation, anchors at D = ∓⟨D_entry⟩/2, tick values the signed x′ in mm — while the depth panels keep x′, y′, z′, and the server's axis symbols and panel names (X′Y′, Y′Z′, X′Z′) are not renamed.
  - Absolute / segmentation / density is the built-in cold-boot view. An operator may save another in the **Admin Settings** panel (`/api/admin/config`). Saved defaults apply only to a link that carries no view state, so a bookmark never changes meaning. The built-in values (`state.js` `DEFAULTS`) are never edited to change the team's view.
  - **The theme toggle** (`#theme-toggle`, `js/theme.js`): one header button on all three pages switches between the dark and the light theme.
    - **Default:** with nothing stored, the page follows the OS (`prefers-color-scheme`), live.
    - **A click** stores the choice in `localStorage['calosrv.theme']`. A click that lands on the OS's own theme clears it instead, so the page follows the OS again (Martin's decision, 2026-10-30).
    - **No flash:** a classic `theme_boot.js`, first in `<head>`, sets `data-theme` before the first paint.
    - **Not view state:** the theme never enters the view state, the URL hash or the Admin defaults, so a link means the same in either theme.
    - **A switch** redraws every panel from the payloads in hand, with no request, and the 3-D views keep the reader's camera.
  - Reconstruction model radio toggle: "Segmentation Model", "Energy Estimation Model", "Incident Angle Estimation Model" with dynamic contextual captions and metric summary cards. The selected model drives both the attention channels of the three spatial panels (its per-hit CAM columns in the selected frame; the D-frame uses the absolute-frame networks) and the metric cards; plot 4 stays the segmentation reconstruction of the selected frame's segmentation network.
  - The four on-card footnotes are replaced by a per-panel **Details** drawer (`<aside id="inspector">`, `js/shell.js`, text from `js/panel_notes.js`): the former footnote's home, opened from each card's Details button — the keyboard trigger, flagged with a warning dot when the panel carries a hazard — or its title row, in sections Selection / What is drawn / Disclosures / Marks and legend, plus Reading the density axis on the energy panel. Every drawer opens with a link to the Methodology section that explains its panel (see Page 3 below). The key counts stay on screen without opening it: the energy card's `#energy-sparse` notices (which also carry the energy-axis clipping note), the status-bar ρ_ref and **Clipped** readouts (`#stat-clipped`: clipped ramp cells in the Absolute frame, bins below the display floor in a co-registered frame), and the sidebar's info dots (the comb and frame notices).
  - Exported SVG/PNG figures are the plot canvas only, by directive: axes, raster, overlays and the colour-scale legend on `#FFFFFF` in `#111827` ink, with no caption band, no reserved bottom height, no `<g id="figure-disclosure">` and no μ/σ table rows. This overrides the earlier rule that the figure carries its own disclosures; the drawer's text is what goes into a manuscript caption.
  - **Tooltips may leave their chart, but never cover the panel being read.**
    - Every tooltip is mounted on `#tooltip-layer`, above every other element, and is never clipped.
    - An explanation sits outside the hovered plot.
    - A readout stays beside the pointer only where it covers at most 20% of the hovered plot there. Otherwise it leaves the plot, as an explanation does (`static/js/panels/tooltip.js`).
    - The browser tests hold both pages to the 20% cap.
  - The dataset upload form lives inside the **Admin Settings** panel, between the default-view form and the Automatic ingest section; there is no header upload button. The panel's Close button closes it, a running ingest survives closing, and a Clear form button resets it.
* **Models page (Page 2) requirements**:
  - **Cards.** It holds:
    - the networks' per-momentum-bin performance (E2);
    - prediction against truth and its residuals;
    - the feature explorer (table, correlations, histogram, 2-D histogram), which draws one shower at a time on two-shower data and never pools A and B;
    - the primary-tag rate;
    - the two 3-D views of the recorded exception above;
    - on an aggregate experiment paired with its XGBoost models, the cards E1 (cross-validation), E3 (thresholded classification), E4 (surrogate tree) and E5 (gain importance), plus the XGBoost series of E2 and of the prediction density.
  - **E2's per-bin marks follow the low-N table.**
    - One shower is drawn as a dot, never as an aggregate bar.
    - A point without an interval is faded, and its tooltip names the floor of its own quantity.
    - A momentum bin's RMSE carries a χ² interval below N = 20, under a stated normal-residual assumption, and a seeded percentile bootstrap from N = 20 (`calosrv/stats/rmse.py`).
      - It is never √ of the t interval of the MSE, whose lower end collapses to 0 at small N.
      - Page 1's metric cards keep that older estimator for now.
  - **E3 states the class ratio it drew**, the realised ratio against the designed 99 : 1, and which rates depend on it.
    - Accuracy and the precisions depend on it.
    - The recalls and the balanced accuracy do not.
  - **E4 judges surrogate fidelity per output.**
    - Each output's own fidelity is printed.
      - φ is judged on a circular R², 1 − Σ(1 − cos Δ) / Σ(1 − cos(φ − φ̄)), and on the wrapped MAE.
      - φ's linear R² stays as notebook parity.
    - The "low surrogate fidelity" warning is judged per output, below R² 0.5 (φ on the circular R²).
    - The average is never judged and never printed alone. On electrons the linear R² of φ is 0.978 and of θ 0.004; their average, 0.49, would hide both.
    - Within-node SDs use ddof = 1 and are flagged weak below 20 rows.
    - The colour domain comes from nodes of 20 rows or more. A leaf beyond it is marked and counted.
  - **E5 shows the top 15 features by the notebooks' `feature_importances_`** (average split gain, normalised), labelled as such.
    - The plot counts the rest.
    - The tooltip and the drawer give each feature's total-gain share and rank, and the drawer lists every feature.
    - There is no "show all" toggle.
  - **The feature explorer:**
    - fades the correlation cells whose 95% interval contains 0;
    - on an aggregate experiment, offers a frame choice (absolute, per-shower translated, local; never the D-frame) through the shared `frame` key.
  - **The training-split check.** An analysis whose training split is not reproduced is still shown, and its cards and its Admin row carry the hazard. Reproduced means the validation/training MSE at `random_state` 42 clears the largest of 99 other seeds by the stated margin.
* **Methodology page (Page 3) requirements**:
  - **The article follows the code.** Where the two disagree, the code is right and the article is corrected. The content lives in `static/js/methodology/content/`, as plain data in one module per part.
  - **Every number it quotes comes from `static/js/methodology/constants.js`.** Each entry names its source, and `tests/test_methodology_constants.py` resolves it against the live code. A measured figure is cited with its dataset and source, never quoted as a constant.
  - **Results audits encodings.** It explains every visualisation of Pages 1 and 2 — what it encodes, why that mark and scale, which distortion it prevents. It reports no dataset's findings.
  - **Equations are native MathML** from `static/js/math.js`: a closed LaTeX subset, with no vendored library, font or CDN.
    - A command outside its whitelist throws, and a test compiles every equation.
    - Display equations are numbered, and each carries its LaTeX source to copy.
    - The D-frame's entry-anchor explainer on Page 1 sets its formulas through the same compiler, in the article's notation.
  - **The hash.** The page writes no view key. Its own place is the key `at`, which no State reads and every link to Pages 1 and 2 drops.
  - **Badges.** An "Open in Physics/Models →" badge opens `?panel=<card>&from=<anchor>&from_sec=<section>` with the reader's view. A hash without view state takes the view a cold boot would open. A Physics badge drops `event` and `compare`, which hide the ensemble panels, unless it sets them itself.
    - The landing page scrolls to the card and opens its Details drawer, which links back to the badge's place in the article.
    - A card the experiment does not serve says so on the banner, and so does one the view on screen hides, naming the view rather than the experiment.
  - **Every Details drawer links to its section.** On Pages 1 and 2 a drawer opens with a link to the article section that explains its panel: the Results subsection that audits it, at its badge row.
    - The pages do not load the article, so the map is data (`static/js/article_sections.js`). `tests/test_article_sections.py` derives it from the article and fails on drift.
    - A card two Results rows name lands on the one that audits it; the test's `AUDITED_IN` names those cases.
  - **Export.** The header's Export button downloads one zip, built in the browser: the article as pdfLaTeX (`static/js/methodology/latex.js`), the cited references as BibTeX, and every figure as SVG and as a 300 dpi PNG (`methodology/export.js`).
    - The `.tex` is ASCII: every character the content uses is mapped to LaTeX, and an unmapped one is an error. It needs only standard TeX Live packages, and `tests/test_js_latex.py` compiles it with pdflatex and bibtex.
    - The BibTeX comes from the structured `bib` fields of `content/references.js`, which a test holds to the printed `text`.
  - **Exported figures are drawn for paper** (`exhibits.js` medium `'paper'`). The page keeps its screen figures.
    - No dark ground. Where a figure shows contrast against the screen card, the card becomes a white framed panel and the labels say the numbers are measured against it.
    - Ink from `export/tokens.js` `PRINT_INK`, every text colour at 4.5:1 or more on white.
    - Drawn for the 160 mm LaTeX text width and included at 100%, so no type is below 9 pt (`MIN_PT`).