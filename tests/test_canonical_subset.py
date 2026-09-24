"""Canonical-frame behaviour at production scale, on a subset of the real data.

Runs only when ``CALOSRV_TEST_SUBSET_CSV`` points at a 29-column CSV cut from
the production file (a few hundred to a few thousand events); see plan.md,
Verification step 2, for how to produce one from ``data/calorimeter.duckdb``.
The two-event demonstration file cannot exercise the sub-cell factor budget,
the payload guard on a wide window, the dataset-wide density reference or the
coherence of the ensemble axes across separation slices.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from calosrv.db import naming, registry
from calosrv.db.naming import quote
from calosrv.grid import frame
from calosrv.grid.resolution import MODE_CONTINUOUS, MODE_NATIVE
from calosrv.query import canonical, canonical_cache, density, filters, stagger, window

SUBSET_CSV = os.environ.get("CALOSRV_TEST_SUBSET_CSV", "")
TABLE = "subset_experiment"

pytestmark = pytest.mark.skipif(
    not SUBSET_CSV or not Path(SUBSET_CSV).is_file(),
    reason="set CALOSRV_TEST_SUBSET_CSV to a production subset CSV to run",
)


@pytest.fixture(scope="module")
def subset(ingested):
    """Ingest the subset beside the demonstration experiment, once per module."""
    from calosrv.ingest import derive_events, derive_proj, lattice_fit, load

    database = ingested["database"]
    with database.write_lock() as con:
        if registry.get_experiment(con, TABLE) is None:
            record = registry.ExperimentRecord(table_name=TABLE)
            record.status = registry.STATUS_INGESTING
            registry.upsert(con, record)
            n_hits = load.load_csv(con, TABLE, Path(SUBSET_CSV))
            lattice = lattice_fit.measure_lattice(con, naming.hit_table(TABLE))
            bounds = lattice_fit.measure_bounds(con, naming.hit_table(TABLE))
            record.lattice = lattice
            registry.upsert(con, record)
            derive_proj.build(con, TABLE, lattice)
            n_events = derive_events.build(con, TABLE)
            cell_max, cell_p999 = derive_proj.measure_color_anchors(con, TABLE, lattice.slab_iz)
            derive_proj.build_sample(con, TABLE, 10.0)
            record.n_hits, record.n_events = n_hits, n_events
            record.n_events_no_d = bounds["n_events_no_d"]
            record.e1_min, record.e1_max = bounds["e1_min"], bounds["e1_max"]
            record.e2_min, record.e2_max = bounds["e2_min"], bounds["e2_max"]
            record.d_min, record.d_max = bounds["d_min"], bounds["d_max"]
            record.overlaps = bounds["overlaps"]
            record.cell_e_max, record.cell_e_p999 = cell_max, cell_p999
            record.has_sample = True
            record.status = registry.STATUS_READY
            registry.upsert(con, record)
    with database.read_cursor() as con:
        yield {"database": database, "record": registry.require_ready(con, TABLE),
               "settings": ingested["settings"]}


def _bundle(con, record, spec):
    stats = canonical.frame_statistics(con, record, spec)
    footprint = canonical.cell_footprint(con, record)
    grid = frame.plan_window(stats.d_entry_max, stats.theta_max, record.lattice)
    k = frame.choose_subsample(stats.n_hits)
    return canonical.fetch_canonical(con, record, spec, stats, grid, k, footprint), stats, grid, k


def test_footprint_is_the_production_cell(subset):
    with subset["database"].read_cursor() as con:
        w_x, w_y = canonical.cell_footprint(con, subset["record"])
    assert w_x == pytest.approx(48.27, abs=0.05)
    assert w_y == pytest.approx(48.6, abs=0.05)


def test_no_comb_at_the_budgeted_factor_and_energy_conserved(subset):
    record = subset["record"]
    with subset["database"].read_cursor() as con:
        spec = filters.build(record)
        bundle, stats, grid, k = _bundle(con, record, spec)
        proj = quote(naming.proj_table(TABLE))
        event = quote(naming.event_table(TABLE))
        defined = " AND ".join(f"e.{c} IS NOT NULL" for c in canonical._FRAME_COLUMNS)
        expected = float(con.execute(
            f"SELECT sum(p.energy) FROM {proj} p JOIN {event} e USING (event_number) WHERE {defined}"
        ).fetchone()[0])
    assert k >= frame.MIN_SUBSAMPLE
    assert bundle.total_energy + bundle.energy_outside == pytest.approx(expected, rel=1e-9)
    assert bundle.energy_fraction_outside < 1e-3
    comb = stagger.detect(bundle.xy.planes["e"])
    assert comb.lag1 is not None
    assert not comb.staggered, f"footprint comb measured at k={k}: lag-1 {comb.lag1:.3f}"


@pytest.mark.parametrize("mode,resolution", [(MODE_NATIVE, 150), (MODE_CONTINUOUS, 150), (MODE_CONTINUOUS, 400)])
def test_payload_budget_holds_on_a_wide_window(subset, mode, resolution):
    record = subset["record"]
    with subset["database"].read_cursor() as con:
        bundle, *_ = _bundle(con, record, filters.build(record))
    fit = window.fit_window(bundle)
    out = density.render_canonical(bundle, fit, mode, resolution)
    assert len(json.dumps(out["panels"]).encode()) < 100_000
    assert out["resolution"]["r_z"] == bundle.grid.n_z


def test_dataset_reference_is_the_full_selection_peak(subset):
    record = subset["record"]
    with subset["database"].read_cursor() as con:
        footprint = canonical.cell_footprint(con, record)
        reference = canonical_cache.dataset_reference(con, record, subset["settings"], footprint)
        bundle, *_ = _bundle(con, record, filters.build(record))
    peaks = density.selection_peaks(bundle)
    assert reference["xy"] == pytest.approx(peaks["xy"], rel=1e-9)
    assert reference["depth"] == pytest.approx(peaks["depth"], rel=1e-9)
    assert reference["xy"] > 0 and reference["depth"] > 0


def test_direction_coherence_grows_with_separation(subset):
    """Well-separated showers diverge along ±x′; overlapping ones do not."""
    record = subset["record"]
    event = quote(naming.event_table(TABLE))
    with subset["database"].read_cursor() as con:
        # Slices are the subset's own D quartiles: a cut of the production file
        # need not contain the smallest separations.
        q25, q75 = con.execute(
            f"SELECT quantile_cont(d, 0.25), quantile_cont(d, 0.75) FROM {event} WHERE d IS NOT NULL"
        ).fetchone()
        wide = canonical.frame_statistics(con, record, filters.build(record, d_min=float(q75)))
        narrow = canonical.frame_statistics(con, record, filters.build(record, d_max=float(q25)))
    if wide.n_events < 20 or narrow.n_events < 20:
        pytest.skip("subset too small for both separation slices")
    assert wide.a.resultant_transverse > narrow.a.resultant_transverse
    assert wide.a.slope_mean[0] < 0 < wide.b.slope_mean[0], "A drifts to −x′, B to +x′"
    assert wide.a.rayleigh_p < 1e-3


def test_anchors_sit_where_the_showers_enter(subset):
    """Per-event canonical slab centroids scatter about ∓D_entry/2 by well under a cell."""
    record = subset["record"]
    lat = record.lattice
    proj = quote(naming.proj_table(TABLE))
    event = quote(naming.event_table(TABLE))
    with subset["database"].read_cursor() as con:
        rows = con.execute(
            f"""
            WITH ev AS (
                SELECT event_number, {canonical._ENTRY_SQL}
                FROM {event} WHERE {canonical._FRAME_DEFINED}
            ), fr AS (
                SELECT event_number, (xa + xb) / 2 AS x0, (ya + yb) / 2 AS y0,
                       cos(atan2(yb - ya, xb - xa)) AS c, sin(atan2(yb - ya, xb - xa)) AS s,
                       sqrt((xb - xa) * (xb - xa) + (yb - ya) * (yb - ya)) AS d_entry
                FROM ev
            ), pts AS (
                SELECT p.event_number, p.energy, p.fa_true, f.d_entry,
                       list_extract($xc, p.ix + 1) - f.x0 AS xt,
                       list_extract($yc, p.iy + 1) - f.y0 AS yt, f.c, f.s
                FROM {proj} p JOIN fr f USING (event_number) WHERE p.iz <= {lat.slab_iz}
            )
            SELECT max(d_entry),
                   sum((c * xt + s * yt) * energy * fa_true) / sum(energy * fa_true),
                   sum((-s * xt + c * yt) * energy * fa_true) / sum(energy * fa_true)
            FROM pts GROUP BY event_number
            """,
            {"zf": float(lat.z.lo), "xc": [float(v) for v in lat.x.coords],
             "yc": [float(v) for v in lat.y.coords]},
        ).fetchall()
    arr = np.array(
        [r for r in rows if all(v is not None for v in r)], dtype=np.float64
    )
    arr = arr[np.isfinite(arr).all(axis=1)]
    assert arr.shape[0] > 100, "the subset must hold events with shower-A energy in the slab"
    residual = np.hypot(arr[:, 1] + arr[:, 0] / 2, arr[:, 2])
    assert np.median(residual) < 120.0, f"median anchor residual {np.median(residual):.0f} mm"
    assert abs(np.median(arr[:, 2])) < 10.0, "showers must lie on the y′ = 0 plane"
