# Particle Physics Visualization

Diagnostic tooling for calorimeter shower reconstruction on overlapping two-particle
events. The repository holds two complementary architectures; pick one by dataset size.

| | **`calosrv/`** — out-of-core server | **`calodash/`** — batch compiler |
|---|---|---|
| Deliverable | Dockerised FastAPI + DuckDB service | one standalone `.html` file |
| Dataset size | unbounded (tested at 7.4 GB / 22.5 M rows) | fits in browser memory |
| Aggregation | server-side in DuckDB | at build time, in pandas |
| Frontend | Apache ECharts, vendored | Plotly, embedded |
| Entry point | `docker compose up --build` | `uv run build_dashboard.py` |

Both honour the same scientific-integrity rules — see [CLAUDE.md](CLAUDE.md).

---

## Quick start

```bash
docker compose up --build
```

Then open <http://localhost:8000>.

On a first boot the database is empty, so the server seeds a demonstration
experiment from the full 1000 rows of `hits_with_gradcam_dummy.csv` through
exactly the same pipeline a real upload uses. No synthetic records are
generated. That file holds only two events, both well separated, so the three
spatial panels render correctly while the reconstructed-energy panel reports its
two-event mean and width flagged as `moments (1 d.o.f.)` and draws the events
themselves — no fitted curve, and a density axis left deliberately unlabelled.

The boot log states the resolved hardware allocation:

```
DuckDB memory ceiling : 16 GB  (DUCKDB_MEMORY_GB)
DuckDB worker threads : 11  (of 12 host CPU cores)
```

---

## Configuration

Set in `docker-compose.yml`:

| Variable | Default | Meaning |
|---|---|---|
| `DUCKDB_MEMORY_GB` | `16` | Integer memory ceiling for DuckDB. Override to `100` on the production server. |
| `PORT` | `8000` | HTTP listen port. |
| `CALOSRV_DATA_DIR` | `/app/data` | Database, upload staging and DuckDB temp spill. |
| `CALOSRV_SEED_CSV` | — | Override the baseline seed file. |
| `CALOSRV_CACHE_ENTRIES` | `128` | Native-resolution matrix bundles held in the LRU. |
| `CALOSRV_CANONICAL_CACHE_ENTRIES` | `32` | Canonical-frame bundles held in their own LRU; one spans the full accumulation window, so fewer fit. |

> **Give the container more memory than DuckDB's ceiling.** `DUCKDB_MEMORY_GB`
> bounds DuckDB's buffer manager only — not the Python heap, the Arrow result
> buffers, or the ~230 MB projection cache. `docker-compose.yml` sets
> `mem_limit: 20g` against a 16 GB ceiling. Setting them equal will get the
> process OOM-killed partway through a large ingest.

Threads are derived, not configured: `min(32, max(2, cores // 2 if mem >= 64 else cores - 1))`.
A large memory ceiling implies a shared production host, so only half the cores
are claimed.

---

## Loading data

### Large files already on the server (preferred)

```bash
docker compose exec calorimeter-dashboard \
    python -m calosrv.ingest --input /app/host/hits_with_gradcam_v37.csv --table v37
```

The repository is mounted read-only at `/app/host`, so a multi-gigabyte CSV is
read in place and never traverses HTTP. Measured on the 7.4 GB / 22,532,577-row
production file: about 2 minutes, producing a 1.2 GB database.

```
--input / -i        path to the CSV
--table / -t        experiment name (lowercase letters, digits, underscores)
--mode / -m         create_new (default) | append
--display-name      label shown in the experiment dropdown
--event-offset      shift incoming event numbers when appending
--no-sample         skip the 10% preview-sample table
--direct            always open the database directly (see below)
--server-url        base URL of a running server
```

> **How this reaches the database.** DuckDB holds its lock on the database file
> *across processes*, not merely within one, so a second process cannot open it
> while the server is running — the attempt fails immediately rather than
> waiting its turn. The command therefore detects a running server and **posts
> the path** to `POST /api/ingest-local`, letting the server process (which
> already owns the lock) do the work on the same background worker an upload
> uses, while following the job to completion. Only the path crosses HTTP; the
> file is still read in place. With no server running it opens the database
> itself. `--direct` forces the second mode and fails loudly if the database is
> locked.

The same route is available from the interface: the upload modal's **Source**
selector offers "Already on the server", which lists the CSVs under the mounted
root. Paths are confined to that one directory — every request is resolved
(following symlinks, collapsing `..`) and rejected if it lands outside — so the
endpoint cannot be used to read arbitrary server files.

### Through the browser

The **Upload Dataset** button streams a file to disk in 8 MiB chunks and hands
it to a background ingest job, polled for progress. Large uploads are permitted
— external collaborators have no shell access and this is their only route — but
the modal warns that a browser upload cannot resume, and that ingestion needs
roughly three times the CSV size in free disk space.

`CREATE_NEW` drops any existing tables of that name and builds a clean, isolated
experiment. `APPEND` adds rows, and is **rejected** if the incoming event numbers
overlap those already stored; merging two files that each number events from zero
would fuse distinct physics events. Pass an `event_offset` to shift them clear.

### Expected schema

29 columns, in this exact order:

```
event_number, overlap, cellID, x, y, z, energy, particle_origin,
earliest_contribution_time_A, earliest_contribution_time_B,
incoming_momentum_A, incoming_momentum_B,
incoming_momentum_bin_A, incoming_momentum_bin_B,
incoming_theta_A, incoming_theta_B, incoming_phi_A, incoming_phi_B,
gradcam, gradcam_energy, voxel_fA_pred, voxel_fA_true,
centroid_A_x, centroid_A_y, centroid_A_z,
centroid_B_x, centroid_B_y, centroid_B_z, centroid_AB_distance
```

Types are pinned rather than sniffed. On the production file the sniffer's prefix
sample is entirely `overlap = 0` — the one region with no empty `centroid_A_*`
fields — so `read_csv_auto` would type those columns from data that never
exhibits the failure mode. Empty fields are read as NULL; rows with a missing
coordinate or a non-positive energy are excluded from the projections and counted
in the ingest report.

---

## The interface

**Header** — experiment dropdown, a compute badge showing the active
`DUCKDB_MEMORY_GB` and thread count, an exact/preview badge, and the upload
button.

**Sidebar** — filters for E₁ (`incoming_momentum_A`), E₂ (`incoming_momentum_B`)
and D (`centroid_AB_distance`), combined with chained boolean AND and debounced
by 150 ms; a **Reference Frame** radio — *Canonical centre-of-separation* (the
default) or *Laboratory* — with a caption stating what the frame does; the
spatial resolution control; the display channel selector, under which a
**Density normalisation** radio (relative to this selection's peak, or to the
dataset peak) appears only in the canonical frame, where it replaces the
lock-scale checkbox; the model selector; and the performance KPI card. Both
`frame` and `rho_norm` travel in the URL hash like every other control.

Each filter carries **both a numeric pair and a slider, on one shared grid**.
The slider's integer domain *is* the numeric step — 0.05 GeV for the energies,
1 mm for D — with the range snapped outward to whole multiples, so typing 2.05
and dragging to 2.05 reach the same value and the URL needs no rounding. (The
earlier fixed 1000-step slider put one step at 0.0196 GeV, so a typed 2.05 could
only land on 2.0455.) Typing a lower bound above the current upper bound pushes
the upper one along rather than swapping the two.

Persistent explanations — the staggered-lattice comb, the depth-lock caveat, the
undefined-D count — appear as **ⓘ popovers beside the control they concern**.
The banner across the plots carries only transient, actionable messages and can
be dismissed; dismissal is keyed by message text, so a warning re-sent on the
next response stays dismissed.

**2×2 canvas**

1. **XY Projection — shower entry.** The entrance slab (first six sampling
   layers, 120 mm from the front face at z = 3662.4 mm). Centroid markers and the
   labelled separation vector D. Locked to a 1:1 metric aspect so D can be read
   off the picture.
2. **YZ Projection — longitudinal evolution** along depth.
3. **XZ Projection — lateral profile**, sharing the YZ colour scale so the two
   are directly comparable.
4. **Reconstructed energy vs. separation D**, with layered Gaussian fits,
   isolated-shower reference markers, and an embedded (μ, σ) table.

In the canonical frame the three spatial panels are retitled X′Y′ / Y′Z′ / X′Z′
and their axes carry the primed symbols with their meaning spelled out —
*x′ — along the A→B separation*, *y′ — normal to the shower plane*, *z′ — depth
from the front face* — so a reader cannot mistake a co-registered picture for
detector coordinates. Their footnotes carry every disclosure the frame
generates; see [Canonical centre-of-separation frame](#canonical-centre-of-separation-frame).

All three spatial panels **scroll to zoom and drag to pan**, with an *Auto-fit
RoI* button that frames the box holding 99% of the selected energy (bounded by
energy percentile, not by the outermost hit, so one stray cell cannot define the
view) and a *Reset*. Both axes always scale by the same factor, so the 1:1
metric aspect survives zooming — verified at 4.974 mm/px on both axes after four
wheel notches. When the selected showers already span the detector, as most
multi-event selections do, the fit says so rather than appearing inert.

### Direction overlays on the depth panels

This section describes the **laboratory frame**; in the canonical frame (next
section) both overlays give way to two ensemble axes. In the lab the two
overlays are complements, and only one is honest at a time.

*Selections of 50 events or fewer* get the **individual incident trajectories**,
projected from each event's centroid and (θ, φ) across the fiducial depth.

*Larger selections* get the **energy-weighted shower axis** — the transverse
centroid per depth layer, measured from the binned data on screen.

> **No averaged trajectory is ever drawn in this frame.** Azimuth is circular,
> and its mean resultant length R̄ is 0.012 over the full dataset, 0.042 for a
> 122-event window and 0.178 even for 7 events: the direction is near-uniform at
> every reachable selection size, so an "average" would point somewhere
> arbitrary while looking authoritative. The panel states the measured R̄
> instead. For the same reason the ensemble axis is withheld below the
> trajectory threshold — averaging the position of a handful of showers that
> sit in different places has no common centre to converge on.

### Canonical centre-of-separation frame

The **Reference Frame** control defaults to this view. In the laboratory frame
every event's two showers land wherever the particles struck, so a multi-event
selection is a smear across the 5.2 m face, and the prohibition above holds
with no exception: with φ uniform, nothing can be averaged. The canonical frame
changes the premise rather than bending the rule. Every selected event is moved
by one **rigid-body motion** — an element of SE(3), so distances, transverse
widths and longitudinal profiles are preserved exactly — such that its two
showers sit at the same place as every other event's, and only then is anything
summed or averaged. Whether the result is coherent is then *measured*, and the
measurement is printed beside every mark it licenses.

**The transform.** The dataset's `centroid_A/B_*` columns are
**three-dimensional whole-shower centroids** — their z sits a median 253 mm
behind the front face — and `centroid_AB_distance` is their 3-D distance, so
neither is an entry point. Each centroid is therefore back-projected to the
front face z_f along its own incident direction:

```
entry_S = c_S − (c_S,z − z_f) · tan θ_S · (cos φ_S, sin φ_S)          S ∈ {A, B}
```

The sign is fixed by the data, not by convention: this lands a median 82 mm (A)
and 69 mm (B) from the per-event energy-weighted entrance-slab centroid, the
opposite sign 181 mm. The midpoint of the two entry points becomes the origin,
ψ = atan2(entry_B − entry_A) turns the A→B separation onto +x′ by the passive
rotation R_z(−ψ) — `x′ = cos ψ·(x − x₀) + sin ψ·(y − y₀)`,
`y′ = −sin ψ·(x − x₀) + cos ψ·(y − y₀)` — and z′ = z − z_f puts the front face
at zero. B then sits at (+D_entry/2, 0) and A at (−D_entry/2, 0); direction
vectors transform by the linear part alone. Because the rotation is per event
it cannot be applied to a cached lab bundle after the fact, so it runs **inside
DuckDB**: each hit row joins a 20 k-row CTE of frame parameters, and the
rotated position is binned with the same single-scan `GROUPING SETS` pattern as
the lab query. Bin indices become millimetres only through the coordinate
arrays measured at ingest, bound as list parameters — never by multiplying a
pitch.

The frame is checked on the data it is applied to. Per-event canonical slab
centroids sit at y′ = +0.3 / −0.0 mm (median), and at x′ + D_entry/2 = +19 mm
(A), x′ − D_entry/2 = +17 mm (B). That x′ offset is a **mixture, not a
constant** — outward by −22 / +24 mm for D_entry > 500 mm, and +44 / +9 mm for
D_entry < 80 mm, where overlapping deposits drag the A slab centroid toward B —
so the payload reports the measured anchor–centroid offsets per selection
(`frame.anchor_offsets`) and the X′Y′ footnote prints them.

**D_entry is not D.** The transverse separation of the two entry points at the
face is the frame's own separation; it differs from the slider's 3-D centroid
distance by up to 726 mm per event — over the full dataset ⟨D_entry⟩ = 765 mm
against ⟨D⟩ = 854 mm, and in the D 240–260 mm slice 157 mm against 249 mm. Both
are always printed side by side, the mean D_entry with the Student-t 95 %
interval of the mean, named as such (the payload also carries the bare standard
error; at N = 2 the two differ by a factor 12.7). The 182 events (0.9%) with no
A centroid have no frame and are excluded from N and counted, even when
*include undefined D* admits them elsewhere. Below D_entry = 80 mm — 28.2% of
all events — the rotation angle is dominated by the ~80 mm anchor residual and
is effectively random: those events' energy enters ⟨ρ⟩ averaged over azimuth,
and their randomly oriented directions enter the ensemble-axis statistics (R̄′,
the Rayleigh p, the dispersion band) as noise that lowers R̄′ and raises p. The
count is disclosed on the panel and in the figure.

**A hit is a cell, and rotation does not smooth the lattice.** The physical
footprint is measured from the populated `(ix, iy)` occupancy of the projection
table — the pitch between adjacent cells sharing a row or a column, read from
the lowest gap cluster — as **48.27 mm in x and 48.6 mm in y**, on the
production lattice and on the demonstration file alike. The sorted union of x
coordinates shows 4.4 mm "twins" because rows come in blocks of four offset by
4.4 mm between blocks; those twins are not cells, and the ~24 mm midpoint tiles
of the one-dimensional lattice axes are bookkeeping, not footprint. (A
lattice-only fallback exists for a table with no two cells in one row; it
over-estimates a sparse lattice, which is why occupancy is preferred.) Each
cell's energy is split into k × k equal sub-deposits over that footprint before
rotation and binning into a 20 mm grid, which conserves the total exactly for
any k and leaves no hole under a rotated footprint from k = 4. The obvious
shortcut — point-binning the rotated centres (k = 1) and trusting 20 000
near-uniform rotation angles (R̄(ψ) = 0.014) to fill the gaps — was tried and
**measured**: a real comb remains, with a lag-1 autocorrelation of the
shower-core row of −0.26 over 20 143 co-registered events and −0.47 on a
221-event slice, against +0.4 to +0.7 at k ≥ 2. So k ≥ 2 is enforced, k rises
to 6 as the selection shrinks under a 3 × 10⁷ sub-row budget, and the comb is
measured on **every response** with two instruments run on the uncropped
accumulation raster: the occupancy lag-1 the lab XY panel uses, and — because a
footprint splat fills every bin under a cell by construction, so occupancy
alone cannot see a residual *intensity* comb — the lag-1 of the detrended energy
profiles of the brightest row and of the column sums. Either below −0.10 is
reported as a comb, with canonical wording in `meta.stagger` and `frame.comb`. The payload also states whether the splat
is gap-free at the chosen k (`frame.smoothing`).

**What a bin holds.** The value is the ensemble-averaged projected surface
density ⟨ρ⟩ = ΣE / (N · ΔA) in **GeV mm⁻² per event**: dividing by N makes
selections of different size comparable, dividing by the bin area makes the
value independent of the display resolution, and area-weighted resampling
conserves the sum, so no coarser bin can exceed the finest-grid peak. Colour is
⟨ρ⟩ / ρ_ref on a log₁₀ ramp over [−3, max(0, log₁₀ of the peak ratio)],
labelled **Average hit density (a.u.)**. The reference is chosen in the
sidebar: the selection's own peak (default, `rho_norm=selection`, badge
*Autoscaled*) so every selection uses the whole ramp, or the dataset's peak
(`rho_norm=dataset`, computed once from the cached full-range bundle) so
colours compare across D slices — where superposed showers reach about twice an
isolated peak and the ramp extends above 10⁰ rather than saturating. Because
vmax always covers the peak, `clipped_high` is omitted in this mode;
`clipped_low` and `empty_cells` are counted. ρ_ref and its reference are
printed on every panel and in the figure caption, the exact `topk` values ship
in physical units and `total` keeps its GeV meaning, so the physical density is
always recoverable from a picture drawn in a.u. Tooltips show both. The
Grad-CAM channel keeps the lab's fixed 0–1 scale.

**Where the picture is cropped.** The accumulation window is planned from the
selection's own kinematics — `half_x = max(D_entry)/2 + M`, `half_y = M`,
`M = depth · tan θ_max + 500 mm` (twice the p90 energy-weighted RMS radius of a
shower about its axis), snapped up to whole bins — so it is lossless up to a
counted remainder: on the full production selection **±3980 × ±1380 mm**
(398 × 138 bins) with 0.008% of the energy outside. What is *sent* is narrower.
Per panel, the energy-weighted 1st–99th percentile along each transverse axis
(X′Y′ from slab energy, the depth panels from full-depth energy) is snapped
outward to whole 20 mm bins, and the energy outside each panel's window is
reported in its footnote. Depth is never cropped: the longitudinal profile,
leakage into the back layers included, is what the depth panels exist to show.
Below 20 co-registered events the fitted range is labelled **provisional** on
the axis itself. A budget guard keeps the payload under 100 KB by lowering R in
25% steps in continuous mode, or merging transverse bins pairwise in native
mode (2 × 2 on X′Y′, 2 × 1 on the depth panels — depth layers are never
merged); each step is disclosed as a notice.

**What is drawn.** Exactly two dashed ensemble axes on the depth panels, from
(∓⟨D_entry⟩/2, 0, 0) along the mean per-event projected slope s = u′_t / u′_z.
Each carries two separate marks, because they answer different questions and
differ by √N: a shaded wedge for the **sample SD** of the per-event slopes
(dispersion — where individual showers go) and a thin envelope for the
**Student-t 95% interval of the mean** (uncertainty — how well the axis is
known), from the same t table the energy panel uses. R̄′, the Rayleigh
p = exp(−N R̄′²) and N are printed beside each axis; an axis with p > 0.05 is
drawn **faded, never hidden**, because there are always exactly two. The
coherence that licenses the mark is measured, not assumed: R̄′_A / R̄′_B is
0.779 / 0.819 for D 2700–3000 mm (with ⟨û′_A⟩ → −x′ and ⟨û′_B⟩ → +x′: the two
showers diverge with depth), 0.339 / 0.340 for D 20–40 mm, and 0.024 / 0.371
over the full selection, against 0.012 in the laboratory frame. The anchors
(diamond A, circle B) carry an uncapped bar for the spread of D_entry/2 across
events, with the t-based SE of the mean anchor in the tooltip. The measured
ensemble entry centroids (`truth_voxel`, `pred_voxel`) are drawn as smaller
markers together with `canonical_mean`, the dataset centroids averaged *after*
co-registration; `truth_dataset`, a lab-frame mean of positions, is omitted
here because averaging positions across events that sit in different places is
exactly what this frame exists to avoid. Thin rules mark the front and back
faces at z′ = 0 and 1209.5 mm. **Not drawn**: individual trajectories (the
ensemble axes replace them), and the transverse detector outline, which rotates
with each event and has no ensemble image — the footnote says so.

**Low N.** Numbers are reported from N ≥ 2 and marks are gated separately, as
in plot 4. With no framed event the panels are empty and say so. A single event
gets its own two incident lines labelled *single event, not an ensemble*, no
band, and R̄′, p and σ stated as undefined. From N = 2 the axes, band and
envelope are drawn, with R̄′ / p labelled `weak (N = …)` below 20 and σ labelled
`1 d.o.f.` at N = 2. Because ρ_ref defaults to the selection peak, a low-N slice
never rescales any other view.

**Cost.** The co-registration scan is the one query in the service that takes
seconds. k = 1 would have answered the full 22.5 M-row selection in 0.54 s and
was rejected on the comb measurement above; k = 2 costs about **2.0 s cold**
(~90 M sub-deposit rows), is cached under a key that includes the window, k and
footprint, and is **pre-warmed in a background thread** at server start-up and
after each successful ingest, so the first page load does not wait for it. A
1000-event slice runs at k = 4 in about 0.4 s. Sampled drag previews cap k at 2.
Depth panels are drawn at a 1:1 metric aspect when the fitted spans allow it
(the letterboxed plot keeps at least 45% of the card width and the span ratio
lies within [0.45, 1.3]), otherwise with true extents and a footnote saying so.
The zoom window survives slider ticks within one frame — the fitted extents
move on every tick, and resetting the view each time would make zooming during
a drag impossible — and is reset only on a change of frame or experiment.

**API.** `GET /api/projections?frame=lab|canonical` (default `lab`, so every
existing contract and test is untouched) and `rho_norm=selection|dataset`.
`lock_scale` and `scale_mode` are accepted but ignored in the canonical frame.
The canonical envelope keeps every lab key and adds a `frame` block (anchor
definition, window, fit, footprint, k, comb, ρ_ref, D_entry / D moments,
per-shower slopes with SD, R̄′ and p, anchor offsets), `overlays.ensemble_axes`,
`overlays.anchors`, an axis `symbol` (x′ / y′ / z′), `scale.rho_ref / rho_unit /
decades / norm`, and per panel `total_energy_all_gev`, `n_events`, `topk_unit`,
`bin_area_mm2` and `rho_peak`. `GET /api/experiments` lists `frames` and
`z_front` per experiment and the canonical cache under `compute.canonical_cache`.
`CALOSRV_CANONICAL_CACHE_ENTRIES` (default 32) sizes the LRU.

### Low statistics in plot 4

**Reported numbers and drawn marks are gated separately.** A table cell makes no
claim about the shape of a distribution; a smooth curve does. So μ, σ and σ/μ are
reported from **N = 2** — with their standard errors and, on hover, their
asymmetric 95% intervals — while each mark on the canvas waits for the sample
size that supports it:

| Floor | What it gates |
|---|---|
| N ≥ 2 | μ, σ, σ/μ as reported numbers (at N = 2, flagged `moments (1 d.o.f.)`) |
| N ≥ 8 | the continuous parametric density curve |
| N ≥ 15 | the density histogram, and the iterated ±2.5σ core refit |
| N ≥ 20 | the robust width and the Gaussian-shape verdict |

The histogram has the highest floor for a reason specific to the estimator: a
`density=True` histogram normalises by `N × bin_width`, so once the bins are
finer than the spacing between events each occupied bin holds exactly one and
reports a height set by the binning rather than by the distribution — the tall
narrow spikes the panel used to show at small N. That argument is about the
histogram and does not extend to the mean and width of the same events.

Below the histogram floor the panel draws the individual events as baseline
ticks, the sample dispersion as an uncapped shaded band, and the mean with its
**95% confidence interval** (Student-t, not a normal approximation) as a capped
whisker. The band and the whisker are deliberately different marks: they differ
by a factor of √N and answer opposite questions — how spread out the events are,
against how precisely the mean is known — and each tooltip says which it is.
These marks sit in a tinted, captioned band at the foot of the plot whose
vertical positions are drawing offsets rather than densities, which the caption
and every tooltip in it state.

Above the histogram floor the bin count follows the sample size (Rice rule,
clamped to 8–120) driven by the smallest slice whose histogram is drawn, so all
slices share one binning and none is finer than its own statistics support.

**The y-axis is scaled from the statistically robust slices only.** A fitted
curve peaks at `1/(σ√2π)`, so a thin slice with a poorly determined σ would
flatten every well-measured slice beside it — measured on a test set, two
10-event slices peaked at 2.52 and 2.09 GeV⁻¹ against a robust maximum of 0.38.
Thin curves are therefore drawn de-weighted, adapt to the established range, and
where one overflows it is clipped with a caret at the axis top and named in the
footnote with its true peak. If no slice reaches N = 15 the axis is labelled
*provisional*; if nothing estimable is drawn at all the density axis is left
unlabelled rather than showing a 0–1 grid nothing is measured against.

Widths are the unbiased sample estimator (`ddof = 1`) in both architectures; the
population form understates σ by 18% at N = 3 and below 0.3% above a few hundred
events. `calosrv` also reports a `ddof = 0` width so the reference notebook stays
directly comparable.

The x-axis range is rounded outward to clean tick boundaries *before* anything
is binned, so bars, curve and labels share one range and a raw percentile bound
such as `9.197060758` can never reach a tick. The y-axis is labelled
**Probability Density [GeV⁻¹]** with an ⓘ explaining that a density integrates
to 1.0 and legitimately exceeds 1.0 when the distribution is narrow.

Separation slice is carried by colour, shower identity by line style (A solid,
B dashed), and the isolated references by dotted vertical markers at μ with a
shaded μ ± σ band — drawn as position-and-width rather than as density curves,
because their stated 5% resolution is an order of magnitude narrower than the
reconstructed distributions and a curve that narrow takes the y-axis with it.
An **A / B / Both** toggle filters by shower without a round trip.

### Spatial resolution: two modes

**Native Detector Lattice** gives one bin per real calorimeter cell —
212 × 104 transverse, 60 depth layers on the production file. Because a bin index
is an *ordinal* over the cell coordinates that actually occur, every
one-dimensional bin corresponds to a cell that exists, so the depth axes carry no
empty-bin comb.

> **The XY panel is the exception, and the interface says so.** That panel is a
> product of two ordinal axes, and the populated `(x, y)` pairs are *not* the
> full product: this detector's transverse cells are staggered, so adjacent x
> columns intersect different subsets of the y cells. Measured on the production
> file, adjacent native columns alternate between 46.2% and 42.3% occupancy, and
> the lag-1 autocorrelation of the detrended column profile is −0.25. The result
> is a fine vertical comb which is **detector segmentation, not shower
> structure**. The server measures this per request and the XY panel footnote
> names it. Switching to Continuous Field merges the staggered pairs: the same
> selection at R = 150 measures +0.05 with 90% occupancy, and at R = 104 it is
> +0.85 with 94%. This is the same effect `calodash/constants.py` documented for
> the batch pipeline, where a 50.5 mm transverse bin was chosen for exactly this
> reason.

**Continuous Field** builds a uniform grid at resolution R: `R_x = R`,
`R_y = round(R · n_y / n_x)`, and `R_z` **locked** to the native sampling layers,
because there is no measurement between two scintillator layers 20.5 mm apart.
Energy is distributed by *geometric overlap*, not point-binned, so the image
refines as R rises without picket-fencing. Resampling runs in NumPy against a
cached native-resolution bundle, so changing R costs no database access.

> The transverse x lattice is **not** uniformly spaced — cells sit in tight pairs
> 4.4 mm apart with a group pitch alternating 43.87 / 48.27 mm. Panels are
> therefore positioned from physical millimetre extents, never from matrix shape.

In the canonical frame the two modes keep their names but act on the uniform
20 mm accumulation grid rather than on the lattice: **Native** sends the cropped
grid as it is (no resample; `r_x`, `r_y` are the cropped shape), **Continuous**
resamples the cropped transverse axes to R by area-weighted overlap, and depth
stays the 60 native layers in both. The display caption says which applied.

### Energy calibration

A sampling calorimeter records only a fraction of a particle's energy. Summed
deposits are of order 0.05 GeV per event while incident momenta are 0.4–20 GeV,
so the two are not comparable without calibration. Per-shower constants are
fitted from ground truth over the active selection:

```
c_A = Σ(incoming_momentum_A) / Σ(energy · voxel_fA_true)
E_reco_A = Σ(energy · voxel_fA_pred) · c_A
```

Summing before dividing, rather than averaging per-event ratios, is deliberate: a
per-event normalisation would force each event onto its own truth exactly and
erase the containment scatter the resolution measurement exists to quantify.
Pass `calibrated=false` to see the raw deposited sums, in which case the
benchmark curves are hidden because they would not be comparable.

### Exporting figures for publication

Every panel header carries an **Export ▾** control offering lossless SVG or
300 DPI PNG, at 85 mm (single column) or 175 mm (double column). The figure is
whatever is on screen at that moment: the active zoom window, the A / B / Both
selection, the filters, the display mode and the colour map.

Figures are authored in millimetres converted at 96 DPI, so 85 mm is 321 logical
pixels and rasterising at ×3.125 lands on 300 DPI by construction — a
double-column PNG measures 2065 px. The same convention makes a point
meaningful, since 1 pt is then 4/3 logical px.

> **Print type is larger than screen type, not smaller.** Legibility is the
> font's share of the figure width, and the interface's 9–10 px labels in a
> ~600 px panel become 6.8 pt when reproduced literally in an 85 mm figure.
> Nine points is 12 logical px here, so every print size is quoted in points and
> converted. Each colour drawn as text or axis chrome clears 4.5:1 against white,
> asserted by `tests/test_export_assets.py` rather than judged by eye.

**The figure carries its own disclosures.** The panel footnote travels into the
image as a caption, together with the selection it was measured on and, for a
zoomed panel, the displayed window in millimetres. This is not decoration: the
footnotes hold the percentile-clipping count, the staggered-comb warning, the
*provisional* density-axis basis and the true peak of any clipped low-N curve.
The energy figure additionally embeds its fitted μ and σ as an aligned table,
which on screen lives in HTML beside the chart and would otherwise be left
behind. A figure that reached print without those sentences would be exactly the
silent omission the rest of this interface exists to avoid.

In SVG the caption band is an isolated **`<g id="figure-disclosure">`** spliced
before `</svg>`, so a downstream tool can find, restyle or extract it. It has
to be composed by our own code: zrender's SVG painter flattens the display
list, so ECharts `graphic` groups never become `<g>` elements. `caption.js`
serialises the *same* laid-out caption items the PNG draws as ECharts graphics
— baseline at `offsetY + top + 0.71·fontSize`, since zrender centres text on
its line — so the two formats cannot drift. Its sentences are read
**structurally from the payload** (`static/js/export/disclosure.js`), not
scraped from the on-screen footnote: a footnote is prose assembled for a card
and may be shortened or rounded, whereas the figure must state what was
*computed*. In the canonical frame that means the frame definition, N and the
events excluded without a frame, ⟨D_entry⟩ against ⟨D⟩, ρ_ref with its reference
and the ramp bounds, the display window and the energy it leaves out, the
provisional flag, the footprint and k, the measured comb, the ill-conditioned
count and R̄′ / Rayleigh p / N for each ensemble axis; in the laboratory frame
the ramp's clipping counts and the staggered-comb note; in either, whether the
values came from the 10% sample. The live footnote still travels too,
de-duplicated against these lines.

Two things change for white paper beyond the obvious inversion:

- **The categorical sub-range flips.** `categoricalStops` samples the *upper*
  ramp on screen because Viridis begins at `#440154`, invisible as a one-pixel
  line on `#0d1117`. On white the failure is the mirror image — the `#fde725` end
  vanishes — so print samples [0, 0.75]. The ramp's identity and its lightness
  ordering are untouched; this is a sub-range change, not a palette inversion.
- **The colour bar moves below the x axis.** A vertical bar costs about seven
  label widths, which on a 321 px figure is a quarter of the canvas.

> **The spatial panels' density field stays a raster.** It is a bitmap of
> detector cells, so the SVG embeds it as an `<image>`; the axes, overlays,
> legend and every label are true vector `<text>` and `<path>`, which is what
> LaTeX compilation turns on. The bitmap is upscaled by an **integer** factor
> with smoothing off — each pixel is one cell, a discrete measurement, and
> interpolating between them would invent values across the lattice. The energy
> panel is line and path geometry throughout and vectorises completely.

Exports never touch the live charts: the panel is re-rendered into a detached
off-screen instance under a swapped theme, so the screen does not flash and no
zoom, filter or toggle is reset. The render is synchronous and blocks the main
thread for a fraction of a second at double-column PNG — ECharts needs a real
DOM node and cannot be moved to a worker — so the button disables and relabels
first rather than appearing to ignore the click.

Names are deterministic: `[panel-id]_[slice]_[YYYYMMDD_HHMMSS].[svg|png]`, where
the slice names only the axes actually narrowed, for the same reason the URL
hash omits untouched bounds. A figure taken in the canonical frame carries a
`canonical` token in the slice, so two exports of the same selection in the two
frames never collide.

---

## API

All endpoints return pre-aggregated payloads; none returns a raw hit array.

| Endpoint | Purpose |
|---|---|
| `GET /api/experiments` | Registered tables, row/event counts, kinematic bounds, lattice, compute allocation. |
| `POST /api/upload` | Streamed multipart ingest. Returns a job id. |
| `GET /api/upload/{job_id}` | Ingest progress and result. |
| `GET /api/projections` | The three spatial panels as quantised rasters (~35 KB), in the laboratory frame (`frame=lab`, default) or the canonical centre-of-separation frame (`frame=canonical`, with `rho_norm=selection\|dataset`). |
| `GET /api/energy-distribution` | Per-slice Gaussian fits, histograms and benchmarks. |
| `GET /api/model-performance` | Voxel accuracy, MAE, energy residuals, per-slice breakdown. |
| `GET /api/health` | Liveness, with the resolved memory and thread allocation. |

Interactive documentation at <http://localhost:8000/docs>.

Projection payloads ship as `log10 → uint8 → base64` rasters with the scale
constants attached. 254 levels across six decades is 5.6% per step — finer than
the eye resolves — and the brightest 64 cells additionally carry their exact
float64 value so tooltips stay quotable.

---

## Performance

A cold projection scan over 22.5 M rows cannot be answered in under 100 ms; the
floor is decompressing and hashing a few hundred megabytes. What is delivered
instead:

| Request class | Expected p50 |
|---|---|
| Event-level endpoints (experiments, energy, performance) | 1–5 ms |
| Cache hit — resolution, mode, palette change | 5–20 ms |
| Sampled drag preview | 20–40 ms |
| Exact cold projection, D-narrowed | 60–200 ms |
| Exact cold projection, unfiltered | 200–400 ms |
| Canonical frame, 1000-event slice, cold (k = 4) | ~400 ms |
| Canonical frame, unfiltered, cold (k = 2) | ~2.0 s — paid once, pre-warmed at start-up and after ingest |

This comes from a 150 ms debounce that fires on release rather than drag, an LRU
of native-resolution matrix bundles, a 10% Bernoulli sample served during drags
(marked `exact: false` in the payload and flagged in the header), and ingest in
file order so the D slider prunes row groups via zone maps.

---

## Development

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python \
    "fastapi>=0.115,<1" "uvicorn[standard]>=0.32,<1" "duckdb>=1.1,<2" \
    "numpy>=1.26,<3" "pandas>=2.0,<3" "python-multipart>=0.0.12" pytest

CALOSRV_DATA_DIR=./data DUCKDB_MEMORY_GB=4 .venv/bin/python -m calosrv
.venv/bin/python -m pytest
```

Two test fixtures are worth knowing about. `tests/test_canonical_subset.py`
runs only when `CALOSRV_TEST_SUBSET_CSV` points at a subset of the production
CSV (cut with `event_number < 1500`, say): the k = 1 comb measurement, the row
budget on a realistic window, the dataset-reference ρ_ref and R̄′ rising on a
wide-D slice cannot be exercised on the two-event demonstration file, so without
the variable those tests are skipped, not passed. `tests/test_golden_lab.py`
asserts that the laboratory-frame output on the demonstration dataset is
**byte-identical** to `tests/golden/lab_demo.json`, so the shared code the
canonical frame touches (`NativeBundle.axis`, `centroids`, `panels.shower_axes`)
cannot move the lab picture unnoticed. Regenerate the snapshot deliberately with
`.venv/bin/python tests/make_golden.py` only when the lab output is *meant* to
change.

### Static assets and caching

Asset URLs are stamped with a hash of the static tree (`/static/js/main.js?v=…`)
and served `immutable`; the page itself is `no-cache`, and any unstamped asset —
which includes the relative ES module imports inside `main.js` — revalidates
against its ETag.

This is not housekeeping. The page and its scripts are separate downloads with
independent cache lifetimes, so a browser can hold a **stale script against
fresh markup**. When that happened here, the cached script still expected the
readout spans that the numeric inputs replaced and threw

```
TypeError: Cannot set properties of null (setting 'textContent')
```

during module initialisation — before ECharts was configured or any data
fetched, so the interface was dead with nothing on screen to explain why. The
same stale stylesheet lacked the rules for the new inputs and buttons, which
rendered them as browser-default white boxes. Stamping the URLs makes that
pairing impossible; `dom.js` and the startup id audit make it survivable and
self-explaining if it ever recurs.

### Module layout

```
calosrv/
  config.py logging_setup.py errors.py app.py
  db/      connection settings ddl naming registry bootstrap
  ingest/  stream csv_spec load lattice_fit derive_proj derive_events verify jobs cli
  grid/    lattice splat resolution slab frame
  query/   filters projections panels centroids summary energy performance sampling cache experiments
           stagger canonical window density ensemble canonical_cache
  stats/   gaussian histogram slices metrics clip
  encode/  scale quantize matrix topk
  api/     deps routes_* frame_canonical
  static/  index.html css/ js/
             js/      main api state scale palette decode dom textfit
             js/panels/   projection energy metrics
             js/controls/ range_slider upload
             js/export/   tokens figure caption disclosure filename download menu
```

The canonical frame is its own column of that layout, one responsibility per
file: `grid/frame.py` holds the pure-NumPy SE(3) mathematics, the footprint
measurement, the window planner and the sub-sampling rule; `query/canonical.py`
the per-event frame statistics and the DuckDB accumulation scan; `query/window.py`
the percentile crop; `query/density.py` the crop → resample → ⟨ρ⟩ → encode step
and the payload budget guard; `query/ensemble.py` the two axes with their band
and envelope; `query/canonical_cache.py` the cached bundle and its start-up
warmer; `api/frame_canonical.py` the envelope assembly; and
`static/js/export/disclosure.js` the structured figure disclosures.

Three structural rules the layout exists to enforce:

- **`db/naming.py` is the only place a table name becomes SQL identifier text.**
  DuckDB cannot parameterise identifiers, so interpolation is unavoidable;
  confining it to one validated function keeps the injection surface auditable in
  one file.
- **No SQL string lives outside `query/` and `db/ddl.py`.** Route modules build a
  `FilterSpec` and call a query module.
- **A panel builds its chart option from `metrics`, never from its own element,
  and styles it from `THEME` tokens, never from literals.** Both exist so one set
  of option builders can serve the screen and a publication figure. `THEME` is a
  mutable singleton the exporter swaps for the duration of *one synchronous
  block* — swap, render, serialise, restore, with no `await` between — which is
  what keeps a global style change invisible to the live charts. A hardcoded
  `fontSize: 10` or a read of `this.element.clientHeight` inside an option
  builder silently reintroduces the screen's geometry into the exported figure.
- **The laboratory-frame path is never edited to add a frame.** The canonical
  response is assembled beside the route in `api/frame_canonical.py`, and the
  only shared code it reaches (`NativeBundle.axis`, `centroids`,
  `panels.shower_axes`) is pinned byte-identical by the golden snapshot test.
  A change that moves the lab picture must move `tests/golden/lab_demo.json`
  on purpose.

### The legacy batch compiler

`build_dashboard.py` and `calodash/` are untouched and still work. The two
packages deliberately share no imports: the estimators `calosrv` needs are
re-implemented so neither path can break the other.
`calosrv/stats/gaussian.py` documents where it must stay numerically identical to
`calodash/stats.py`.
