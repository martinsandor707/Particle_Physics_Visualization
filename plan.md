# Canonical Centre-of-Separation Frame & Publication Export — Implementation Plan

> Approved implementation plan (revision 2). It incorporates 27 findings from a three-lens adversarial review
> (physics/statistics, backend/tests, frontend/export), each verified against the source and the production data.
>
> Revision 3 (appended at the end) supersedes decision 2 (interface default), §2 "No schema, ingest or Docker
> change", §1.5 Grad-CAM = `ge`, and §3.2 `frame: 'canonical'`. The §1.7 low-N table stands, is cited by CLAUDE.md
> §2, and also governs the translated and local frames.

## Context

The three spatial panels of `calosrv` (XY entrance slab, YZ and XZ depth views) aggregate hits in laboratory
detector coordinates. Every event's two showers land wherever the particles struck, so a multi-event selection is a
smear across the 5.2 m face, and the depth panels either draw ≤ 50 individual trajectories or an ensemble centroid
axis that wanders. `CLAUDE.md` §2 forbids averaging the incident azimuth because in the lab frame it is uniform
(mean resultant length R̄ = 0.012).

The directive asks for a rigid-body (SE(3)) co-registration of every selected event into a **canonical
centre-of-separation frame** — translate to the midpoint of the two shower entry points, rotate so the A→B
separation lies along +x′, shift depth so the front face is z′ = 0 — then accumulate an **ensemble energy density**
⟨ρ⟩ over the selection and draw **exactly two ensemble shower axes**. It also asks the existing publication exporter
to carry an isolated `<g id="figure-disclosure">` caption band.

### What discovery established (read-only, on `data/calorimeter.duckdb`, experiment `v37`, 20 325 events)

| Fact | Measurement | Consequence |
|---|---|---|
| `centroid_A/B_*` are **3-D whole-shower centroids**, not entry points | `caz` median 3915 mm = 253 mm behind the front face (p99 838 mm); equals the `voxel_fA_true`-weighted centroid of all hits to 4.4 mm median | Entry anchors must be **derived** by back-projection |
| `D` is the **3-D** centroid distance | \|D − 3-D\| ≤ 5×10⁻⁴ mm; \|D − transverse\| up to 726 mm; \|caz − cbz\| median 93, p99 650 mm | Frame separation `D_entry` (transverse, at the face) ≠ slider `D`; both reported |
| Angles | θ ∈ [0.053, 0.628] rad; φ uniform (R̄ = 0.012) | Drift over 1209.5 mm depth reaches 879 mm; the accumulation window budgets for it |
| Back-projection sign | entry = c − (c_z − z_f)·tanθ·(cosφ, sinφ): 82 mm median from the per-event slab centroid; opposite sign 181 mm (reviewer: 56 vs 194 on 3000 events) | Sign fixed by data |
| Frame invariance | per-event canonical slab centroids: A x′ + D_entry/2 = +19 mm, y′ = +0.3 mm (median); B x′ − D_entry/2 = +17, y′ = −0.0 mm | Rotation correct. The x′ offset is a **mixture** (D_entry > 500 mm: A −22 / B +24 outward; D_entry < 80 mm: A +44 / B +9 overlap pull) → reported **per selection**, not as a constant |
| Direction coherence **in the canonical frame** | full: R̄′_A = 0.024, R̄′_B = 0.371; D 2700–3000: 0.779 / 0.819 with ⟨û′_A⟩ → −x′, ⟨û′_B⟩ → +x′; D 20–40: 0.339 / 0.340 | Ensemble axes are meaningful here; R̄′, its Rayleigh p and N are always shown |
| Rotation-angle ensemble | R̄(ψ) = 0.014 full; 0.02–0.06 on slices; 0.42 for 7 events. **It does not smooth the cell comb**: point-binning (k = 1) measured lag-1 −0.26 on the shower-core row over 20 143 events and −0.47 on a 221-event slice; k ≥ 2 measures +0.4 to +0.7 | Reported as context only. k = 1 is never used (`MIN_SUBSAMPLE = 2`); comb presence is **measured** on the canonical raster (§1.3) |
| ψ conditioning | D_entry < 80 mm: 28.2 % of events; < 20 mm: 3.0 %; < 5 mm: 0.2 % | Orientation is noise for overlapping showers; harmless to ⟨ρ⟩, disclosed as a count |
| 182 events have no A centroid (`cax IS NULL` ⇔ `d IS NULL`) | 0.9 % | No frame; excluded from N and counted even with `include_undefined_d` |
| **Cell geometry** (new) | within a y row the x pitch is 48.27 mm (module gaps 57 mm); within an x column the y pitch is 48.6 mm; rows form blocks of 4 offset by 4.4 mm in x between blocks; each x column intersects ~24 of 104 rows; 8752 distinct (x, y) cells; layer parity 50/50 | Physical footprint ≈ **48.3 × 48.6 mm** centred on the cell. `Axis.edges` midpoint tiles (median 24.1 mm wide, asymmetric) are a 1-D bookkeeping device, not the footprint |
| Energy-weighted p1–p99 extents | full: x′ −2090…1910, y′ ±390; D 240–260: x′ ±450, y′ −430…390; D 2700–3000: x′ ±1740, y′ −450…390 | Windows are selection-dependent → data-fitted |
| Energy outside ±3500 × ±1380 mm | 0.0073 % (full), ≤ 0.008 % on slices | Margin-based accumulation window is effectively lossless; remainder counted |
| Query cost, full 22.5 M rows | lab 0.35 s; canonical k=1 0.54 s, k=2 2.0 s, k=3 4.2 s; 1000-event slice k=4 0.41 s; 51 events k=6 0.07 s; EXPLAIN = one `SEQ_SCAN` of `proj_`, one of `event_`, two `RANGE` | **Query-time transform, no schema/ingest change**, adaptive k |
| Energy conservation | Σ E(XZ set) equals the lab scan to 10⁻¹⁵ relative | Exact by construction; asserted |

### Decisions taken with the user

1. **Anchors = back-projected entry points**; `D_entry` reported beside dataset `D`.
2. **Reference-frame toggle**, interface default **canonical**; API default stays `frame=lab`, so every existing contract and test is untouched.
3. **z′ always spans the full instrumented depth** (60 native layers); only x′, y′ are percentile-fitted.
4. **Hybrid density encoding**: binned value = physical projected surface density ⟨ρ⟩ = ΣE / (N·ΔA) in GeV mm⁻² per event; colour = ⟨ρ⟩/ρ_max on a log ramp **10⁻³ … 1.0** labelled `Average hit density (a.u.)`; tooltips show both; ρ_max published in footnote and figure caption. *Flagged:* the answer says "4 decades from 10⁻³ to 1.0" (3 decades); the explicit bounds win, `RAMP_DECADES = 3.0` is one constant echoed as `scale.decades`. *Review addendum (§1.5):* the normalisation reference is selectable — the selection's own peak (default, decision 4) or the whole dataset's peak (keeps ⟨ρ⟩ colours comparable across D slices, the codebase's colour-lock principle); both are disclosed.

---

## 1. Perceptual & Statistical Audit

### 1.1 The SE(3) element and its sign conventions

For event *i* with dataset centroids **c**_A, **c**_B, angles (θ_S, φ_S), and the global front face z_f = `lattice.z.lo` (3662.4 mm; `grid/slab.py` documents why it is global):

```
entry_S = (c_S,x − (c_S,z − z_f)·tanθ_S·cosφ_S ,  c_S,y − (c_S,z − z_f)·tanθ_S·sinφ_S ,  z_f)      S ∈ {A, B}
(x0, y0) = (entry_A + entry_B)/2                       translation
ψ_i      = atan2(entry_B,y − entry_A,y , entry_B,x − entry_A,x)
D_entry  = ‖entry_B − entry_A‖                          transverse, at the front face
r′ = R_z(−ψ_i)·(r − (x0, y0, z_f)):   x′ =  cosψ·(x−x0) + sinψ·(y−y0)
                                       y′ = −sinψ·(x−x0) + cosψ·(y−y0)
                                       z′ =  z − z_f
```

Check: entry_B − (x0, y0) = (D/2)(cosψ, sinψ) ⇒ x′ = D/2, y′ = 0; A ⇒ (−D/2, 0). Passive rotation, i.e. the matrix in the directive. Unit directions **û** = (sinθcosφ, sinθsinφ, cosθ) transform by the linear part only (u′_z = u_z, norm preserved). SE(3) is an isometry: distances, widths and longitudinal profiles are conserved exactly. Directions point **into** the calorimeter (u_z > 0); the shower core drifts along +(sinθcosφ, sinθsinφ) with depth, which fixes the back-projection sign.

### 1.2 Where the transform happens

`proj_<name>` stores ordinal indices per hit plus `event_number` ([ddl.py:77-101](calosrv/db/ddl.py#L77)); `event_<name>` holds `cax…cbz, theta_*, phi_*, d` ([ddl.py:104-147](calosrv/db/ddl.py#L104)). The rotation is per event, so it is applied **inside DuckDB**: each hit row joins its event's frame parameters (a 20 k-row CTE), the rotated position is binned into a uniform canonical grid, and the same `GROUP BY GROUPING SETS ((jx,jy),(jy,iz),(jx,iz))` single-scan pattern as [projections.py:98-122](calosrv/query/projections.py#L98) produces all three panels. Index → mm goes through the stored coordinate arrays bound as list parameters (`list_extract($x_coords, ix+1)`; verified to bind on duckdb 1.5.5), never a pitch.

### 1.3 Cell footprints, sub-cell splatting, and the *measured* comb

A hit is a **48.3 × 48.6 mm cell** centred on its coordinate (§Context). Point-binning rotated centres into 20 mm bins leaves a dotted comb around each event, so each cell's energy is split into k × k equal sub-deposits at the centres of a regular partition of its footprint (`CROSS JOIN range(k) × range(k)`, E/k² each, offsets `(f − 0.5)·w`):

* **Footprint derivation** (`frame.cell_footprint(lattice)`): an axis is *twinned* when ≥ 20 % of its consecutive gaps are below 0.25 × the 90th-percentile gap; a twinned axis' footprint is the median **two-step** gap (x: 48.27 mm), otherwise the median one-step gap (y: 48.6 mm). A test compares this to the direct 2-D measurement (within-row / within-column medians) and to the demo lattice. `frame.footprint_mm` is in the payload.
* **Exact total** for any k (asserted).
* **No empty bins under a footprint** once s = w/k ≤ p/√2 ⇒ k ≥ ⌈√2·48.6/20⌉ = 4 (s = 12.2 mm).
* **Budget**: `k = clamp(⌊√(B / rows_scanned)⌋, 2, 6)` (never 1: point-binning was measured to comb, see Implementation notes), B = 3×10⁷ sub-rows; `rows_scanned` is the selection's hit count times the sample fraction when previewing. Full dataset → k = 1 (0.54 s); < 7.5 M → 2; < 1.9 M → 4 (0.41 s at 1.27 M); < 0.83 M → 6.
* **The comb is measured, not asserted** (CLAUDE.md §2 last rule). `stagger.detect` ([stagger.py:80-106](calosrv/query/stagger.py#L80)) runs on the **uncropped accumulation matrix** (e.g. 138 × 350 for the full dataset) *before* cropping or resampling, so the 15 % edge trim and the 27-sample minimum of `_lag1` are met even for narrow-D fits; the result is carried as `frame.comb` and copied into `meta.stagger` with its `note` **overwritten** by canonical wording (the lab note tells the user to "switch to Continuous Field to merge staggered pairs", which is meaningless here). Three branches: "no cell-footprint comb measured (lag-1 = …, occupancy …)", "a footprint comb is present (lag-1 = …): k = … sub-deposits per cell over N = … events; a larger selection or a coarser R removes it", and "not measurable (only n columns)" when `_lag1` returns None. R̄(ψ) is reported as context only.
* **k and ρ_max**: point-binned centres (k = 1) are **not** smoothed by the ensemble of rotations — measured lag-1 −0.26 over 20 143 co-registered events and −0.47 on a 221-event slice — so k = 1 is never used (`MIN_SUBSAMPLE = 2`, which measures +0.4 to +0.7); from k ≥ 4 the splat is gap-free at every rotation angle. The regime (`frame.subsample_regime`, originally `frame.smoothing` and renamed by Implementation note 22: `sub-cell-sampling-gapless` / `sub-cell-sampling-partial`) and k are named in the payload; the effect on peak values is bounded by the measured comb statistic.

### 1.4 Data-fitted spatial domain (two levels, one scan)

* **Accumulation window** (lossless, cache-stable): from the selection's event table, snapped outward to the pitch: `half_x = max(D_entry)/2 + M`, `half_y = M`, `M = (z_hi − z_lo)·tan(max θ) + R_shower`, R_shower = 500 mm (twice the p90 energy-weighted RMS radius of a shower about its axis, 246 mm). Full dataset ⇒ ±3500 × ±1380 mm, 0.0073 % outside, counted in the query (`sum(energy) FILTER (WHERE outside)`, scaled like the other sums when sampled). Grid: `CANONICAL_PITCH_MM = 20.0` (≈ the 20.5 mm layer pitch, < half a cell); depth = the 60 native layers (z′ is layer-aligned; never resampled).
* **Display window** (what is sent): per panel, the energy-weighted 1st–99th percentile of the marginal along each transverse axis, snapped outward to bin edges — XY from slab marginals, YZ/XZ from full-depth marginals; z′ never cropped. Energy outside each panel's window → `fit.<panel>.energy_fraction_outside` and the footnote. Below **N = 20 events** the fitted range is labelled **provisional (N events)** in the axis title and `fit.provisional = true` (CLAUDE.md §2: ranges from weak evidence are labelled on the axis). Depth panels integrate the third coordinate over the whole accumulation window (δ_x = half_x, δ_y = half_y); the payload states δ and the excluded fraction.
* **Aspect**: XY keeps the 1:1 letterbox. A depth panel renders isometric only when its letterboxed plot would keep ≥ 45 % of the card width **and** transverse/depth span lies within the export clamp [0.45, 1.3] ([projection.js:227](calosrv/static/js/panels/projection.js#L227)); otherwise the existing fixed aspect with true mm extents, and the footnote says which applied.

### 1.5 Density normalisation and the colour scale

* ⟨ρ⟩ = ΣE_bin / (N_frame · ΔA) in GeV mm⁻² per event; ΔA = p² (XY) or p·20.5 mm (depth). Under area-weighted resampling (`splat.overlap_matrix`, columns sum ≤ 1) the sum is conserved and the density is an area-weighted mean, so ⟨ρ⟩ is R-invariant and no coarser bin exceeds the finest-grid maximum.
* N_frame = selected events with `cax, cbx, theta_*, phi_*, d` all non-null. Sampled preview: sums (including `energy_outside`) scaled by 100/percent, N exact ⇒ unbiased, `exact: false`.
* **Reference ρ_max** (`rho_norm`): `selection` (default, decision 4) = max ⟨ρ⟩ on the accumulation grid over this selection — one value for XY, one shared by YZ + XZ; `dataset` = the same computed once per experiment on the full selection (its canonical bundle is cached under the full-range key) — keeps colours comparable across D slices, where superposed showers can reach ~2× an isolated peak. Colour = log₁₀(⟨ρ⟩/ρ_ref) with vmin = −3, vmax = max(0, log₁₀ of the selection's peak ratio) so a slice brighter than the dataset reference extends the ramp rather than saturating; because vmax always covers the peak, `clipped_high` is identically 0 in relative mode and is **omitted**; `clipped_low` (< 10⁻³) and `empty_cells` are counted from the ratio matrix. The a.u. ramp reads `Average hit density (a.u.)` with end labels **derived from `scale.vmin`/`scale.vmax`** (`10⁻³ a.u.` … `10^{vmax} a.u.`, so `10⁰·³ a.u.` when a slice exceeds the dataset peak) and `visualMap.max = scale.vmax`; tooltips: `0.42 a.u. · 3.1e-7 GeV mm⁻² per event · 20 × 20 mm bin`; footnote and caption: `ρ_ref = … GeV mm⁻² per event (selection peak | dataset peak)`. When the reference is the selection peak the header badge reads **Autoscaled**, as the lab path does for an unlocked ramp.
* **Other channels and parameters in this frame**: `lock_scale` and `scale_mode` are accepted but ignored (`rho_norm` replaces them; the response echoes `frame.rho.norm`); `mode=gradcam` keeps the lab's fixed 0–1 linear scale, computed as Σ(E·cam)/ΣE (or count-weighted per `weighting`, exactly as in lab) over the splatted sub-deposits via `splat.resample_ratio`, so attention maps remain comparable across frames and selections.
* Palette: Viridis default, Turbo available.

### 1.6 Ensemble overlays — aggregate, dispersion and uncertainty as separate marks

Per event and shower the projected **slopes** s_x = u′_x/u′_z, s_y = u′_y/u′_z are linear statistics; the panel-relevant aggregate is their mean, so:

* **Axis** (dashed): `x′(z′) = ∓⟨D_entry⟩/2 + ⟨s_x⟩·z′`, `y′(z′) = ⟨s_y⟩·z′` from z′ = 0 to the back face. Exactly two.
* **Dispersion band** (uncapped shaded wedge behind the axis): ± σ(s)·z′ with σ the sample SD (ddof = 1) of the per-event slope in that panel's transverse coordinate — "the spread of individual shower directions", named in the bin tooltip of every point inside it (the wedge itself is silent, so the bins under it stay readable). Requires N ≥ 2 (labelled `1 d.o.f.` at N = 2).
* **Mean uncertainty** (thin envelope): ± t₀.₉₇₅,N−1·σ/√N·z′ — "95 % interval of the ensemble axis". Both marks name their quantity, per CLAUDE.md's whisker rule.
* **Coherence**: R̄′_S (transverse resultant length of û′), Rayleigh p = exp(−N·R̄′²) and N are printed beside each axis from N ≥ 2; the axis is faded when p > 0.05 (D 240–260 mm: N = 221, R̄′ = 0.21 ⇒ z = 9.8, p ≈ 6×10⁻⁵, drawn full; N = 20, R̄′ = 0.30 ⇒ p = 0.17, faded).
* **Anchors** A (diamond) / B (circle) at (∓⟨D_entry⟩/2, 0) on XY and at z′ = 0 on the depth panels, each with an uncapped range bar ± σ(D_entry)/2 along x′ (sample dispersion of the entry separation) and the t-based SE of ⟨D_entry⟩ in the tooltip. The dashed separation vector is labelled `⟨D_entry⟩ = … mm (entry) · ⟨D⟩ = … mm (dataset, 3-D)`.
* **Measured ensemble entry centroids** `truth_voxel` / `pred_voxel` from `centroids.compute` on the canonical bundle (canonical coordinates via `bundle.axis()`), and **`canonical_mean`** = mean rotated dataset 3-D centroids (from the frame statistics), all in `CentroidPair` shape under `payload.centroids` with a `CENTROID_STYLE` entry. Their offsets from the anchors are reported per selection in `frame.anchor_offsets` and the footnote.
* Individual trajectories are suppressed in this frame. Front and back faces are drawn as rules at z′ = 0 and 1209.5 mm; the transverse outline rotates per event and has no ensemble image (footnote says so).

### 1.7 Low-N handling (numbers from N ≥ 2, marks gated separately)

| N_frame | Reported numbers | Drawn marks |
|---|---|---|
| 0 | notice "no selected event has a defined frame" | empty panels, no axes |
| 1 | ⟨D_entry⟩, slopes (single event); R̄′, p, σ **undefined — stated** | the event's own two axes, labelled "single event, not an ensemble"; no band; fitted axes marked provisional |
| 2 ≤ N < 20 | all numbers, R̄′/p labelled `weak (N = …)`, σ at N = 2 labelled `1 d.o.f.` | axes + dispersion band + SE envelope; fitted axes labelled provisional (N); comb reported from measurement |
| ≥ 20 | full statements | as above without provisional label |

ρ_ref defaults to the selection peak (decision 4) so a low-N slice never rescales any other view; switching `rho_norm = dataset` makes colours comparable and the ramp extends above 10⁰ when a slice exceeds the dataset peak.

### 1.8 Publication export

Present already: white `#FFFFFF`, `#111827` ink ≥ 4.5:1, outward ticks, 300 DPI, mm-authored widths, zoom/pan and active series captured. Missing: an isolated `<g id="figure-disclosure">` and disclosures read **structurally** from the payload. zrender's SVG painter flattens the display list (ECharts `graphic` groups never become `<g>`), so the band is composed by our code from the same laid-out caption lines and spliced before `</svg>` (root carries width/height/viewBox in logical px; `sharpenRasterHints` already post-processes there). PNG keeps the caption as ECharts graphics from the same layout, so the formats cannot drift. Text baseline: zrender draws text centred on the line (`dominant-baseline="central"`), so SVG `y = offsetY + top + 0.71·fontSize`; styles are read from each laid-out item, never from the (restored) `THEME`.

---

## 2. Execution & Data Requirements

* **No schema, ingest or Docker change.** Existing databases work as-is.
* **Dependencies unchanged**; tests via `.venv/bin/python -m pytest`.
* **Run**: `CALOSRV_DATA_DIR=./data DUCKDB_MEMORY_GB=4 .venv/bin/python -m calosrv` or `docker compose up --build`.
* **Settings**: `CALOSRV_CANONICAL_CACHE_ENTRIES` (default 32, dataclass field with default placed after `cors_origins`).
* **API**: `GET /api/projections` gains `frame=lab|canonical` (default `lab`) and `rho_norm=selection|dataset` (canonical only, default `selection`). The canonical envelope keeps **every top-level key and shape** of the lab envelope so `main.js` reads it unchanged: `meta` (with `resolution {mode, requested, r_x, r_y, r_z, pitch_mm, shapes, warnings}`, `stagger` measured on the canonical accumulation XY with canonical wording, `notices`), `panels`, `centroids`, `selection` (unchanged `summary.summarise`), `filter`, `overlays` (`trajectories: []`, `axes: {}`, `coherence`, plus `ensemble_axes`, `anchors`), `slab`, plus the new `frame` block. One deliberate difference: `centroids.truth_dataset` (a lab-frame mean of dataset centroids) is **omitted** and `centroids.canonical_mean` is its frame-consistent replacement (`projection.js` skips absent keys). **`display=native` in this frame means the 20 mm accumulation pitch with no resampling**, `r_x`/`r_y` = the cropped grid shape, `r_z` = 60; `display=continuous` resamples the cropped transverse axes to R (`r_y = round(R·span_y/span_x)`); the canonical display caption reads "Canonical grid: 20 mm bins, no resample" or "Canonical grid resampled to R = … (area-weighted)". Payload < 100 KB with a budget guard.
* **Frontend state**: `frame` (default `canonical`) and `rho_norm` (default `selection`) join `DEFAULTS`/hash; `frame` adds a `canonical` token to export filenames.

### Payload additions (canonical only)

```
frame: {
  kind: "canonical", anchor: "entry_backprojection", z_front_mm,
  pitch_mm: 20, footprint_mm: [48.3, 48.6], subsample_k, subsample_budget_rows, rows_scanned,
  window: { x: [-hx, hx], y: [-hy, hy], margin_mm, energy_fraction_outside },
  fit: { percentiles: [1, 99], provisional: bool,
         xy: { x: [lo, hi], y: [lo, hi], energy_fraction_outside },
         yz: { y: [lo, hi], energy_fraction_outside }, xz: { x: [lo, hi], energy_fraction_outside } },
  n_events, n_excluded_no_frame, n_ill_conditioned, ill_conditioned_threshold_mm: 80,
  d_entry: { mean, median, sd, se, min, max }, d_dataset: { mean, median, sd, min, max },
  psi_resultant, comb: meta.stagger (repeated for the caption),
  rho: { norm: "selection"|"dataset", ref: { xy, depth }, unit: "GeV/mm^2/event", decades: 3, selection_peak: { xy, depth } },
  axes: { a: { origin: [x,y,z], slope: [sx, sy], slope_sd: [..], slope_se95: [..], direction: [ux,uy,uz],
               resultant_transverse, rayleigh_p, n }, b: { ... } },
  anchor_offsets: { truth_voxel: { a: [dx, dy], b: [dx, dy] }, canonical_mean: { ... } },
  notes: [ ... ]
}
overlays.ensemble_axes: { yz: { a: { axis: [[z,y],[z,y]], band: [[z,lo,hi],...], envelope: [...] }, b: {...} }, xz: {...} }
overlays.anchors: { a: { x, y, spread: [lo, hi] }, b: {...} }
panels.<p>.axes.{row,col}.symbol: "x′" | "y′" | "z′"      (lab: "x" | "y" | "z")
panels.<p>.scale: { scale: "log10", vmin: -3, vmax: >= 0, unit: "a.u.", rho_ref, rho_unit, decades, norm, clipped_low, empty_cells, shared_with? }   (no clipped_high: vmax always covers the peak)
panels.<p>.total = Σ E inside the panel window [GeV]   (overwritten; same meaning as lab)
panels.<p>.total_energy_all_gev, panels.<p>.n_events
panels.<p>.topk[].value in GeV/mm^2/event (physical); the client divides by scale.rho_ref for a.u.
```

---

## 3. Implementation

One responsibility per file; ✚ = new. Lab code paths stay behaviourally identical (a snapshot test asserts byte-identical lab payloads on the demo DB).

### 3.1 Backend

| File | Change |
|---|---|
| ✚ `calosrv/grid/frame.py` | Pure NumPy: `entry_anchor`, `frame_of → FrameParams(x0, y0, psi, d_entry)`, `rotate_xy`, `rotate_direction`, `unit_direction`, `cell_footprint(lattice) → (w_x, w_y)` (twin rule §1.3), `plan_window(d_entry_max, theta_max, lattice, pitch) → CanonicalGrid(pitch, half_x, half_y, x_edges, y_edges, z_edges)` with `axis(name) → Axis` (bin centres; z′ = z − z_f), `choose_subsample(rows_scanned, budget) → k`; constants `CANONICAL_PITCH_MM`, `SHOWER_MARGIN_MM = 500`, `SUBSAMPLE_ROW_BUDGET = 30_000_000`, `MAX_SUBSAMPLE = 6`, `ILL_CONDITIONED_D_MM = 80`, `RAMP_DECADES = 3.0`, `PROVISIONAL_N = 20`. |
| ✚ `calosrv/query/canonical.py` | `frame_statistics(con, record, spec) → FrameStats` (event table: N_frame, n_excluded, D_entry/D moments + SE, max D_entry, max θ, per-shower mean/SD of slopes, ⟨û′⟩, R̄′, Rayleigh p, R̄(ψ), ill-conditioned count, mean canonical 3-D centroids, hits in selection). `build_sql(record, spec, grid, k, footprint, sampled)`: CTEs `ev → fr → sub → pts → rot`, grouping sets with the twelve `_QUERY` aggregates plus `sum(energy) FILTER (WHERE outside)`, slab filter; params `$x_coords`, `$y_coords` (registry arrays), `$zf`, `$wx`, `$wy`, filter params via `spec.where_sql("p")` / `spec.where_sql()`. `fetch_canonical(...) → CanonicalBundle` (`xy, yz, xz: Panel`, `grid`, `stats`, `k`, `energy_outside`, `exact`, `query_ms`, `n_hits`; `axis(name)` delegating to `grid`; `nbytes`). `explain()`. |
| ✚ `calosrv/query/window.py` | `fit_window(bundle) → WindowFit` (energy-weighted p1–p99 per panel from marginals, snapped to edges, `energy_fraction_outside`, `provisional = N < 20`, note text). |
| ✚ `calosrv/query/density.py` | `render_canonical(bundle, fit, plan, rho_norm, reference) → panels`: crop → optional resample (`splat.overlap_matrix` on uniform edges; `r_y = round(R·span_y/span_x)`; depth passthrough) → ⟨ρ⟩ → ratio vs ρ_ref → `scale.relative_log_scale(ratio, rho_ref, decades)` → `matrix.encode_matrix(ratio, …)` then overwrite `total` with Σ E and `topk` with physical ⟨ρ⟩ values; Grad-CAM via `splat.resample_ratio` with the lab's fixed 0–1 scale. `fit_budget(render, limit=96_000)`: continuous → R × 0.75 steps; native → merge transverse bins pairwise (2 × 2 on XY, **2 × 1 on the depth panels so z′ keeps its 60 layers**; exact for a uniform grid) then `topk` trimmed; each step adds a notice. `dataset_reference(con, record, settings) → {xy, depth}` computed once per table from the full-range canonical bundle (cached). |
| ✚ `calosrv/query/ensemble.py` | Axis, band and envelope polylines per depth panel from `FrameStats`; the 95 % envelope uses a **Student-t table t₀.₉₇₅ for df = 1…30** (no scipy) and the normal quantile only above df = 30, per CLAUDE.md's small-N rule; anchors with spread; wording fragments (single-event, weak, provisional). |
| `calosrv/encode/scale.py` | `relative_log_scale(ratio, rho_ref, decades) → ColorScale` (vmin = −decades, vmax = max(0, log₁₀ ratio.max()), unit `a.u.`, mode `relative`, counts `n_below`, `n_above`, `n_empty`); `ColorScale.as_dict` gains `rho_ref`, `rho_unit`, `decades`, `norm`. |
| `calosrv/encode/matrix.py` | axis dicts gain `symbol` (from a `symbols` argument; lab passes `x/y/z`). |
| `calosrv/query/projections.py` | `NativeBundle.axis(name) → lattice.axis(name)`. |
| `calosrv/query/centroids.py`, `calosrv/query/panels.py` | replace `lattice.axis(...)`/`lattice.z` reads with `bundle.axis(name)` **only in the two consumers the canonical route reaches**: `centroids._pair_from_panel`/`compute` and `panels.shower_axes` (it is reused for the measured per-layer centroid diagnostic in `frame.anchor_offsets`). `render_panel`/`render_all` are **not** touched — `density.render_canonical` does its own crop/resample/encode. Lab results unchanged (golden snapshot test on `render_all` + `centroids.compute` + `shower_axes`). |
| `calosrv/query/cache.py` | `get_cache(max_entries, name="lab")` becomes a name-keyed registry; `reset_cache()` clears all; `invalidate_all(table_name)` helper used at [routes_upload.py:89,148](calosrv/api/routes_upload.py#L89) and [routes_experiments.py:62](calosrv/api/routes_experiments.py#L62). Canonical key = `(*spec.cache_key(), sampled, "canonical", pitch, k, footprint)` — `table_name` stays first. |
| `calosrv/config.py` | `canonical_cache_entries: int = 32` (defaulted field after `cors_origins`). |
| `calosrv/api/routes_projections.py` | `frame`, `rho_norm` params validated; lab branch unchanged; canonical branch: `frame_statistics → cell_footprint → plan_window → choose_subsample(rows_scanned) → cache → stagger.detect(bundle.xy accumulation matrix, uncropped) → fit_window → (dataset_reference if requested) → render_canonical → centroids.compute → ensemble_axes → notices` (excluded events, ill-conditioned ψ, energy outside window/fit, comb measurement with canonical wording, k regime, provisional ranges, budget downgrade, `include_undefined_d` cannot co-register; `lock_scale`/`scale_mode` ignored with a note). Envelope as in §2 (`truth_dataset` omitted, `canonical_mean` added). |
| `calosrv/query/experiments.py` | `describe()` adds `frames: ["lab", "canonical"]`, `z_front`. |

### 3.2 Frontend (vendored ECharts 5.5.1 only)

The bundle is ECharts **5.5.1** (`echarts.version`). An earlier revision of this heading said 5.6.0, which is the `zrender` dependency version that the same file also contains.

| File | Change |
|---|---|
| `static/index.html` | Sidebar `Reference Frame` radios (`name="frame"`: canonical / laboratory) with `info-dot#info-frame` and `.caption#frame-caption`; under Colour Map a `Density normalisation` radio pair (`name="rho_norm"`: selection peak / dataset peak) shown only in canonical, replacing the lock-scale checkbox there; card titles wrapped as `<span id="title-xy|yz|xz">` **inside** the `<h2>` before `.tag`, so `setText` never touches `.card-actions` (kept last for the export-toolbar test); D-slider hint mentions `D_entry`. New ids: `info-frame`, `frame-caption`, `title-xy`, `title-yz`, `title-xz`, `ctl-rho-norm` — all present in markup (id audit) and in `REQUIRED_IDS`. |
| `static/js/state.js` | `frame: 'canonical'`, `rho_norm: 'selection'` in `DEFAULTS`; `projectionParams()` sends both. |
| `static/js/main.js` | radio wiring for `frame` and `rho_norm` (mirrors [main.js:509](calosrv/static/js/main.js#L509)); `restoreControlsFromState` restores both radios and applies canonical-mode control states at boot; `loadProjections` branches on `payload.frame?.kind`: passes `ensembleAxes`, `anchors`, `frame` to panels, sets depth-panel `isometric` by the §1.4 rule, writes canonical display/channel captions and footnotes (anchor definition, N/excluded, ⟨D_entry⟩ vs ⟨D⟩ with SE, ρ_ref + norm, windows + outside fractions + provisional, k/regime + measured comb, R̄′/p per axis, ψ-conditioning, anchor offsets, boundary statement), `frame` info-dot notices, Autoscaled badge; `EXPORT_PANELS` titles are functions of the frame; `resolve()` adds `disclosure: figureDisclosure(lastProjections, panelId, state)`. |
| `static/js/panels/projection.js` | `AXIS_LABEL` keyed by `axis.symbol` (x′ — along separation; y′ — normal to shower plane; z′ — depth from front face); all tooltips and `describeView` callers use `axis.symbol ?? axis.name`; tooltip prints a.u., GeV mm⁻² per event and bin size when `scale.unit === 'a.u.'`; `addEnsembleAxes` (dashed axis, shaded dispersion band, thin SE envelope, faded when `rayleigh_p > 0.05`, tooltips naming each quantity), `addAnchors` (markers + uncapped spread bars), `addDepthBounds`; `CENTROID_STYLE.canonical_mean`; `isometric` settable per render and honoured by `exportMetrics`; **view policy**: reset `this.view` only when the frame kind or experiment changes, otherwise clamp the existing window to the new extents (so slider-drag previews keep the zoom). |
| `static/js/scale.js` | `visualMap`: for `unit === 'a.u.'`, `min/max` from `scale.vmin/vmax` and both end labels derived from them (`10^{vmax} a.u.` / `10^{vmin} a.u.`, superscripted as today), formatter in a.u.; exports `rampTitle(scale, metrics)` → a `graphic` text `Average hit density (a.u.)` positioned from the ramp geometry (vertical: above the bar at `right`; horizontal print: centred above the bar, `bottomInset`-aware) that the panel adds to `graphic` in both formats. |
| ✚ `static/js/export/disclosure.js` | `figureDisclosure(payload, panelId, state) → string[]` from structured fields (frame + anchors, counts, ρ_ref/norm/decades, windows + outside + provisional, k/regime + comb lag-1, ψ conditioning, R̄′/p, `scale.clipped_low` (and the lab ramp's `clipped_high`), `meta.stagger.note`, exact/sampled). Imports `formatSci`, `formatInt` from `../scale.js` (so it is inside the stamped graph). |
| `static/js/export/caption.js` | `buildCaption({…, disclosure})` renders disclosure lines before the live footnote (de-duplicated); `describeSelection(state, experiment, selection, frame)` says `canonical centre-of-separation frame, 20 mm grid` and `average hit density (a.u., ρ_ref = …)` when canonical; exports `captionToSvg(graphic, offsetY) → '<g id="figure-disclosure">…</g>'` (`dominant-baseline="central"`, y = offsetY + top + 0.71·fontSize, XML-escaped, styles from each item). |
| `static/js/export/menu.js` | forwards `disclosure` from `resolve()` to `exportPanel`. |
| `static/js/export/figure.js` | SVG: build the print option with `graphic` = ramp title only (caption height still reserved), splice `captionToSvg` before `</svg>` in the post-processing step; PNG: caption graphics as today. The synchronous THEME-swap block is unchanged. |
| `static/js/export/filename.js` | `describeSlice` pushes `canonical` when `state.get('frame') === 'canonical'`. |

### 3.3 Tests

| File | Coverage |
|---|---|
| ✚ `tests/test_frame.py` (no DB) | anchors → (∓D/2, 0) to 1e-12; isometry on random clouds; `rotate_direction` keeps norm and u_z; back-projection sign on a synthetic straight-line shower; `cell_footprint` on a synthetic twinned lattice (exact expected values) and on the demo lattice **against an independent 2-D within-row/within-column measurement of that lattice** (≈ 52.7 × 52.4 mm there — the v37 constants 48.3 × 48.6 are asserted only in `test_canonical_subset.py`); `plan_window` snapping/coverage; `choose_subsample` table (22.5 M → 2, 1.27 M → 4, 73 k → 6). |
| ✚ `tests/test_canonical.py` (demo DB) | EXPLAIN contains `naming.proj_table(name)` exactly once (event and RANGE scans expected, documented); Σ E(XZ set) == Σ E of framed hits (1e-9) for k ∈ {1, 3, 6}; slab energy; Σ⟨ρ⟩·N·ΔA == Σ E per panel at native / R = 90 / 250; per-event canonical slab centroid == rotate(lab slab centroid) skipping empty-slab events; `truth_voxel` at N = 1 == rotated lab `truth_voxel`; frame statistics vs NumPy recomputation; `fit_window` covers ≥ 98 % and reports the rest, `provisional` true at N = 2; ratio ≤ 1 vs selection peak, codes in [0, 255], `clipped_low` counted; `stagger.detect` report present; exactly two axes with band/envelope, origins at ∓⟨D_entry⟩/2; N = 2 labels (`1 d.o.f.`, `weak`); `total` is energy, `topk.value` physical; payload < 100 KB at native, R = 150/200/400 and guard exercised at 512; no raw hits; **lab snapshot**: `render_all` + `centroids.compute` output on the demo DB byte-identical before/after the `bundle.axis` refactor (golden JSON committed under `tests/golden/`). |
| ✚ `tests/test_canonical_subset.py` | runs only if `CALOSRV_TEST_SUBSET_CSV` is set (the v37 subset from Verification step 2): k = 1 comb measurement, budget on a realistic window, dataset-reference ρ_ref, R̄′ rising on a wide-D slice. |
| `tests/test_api.py` | `frame=canonical` → 200, `frame.kind`, `scale.unit == 'a.u.'`, two `ensemble_axes`, `trajectories == []`, `meta.resolution.pitch_mm`, `meta.stagger` present; `frame=hologram` → 422; `rho_norm=dataset` changes `scale.rho_ref` and `norm`; canonical and lab never share cache entries; second identical canonical request `cached`; `include_undefined_d=true` notice. Existing lab tests untouched. |
| `tests/test_export_assets.py` | `disclosure.js` added to served + stamped + reachable lists (it imports `../scale.js`); assert `figure.js` contains `figure-disclosure` and `caption.js` exports `captionToSvg`; `menu.js` forwards `disclosure`. |
| `tests/test_queries.py` | one assertion: `NativeBundle.axis("x").coords` equals `lattice.x.coords`. |

### 3.4 Documentation

* `README.md`: section "Canonical centre-of-separation frame" (transform, anchors and their measured residuals as a *distribution*, D_entry vs D, footprint and k, ⟨ρ⟩ and the two normalisation references, window fitting and provisional labelling, what is drawn: axes + dispersion band + SE envelope, what is not), toggle description, `frame`/`rho_norm` API params, module layout, disclosure band.
* `CLAUDE.md` §2 "Never Average a Circular Quantity": sanctioned exception — averaging is permitted **only after** SE(3) co-registration, the drawn axis must carry its dispersion band and SE envelope, and R̄′, Rayleigh p and N are always printed beside it (numbers from N ≥ 2, marks gated as §1.7).
* `plan.md` at the repository root = this document.

### 3.5 Order of work

1. `plan.md`; `grid/frame.py` + `tests/test_frame.py`.
2. Golden lab snapshot test, then the `bundle.axis` refactor (`projections.NativeBundle.axis`, `centroids`, `panels.shower_axes` only) — green before anything canonical exists.
3. `query/canonical.py` (+ conservation / invariance / single-scan tests).
4. `query/window.py`, `encode/scale.py`, `encode/matrix.py` symbol, `query/density.py`, `query/ensemble.py`.
5. Cache registry + invalidation, config, route branch, experiments exposure; API tests.
6. Frontend: state/markup/wiring → panel rendering → footnotes/badges → export (disclosure, caption, SVG splice); export-asset tests.
7. Docs; full `pytest`; manual verification.

---

## 4. Data Integrity Checklist

- [ ] **Energy conservation**: Σ⟨ρ⟩·N·ΔA per panel == Σ E of framed hits inside the window at every k and R; energy outside the accumulation window and each fit window reported.
- [ ] **Frame invariance**: isometry test; per-event canonical centroid == rotated lab centroid (exact); anchors at (∓D_entry/2, 0) analytically; measured anchor–centroid offsets reported **per selection**.
- [ ] **Data-fitted baselines**: no hard-coded transverse bounds; accumulation window from the selection's max D_entry and max θ plus a stated margin; display window p1–p99 with disclosure and provisional labelling below N = 20; z′ full depth by decision.
- [ ] **Zero axis distortion**: XY 1:1; depth panels isometric when the §1.4 rule holds, otherwise true-extent axes and a footnote; z′ locked to layers; no dual axes.
- [ ] **Uncertainty by default**: ensemble axes carry a dispersion band (sample SD, uncapped) and a Student-t SE envelope, each named; anchors carry D_entry spread and SE; R̄′, Rayleigh p, N printed; numbers from N ≥ 2, marks gated.
- [ ] **Colour scale**: a.u. ramp 10⁻³ … 10^{vmax} (vmax ≥ 0 always covers the peak) with ρ_ref, its reference (selection | dataset) and unit printed; end labels derived from vmin/vmax; `clipped_low` counted; Autoscaled badge when per-selection; Viridis/Turbo only.
- [ ] **Lattice rules**: index → mm only via stored arrays; physical footprint 48.3 × 48.6 mm derived and echoed; comb **measured** by `stagger.detect` on the canonical raster, never asserted.
- [ ] **Architecture B**: all transforms in DuckDB/NumPy; payload < 100 KB with a guard that has a lever in both display modes; no raw hits; vendored ECharts.
- [ ] **Export**: white background, `#111827` ink, outward ticks, zoom/pan captured, `<g id="figure-disclosure">` in SVG with structured disclosures; PNG caption from the same layout; frame-aware provenance sentence and filename.
- [ ] **Regression**: lab payloads byte-identical (golden test); API default `frame=lab`; all existing tests green.

---

## Verification (end to end)

1. `.venv/bin/python -m pytest`.
2. **Realistic subset** without touching the root-owned production DB: attach `data/calorimeter.duckdb` read-only, `COPY (SELECT * FROM hit_v37 WHERE event_number < 1500 ORDER BY event_number) TO '<scratch>/v37_sub.csv'`, ingest with `python -m calosrv.ingest --direct --input <scratch>/v37_sub.csv --table v37_sub` into a scratch `CALOSRV_DATA_DIR`; export `CALOSRV_TEST_SUBSET_CSV` and rerun pytest so `test_canonical_subset.py` runs. Script checks on `GET /api/projections?frame=canonical&table_name=v37_sub`: size < 100 KB; `frame.n_events` == events with non-null `cax`; `total` consistency; axis origins at ∓⟨D_entry⟩/2; `meta.stagger` populated; then D-slice requests show R̄′ rising and `fit` windows shrinking as in discovery.
3. **Browser**: serve the scratch DB, open `/`: toggle defaults to canonical; showers at ∓⟨D_entry⟩/2 on X′Y′; two dashed axes with bands on the depth panels; tooltip shows a.u. and GeV mm⁻²; footnotes carry ρ_ref, windows, k, comb lag-1, R̄′/p; switch normalisation to dataset peak and confirm the ramp/badge change; switch to Laboratory and confirm previous behaviour; zoom, nudge a slider, confirm the view is kept; export SVG + PNG for X′Y′ and YZ and confirm `<g id="figure-disclosure">` wraps the caption, white background, `#111827` text, ramp title present.
4. **Performance**: `frame=canonical` on the full `v37` selection ≤ 2.5 s cold (k = 2; pre-warmed at start-up so the first page load hits the cache), cache hit ≤ 50 ms; a 1000-event slice ≤ 0.5 s (k = 4).

---

## Implementation notes (post-review)

Deviations from the approved plan above, each verified against the code and the production data. Where a section above still states the superseded figure, this list wins.

1. **k ≥ 2 is enforced** (`grid/frame.py`: `MIN_SUBSAMPLE = 2`, honoured by `choose_subsample`). §1.3's budget line assumed k = 1 for the full dataset because the ensemble of rotation angles would smooth point-binned cell centres. Measured, it does not: lag-1 autocorrelation of the shower-core row −0.26 over 20 143 co-registered events and −0.47 on a 221-event slice at k = 1, against +0.4 to +0.7 at k ≥ 2. The full production selection therefore scans at k = 2 (~90 M sub-deposit rows, 2.0 s cold) rather than k = 1 (0.54 s), and Verification step 4's "≤ 1 s cold" no longer applies to the cold path. Sampled drag previews cap k at 2 (`PREVIEW_MAX_SUBSAMPLE`).
2. **The cold cost is hidden by a cache warmer** (`query/canonical_cache.py: warm`): a daemon thread started from `app.py`'s lifespan for every ready experiment and again from `ingest/jobs.py` after each successful ingest. Best-effort — a failure is logged, never raised — because the request path computes the same bundle on demand.
3. **`_bundle_for` lives in `query/canonical_cache.py`**, not in the route module: frame statistics → `plan_window` → `choose_subsample` → cache lookup → `fetch_canonical` (+ `scale_sample` when previewing). Placing it in the query layer lets the ingest job runner warm the cache without importing from `api/`; `api/frame_canonical.py` re-exports it and `dataset_reference` under the planned names.
4. **The footprint is measured from occupancy, not from the lattice** (`frame.footprint_from_occupancy`, memoised per table and row count in `canonical.cell_footprint`). The twin rule over the sorted coordinate union (§1.3, kept as `footprint_axis_width`) mis-estimates a sparse lattice — 52.7 mm on the two-event demonstration file against a true 48.3 — because the twins it relies on are missing there. The implemented measurement reads the pitch between *adjacent* populated cells sharing a y row (x) or an x column (y), from the lowest gap cluster, and gives 48.27 × 48.6 mm on both the production lattice and the demonstration file. The lattice-only rule survives as the fallback for a table with no two cells in one row.
5. **Accumulation window on the full production selection is ±3980 × ±1380 mm** (398 × 138 bins of 20 mm; max D_entry 5176 mm, θ_max 0.628 rad, margin 500 mm), leaving 0.008 % of the energy outside, counted and reported. §1.4's "±3500 × ±1380" was an estimate from discovery.
6. **`centroids.truth_dataset` is omitted and `centroids.canonical_mean` added** in the canonical envelope, as §2 states; recorded here because §1.6's "all in `CentroidPair` shape" could be read as including it. The lab-frame mean of dataset centroids is exactly the position average this frame exists to avoid; `canonical_mean` averages the same centroids *after* co-registration.
7. **`scale.clipped_high` is omitted** in relative mode: vmax = max(0, log₁₀ of the selection's peak ratio) always covers the peak, so the count is identically zero and printing it would suggest a clip that cannot happen. `clipped_low` and `empty_cells` remain.
8. **Statistics below two events are undefined, not trivial** (`query/canonical.py: frame_statistics`): R̄′, Rayleigh p and the slope dispersion are `null` for N = 1 in the `frame.axes` block as well as in `frame.ensemble`, so no consumer can read the trivial resultant of 1.0 of a single direction; the export disclosure reads the gated block.
9. **⟨D_entry⟩ is quoted with its Student-t 95 % interval** (`Moments.ci95_half`), labelled as such on the panel and in the figure; the bare standard error is still reported in the payload. At N = 2 the two differ by a factor 12.7.
10. **The comb is measured on energy as well as occupancy** (`query/stagger.py: intensity_lag1`): a footprint splat fills every bin under a cell by construction, so occupancy alone cannot see a residual intensity comb; the lag-1 of the brightest row's and the column-summed energy profiles is reported beside it, and either below −0.10 is called a comb. The occupancy percentage (of the whole window, margins included) is no longer quoted.
11. **Clamping a filter to the dataset range only when it intersects it** (`FilterSpec.clamped`): an interval lying wholly outside the data stays empty instead of collapsing onto the boundary event, so the KPI card and the canonical panels can never disagree about N.
12. **The dataset reference discloses its sub-cell factor** (`frame.rho.ref_k` against `frame.rho.selection_k`, with a notice when they differ): a peak is a maximum statistic and the full-range bundle is splatted more coarsely (k = 2) than a slice (k = 4–6).
13. **Depth ends agree**: ensemble axes, dispersion bands and the drawn back-face rule all end at the last sampling layer (`frame.depth_mm`), in the convention that puts the front face at the first one.
14. **Zoom and Auto-fit RoI keep the panel isometric on non-square extents**: a kept window is re-proportioned to the new fitted extent's span ratio, and the RoI fit widens the narrower axis to that ratio rather than to a square.
15. **`meta.sample_percent`** is emitted by both frames so the exported figure names the true sampling fraction; `overlays.coherence.note` and `selection.centroid_dataset.label` carry canonical wording in the canonical envelope; ignored `lock_scale`/`scale_mode` values produce a notice; the ρ_ref reference is shown in the status bar.

### Canonical panels revision: Continuous Field, transparent floor, symmetric windows, lighter anchors

This follow-up change to the canonical panels was planned and adversarially reviewed on its own, then measured read-only on production v37 (20 143 co-registered events). Where §1–§3 above state a rule that this revision replaced, the notes below win. The change fixed four defects:

- the frame opened on the raw 20 mm grid, which showed a five-event selection as rotated 48 mm cell blocks;
- sub-floor bins were folded into the opaque bottom colour, which painted the whole crop as a dark-purple rectangle;
- the percentile window was asymmetric, so the origin was off-centre (for example x′ ∈ [−260, 340]);
- 15 px filled anchors, a 6 px spread bar and a floating ⟨D_entry⟩ badge covered the shower cores.

16. **Display windows are symmetric about the origin at p0.1–p99.9** (`query/window.py: symmetric_axis`). This supersedes §1.4's display window and the `fit.percentiles: [1, 99]` of §2.
    - **Steps, per cropped transverse axis:**
      1. Δ = max(|lo|, |hi|) of the energy-weighted p0.1/p99.9 fit.
      2. Raise Δ to the floor (`floored`).
      3. Snap it outward to 20 mm.
      4. Clamp it to the accumulation half-width (`clamped`).
      5. Convert to indices, `lo_i = round((half − Δ)/p)` and `hi_i = n − lo_i`.

      The range is reported from the bin count, so it is exactly antisymmetric. The outside fraction is re-measured on the final window.
    - **The floor** is 200 mm while provisional (`SHOWER_RADIUS_MIN_MM`: the median single-shower slab |y′| p98). Otherwise it is `WINDOW_FLOOR_FOOTPRINTS` × 48.6 mm, snapped to 100 mm. The 200 mm is not the narrowest robust window: D-only slices at N ≥ 20 measure y′ ±360 mm or more, but E₁, E₂ < 2 GeV (N = 691) measures ±160 mm, < 1.5 GeV (N = 643) ±100 mm and < 1 GeV (N = 468) ±80 mm, which the 100 mm floor holds. A fixed 200 mm floor would widen those 1.25–2.5×.
    - **Payload.** `fit` gains `rule: "symmetric"`, `percentiles: [0.1, 99.9]`, `floor_mm` and `snap_mm`. Each axis gains `percentile_range`, `symmetric`, `half_width` (null on depth), `floored` and `clamped`.
    - **Unchanged.** `fit_axis` keeps its 1/99 defaults as the primitive, depth is never cropped, and the provisional labelling is as before.
    - **Why.** A 1–99 crop cut the halo 15–110× above the 10⁻³ display floor and left 14–99% of the X′Y′ boundary bins above it; at 0.1–99.9 that figure is 2–11%. This is recorded as an exception in CLAUDE.md §2, "Outlier Clipping".
17. **Continuous Field is a conservative kernel reconstruction, and the canonical frame opens in it.** This supersedes §2's "`display=continuous` resamples the cropped transverse axes to R" by area-weighted overlap.
    - **The operator** (`grid/kernel.py`, maths only) is `W[r, c] = G_c(d_{r+1}) − G_c(d_r)`, so every column telescopes to the kernel mass inside the destination and no entry is negative.
    - **Box** is `splat.overlap_matrix`, unchanged.
    - **Gaussian** is `overlap_matrix + Δ_r[(σ/w)(ψ̃(u_a) − ψ̃(u_b))]` with `ψ̃(z) = φ(|z|) − |z|·½erfc(|z|/√2)`. ψ̃ is exactly zero at |z| ≥ 9, so σ → 0 is the box.
      - `erfc` is Numerical Recipes' `erfcc`, max fractional error 1.04 × 10⁻⁷. Abramowitz & Stegun 7.1.26 was rejected: its tail error is 0.3–1.8%.
      - ψ̃ is evaluated once per edge, and only inside the 9σ band. This deviates from the per-half plan. It gives the same numbers bit for bit on 200 random grids and cut the N = 5 render from 8.9 to 5.4 ms, under the 7 ms target.
    - **Tent** is the exact linear interpolation through the bin centres. It raises `ValueError` on a non-uniform source.
    - **Precision.** Every input is cast to float64 (guard 8b.3); float32 edges give output bit-identical to the float64 path.
    - **Policy** (`query/reconstruct.py: choose_kernel`): Native gets `none`. N < 50 gets a Gaussian of σ = 10 mm (`SMOOTH_SIGMA_MM = CANONICAL_PITCH_MM / 2`). N ≥ 50 gets the tent.
    - **Spread per 20 mm bin:** box 5.77 mm, tent 8.165 mm, Gaussian 11.547 mm RMS.
    - **Source bins.** A continuous axis starts from the *full* accumulation axis sliced to the window plus the kernel's reach: 1 bin for the tent, ⌈9σ/p⌉ + 1 for the Gaussian. Depth always passes through.
    - **Rejected:** bicubic (negative lobes, overshoot) and point interpolation (not conservative).
    - **Native Grid** is kept as the audit view: raw bins, the new window and the transparent floor.
18. **Energy bookkeeping is measured after reconstruction.**
    - Per panel, `total` is the in-window GeV after reconstruction, and `energy_fraction_outside_window = clip(1 − total / total_all, 0, 1)`. `energy_fraction_outside_window_raw` is the window-fit figure, and `energy_outside_window_gev` and `kernel` are added.
    - In continuous mode the test asserts `total == inside_weights_row @ E @ inside_weights_colᵀ` to 10⁻¹² relative. Production X′Y′ agrees to 3.5 × 10⁻¹⁶.
    - Across seven production selections, raw and reconstructed outside fractions differ by at most 0.007 percentage points.
19. **ρ_ref stays the raw 20 mm-grid peak.** Both kernels, like the box merge, are non-negative partitions of unity, so that peak is a proven upper bound on the displayed field and is independent of R, the kernel and the window.
    - `frame.rho` gains `basis`, and per panel `displayed_peak`, `displayed_over_ref` and `kernel_attenuation`. The last is the displayed peak over that panel's own raw accumulation-grid peak.
    - The dataset-norm notice quotes `kernel_attenuation`, not `displayed_over_ref`. The latter is dominated by how bright the selection is: 1.95 on X′Y′ for the N = 5 slice D 257–258 mm, whose ramp top rises to 10⁰·²⁹.
    - **The kernel-switch figure was re-measured.** The design's estimate that the N = 50 switch raises the displayed peak by 9% did not reproduce. Re-rendering the same N = 49 / N = 50 bundles (D 753–762 / 753–763 mm) with both kernels gives +6.4–7.1% on X′Y′ and +4–5% on the depth panels. The same effect is 1.8% over the full selection and 20% at N = 5. The kernel is 29% narrower after the switch. `GAUSSIAN_KERNEL_BELOW_N`'s docstring and the kernel sentence quote the measured figures.
20. **The display floor is transparent** (`encode/quantize.py`, `encode/scale.py`, `encode/matrix.py`, `static/js/decode.js`, `static/js/scale.js`).
    - **Codes.** `BELOW_CODE = 1`. With a `below_code` the ramp starts at `min_code` 2 with 253 levels (0.0119 decades, 2.8% per step), and code 0 stays empty. Without one, the lab arithmetic is `rint(normalised · 254) + 1`, byte-identical to the legacy formula (tested).
    - **Helpers.** `below_floor_mask` applies exactly the criterion `relative_log_scale` counts as `clipped_low`. `dequantize` and `occupancy` take `min_code`, so canonical `occupancy` counts only bins drawn on the ramp.
    - **Scale.** `ColorScale.floor` / `floor_ratio` are emitted only when set, so neither the lab key set nor a Grad-CAM scale changes. `relative_log_scale` snaps a vmax within 10⁻¹² decades of 0 back to 0, against box-merge round-off. `encode_matrix` adds `below_code` and `below_floor_cells` only when given.
    - **Client** (`codeTable`):
      - `empty_code` and `below_code` are transparent.
      - Colours are indexed at `round((code − min_code)/(max_code − min_code)·255)`.
      - On a relative log ramp the alpha tapers linearly in log density over `THEME.floorFadeDecades`, which is 0.5 on screen and 0 in print.
      - Guard 8b.1: the taper applies only when that token is finite and positive. Otherwise the alpha is a pure 0/255 step, and the token is never a divisor.
    - **Legend.** It mirrors the taper with 48 rgba stops; Node SSR on the vendored bundle confirmed `stop-opacity` is interpolated. Its `outOfRange` is made transparent because ECharts' default `#aaa` underlay showed through the faded stops.
    - **Grad-CAM** gets `attention_mask {rule, cells, hit_fraction, max_attention}` and no `scale.floor`.
      - Continuous masks bins whose *reconstructed* density is below 10⁻³ ρ_ref. At N = 5 that is 8,753 X′Y′ bins, holding 20% of the reconstructed hit count: dust hits that carry little energy. `max_attention` is the largest attention among them.
      - Native masks only hitless bins (`cells` 0, `max_attention` null).
      - `topk` excludes masked bins in both channels, and `below_floor_cells` / `below_floor_energy_fraction` count the masked bins.
21. **The comb is measured before display smoothing.**
    - **Order in `build_response`:**
      1. The kernel is chosen from the exact N, which comes from the event table even when the hits are sampled.
      2. The comb is measured on the raw, uncropped `bundle.xy.planes['e']`, as before.
      3. The window is fitted.
      4. The panels are rendered.
      5. The whole response is budgeted.
    - **Payload and note.** `comb.measured_on = "raw accumulation grid, before display smoothing"`. The note drops §1.3's "a larger selection or a coarser R removes it" advice. It now says Native Grid shows the comb as measured, and Continuous Field hides it for display without removing it.
    - **Why.** Smoothing hid a real k = 1 comb in 7 of 7 tests; this is recorded in CLAUDE.md §2.
    - **Production.** The comb fields are identical across display modes for every selection, and none is staggered. Over the full range the occupancy lag-1 is +0.245 and the energy lag-1 is +0.892 (core row) and +0.919 (columns).
22. **`frame.smoothing` is renamed `frame.subsample_regime`** (`_subsample_regime`), because "smoothing" now means the display kernel. Its values (`sub-cell-sampling-gapless` / `-partial`) are unchanged, and no JS or test read the old key.
23. **`frame.reconstruction` and `meta.resolution.kernel` say what the display did.**
    - `meta.resolution.kernel` is `{type, sigma_mm, bin_spread_rms_mm, separable, conservative, non_negative}`.
    - `frame.reconstruction` (`reconstruct.reconstruction_report`) carries:
      - `display`, `kernel`, `label`;
      - `sigma_mm` (null unless Gaussian) and `bin_spread_rms_mm`;
      - `blur_rms_mm {x, y}`, `subsample_k` and `gaussian_below_n` 50;
      - `axes ["x′","y′"]` in both display modes, and `depth: "native sampling layers, never smoothed or interpolated"`;
      - `conservative` and `floor_ratio` 0.001;
      - per-panel `energy_fraction_outside` and `below_floor`, read back from the rendered payloads;
      - a one-sentence `note`.
    - **The blur formula.** `blur_rms_mm` is √(w²(1 − 1/k²)/12 + p²/12 + spread²): the discrete k × k footprint term (the continuous w/√12 overstates that term by 15% at k = 2), the p²/12 of point-binning each sub-deposit into its 20 mm bin, and the kernel's spread per bin. The binning term was missing at first, which understated the blur by 5–8% against a Monte Carlo of rotated cells binned as the scan bins them; with it the formula reproduces the Monte Carlo to 0.1 mm (`test_kernel.py`). On v37 the x′ total is 15.7 mm (tent, k = 2) to 18.9 mm (Gaussian, k = 6).
    - **Extra parameter.** `plan_canonical` also takes `cell_mm`, used only to word the "finer than 20 mm" warning with the 48.6 mm cell.
24. **The 100 KB contract covers the whole response.**
    - **Why.** The panel guard bounds only the rasters. The envelope (frame block, meta, centroids, notices) adds 13–16 KB, and at R = 150 the five-event slice D 257–258 mm measured 108,775 B with its panels inside their guard.
    - **The inner guard** keeps today's `len(json.dumps(panels))`. That measure over-counts the wire form, so it errs towards fitting, and the pinned 15 KB native test still merges.
      - `render_canonical(limit=None)` now resolves `PAYLOAD_LIMIT` at call time.
      - Loop bug fixed. The twelfth attempt used to degrade and append a notice for a step the returned panels never took. The loop now degrades only when another attempt follows, and ends with a "served as they are" notice if still over.
    - **The outer check** (`api/frame_canonical.py`) measures the assembled body with `density.wire_size`, which reproduces `JSONResponse` exactly: compact separators, `ensure_ascii=False`, UTF-8. The tests check it against `len(response.content)`. At 100 000 B or more, the panels are re-rendered from the cached bundle one guard step at a time, continuing from the state the first pass served (`guard["next"]`), and each candidate is measured as it is served until one fits. Every step and a final still-over notice are disclosed. An earlier version compared the guard's over-counted panel measure with a limit of `100 000 − envelope − 1 500` compact bytes; that unit mismatch stepped D 20–40 mm past R = 150 to R = 112 for any request above 150, although R = 150 serves 98,377 B.
    - **Measured.** D 257–258 ships 81,864 B at R = 112. The plan's own reference case, D 246.39–246.54 mm (N = 3), ships 97,531 B at R = 112.
25. **Each frame keeps its own display mode** (`state.js`, `main.js`, `index.html`).
    - **State.** `display_lab` defaults to `native` and `display_canonical` to `continuous`. `get('display')` and `set({display})` act on the active frame; `set` writes the display onto `patch.frame` when the patch carries one, so key order does not matter. `projectionParams` always sends `display`, while the API default stays `native`.
    - **Links.** A legacy `display=` applies to the active frame unless that frame's own key is also present, and unknown `display_*` values are rejected at read. Old canonical links open in Continuous; this is documented in the `state.js` header.
    - **Controls.** `syncDisplayControls()` runs from `applyFrameControls`, the display handler and experiment activation. It sets the radios, the per-frame labels ("Native Grid (raw 20 mm bins, audit)", "Continuous Field (kernel reconstruction)"), the R control and the hint. The lab hint is remembered across frame switches. `REQUIRED_IDS` gains `display-label-native` and `display-label-continuous`.
    - **Native Grid on screen.** `renderRaster` pre-upscales a `kernel: 'none'` raster by an integer nearest-neighbour factor, to about 2048 px and at most ×32. For example, 33 × 20 becomes 1056 × 640.
    - **Continuous depth panels on screen.** A reconstructed Y′Z′ / X′Z′ raster is enlarged by the same rule along its depth columns only (measured canvases 1920 × 213 and 1920 × 203), so the browser's bilinear upscale never blends two sampling layers while the reconstructed transverse rows stay smooth.
    - **Print.** `printRaster` asks `renderRaster(…, {screen: false})` for one pixel per payload bin and applies one integer factor to both axes, capped so the long side stays at or below `MAX_RASTER_PX` (4096). The cap used the width alone before, which let a 60 × ~200 depth raster reach 2040 × 7 242–8 772 px and the lab Y′Z′ 2040 × 17 408.
26. **Lighter anchors and overlays** (new `static/js/panels/canonical_overlays.js`, so `projection.js` does not grow).
    - **Anchors.** 13 px open outlines with a transparent fill, the shower colour and `THEME.anchorOpacity` (0.75 on screen, 1 in print). They are not `emptyDiamond` / `emptyCircle`, which ECharts fills white with a forced 2 px stroke. Y′Z′ draws one merged circle.
    - **Spread bar.** Uncapped, 2.5 px, 0.3 opacity, and named as dispersion in its tooltip. The anchor tooltip also restates the SD, because at N = 5 the ±28 mm bar (7.8 px) sits inside the outline's hover band.
    - **Separation rule.** 1 px dashed in `THEME.separationRule` (`rgba(255,255,255,0.4)` on screen, `#6b7280` in print). Its tooltip carries ⟨D_entry⟩ with its 95% t-interval and N, and ⟨D⟩. The markPoint badge is removed. The X′Y′ tag carries ⟨D_entry⟩ ± interval inside a `.sym` span, which `layout.css` exempts from the tag's uppercase transform.
    - **Centroids.** 7 px, told apart by shape: filled dot (`truth_voxel`), open ring (`pred_voxel`), plus (`canonical_mean`). `centroidLegend` names each set by its payload label for the footnote and the figure. The lab `CENTROID_STYLE` is unchanged.
    - **Canonical grid.** `grid {show: true, z: 3}` is a frame drawn above the raster, and `spatialAxis(..., {onZero: false})` removes the crosshair through the origin.
    - **Print tokens** sit outside `PRINT_INK`, because none of them is text.
27. **Frontend fixes applied in both frames** (`projection.js`, `scale.js`, `decode.js`, new `static/js/panels/marks.js`), as the user chose.
    1. `visualMap` binds `seriesIndex: 0`, the raster. It had been recolouring the scatter markers too, and the lab centroid diamonds measured `rgb(253,231,37)`.
    2. The spread bar, separation rule, ensemble axes, depth-face rules and lab measured shower axes are `customLine` / `customPolyline` series with `clip: true` and `style.fill: 'none'`. A `line` series with `symbol: 'none'` never fires its tooltip. Without `fill: 'none'`, the hover test is the 1 px stroke rather than a ±2.5 px band. The lab trajectories stay silent.
    3. The zr cell-tooltip handler answers everywhere on the plot. The raster is silent, so a target is always an overlay, but a hit area is wider than the ink: the anchors' transparent fill hit-tests the whole disc on the cores, and the face rules' ±2.5 px band covers most of the first and last layers. Returning on every target hid the bin readout over the brightest bin in 10 of 12 production cases. `marks.js: onInk` now tests the ink (half the stroke + 1 px of a line, the outline of an open marker, all of a filled one). Off the ink the handler shows the bin alone; on it, the overlay's own formatter (read from the series model through `echarts.helper.getECData`) followed by the bin. The ensemble wedges are silent, and the readout names the wedges the pointer is inside, each with its quantity.
    4. `autoFitRoI` weights by dequantised value (`occupiedBounds(…, {weight: 'value'})`), and skips below-floor bins in both weightings. On isometric panels it slides the box inside rather than truncating it.
    5. Guard 8b.2: one `ResizeObserver` per panel, rAF-debounced, calls `relayout()`. That runs the `onRelayout` hook, where `main.js` re-decides `depthIsometric`, and rebuilds the option at the new size. Measured: 234 → 160 px keeps 1:1.

    The lab server payload is untouched; `test_golden_lab.py` passes unchanged.
28. **Export reads the display from the payload** (`export/caption.js: displayOf, kernelPhrase`, `filename.js`, `figure.js`, `disclosure.js`).
    - **Deviation from §6's "figure.js: comment only".** `figure.js` builds one descriptor (R, pitch, merge, kernel) from `panel.lastOpts.resolution` and `frame.reconstruction` before the synchronous block, and threads it through two call sites into `describeSelection` and `figureName`. Neither function could otherwise see a guard-lowered R. The swap/render/serialise block and the test-pinned lines are untouched.
    - **File names.** The name takes R from the payload and appends `gauss10` or `tent` last, for example `xy_D-257-258_R112_canonical_gauss10_*.svg`.
    - **Disclosure.** `disclosure.js` stays DOM-free with its single `scale.js` import. It adds:
      - the floor sentence, which in print reads "the dark outline is the 10⁻³ display floor, not a shower edge";
      - the Grad-CAM colour-and-mask sentence;
      - the symmetric window sentence, falling back to the old asymmetric one for older payloads;
      - the reconstruction note, before the comb note;
      - a decimal-aware `ordinal` ("0.1st", "99.9th").
    - **The `printRaster` comment** now says each pixel block is one payload bin: a detector cell in the lab, a raw 20 mm bin in Native Grid, a reconstructed display bin in Continuous Field.
29. **Production re-measurement** (v37, read-only connection, R = 150; C = Continuous Field, N = Native Grid):

    | Selection | N | X′Y′ window x′ × y′ | Kernel | X′Y′ outside raw / C / N | Attenuation X′Y′, Y′Z′, X′Z′ (C) | Wire bytes C / N | Cached request ms C / N |
    |---|---|---|---|---|---|---|---|
    | D 257–258 | 5 | ±420 × ±500 (floor 200) | Gaussian | 0.179 / 0.186 / 0.179% | .756 .900 .884 | 81,864 (R 112) / 41,443 | 22.4 / 11.3 |
    | D 256–257 | 3 | ±740 × ±660 | Gaussian | 0.119 / 0.122 / 0.119% | .756 .859 .864 | 79,414 / 44,689 | 12.9 / 10.7 |
    | D 753–762 | 49 | ±1000 × ±620 (floor 100) | Gaussian | 0.211 / 0.209 / 0.211% | .863 .925 .895 | 69,354 / 49,343 | 12.0 / 10.9 |
    | D 753–763 | 50 | ±1000 × ±600 | tent | 0.217 / 0.216 / 0.217% | .911 .966 .941 | 68,941 / 49,088 | 11.2 / 10.2 |
    | D 20–40 | 549 | ±360 × ±380 | tent | 0.333 / 0.338 / 0.333% | .988 .991 .996 | 98,302 / 37,250 | 12.2 / 10.6 |
    | full range | 20,143 (k = 2) | ±2420 × ±520 | tent | 0.331 / 0.332 / 0.331% | .912 .983 .978 | 50,852 / 69,365 | 29.0 / 25.0 |
    | E₁, E₂ < 2 GeV | 691 | ±2480 × ±160 | tent | 0.210 / 0.214 / 0.210% | .675 .944 .855 | 43,677 / 54,111 | 16.9 / 13.6 |

    - **Render time.** A cached render takes 2.7–5.4 ms; cold scans take 44–470 ms per slice.
    - **Native Grid** gives attenuation 1.0 everywhere.
    - **S1** (D 243.6309–243.8532 mm) reproduces x′ ±480 × y′ ±380 with 0.182% outside.
    - **Grad-CAM** stays under 99 KB in both modes.
    - **Tests.** The full suite then stood at 335 passed and 11 skipped, against a baseline of 253 / 9. The two extra skips are the new subset tests, which run only with `CALOSRV_TEST_SUBSET_CSV`; against a 1,500-event subset, `test_canonical_subset.py` passes 10 of 10.


---

## Revision 3 — multi-model, multi-frame, multi-channel (`hits_all_models.csv`)

### Context

`hits_all_models.csv` (24 GB, 24,161,893 rows, 20,325 events, 99 columns) replaced the 29-column v37 file. Per hit
it carries three coordinate systems (laboratory; *trans*, shifted by the hit's own shower's entry point P₀;
*local*, then rotated by that shower's R(θ, φ)) and nine networks — angle, energy and segmentation, each trained in
the absolute, trans and local frame — with a prediction, its truth and per-hit Grad-CAM and Shap-CAM maps. The
directive asked `calosrv` to expose frame × model × channel, with laboratory / segmentation / density as the
cold-boot view, and to fix the tooltip that appeared to hide behind the sidebar.

| Fact (measured on the full file) | Consequence |
|---|---|
| trans/local are per-shower frames (P₀ spread 0.00037 mm, rotation residual 0.00066 mm) | both showers of an event are superimposed at the origin; the lab lattice does not exist there |
| a shared cell is two rows (1,629,316 split cells); 422 `'A+B'` rows, at the origin | row counts are not cell counts; `'A+B'` counts with B |
| angle/energy predictions are constant per (event, shower) | they live in the event table |
| Shap-CAM is signed, 11–64% negative for angle/energy | a [0, 1] or log ramp would erase it |
| `*_gradcam_energy` = CAM·E_voxel rescaled | summing it double-counts: archived, not plotted |
| `centroid_AB_distance_trans/_local` correlate 0.11 / −0.001 with D | D is always the laboratory separation |
| the tooltip is clipped by `.main`'s overflow box, not stacked under the sidebar | mounted on a fixed layer outside `.main`, no z-index rule on the tip; `confine: true` was tried first and dropped (note 43) |

**Decisions taken with the user.** D1 Shap-CAM on a diverging ramp centred on zero (linear ±1; signed log
±(10⁻³…1)). D2 energy-weighted channels computed server-side as Σ E·CAM. D3 projections *and* cards follow
(model, frame); plot 4 stays the segmentation reconstruction of the frame's segmentation network. D4 the measured
minimal tooltip fix. D5 v37 retired. D6 DuckDB + an immutable zstd Parquet archive + memory hardening (PostgreSQL
evaluated and rejected: no parallel `GROUPING SETS`). D7 the DuckDB default stays 16 GB. D8 folded PuOr on screen,
standard PuOr in print. Execution safeguards S1–S4: the folded palette; `ROW_GROUP_SIZE 100000, zstd, level 3`;
U+2212 for every rendered negative number; plot-4 `meta.network` only, with a synthetic small-N budget test.

### R.1 Perceptual & Statistical Audit

- **Frames.** Four, one radio: Laboratory (default), Translated, Local, Canonical. Translated and local take the
  canonical rules: symmetric 0.1–99.9 windows with the same floors, the Continuous Field kernel on the transverse
  axes only, the comb measured on the raw raster (both transverse axes; w in local), ⟨ρ⟩ = ΣE/(N·ΔA). Footprints are
  splatted, never point-binned: exact box overlap in translated, k × k × k_z rotated sub-deposits (k ≥ 2,
  k_z = 2) in local. D is the laboratory distance everywhere; the superimposed centroid pair is an *offset*.
- **Directions.** Translated keeps the laboratory azimuth (R̄ = 0.012): individual trajectories from the origin
  for ≤ 50 events, else R̄ stated. Local: +w by construction, nothing drawn, said so. `frame_mean` (per-event
  centroid offset from P₀) is drawn with its SD as an uncapped cross and its Student-t 95% interval as capped
  whiskers.
- **Channels.** Density; Grad-CAM mean (linear 0–1); Σ E·Grad-CAM (log, three decades of the selection's raw-grid
  peak, transparent floor); Shap-CAM mean (linear ±1, PuOr); Σ E·Shap-CAM (signed log, PuOr, |v| < 10⁻³
  transparent), the positive and negative parts kept as separate conserved planes. The CAM normalisation (per
  shower / per event) is stated with every CAM panel.
- **Palette.** Standard PuOr fails on the dark card (`#2d004b` 1.07:1, `#7f3b08` 1.95:1, a bright `#f7f7f7`
  centre). The screen folds it: each arm rises from the card; the first 3:1 colour sits at 10^−2.5, where the
  taper reaches full opacity; raw Shap-CAM zero is `#30363d`.
- **Cards.** Every card carries its SE and a named 95% interval: clustered ratio (events as clusters, Student-t),
  χ² for σ with the c₄ note, Student-t for a bias, Fisher-z for a correlation; the interval replaces the SE below
  N = 15.

### R.2 Execution & Data Requirements

- `python -m calosrv.ingest -i hits_all_models.csv -t all_models` (or through the running server); `--rebuild`
  rebuilds the derived tables from the archive. The 99-column header is checked before parsing.
- `duckdb==1.5.5`; compose `DUCKDB_MEMORY_GB=16`, `mem_limit` = `memswap_limit` = 20g, `TMPDIR=/app/data/staging`.
  Start-up refuses RAM-backed database, temp or archive storage (`CALOSRV_ALLOW_RAM_STORAGE=1` for tests only).
- Full-dataset jobs run alone, with an explicit memory limit, inside a memory-capped scope.

### R.3 Implementation

Branch `multi-model-frames` from `81c66d3`, in commit order: golden re-baseline on a 29-column derivation of the
new dummy (only the golden moved); the tooltip fix; the Parquet archive, 99-column DDL, registry migration, v37
retirement and memory hardening; the five channels on the lab and canonical paths; the translated and local frames;
the per-shower scans as plain sums; `/api/experiments` capabilities; the metric cards, plot-4 frame and budget
guard, and the synthetic S4 fixture; the frontend (state mapping, `frame_views.js`, folded PuOr, U+2212, cards,
export); the real-data fixture tool; the lab and canonical scans split; presentation fixes from the full-dataset
screenshot pass.

### R.4 Data Integrity Checklist

- [x] Zero axis distortion: panels sized from millimetre extents; depth panels 1:1 when affordable, stated otherwise.
- [x] Uncertainty by default: `frame_mean` SD band + t-whiskers; every card SE + named interval; D half-widths quoted.
- [x] Perceptual uniformity: sequential Viridis/Cividis/Plasma/Turbo; PuOr (ColorBrewer) for signed channels only.
- [x] Disclosure: every floor, crop, outside-grid mass, comb, kernel, sample and guard step is counted and stated.
- [x] Conservation: Σ E·CAM (and each Shap sign) equals the hits' sums to ≤ 3.3e−13 in all four frames.
- [x] Payload: 900-view production matrix, largest response 99,863 B; plot 4 guarded (98,064 B worst of 75).
- [x] Golden: passes byte-identically, never regenerated after the re-baseline.
- [x] Cold boot: laboratory / segmentation / density (JS state test and browser).

### R.5 Verification

`pytest tests/` (817 passed on the dummy and the fixture); `CALOSRV_TEST_SUBSET_CSV=… pytest
tests/test_canonical_subset.py` (13); `CALOSRV_BROWSER_TESTS=1 pytest tests/test_browser_tooltip.py` (8, all four
frames at two viewports). Production measurements are in the implementation notes below.

### Implementation notes (revision 3)

30. **Ingest resources (M1).** 61 s at `DUCKDB_MEMORY_GB=10` in a 14 GB cgroup with no swap; peak RSS 5.9 GB; DuckDB
    buffers 2.8 GB; nothing spilled. Outside a cgroup the page cache pushed 6.2 GB of other processes into zram,
    which is why compose sets `memswap_limit` equal to `mem_limit`.
31. **Storage (M4, M10).** Database 2.5 GB, archive 2.7 GB. `ROW_GROUP_SIZE` is a target: 241 row groups of
    11,448–102,040 rows, DuckDB's parallel writer overshooting by up to 2%. The M10 criterion is read as
    "target 100,000, ≤ 2% overshoot".
32. **Data contracts (M2, M3).** 24,161,893 rows, 20,325 events, 22,532,577 cells (= v37), 1,629,316 split cells,
    0 bad, 422 `'A+B'` rows at the origin, 57 events without D, calibration c_A 46.752 / c_B 49.712 in all frames.
33. **Translated frame by exact box overlap.** Four moments per hit keyed by (first bin, side), expanded by two
    matrices per axis; brute force agrees to 1e−12 of the total. A footprint not wholly inside the grid is outside in
    every panel alike.
34. **Local frame by rotated sub-deposits**, depth w binned at the 20.5 mm layer pitch; the grid of both frames is
    planned from the ingest-time 10⁻⁴ / 0.9999 energy-weighted quantiles plus half a footprint (0.027% / 0.035% of
    the energy outside).
35. **Every scan is plain sums in two queries.** `FILTER` aggregates are evaluated in every grouping set, so the
    entrance slab is its own query and outside mass is keyed −1: local 15.9 → 2.5 s, translated 2.7 → 0.85 s,
    canonical 5.9–6.3 → 1.7 s (preview 0.27 s), lab 565 → 270 ms (v37's six-plane pass: 313 ms on the same machine).
    The golden passed unregenerated.
36. **Comb and window (M-K, M-W)** over N = 3 … 20,268: no comb in either frame; 0.1–99.9 windows leave 0–6.4% of
    the boundary bins above the floor against 22–95% for 1–99. k_z = 1 shows no comb either, but its depth lag-1
    falls to +0.0003 at N = 5, so k_z = 2 is kept.
37. **Payload (M-P, M-E).** 900 production views, largest 99,863 B (the guard lowered R in 360). Plot 4 reached
    119,816 B at eight slices; the curve re-sampling guard brings the worst of 75 to 98,064 B.
38. **Conservation (M-C).** All four frames, three networks, both displays, R 50–400: ≤ 3.3e−13 against direct
    sums. A first lab check that omitted the default filter's `d IS NOT NULL` showed 1e−5…1e−3 — the reference,
    not the code.
39. **Cards (M5, M6).** Within 0.05 pp of the characterisation table except two shower-B entries (σ_rel 34.43% vs
    33.7%, local σθ 31.3 vs 30 mrad), which an independent archive recomputation reproduces to 1e−15: the table's
    values are not reproducible from the full file. Cards 7–11 ms, plot 4 12–13 ms.
40. **Migration (M8)** on a copy of the v37 database: v37 rows marked failed with the exact text, the baseline
    reseeded, DELETE drops the v37 tables. **Fixture (M9)**: 9 events, 380 MB RSS.
41. **Tooltip (M-T).** Clipped by `.main`'s overflow at a 41 px margin before the fix. With `confine: true`, no tip
    started left of its chart or resolved to the sidebar over a 9 × 7 grid on all four charts, all four frames and
    two viewports. Note 43 replaces that fix.
42. **Presentation details from the full-dataset screenshot pass:** the diverging zero mark is positioned from
    the measured legend width (a fixed offset hid it under the narrow linear bar); signed Shap-CAM totals are sums
    in GeV, not densities; a D half-width below 10 mm is quoted to one decimal.

43. **Tooltips leave the panel they explain (user review).** `confine: true` kept a large tip inside its own chart,
    over the plot it explains. Measured on the demonstration data, an overlay tip covered a median 35% of the plot
    area at 1600 × 900 and up to 98% at 1280 × 800; plain readouts sometimes sat on the pointer.
    - Every tip is now mounted on `#tooltip-layer`, a fixed, viewport-sized layer outside `.main`, where nothing
      clips it. Fixed rather than `<body>`: ECharts hides a tip without moving it, and on `<body>` a hidden tip grew
      the document after the window shrank.
    - `tooltip.js: placeTooltip` places a tip by its kind. The plain bin readout stays beside the pointer. Every
      explanation (a mark's, an overlay's, plot 4's) goes just outside the chart, on the side with the most room:
      over a neighbouring panel, inside `.main`'s visible area, then the viewport. Failing that it goes outside the
      plot area, and last to the position covering the least plot. No step may cover the pointer.
    - A first version chose by size (a tip at most 20% of the plot stayed at the pointer). An adversarial review
      dropped it: readout sizes straddle the line from bin to bin, so the readout jumped about 360 px to the next
      panel and back (451 flips in a sweep).
    - The same review found three more problems:
      - zrender's cached client transforms (`___zrEVENTSAVED`) share one validity check, so a scroll and then a
        drag left one stale, and a tip was drawn 120–240 px from its place. They are now dropped before every
        placement and on scroll; a test pins the internal.
      - The hidden tip on `<body>` grew the document (above).
      - The 100 ms `hideDelay` left a tip floating after a scroll; it is now 0.
    - Result, over 3,039 tips at four viewports: all 2,646 readouts beside the pointer, 0 of 393 explanations over
      their chart, and 0 clipped, covered, off screen or on the pointer. M-T asserts this over grid, sweep and
      marker hovers at three viewports, and replays the three cases above. Each fix has a mutation the test catches:
      no transform reset, `hideDelay` left at its default, and the layer made `absolute`.
