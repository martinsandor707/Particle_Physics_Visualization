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
display-mode and resolution control, whose labels, default and hint follow the
frame (see [Display modes in the canonical frame](#display-modes-in-the-canonical-frame));
the display channel selector, under which a
**Density normalisation** radio (relative to this selection's peak, or to the
dataset peak) appears only in the canonical frame, where it replaces the
lock-scale checkbox; the model selector; and the performance KPI card. `frame`,
`rho_norm` and the two per-frame display modes (`display_lab`,
`display_canonical`) travel in the URL hash like every other control.

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

### Overlay and layout behaviour shared by both frames

These fixes were found while reworking the canonical panels. They were applied
to the laboratory frame too. The lab *server* payload did not change: the
golden test pins it byte for byte.

- **The colour bar colours the raster and nothing else** (`visualMap`
  `seriesIndex: 0`). Without a series index ECharts coloured *every* series by
  its data value. So the lab's pink and blue centroid diamonds came out in
  whatever ramp colour their coordinates mapped to, measured as a fill of
  `rgb(253,231,37)`, the top of Viridis. They are pink and blue again.
- **Every overlay line that names its quantity now shows its tooltip.** A
  `line` series drawn with `symbol: 'none'` never fires an item tooltip, so the
  wording CLAUDE.md requires was attached and never seen. These lines are now
  custom series from `static/js/panels/marks.js`: the spread bar, the
  separation rule, the ensemble axes, the depth-face rules and the lab's
  measured shower axes. Two settings in those series are load-bearing:
  - `clip: true`, because a custom series is unclipped by default and would
    run out of a zoomed plot across the axes;
  - `style.fill: 'none'`, because otherwise zrender fills the path. The hover
    test then covers only the 1 px stroke instead of a ±2.5 px band.

  The lab's dashed incident trajectories stay silent.
- **The bin readout answers everywhere, and an overlay adds to it on its ink.**
  The raster is `silent`, so any element under the pointer is an overlay. But a
  mark's hit area is wider than its ink: the open anchor rings hit-test their
  whole 13 px disc on the shower cores, a face rule's ±2.5 px band covers most
  of a 6.6 px first or last layer, and the axis lines run through the cores.
  Standing aside for every hit target hid the bin readout, the only place the
  exact top-k values and the below-floor wording appear, over the brightest bin
  in 10 of 12 panel × selection cases. So `marks.js: onInk` tests the pointer
  against the drawn ink: within half the stroke plus 1 px of a line, on the
  outline of an open marker, anywhere on a filled one. Off the ink the handler
  shows the bin alone. On the ink it shows the overlay's own text, read from its
  series, followed by the bin. The ensemble wedges are silent, because at small
  N they are wide areas over the data (the N = 3 Y′Z′ envelope spans
  −1172…+636 mm of a ±720 mm window). The bin readout names the wedges the
  pointer is inside instead, each with its quantity: the dispersion band as
  ± the sample SD of the per-event slopes, and the envelope as the 95% interval
  of the mean. Measured on production v37 over five selections: the brightest
  bin of each of the 15 panels shows its readout, and so do all 63 points of a
  9 × 7 grid over each plot; anchors, rules and axis lines still name
  themselves when hovered on their ink.
- **Auto-fit RoI weights bins by energy, not by colour code.** Codes are
  monotone in energy but not proportional to it. On the three-decade canonical
  ramp a bin a tenth as bright as the peak carried two thirds of the peak's
  weight, so the "99% of the energy" box swelled towards the halo. On an
  isometric panel the fitted box is now slid inside the panel rather than
  truncated at its edge, so it keeps 1:1.
- **The isometric letterbox follows the container, not only the window.** Each
  panel has one `ResizeObserver`, debounced to an animation frame. On a resize
  it rebuilds the option from the retained payload and view, and the depth
  panels re-decide whether they can be drawn isometric. `chart.resize()` alone
  left a stale letterbox. Measured: shrinking a card from 234 to 160 px now
  keeps 1:1.

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
to 6 as the selection shrinks under a 3 × 10⁷ sub-row budget. The comb is
measured on **every response**, with two instruments run on the uncropped
accumulation raster:

- the occupancy lag-1 that the lab XY panel uses;
- the lag-1 of the detrended energy profiles of the brightest row and of the
  column sums. This second one is needed because a footprint splat fills every
  bin under a cell by construction, so occupancy alone cannot see a residual
  *intensity* comb.

Either below −0.10 is reported as a comb, with canonical wording in
`meta.stagger` and `frame.comb`. The measurement is taken on the **raw grid,
before any display smoothing**, and `frame.comb.measured_on` says so. The
verdict is therefore identical in both display modes. This order matters:
smoothing was measured to hide a real k = 1 comb in 7 of 7 tests. Native Grid
shows a comb as measured. Continuous Field smooths it for display, which hides
it without removing it, so the note never advises smoothing it away. The payload
also states whether the splat is gap-free at the chosen k
(`frame.subsample_regime`: `sub-cell-sampling-gapless` or
`sub-cell-sampling-partial`). That field was called `frame.smoothing` before the
display kernels existed, and was renamed so the two cannot be confused.

**What a bin holds.** The value is the ensemble-averaged projected surface
density ⟨ρ⟩ = ΣE / (N · ΔA) in **GeV mm⁻² per event**:

- dividing by N makes selections of different size comparable;
- dividing by the bin area makes the value independent of the display
  resolution;
- every display operator conserves the sum and cannot raise any bin above the
  raw peak. Those operators are Native Grid's box merge and both Continuous
  Field kernels (see [Display modes in the canonical frame](#display-modes-in-the-canonical-frame)).
  Each is a non-negative partition of unity on the uniform grid, so a displayed
  bin is a weighted *mean* of raw 20 mm bins.

Colour is ⟨ρ⟩ / ρ_ref on a log₁₀ ramp over [−3, max(0, log₁₀ of the peak ratio)],
labelled **Average hit density (a.u.)**. The reference is always a **raw 20 mm
accumulation-grid peak** (`frame.rho.basis`), never the peak of the displayed
field. It is a proven upper bound on everything drawn, and it does not depend on
R, the kernel or the window, so a normalisation stays comparable across
selections. Which peak is chosen in the sidebar:

- the selection's own peak (default, `rho_norm=selection`, badge *Autoscaled*),
  so every selection uses the whole ramp;
- the dataset's peak (`rho_norm=dataset`, computed once from the cached
  full-range bundle), so colours compare across D slices. There, superposed
  showers reach about twice an isolated peak, and the ramp extends above 10⁰
  rather than saturating.

Because vmax always covers the peak, `clipped_high` is omitted in this mode.
`frame.rho` also reports each panel's `displayed_peak`, its `displayed_over_ref`,
and `kernel_attenuation`, the displayed peak over that panel's own raw peak.
Measured at R = 150:

| Selection | X′Y′ `kernel_attenuation` | X′Z′ `kernel_attenuation` |
|---|---|---|
| D 257–258 mm, N = 5 | 0.756 | 0.884 |
| full production range | 0.912 | 0.978 |
| Native Grid, any selection | 1.0 | 1.0 |

Under dataset normalisation a notice quotes `kernel_attenuation`, because part
of a colour difference between two selections can then be the display rather
than the physics. It does not quote `displayed_over_ref`, which is dominated by
how bright the selection is relative to the dataset. For example, the ratio is
1.95 on X′Y′ for the N = 5 slice, whose ramp top therefore rises to 10⁰·²⁹.

ρ_ref and its reference are printed on every panel and in the figure caption.
The exact `topk` values ship in physical units and `total` keeps its GeV
meaning, so the physical density can always be recovered from a picture drawn in
a.u. Tooltips show both. The top-k list is the *displayed* field, labelled
"(exact, reconstructed)" in Continuous Field, and never offers a bin that is not
drawn.

**The display floor is transparent.** Bins below 10⁻³ of ρ_ref are **not
drawn**. They used to be clamped into colour code 1, the opaque bottom of the
ramp, which painted the whole crop as a dark-purple rectangle around the
showers.

- **Codes.** A canonical panel now reserves code 1 (`below_code`) for them. The
  ramp starts at `min_code` 2 with 253 levels, and code 0 still means empty.
- **Counts.** The payload counts the undrawn bins (`below_floor_cells`, equal to
  `scale.clipped_low`) and gives the share of the panel's in-window
  reconstructed energy they hold (`below_floor_energy_fraction`). It states the
  rule as `scale.floor: "transparent"` and `scale.floor_ratio: 0.001`.
- **The fade on screen.** A hard edge would still draw a rim. The dark end of
  Viridis against the `#1c2128` card is only 1.07:1 in WCAG contrast but
  ΔE76 ≈ 49 in colour. So the bottom half decade, 10⁻³ to 10⁻²·⁵, fades
  linearly in alpha (`THEME.floorFadeDecades` 0.5), and the field dissolves into
  the card. The legend mirrors the fade with translucent stops and reads
  "10⁻³ a.u. — fades to not drawn".
- **Print.** The token is 0 in print, which gives a hard contour. The caption
  says the contour is the 10⁻³ display floor and not a shower edge.
- **Grad-CAM** keeps the lab's fixed 0–1 scale and gets an `attention_mask`
  block instead:
  - *Continuous Field* masks attention where the *reconstructed* energy density
    is below the same floor, because the kernel tails carry attention into bins
    no measured energy reached. At N = 5, 8,753 X′Y′ bins are masked, holding
    20% of the reconstructed hit count.
  - *Native Grid* leaves only hitless bins transparent, as the lab does. The
    audit view never hides attention measured on real hits.

**Where the picture is cropped.** The accumulation window is planned from the
selection's own kinematics — `half_x = max(D_entry)/2 + M`, `half_y = M`,
`M = depth · tan θ_max + 500 mm` (twice the p90 energy-weighted RMS radius of a
shower about its axis), snapped up to whole bins — so it is lossless up to a
counted remainder: on the full production selection **±3980 × ±1380 mm**
(398 × 138 bins) with 0.008% of the energy outside. What is *sent* is narrower.
Each panel is cropped along each transverse axis to a window **symmetric about
the origin**, x′ ∈ ±Δx and y′ ∈ ±Δy (`query/window.py: symmetric_axis`).
X′Y′ uses the slab energy; the depth panels use their own full-depth energy.

1. Δ is the larger excursion of the energy-weighted **0.1st–99.9th**
   percentile.
2. It is raised to a floor. While the range is provisional (N < 20) the floor
   is **200 mm**, the median single-shower |y′| p98 of the entrance slab, so a
   handful of events cannot shrink the view below one shower's own extent.
   Above that it is **two cell footprints**, 2 × 48.6 mm snapped to 100 mm,
   the physical resolution. The robust floor is lower on purpose. D-only
   slices at N ≥ 20 measure y′ ±360 mm or more, but energy cuts go well below
   200 mm: E₁, E₂ < 2 GeV (N = 691) measures ±160 mm, < 1.5 GeV (N = 643)
   ±100 mm and < 1 GeV (N = 468) ±80 mm, which the 100 mm floor holds. A fixed
   200 mm floor would widen them 1.25–2.5× for no statistical reason.
3. It is snapped outward to whole 20 mm bins.
4. It is clamped to the accumulation window.

The origin is the midpoint of the two anchors, so a centred window keeps it in
the middle of the panel. The X′Y′ panel's 1:1 aspect comes from the letterbox,
not from forcing a square. `frame.fit.<panel>.<row|col>` carries the
`percentile_range` before centring, `half_width`, `floored` and `clamped`; the
footnote prints the window as `x′ ±480 mm` and names a floor or a clamp where
one applied. Measured on production v37:

| Selection | N | X′Y′ window | X′Y′ energy outside (raw grid) |
|---|---|---|---|
| D 243.63–243.85 mm | 5 | ±480 × ±380 mm | 0.18% |
| D 20–40 mm | 549 | ±360 × ±380 mm | 0.33% |
| full range | 20,143 | ±2420 × ±520 mm | 0.33% |

This is a recorded exception to the CLAUDE.md 1st–99th default. The panels do
not draw below 10⁻³ ρ_ref, and a 1–99 crop cut the halo where it was still
15–110× above that floor. The colour then ended at the window edge and looked
like the edge of the shower: 14–99% of the X′Y′ boundary bins were above the
floor, against 2–11% now.

The disclosure is unchanged in kind. The energy outside each window is reported
in its footnote, measured *after* display reconstruction
(`energy_fraction_outside_window`), because a kernel moves a little energy
across the window edge in both directions. The raw-grid figure travels beside
it (`energy_fraction_outside_window_raw`). Across seven production selections
the two differ by at most 0.007 percentage points.

Depth is never cropped: the longitudinal profile, leakage into the back layers
included, is what the depth panels exist to show. Below 20 co-registered events
the fitted range is labelled **provisional** on the axis itself.

**The 100 KB budget covers the whole response.**

- **The panel guard.** It lowers R in 25% steps in continuous mode, or merges
  transverse bins pairwise in native mode: 2 × 2 on X′Y′, 2 × 1 on the depth
  panels, because depth layers are never merged. It allows twelve attempts.
  It degrades only when another attempt follows, so every notice describes a
  step the returned panels actually took. If the last attempt is still over,
  it says so.
- **Why the guard is not enough.** The envelope around the panels (frame block,
  meta, centroids, notices) adds 13–16 KB. Panels that passed their own guard
  still gave a 108,775-byte response for the five-event slice D 257–258 mm.
- **The whole-response check.** `api/frame_canonical.py` measures the assembled
  response exactly as FastAPI serialises it (`density.wire_size`: compact,
  UTF-8, no ASCII escapes). If it reaches 100,000 bytes, the panels are
  re-rendered from the cached bundle one guard step at a time, continuing the
  guard's sequence from the state it served, and each candidate is measured
  the same way until one fits. That slice then ships at R = 112. Every step is
  disclosed as a notice.
- **Why each candidate is measured.** An earlier version derived a panel limit
  from the compact wire size and compared it with the guard's deliberately
  over-counted panel measure. On D 20–40 mm that stepped any request above
  R = 150 past 150 to R = 112, although R = 150 serves 98,377 bytes, so asking
  for more detail served less. Measuring what is actually served keeps a
  higher request at or above the R the default request gets.

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
over the full selection, against 0.012 in the laboratory frame.

**The marks near the cores are deliberately light.** By construction the anchors
sit on the two brightest places in the picture. The earlier marks were 15 px
filled markers, a 6 px spread bar and a floating ⟨D_entry⟩ badge, and they
covered exactly the bins the panel exists to show. They are drawn by
`static/js/panels/canonical_overlays.js`:

- **Anchors** (diamond A, circle B) are 13 px open outlines, with a transparent
  fill and the shower's colour at 0.75 opacity. They are not ECharts'
  `emptyDiamond` / `emptyCircle`, which are filled white and forced to a 2 px
  stroke. On Y′Z′, where both anchors project onto the origin, one merged open
  circle stands for the two. The tooltip gives the t-based 95% interval of the
  mean anchor.
- **The spread bar** stays, because CLAUDE.md requires dispersion to be
  encoded. It is uncapped, 2.5 px wide at 0.3 opacity, and its tooltip names it
  as the sample SD of D_entry/2 across events: dispersion, not the uncertainty
  of the mean.
- **The separation rule** between the anchors is a 1 px dashed line,
  translucent white on screen and `#6b7280` in print. Its tooltip carries
  ⟨D_entry⟩ with its Student-t 95% interval and N, and ⟨D⟩ beside it. The badge
  is gone. The same ⟨D_entry⟩ ± interval is printed in the X′Y′ panel tag, in a
  `.sym` span so the tag's uppercase transform leaves the symbols alone.
- **The measured centroid sets** are all small (7 px) and told apart by shape,
  with the shower carried by colour:
  - a filled dot for the ground-truth `truth_voxel`;
  - an open ring for the prediction `pred_voxel`;
  - a plus for `canonical_mean`, the dataset centroids averaged *after*
    co-registration.

  The footnote and the exported figure name each set by the payload's own
  label (`centroidLegend`), so the three never disagree. `truth_dataset`, a
  lab-frame mean of positions, is omitted here, because averaging positions
  across events that sit in different places is exactly what this frame exists
  to avoid.
- **Plot chrome.** The canonical plots are framed by a thin border drawn above
  the raster. The axis lines no longer sit on zero: a symmetric window would
  otherwise put a crosshair through the middle of both showers.

Thin rules mark the front and back faces at z′ = 0 and 1209.5 mm. **Not drawn**:
individual trajectories (the ensemble axes replace them), and the transverse
detector outline, which rotates with each event and has no ensemble image. The
footnote says so.

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
lies within [0.45, 1.3]), otherwise with true extents and a footnote saying so;
the decision is re-taken whenever the card resizes.
The zoom window survives slider ticks within one frame — the fitted extents
move on every tick, and resetting the view each time would make zooming during
a drag impossible — and is reset only on a change of frame or experiment.

**API.**

- **Parameters.** `GET /api/projections?frame=lab|canonical` defaults to `lab`,
  so every existing contract and test is untouched. It also takes
  `rho_norm=selection|dataset` and `display=native|continuous`, whose server
  default stays `native` in both frames. The interface always sends `display`
  explicitly. `lock_scale` and `scale_mode` are accepted but ignored in the
  canonical frame.
- **The envelope.** The canonical envelope keeps every lab key and adds:
  - a `frame` block: anchor definition, window, fit, footprint, k,
    `subsample_regime`, comb (with `measured_on`), ρ_ref (with `basis`,
    `displayed_peak`, `displayed_over_ref`, `kernel_attenuation`),
    `reconstruction`, D_entry / D moments, per-shower slopes with SD, R̄′ and p,
    and anchor offsets;
  - `overlays.ensemble_axes` and `overlays.anchors`;
  - an axis `symbol` (x′ / y′ / z′);
  - `scale.rho_ref / rho_unit / decades / norm / floor / floor_ratio`;
  - per panel: `below_code`, `min_code` 2, `below_floor_cells`,
    `below_floor_energy_fraction`, `kernel`, `total` (in-window GeV after
    reconstruction), `total_energy_all_gev`, `energy_outside_window_gev`,
    `energy_fraction_outside_window` and its `_raw` twin, `n_events`,
    `topk_unit`, `bin_area_mm2` and `rho_peak`; Grad-CAM panels also carry
    `attention_mask {rule, cells, hit_fraction, max_attention}`;
  - `meta.resolution.kernel`: `{type, sigma_mm, bin_spread_rms_mm, separable,
    conservative, non_negative}`.
- **`frame.reconstruction`** states what the display did to the raw grid:
  - `display`, `kernel`, `label`;
  - `sigma_mm`, null unless Gaussian, and `bin_spread_rms_mm`;
  - `blur_rms_mm {x, y}`, the RMS spread of one cell's energy on the display
    about the cell centre, √(w²(1 − 1/k²)/12 + p²/12 + spread²): the discrete
    k × k footprint term (the continuous w/√12 would overstate it by 15% at
    k = 2), the point binning of each sub-deposit into its p = 20 mm bin, and
    the kernel's spread per bin. A Monte Carlo of randomly rotated cells,
    binned as the scan bins them, reproduces it to 0.1 mm for the box, tent
    and Gaussian; without the binning term it ran 5–8% low;
  - `subsample_k`, `gaussian_below_n` 50, and `axes ["x′","y′"]`;
  - `depth`, which is always "native sampling layers, never smoothed or
    interpolated";
  - `conservative`, `floor_ratio`;
  - per-panel `energy_fraction_outside` and `below_floor`;
  - a one-sentence `note`.

  The per-panel figures are read back from the rendered payloads, so the block
  cannot disagree with them.
- **Other endpoints.** `GET /api/experiments` lists `frames` and `z_front` per
  experiment and the canonical cache under `compute.canonical_cache`.
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

### Display modes in the canonical frame

In the canonical frame the two modes act on the uniform 20 mm accumulation grid,
not on the lattice. They mean different things there, so the radios are
relabelled and each frame keeps its own mode.

**Native Grid** *(raw 20 mm bins, audit)* sends the cropped accumulation bins
as they are. `r_x` and `r_y` are the cropped shape, and the kernel is `none`.
The payload guard may box-merge bins pairwise. It is the audit view:

- it shows a cell-footprint comb exactly as measured;
- its Grad-CAM leaves only hitless bins transparent;
- `kernel_attenuation` is 1.0 on every panel.

A handful of rotated events shows each 48 mm cell as a tilted block, so this is
not the view the frame opens in. On screen a Native Grid raster is first
enlarged by an integer nearest-neighbour factor, up to about 2048 px and at most
×32, before the browser scales it. The raw bins then read as crisp blocks rather
than a bilinear blur of a 33 × 20 bitmap that the payload does not contain.
A Continuous Field Y′Z′ or X′Z′ raster gets the same enlargement along its 60
depth columns only (60 → 1920 px, rows untouched), so the browser's smooth
upscale acts along the transverse rows, which the kernel reconstructed, and
never blends two sampling layers.

**Continuous Field** *(kernel reconstruction)* is where the canonical frame
opens. It reconstructs **x′ and y′ only** with a conservative kernel
(`grid/kernel.py`, applied by `query/reconstruct.py`). R sets the display bins
across the X′Y′ window. The kernel, not R, sets the resolution: no detail exists
below the 20 mm grid or the 48 mm cell.

| Selection | Kernel | Spread per 20 mm bin (RMS) | Total x′ blur, with the k × k footprint splat and the 20 mm binning |
|---|---|---|---|
| N < 50 | Gaussian, σ = 10 mm, over each uniform bin | 11.5 mm | 17.7 mm at k = 2, 18.9 mm at k = 6 |
| N ≥ 50 | bilinear tent: exact linear interpolation between bin centres | 8.2 mm | 15.7 mm at k = 2, 17.0 mm at k = 6 |

- **Why two kernels.** A handful of events leaves rotated cell blocks that the
  tent alone would still show. From 50 events the ensemble of rotation angles
  fills the footprint.
- **The switch at N = 50.** The tent is 29% narrower. Re-rendering the
  production N = 49 and N = 50 bundles with both kernels shows that the switch
  raises the displayed X′Y′ peak by 6–7% and the depth peaks by 4–5%. The
  kernel sentence (`frame.reconstruction.note`, in the notices and the panel
  footnote) discloses it.
- **Which source bins.** Each axis is reconstructed from the full accumulation
  axis sliced to the window plus the kernel's reach: one bin for the tent,
  ⌈9σ/p⌉ + 1 for the Gaussian, whose tail is exactly zero past 9σ. Energy just
  outside the window therefore blurs in, and energy leaving it is counted. On
  X′Y′ the in-window total agrees with the row and column inside-weights applied
  to the raw grid to 3.5 × 10⁻¹⁶ relative.
- **Grad-CAM** uses the same operator on the numerator and the denominator (a
  normalised convolution), so a constant attention field stays exactly
  constant.
- **Depth** keeps its 60 native sampling layers in both modes and is never
  smoothed or interpolated. There is no measurement between two layers 20.5 mm
  apart.

Bicubic interpolation was rejected: its negative lobes give negative density and
overshoot the peak. Point interpolation was rejected because it does not
conserve energy. The display caption names the kernel, σ, its RMS spread, the
total blur, the display pitch and the N gate.

**One mode per frame.** The state holds `display_lab` (default `native`, the
hardware lattice) and `display_canonical` (default `continuous`).
`state.get('display')` and `set({display})` address the active frame's key.
Switching frame and back returns each frame to the mode it was left in, and
re-syncs the radios, their per-frame labels, the R control and its hint. The
hash writes each key only when it differs from its default. A pre-split
`#display=native` link still works: it is applied to the active frame, unless
the link also carries that frame's own key. Canonical links written before the
split never carried `display`, because Native was the default, so they now open
in Continuous Field.

**Switching costs no scan.** The canonical cache key names the selection, the
sampling, the accumulation grid, k and the footprint. It says nothing about the
display mode, R or the kernel, all of which are applied afterwards to the cached
raw grid. A mode or R change is therefore a re-render: 10–29 ms for the whole
request on production, of which the render itself takes 3–6 ms.

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
*computed*.

- **In the canonical frame** the sentences state:
  - the frame definition, N and the events excluded without a frame;
  - ⟨D_entry⟩ against ⟨D⟩;
  - ρ_ref with its reference and the ramp bounds;
  - the display floor: the undrawn bins and their energy share, or for Grad-CAM
    the masking rule of the display mode;
  - the symmetric display window ("x′ ±480 mm, y′ ±380 mm, symmetric about the
    origin at the 0.1st–99.9th energy percentile") with any floor or clamp, and
    the energy it leaves out after reconstruction;
  - the provisional flag;
  - the reconstruction note (kernel, σ, spread, total blur);
  - the footprint and k, and the measured comb;
  - the ill-conditioned count;
  - R̄′ / Rayleigh p / N for each ensemble axis.
- **In the laboratory frame** they state the ramp's clipping counts and the
  staggered-comb note.
- **In either frame** they state whether the values came from the 10% sample.

The live footnote still travels too, de-duplicated against these lines.

**The provenance line and the file name read the display from the payload, not
from the controls.** Both use R, the merge and the kernel (`caption.displayOf`,
from `meta.resolution` and `frame.reconstruction`). The payload guard can lower
R below the slider, and a figure labelled R150 that holds R112 bins is
mislabelled. The provenance line names the grid, for example "canonical
centre-of-separation frame, Gaussian kernel, σ = 10 mm on 7.5 mm display bins
(R = 112)" or "raw 20 mm bins (Native Grid, no reconstruction)".

Two things change for white paper beyond the obvious inversion:

- **The categorical sub-range flips.** `categoricalStops` samples the *upper*
  ramp on screen because Viridis begins at `#440154`, invisible as a one-pixel
  line on `#0d1117`. On white the failure is the mirror image — the `#fde725` end
  vanishes — so print samples [0, 0.75]. The ramp's identity and its lightness
  ordering are untouched; this is a sub-range change, not a palette inversion.
- **The colour bar moves below the x axis.** A vertical bar costs about seven
  label widths, which on a 321 px figure is a quarter of the canvas.

The canonical overlays change for print as well:

- **The display floor is a hard contour.** `floorFadeDecades` is 0 in print, so
  the alpha is a pure step and never a division by zero. A gradient could band
  or drop out on a printer. The caption therefore says "the dark outline is the
  10⁻³ display floor, not a shower edge", and the ramp title appends "· below
  10⁻³ not drawn", shortened to "· <10⁻³ not drawn" where a single column has no
  room.
- **The separation rule** is `#6b7280` instead of translucent white, which
  vanishes on paper and carries an alpha that PDF renderers composite
  unpredictably.
- **Anchors** print at full opacity.

None of these three tokens is text, so none is held to the 4.5:1 ink floor.

> **The spatial panels' density field stays a raster.** The SVG embeds it as
> an `<image>`. The axes, overlays, legend and every label are true vector
> `<text>` and `<path>`, which is what LaTeX compilation turns on. The bitmap
> is upscaled by an **integer** factor with smoothing off. Each pixel block is
> one **payload bin**:
>
> - a detector cell in the lab frame;
> - a raw 20 mm accumulation bin in the canonical Native Grid;
> - a reconstructed display bin in the Continuous Field.
>
> Every one of them is a value the server computed, and interpolating between
> them would invent values the payload does not contain. On the lab lattice that
> would be resampling by point interpolation, which CLAUDE.md forbids. The
> smoothing a Continuous Field figure shows was done on the server by the kernel
> the caption names, not by the image scaler. Print takes the raster at one
> pixel per payload bin, without either on-screen enlargement, and applies one
> integer factor to both axes. The factor fills the printed width at 300 dpi
> but keeps the long side at or below 4096 px, so a 60-layer depth raster a few
> hundred rows tall is no longer enlarged by its width alone.
> The energy panel is line and path geometry throughout and vectorises
> completely.

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
frames never collide. The display token (`native` or `R112`) is the payload's.
A canonical Continuous Field export appends the kernel last, as `gauss10` or
`tent`, so the 60-character cap drops the kernel before it drops `canonical`.
For example: `xy_D-257-258_R112_canonical_gauss10_20260924_101500.svg`.

---

## API

All endpoints return pre-aggregated payloads; none returns a raw hit array.

| Endpoint | Purpose |
|---|---|
| `GET /api/experiments` | Registered tables, row/event counts, kinematic bounds, lattice, compute allocation. |
| `POST /api/upload` | Streamed multipart ingest. Returns a job id. |
| `GET /api/upload/{job_id}` | Ingest progress and result. |
| `GET /api/projections` | The three spatial panels as quantised rasters (~35 KB in the lab frame; a canonical response is budgeted whole under 100 KB), in the laboratory frame (`frame=lab`, default) or the canonical centre-of-separation frame (`frame=canonical`, with `rho_norm=selection\|dataset`); `display=native\|continuous` in both. |
| `GET /api/energy-distribution` | Per-slice Gaussian fits, histograms and benchmarks. |
| `GET /api/model-performance` | Voxel accuracy, MAE, energy residuals, per-slice breakdown. |
| `GET /api/health` | Liveness, with the resolved memory and thread allocation. |

Interactive documentation at <http://localhost:8000/docs>.

Projection payloads ship as `log10 → uint8 → base64` rasters with the scale
constants attached. The brightest 64 cells also carry their exact float64 value,
so tooltips stay quotable. The two frames use the 8-bit codes differently:

| Frame | Code 0 | Code 1 | Ramp | Step |
|---|---|---|---|---|
| Laboratory | empty | bottom of the ramp | 254 levels from code 1 over six decades | 5.6% |
| Canonical | empty | populated but below the 10⁻³ display floor (`below_code`), drawn transparent | 253 levels from `min_code` 2 over three decades | 2.8% |

Both steps are finer than the eye resolves. The lab quantiser is byte-identical
to its old formula. The client indexes a canonical colour table at
`round((code − min_code)/(max_code − min_code) · 255)`, so a drawn colour sits
where the legend and `dequantize` put it.

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
| Canonical frame, display mode or R change (cache hit, re-render only) | 10–30 ms |

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
budget on a realistic window, the dataset-reference ρ_ref, R̄′ rising on a
wide-D slice, the kernel a sampled Continuous preview picks from the exact N and
the whole-response budget at R = 150 cannot be exercised on the two-event
demonstration file, so without the variable those tests are skipped, not
passed. `tests/test_kernel.py` needs no database at all: it pins every operator
property the display relies on (columns telescope, W ≥ 0, energy conserved,
σ → 0 is the box, the tent is `np.interp`, no displayed bin above the raw peak
over 100 random matrices, flat fields stay flat, float32 input gives the
float64 result) and the symmetric window on hand-computed cases. `tests/test_golden_lab.py`
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
  grid/    lattice splat resolution slab frame kernel
  query/   filters projections panels centroids summary energy performance sampling cache experiments
           stagger canonical window reconstruct density ensemble canonical_cache
  stats/   gaussian histogram slices metrics clip
  encode/  scale quantize matrix topk
  api/     deps routes_* frame_canonical
  static/  index.html css/ js/
             js/      main api state scale palette decode dom textfit
             js/panels/   projection canonical_overlays marks energy metrics
             js/controls/ range_slider upload
             js/export/   tokens figure caption disclosure filename download menu
```

The canonical frame is its own column of that layout, one responsibility per
file.

**Server:**

| File | Responsibility |
|---|---|
| `grid/frame.py` | the pure-NumPy SE(3) mathematics, the footprint measurement, the window planner and the sub-sampling rule; the display constants (`SMOOTH_SIGMA_MM`, `GAUSSIAN_KERNEL_BELOW_N`, the window percentiles and floors), each citing its measurement |
| `grid/kernel.py` | the conservative reconstruction operators, maths only: the Numerical Recipes `erfcc` (numpy has no erf and scipy is not a dependency); the box ⊗ Gaussian operator computed inside its 9σ band; the tent, which refuses a non-uniform source; all float64 throughout |
| `query/canonical.py` | the per-event frame statistics and the DuckDB accumulation scan |
| `query/window.py` | the symmetric crop and its floors |
| `query/reconstruct.py` | the policy: which kernel a display mode and N get, each panel axis as an `AxisMap` (native crop, kernel from the full axis plus reach, or depth passthrough), and the `frame.reconstruction` report |
| `query/density.py` | the crop → reconstruct → ⟨ρ⟩ → encode step, the energy bookkeeping and the panel budget guard |
| `query/ensemble.py` | the two axes with their band and envelope |
| `query/canonical_cache.py` | the cached bundle and its start-up warmer |
| `api/frame_canonical.py` | the envelope assembly and the whole-response budget |

**Client:**

| File | Responsibility |
|---|---|
| `static/js/panels/canonical_overlays.js` | the light anchors, spread bars, separation rule and shape-coded centroids, with the legend sentence the footnote and the figure share |
| `static/js/panels/marks.js` | the clipped, hit-testable custom-series lines both frames draw their named overlays with |
| `static/js/export/disclosure.js` | the structured figure disclosures |

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
