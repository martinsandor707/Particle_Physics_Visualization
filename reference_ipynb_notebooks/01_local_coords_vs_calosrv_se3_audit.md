# Coordinate transformations: `local-coords.ipynb` against `calosrv`

An audit of the two transformations the reference notebook calls *translated*
and *local* against what the dashboard serves under those names, a comparison
of both with the dashboard's own SE(3) co-registration (the Separation-Aligned
D-frame, API `canonical`), and a plan for building every co-registered view on
one SE(3) base.

Scope and method. The notebook
(`coordinate_transformatioons/local-coords.ipynb`) and its proton/pion twin
(`sofiya_visualizations/High_energy_notebook_proton_pion-v5.ipynb`, cells 9–15,
which re-use the same two functions) were read cell by cell; the `core` module
they import and the single-particle CSVs they load are not in this repository,
so nothing was re-run. The dashboard side was read in `calosrv/grid/frame.py`,
`calosrv/query/canonical.py`, `calosrv/query/shower_frames.py`,
`calosrv/ingest/derive_proj.py`, `calosrv/ingest/derive_events.py`,
`calosrv/ingest/verify.py`, `calosrv/api/frame_canonical.py`,
`calosrv/api/frame_shower.py` and the frontend overlays. The rotation
identities quoted in section 1 were checked numerically (2 000 random
(θ, φ) pairs, residuals at the 10⁻¹⁶ level); every "measured on production"
figure is quoted from the repository's own documentation, not re-measured here.

---

## 1. Perceptual & Statistical Audit

### 1.1 What the notebook defines

Two transformations, applied per shower, both documented in the notebook's
first markdown cell and implemented in cells 6–7.

**Translated** (`x_trans, y_trans, z_trans`; cell 7 recomputes them as
`_add_translated_coords`):

```
P0 = (x0, y0, z0)   z0 = min z of the shower's hits (its first populated layer)
                    (x0, y0) = energy-weighted mean of (x, y) over the hits at z = z0
Δ  = (x − x0, y − y0, z − z0)
```

A pure translation: the SE(3) element `T_trans = [ I | −P0 ]`.

**Local** (`x_local, y_local, z_local`): the same Δ, then rotated so the
incident direction `n = (sin θ cos φ, sin θ sin φ, cos θ)` becomes +z′:

```
R(θ, φ) = ⎡ cos θ cos φ   cos θ sin φ   −sin θ ⎤
          ⎢ −sin φ        cos φ          0     ⎥
          ⎣ sin θ cos φ   sin θ sin φ    cos θ ⎦

(x′, y′, z′)ᵀ = R · Δ
```

Checked: `R = R_y(θ) · R_z(φ)` (passive rotation by φ about z, then by θ
about the new y), `R n = (0, 0, 1)`, `R Rᵀ = I`, `det R = +1`. So
`T_local = [ R | −R P0 ]` is an element of SE(3) and preserves every
distance, which is what makes energies of different showers addable after the
transform. One identity the notebook uses without stating it: the first-layer
plane `z = z0` maps to the tilted line `z′ = tan θ · x′` in the X′–Z′ panel
(cell 6, panel 8); it holds exactly for every y′.

Two points that matter for the comparison below:

- The notebook's datasets are **single-particle** (one shower per event), so
  "per shower" and "per event" coincide there. In the production two-shower
  file both frames are **per shower**: every hit is moved by *its own*
  shower's P0 and R, and the two showers of an event end up superimposed at
  the origin.
- The notebook never rotates about anything but the incident direction, and
  never translates to anything but the first-layer centroid.

### 1.2 What `calosrv` serves under the same names

| | Notebook | `calosrv` (API `trans` / `local`) | Match |
|---|---|---|---|
| Coordinates | computed in-notebook (`x_trans`) or read from the file (`x_local`) | **read from the file's own `x/y_trans`, `x/y/z_local` columns** (`derive_proj.py`), never recomputed; only `kt = round(z_trans / 20.5 mm)` is derived | same source columns |
| Rotation | `R(θ, φ)` above | the ingest check `local_rotation` rebuilds **exactly this `R`** in SQL (`verify.py: _archive_checks`) and fails the ingest if any hit's `x/y/z_local` differs from `R · (x_trans, y_trans, z_trans)` by more than 0.01 mm | exact |
| Translation | P0 = energy-weighted centroid of the first populated layer | P0 is recovered per shower as `x − x_trans` (event table `p0a*`, `p0b*`) and verified **rigid** (`p0_constancy`: spread ≤ 0.01 mm within a shower) | rigid shift verified; **the definition of P0 is not verified** (see gap G1) |
| Depth | `z − z0`, continuous | `z_trans` verified to sit on whole 20.5 mm layers (`trans_layers`); stored as the own-shower layer ordinal `kt` | same quantity, stored as a layer index |
| Local sub-cell handling | none: a hit is a point | each 48.27 × 48.6 × 20.5 mm cell is split into k × k × k_z sub-deposits whose offsets are rotated by **the same `R`** (`shower_frames.py: _local_sql`, CTE `rot`) | the same matrix, applied to the cell footprint as well as its centre |
| Accumulation | `hist2d`, 100 point-bins on a fixed window (±500–1000 mm transverse, −100 … 1200 mm depth) | 20 mm grid planned from ingest-time energy quantiles; exact box overlap (trans) or rotated sub-deposits (local); comb measured on every response | dashboard is stricter (CLAUDE.md §2) |
| Direction marks | dashed forward / dotted backward incident line from P0; first-layer plane; origin ✕ marker; principal-axis tilt | trans: individual directions from the origin for ≤ 50 events, else R̄ stated; local: no direction (it is +w by construction); no first-layer plane, no principal axis, no tilt | partial (see §1.4) |

**Verdict for the two notebook frames: the dashboard's Local frame is the
notebook's local transformation, bit for bit at ingest tolerance, and its
legacy Per-shower translated frame is the notebook's translated one.** What
differs is presentation (footprints instead of points, quantile windows, the
measured comb) and the two-shower superposition, which the notebook's data
never needed.

Gap **G1**: the dashboard trusts the producer for *what* P0 is. It proves
that `x − x_trans` is one point per shower, and the README states that point
is "the energy-weighted (x, y) centroid of that shower's first populated
layer, at that layer's z", but no check compares `p0` with that centroid
computed from the hits. Section 3.5 adds one.

### 1.3 The D-frame (API `canonical`) against both

The D-frame is a third transformation, written in `grid/frame.py` and
executed in SQL by `canonical.build_sql`:

```
entry_S = c_S − (c_S,z − z_f) · tan θ_S · (cos φ_S, sin φ_S)      S ∈ {A, B}
                (3-D whole-shower centroid, back-projected to the front face z_f)
m       = (entry_A + entry_B) / 2                                  (origin)
ψ       = atan2(entry_B,y − entry_A,y, entry_B,x − entry_A,x)      (A→B azimuth)
x′ =  cos ψ (x − m_x) + sin ψ (y − m_y)
y′ = −sin ψ (x − m_x) + cos ψ (y − m_y)
z′ =  z − z_f
```

Side by side:

| Property | Notebook *translated* | Notebook *local* | D-frame (`canonical`) |
|---|---|---|---|
| Unit of co-registration | one shower | one shower | one **event** (both showers by the same motion) |
| Translation | own P0 (first-layer centroid) | own P0 | midpoint of the two **back-projected 3-D centroids** at the front face |
| Rotation | none | `R_y(θ) R_z(φ)`: full SO(3), incident direction → +z′ | `R_z(ψ)` only: SO(2) about the detector axis, A→B separation → +x′; incidence stays oblique |
| Depth | `z − z0` (own first layer) | along the incident direction | `z − z_f` (front face) |
| Group | SE(3) | SE(3) | SE(3) |
| What becomes coherent | positions about the entry point | positions and directions (all +w) | positions about the separation, and *measured* directional coherence (R̄′ 0.78–0.82 for well-separated showers) |
| Ensemble direction allowed | no (azimuth uniform, R̄ = 0.012) | no information (every direction is +w) | yes, with band, envelope, R̄′, Rayleigh p |

Checked numerically: the D-frame's linear part is **exactly the notebook's
`R(θ, φ)` evaluated at θ = 0, φ = ψ**, i.e. the notebook's rotation with the
tilt removed and the incident azimuth replaced by the separation azimuth. Its
translation is a different point altogether (the back-projected 3-D centroid
midpoint, which the README measures to land a median 82 mm (A) / 69 mm (B)
from the entrance-slab centroid, against 181 mm for the opposite sign).

**Verdict: the D-frame matches neither notebook transformation exactly.** It
is the notebook's rotation restricted to SO(2) with a different angle, applied
per event rather than per shower, with a different anchor. That is by design:
a full `R(θ, φ)` can align only one of the two showers, so a per-event frame
cannot be the notebook's local frame; and the per-shower local frame cannot
show the separation, which is what the D-frame exists for. All three are
elements of SE(3), and that shared structure is what the plan in section 3
builds on.

### 1.4 Marks and scales the notebook draws, and where they stand

The notebook's cell 6 figure (per event: 3 frames × 3 projections) and cell 7
figure (ensemble: 3 frames × 3 energy-weighted 2-D histograms).

| Notebook mark / scale | Dashboard today | Note |
|---|---|---|
| Energy-weighted 2-D histogram per frame, 100 point-bins, fixed window | the three frames' panels (Absolute / Per-shower translated / Local), footprint-splatted, quantile windows, comb measured | exists, one frame at a time, not side by side |
| Per-event scatter in three frames, equal aspect, per-event window `half = max(ptp)·1.15 ≥ 150 mm` | nothing per event: the API has no event selector; a filter that isolates one event shows it, but not as three frames at once | missing (§3.3) |
| Common log colour scale across all panels, floor at the 1st percentile of positive energies, top at the max | Absolute frame: decades ramp locked to the dataset's brightest cell; co-registered: 3 decades below ρ_ref | different but documented; the notebook's 1st-percentile floor is the CLAUDE.md §2 default |
| Incident direction: dashed forward, dotted backward, from P0 | Absolute ≤ 50 events: individual trajectories from the centroid; Per-shower translated: from the origin; D-frame: two ensemble axes with dispersion wedge and t-envelope | forward only; no backward extrapolation |
| First-layer plane: `z = z0` (dash-dot) and `z′ = tan θ · x′` in local X′–Z′ | D-frame draws front and back **face** rules at z′ = 0 and the last layer; nothing per event | missing as a per-event mark; has no ensemble image in the local frame (each event's tilt differs), which the dashboard already argues for the rotating transverse outline |
| Origin marker (red ✕ at P0 / at (0, 0)) | D-frame anchors (open diamond / circle with spread bars); Local / trans: `frame_mean` cross and whiskers at the mean centroid | the anchors are the D-frame's counterpart; P0 itself is not marked in Local |
| Principal axis–z′ angle (energy-weighted covariance eigenvector of the local cloud) | none | missing (§3.3); cheap server-side |
| Row label: event, hits, θ, φ, origin | none per event | missing (§3.3) |
| Event selection: above-average hit count, largest-θ pool of 20, seeded draw of 5 | none | missing (§3.3) |

---

## 2. Execution & Data Requirements

Everything section 3 needs already exists in the database:

| Input | Where it is |
|---|---|
| Laboratory `x, y, z` per hit | projection table as lattice ordinals `ix, iy, iz`, placed through the registry's coordinate arrays |
| Per-shower `θ, φ` | event table `theta_a, phi_a, theta_b, phi_b` |
| Per-shower P0 | event table `p0ax … p0bz` (DOUBLE, from `x − x_trans`) |
| Per-shower 3-D centroids, D | event table `cax … cbz`, `d` |
| The file's own `x/y_trans`, `x/y/z_local` | projection table `xt, yt, kt, xl, yl, zl` (kept as the cross-check in §3.1) |
| Cell footprint | measured at request time (`canonical.cell_footprint`), 48.27 × 48.6 mm on production |
| Layer pitch, front face | registry lattice (`z_lo`, `pitch_z`) |

No new columns are required for sections 3.1–3.4. Section 3.5 adds two
ingest-report values (no table change). Section 3.6 (datasets without the
`_trans` / `_local` columns) needs a second ingest schema and is scoped there.

Execution environment is the existing service: Python 3.11, DuckDB 1.5.5,
FastAPI, NumPy; vendored ECharts 5.6.0. Nothing new to install.

---

## 3. Plan: one SE(3) base for every co-registered view

The plan does not replace the D-frame and does not change what any existing
view shows. It (i) puts the three transforms on one code path so that the
per-shower frames no longer *depend* on the file's columns, (ii) makes the
anchor an explicit, measured choice, (iii) adds the notebook's per-event
comparison figure, and (iv) closes gap G1.

### 3.1 One SE(3) element, three instantiations

`grid/frame.py` currently holds the SO(2) pieces (`rotate_xy`,
`rotate_direction`, `entry_anchor`, `FrameParams`). Extend it with the SO(3)
general case and express all three frames through it:

```python
# grid/frame.py (addition)
def rotation_matrix(theta, phi) -> np.ndarray:
    """R(theta, phi) = R_y(theta) @ R_z(phi): the notebook's matrix, shape (..., 3, 3).
    R @ unit_direction(theta, phi) == (0, 0, 1)."""
    ...

@dataclass(frozen=True)
class Se3:
    r: np.ndarray   # (..., 3, 3), orthonormal, det +1
    t: np.ndarray   # (..., 3): p' = r @ p + t
    def apply(self, p): ...
    def apply_direction(self, u): ...   # linear part only
    def inverse(self): ...

def per_shower_translated(p0) -> Se3:               return Se3(I, -p0)
def per_shower_local(p0, theta, phi) -> Se3:        R = rotation_matrix(theta, phi); return Se3(R, -R @ p0)
def per_event_canonical(entry_a, entry_b, z_f) -> Se3:
    psi = atan2(...); R = rotation_matrix(0.0, psi); m = (entry_a + entry_b)/2 (z = z_f); return Se3(R, -R @ m)
```

Tests pin the identities checked for this audit: `rotation_matrix(0, psi)`
equals the current `rotate_xy`; `rotation_matrix(theta, phi) @
unit_direction(theta, phi) == +z`; orthonormality; distance preservation; and
`per_shower_local` applied to the laboratory coordinates reproduces the
file's `x/y/z_local` within the ingest tolerance (0.01 mm) on the fixture.

In SQL the generalisation is already half-written: `_local_sql`'s `rot` CTE
builds the nine entries of `R(θ, φ)` per (event, shower) to rotate the
sub-deposit offsets, and `canonical.build_sql`'s `fr` CTE builds `cos ψ, sin
ψ` per event. One shared CTE that emits `r11 … r33, t1, t2, t3` per
(event, shower) serves all three scans; the per-event D-frame simply emits the
same row for both showers. The hit position then transforms as
`p' = R (p_lab − anchor)` **from the laboratory ordinals** (`list_extract` of
the coordinate arrays, as the canonical scan does today), and the file's
`xl, yl, zl` become a per-response cross-check: the scan reports
`max |p'_computed − p'_file|` for the selection, beside the ingest-time
figure. When that residual is at tolerance the two are interchangeable; when
a dataset lacks the columns (§3.6) the computed ones stand alone.

Cost: the local scan already joins the 40 000-row shower CTE and rotates
k × k × k_z sub-deposits per hit; rotating the centre as well adds three
multiply-adds per sub-deposit. Expect a few percent on the 2.5–2.7 s cold
full-selection scan, and nothing on a cache hit.

### 3.2 The anchor as a stated, measured choice

The notebook's origin is P0; the D-frame's is the back-projected 3-D
centroid. Both are available per shower in the event table, so their
difference can be measured on every dataset at ingest:

```
δ_S = | entry_S − (P0_S,x, P0_S,y) |      per shower, in mm
```

Report `median δ`, `p90 δ` and the count above one cell footprint in the
ingest report, and offer `anchor=backprojected|p0` on `frame=canonical`
(default unchanged until the measurement says otherwise). With `anchor=p0`
the D-frame origin becomes the midpoint of the two first-layer centroids
(each back-projected the short distance `(z0 − z_f) tan θ` to the front face
along its direction, so the depth convention `z′ = z − z_f` is untouched) and
ψ the azimuth between them. The payload's `frame.anchor` already names the
definition (`entry_backprojection`); it gains the second value, the drawer
prints the median δ, and `D_entry` is reported for whichever anchor is in
use, beside the dataset's D as now.

Why bother: the README records that the back-projection lands a median
82 / 69 mm from the entrance-slab centroid. If P0 lands closer, the
D-frame's anchors sit nearer the showers' true entry points and the ensemble
widths narrow for reasons that are physics rather than anchor error; if it
does not, the number says so and the default stays. Either way the notebook's
origin and the dashboard's are then related by a measured quantity rather
than by two different definitions.

### 3.3 The notebook's per-event figure: an Event Inspector

The one figure of `local-coords.ipynb` with no dashboard counterpart is cell
6: one event, three frames, three projections each, with the incident
direction, the first-layer plane, the origin and the principal-axis tilt.
Build it as a server-rendered view, not a scatter:

- **Selection.** `event_number` as a query parameter on a new
  `GET /api/event` (filters still apply, so a link carries the context). The
  sidebar gets an event picker: a number field, previous / next within the
  current selection, and "pick for me", which reproduces the notebook's
  `_select_events` (events above the selection's mean hit count, the 20 with
  the largest θ, a seeded draw) and states the rule.
- **Rasters.** For one event the finest honest payload is one value per
  cell. The lab panel is the native lattice (as today, filtered to the
  event); the translated and local panels are the 20 mm accumulation grid
  with footprint splatting (box overlap / rotated sub-deposits at the
  gap-free k), cropped to the notebook's per-event window: `half = 1.15 ×
  max(ptp over x, y, z, x′, y′, z′) ≥ 150 mm`, the same half-width on every
  panel so the tilt reads at its true angle, 1:1 aspect enforced by the
  existing isometric letterbox. Nine quantised rasters of a single event fit
  the 100 KB contract with room; the guard still runs. No per-event density
  claim is made: the colour is energy per cell on a log ramp with the
  notebook's floor (1st percentile of the event's positive cell energies,
  stated), shared across all nine panels as in the notebook.
- **Marks** (all small overlays, drawn by the existing `marks.js`
  conventions): incident direction forward (dashed) and backward (dotted,
  labelled "extrapolated") from the anchor; the first-layer plane as a
  dash-dot rule at `z = z0` (lab, translated) and the tilted line
  `z′ = tan θ · x′` in the local X′–Z′ panel; the origin ✕ at P0 / (0, 0);
  and the **principal-axis tilt**, computed server-side from the
  energy-weighted covariance of the local cloud (largest eigenvector's angle
  to +w) and printed on the X′–Y′ panel with the event's θ, φ, hit count and
  P0, exactly the notebook's row label. For the two-shower file the figure
  is drawn per shower (A and B side by side or toggled), since P0 and R are
  per shower.
- **Where it lives.** Page 1 (physics), as a card that replaces the 2 × 2
  grid while an event is pinned, or as a drawer; the roadmap document places
  it. Its export is the plot area only, as every other panel's.

### 3.4 Side-by-side frames for the ensemble figure

Cell 7 (global / translated / local, 3 × 3) exists as three separate frames.
The only missing piece is a layout that shows them together: a "compare
frames" toggle that issues the three requests and lays the nine panels out
in the notebook's order with one shared window per row. Frontend only; the
payloads and their disclosures are unchanged. Worth doing after 3.3, because
the per-event inspector needs the same nine-panel layout.

### 3.5 Verify what P0 is (closes G1)

Add to `ingest/verify.py` one grouped scan of the archive per (event,
shower): `z0 = min z` over the shower's rows, then the energy-weighted mean
of `(x, y)` over the rows at `z = z0`, compared with the event table's
`p0{a,b}{x,y}` and with `z0` against `p0{a,b}z`. Report the maximum residual
as `p0_definition_residual_mm`; fail above the same 0.01 mm tolerance the
rotation check uses. The 'A+B' rows belong to both showers' first layer
(a comment in `derive_events.py` records it) and must be included on both
sides, as that module's `p0` expressions already do.

### 3.6 Datasets that carry no `_trans` / `_local` columns

The notebooks also work on files the dashboard cannot ingest: the five
fixed-energy ddsim proton files (8 columns: `event_id, hit_index, x, y, z,
hit_energy, contribution_time, contribution_energy`) and the aggregated
per-event files. With section 3.1 in place the per-shower frames need only
`x, y, z, θ, φ` and a P0, all of which an ingest can derive, so a second,
smaller input schema ("single-shower hits") becomes feasible: one shower per
event, no segmentation planes, no CAM channels, frames computed in-DB, P0
computed at ingest by the notebook's rule. This is a separate piece of work
(new schema, new derived tables, the admin upload form learning a second
format); it is listed here because 3.1 is what makes it possible, and the
roadmap document assigns it a phase.

### 3.7 Order of work

1. `grid/frame.py`: `rotation_matrix`, `Se3`, the three constructors, unit
   tests for the identities (half a day).
2. Shared frame CTE in `query/`; per-shower scans transform from lab
   ordinals and report the residual against the file's columns; existing
   tests must pass unchanged, plus one asserting the residual on the
   fixture (one to two days).
3. `verify.py`: `p0_definition` check and the anchor residual δ (half a
   day).
4. `anchor=` parameter on `frame=canonical`, payload and drawer text, tests
   (one day).
5. `GET /api/event`, the inspector's nine rasters and marks, the event
   picker, tests and a browser test for the layout (three to four days).
6. Compare-frames layout (one day).

---

## 4. Data Integrity Checklist

- [x] The dashboard's Local frame applies the notebook's `R(θ, φ)` exactly
      (ingest check `local_rotation`, tolerance 0.01 mm); its Per-shower
      translated frame is the notebook's translated frame.
- [x] The D-frame is a distinct SE(3) element: `R(0, ψ)` about the
      detector axis, per event, anchored on back-projected 3-D centroids. It
      is documented as such and is not presented as either notebook frame.
- [x] G1: P0's definition (first-layer energy-weighted centroid) is now
      verified at ingest (`p0_definition`, `ingest/frame_checks.py`,
      0.01 mm; 0.05 µm on production over 40,650 showers), beside its rigidity.
- [x] Every transform in this plan is distance-preserving (checked
      numerically), so summing energies after it is legitimate.
- [x] After 3.1, the per-shower frames report the residual between
      in-DB coordinates and the file's columns on every response
      (`frame.coordinates`; `coordinates=file|computed`).
- [x] After 3.2, the anchor definition is named in the payload
      (`frame.anchor`, `anchor_choice`) and the measured δ between the two
      definitions is printed in the drawer (`frame.anchor_residual`).
- [x] No raw hit arrays leave the server: the per-event inspector ships
      quantised rasters at cell resolution, under the 100 KB contract.
- [x] Directions: no averaged direction is drawn in the Absolute or
      per-shower frames; the D-frame's ensemble axes keep their R̄′,
      Rayleigh p, dispersion band and t-envelope (unchanged).
- [x] Axis distortion: the inspector enforces one half-width on all nine
      panels and the 1:1 letterbox, as the notebook does with
      `set_aspect('equal')`.
- [x] Colour: the inspector's shared log ramp states its floor (1st
      percentile of the event's positive cell densities) and its top in the
      response (`scale.rule`), beside every ramp and in every cell's drawer.


---

## 5. Implementation notes (carried out)

Everything in section 3 was built on the `se3-frames` branch; the order of
work in 3.7 was followed, and the deviations from the plan as written are
listed last.

**3.1 One SE(3) element.** `grid/frame.py` gained `rotation_matrix(θ, φ)`
(= R_y(θ) R_z(φ), checked to map n(θ, φ) onto +z′ and to be orthonormal),
the frozen `Se3` (`r`, `t`; `about(r, anchor)`, `apply`, `apply_direction`,
`inverse`) and the three constructors. Twenty-four unit tests cover the
notebook identities, the D-frame as `R(0, ψ)` about the entry midpoint, the
isometry and the reproduction of the file's `*_trans` / `*_local` columns.
`query/frame_sql.py` is the same element as SQL: one `fr` CTE per scan,
joined to the lattice ordinals, so the D-frame and both per-shower scans
transform inside DuckDB on one code path. The canonical tests passed
unchanged, bit for bit.

**3.2 The anchor.** `anchor=backprojected|p0` on `frame=canonical`, a radio
under *Translated*, the hash key `anchor`, the payload fields
`frame.anchor` / `anchor_choice` / `anchor_residual`, the drawer sentence,
the caption and a `canonical_p0` file-name token. Measured on production
`hits_all_models.csv`: δ median 46.5 mm (A) / 45.2 mm (B), p90 133.5 /
132.6 mm, 9,620 / 9,382 of 20,268 showers more than one cell footprint
apart. The default stays the back-projected centroid: P₀ does not land
closer to the entrance-slab centroid than the back-projection does, and the
README records the number either way.

**3.5 G1.** `ingest/frame_checks.py: p0_definition_residual` recomputes P₀
from the archive (first populated layer, energy-weighted centroid, 'A+B'
cells on both sides) and `verify.py` fails above 0.01 mm on a file the
sanitiser left whole, warns on one it trimmed (a removed first-layer cell
moves the centroid and the check can then only say "unconfirmed"); the
anchor residual δ joins the report as a notice.

**3.3 The Event Inspector.** `query/event_inspector.py` + `api/routes_event.py`
(`GET /api/event`, `GET /api/event/pick`), `grid/footprint.py` (exact box
overlap and rotated sub-deposits for one event's cells in NumPy),
`stats/shape.py` (the principal axis). Client: `panels/frame_grid.js` (the
3 × 3 grid of cards, charts created on first show), `event_inspector.js`
(the picker and the pinned event in the link, `#event=…&shower=…`),
`ProjectionPanel` learned a `window` distinct from its raster extent and
3-D `marks` projected per panel (`marks.js: projectMarks`, the ✕ marker),
`panel_notes.js: eventNotes`, the `GeV/mm²` unit on the ramp and in the
readout, the `ev<n><A|B>` file-name token. Tests: the server module
(energy conservation in all nine panels, the residual, the computed source,
one ramp, the window rule, the marks, the principal axis, the footprints,
the neighbours, the pick rule, 404, the budget), Node tests of the
projection of marks, the state keys, the notes and the file name, and a
Chromium test of the nine isometric panels sharing one window, the picker,
the link, the drawer, the readout and the plot-only export.

**3.4 Compare frames.** A sidebar checkbox (`#compare=true`) that issues the
three `/api/projections` requests and renders them into the same grid
component, each row that frame's own response with its own notes; a browser
test covers it.

**Deviations from the plan.**

- The inspector is drawn *per shower* with a radio, not side by side: two
  nine-panel figures do not fit one screen, and the row label names the
  shower.
- The inspector replaces the whole 2 × 2 grid while an event is pinned
  (the status bar and the sidebar stay), rather than living in a drawer; a
  pinned event takes precedence over the comparison.
- "Pick for me" takes the notebook's seed first and the next seed per
  click, so repeated picks walk different events while each stays
  reproducible; the response states the seed.
- The colour is the projected energy *surface density* in GeV/mm², not
  energy per cell: the lattice cells and the 20 mm bins have different
  areas, and one ramp over nine panels must compare like with like. The
  floor is the 1st percentile of the shower's positive lattice-cell
  densities, the top its brightest bin anywhere.
- The marks are projected on the client from 3-D lines and points, so the
  nine panels cannot disagree about where a direction goes.
- 3.6 (a second, single-shower input schema) was not started; it is a
  separate piece of work, and the roadmap document places it.
