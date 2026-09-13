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
spatial panels render correctly while the reconstructed-energy panel reports
*insufficient statistics* rather than fitting a meaningless two-point width.

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
by 150 ms; the spatial resolution control; display channel and model selectors;
and the performance KPI card.

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

All three spatial panels **scroll to zoom and drag to pan**, with an *Auto-fit
RoI* button that frames the box holding 99% of the selected energy (bounded by
energy percentile, not by the outermost hit, so one stray cell cannot define the
view) and a *Reset*. Both axes always scale by the same factor, so the 1:1
metric aspect survives zooming — verified at 4.974 mm/px on both axes after four
wheel notches. When the selected showers already span the detector, as most
multi-event selections do, the fit says so rather than appearing inert.

### Direction overlays on the depth panels

The two overlays are complements, and only one is honest at a time.

*Selections of 50 events or fewer* get the **individual incident trajectories**,
projected from each event's centroid and (θ, φ) across the fiducial depth.

*Larger selections* get the **energy-weighted shower axis** — the transverse
centroid per depth layer, measured from the binned data on screen.

> **No averaged trajectory is ever drawn.** Azimuth is circular, and its mean
> resultant length R̄ is 0.012 over the full dataset, 0.042 for a 122-event
> window and 0.178 even for 7 events: the direction is near-uniform at every
> reachable selection size, so an "average" would point somewhere arbitrary
> while looking authoritative. The panel states the measured R̄ instead. For the
> same reason the ensemble axis is withheld below the trajectory threshold —
> averaging the position of a handful of showers that sit in different places
> has no common centre to converge on.

### Low statistics in plot 4

A `density=True` histogram normalises by `N × bin_width`, so once the bins are
finer than the spacing between events each occupied bin holds exactly one and
reports a height set by the binning rather than the distribution — the tall
narrow spikes the panel used to show at small N.

Below **N = 15** in a slice, the histogram and the fitted curve are suppressed
server-side and the individual events are shipped as a **rug strip** instead,
with an explicit note. Above it, the bin count follows the sample size (Rice
rule, clamped to 8–120) driven by the smallest drawn slice, so all slices share
one binning and none is finer than its own statistics support.

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

---

## API

All endpoints return pre-aggregated payloads; none returns a raw hit array.

| Endpoint | Purpose |
|---|---|
| `GET /api/experiments` | Registered tables, row/event counts, kinematic bounds, lattice, compute allocation. |
| `POST /api/upload` | Streamed multipart ingest. Returns a job id. |
| `GET /api/upload/{job_id}` | Ingest progress and result. |
| `GET /api/projections` | The three spatial panels as quantised rasters (~35 KB). |
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

### Module layout

```
calosrv/
  config.py logging_setup.py errors.py app.py
  db/      connection settings ddl naming registry bootstrap
  ingest/  stream csv_spec load lattice_fit derive_proj derive_events verify jobs cli
  grid/    lattice splat resolution slab
  query/   filters projections panels centroids summary energy performance sampling cache experiments
  stats/   gaussian histogram slices metrics clip
  encode/  scale quantize matrix topk
  api/     deps routes_*
  static/  index.html css/ js/
```

Two structural rules the layout exists to enforce:

- **`db/naming.py` is the only place a table name becomes SQL identifier text.**
  DuckDB cannot parameterise identifiers, so interpolation is unavoidable;
  confining it to one validated function keeps the injection surface auditable in
  one file.
- **No SQL string lives outside `query/` and `db/ddl.py`.** Route modules build a
  `FilterSpec` and call a query module.

### The legacy batch compiler

`build_dashboard.py` and `calodash/` are untouched and still work. The two
packages deliberately share no imports: the estimators `calosrv` needs are
re-implemented so neither path can break the other.
`calosrv/stats/gaussian.py` documents where it must stay numerically identical to
`calodash/stats.py`.
