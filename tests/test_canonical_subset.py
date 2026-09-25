"""Canonical-frame behaviour at production scale, on a subset of the real data.

Runs only when ``CALOSRV_TEST_SUBSET_CSV`` points at a 99-column
``hits_all_models`` CSV cut from the production file (a few hundred to a few
thousand events); ``tests/make_all_models_fixture.py subset`` writes one from
the Parquet archive of a development ingest.
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
    from calosrv.ingest import pipeline

    database = ingested["database"]
    with database.write_lock() as con:
        if registry.get_experiment(con, TABLE) is None:
            pipeline.run_ingest(con, ingested["settings"], TABLE, Path(SUBSET_CSV))
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


def _response(subset, **overrides):
    from calosrv.api import frame_canonical
    from calosrv.models.common import Timer

    record = subset["record"]
    params = dict(
        resolution=150, display=MODE_CONTINUOUS, channel="density", weighting="energy",
        rho_norm="selection", preview=False,
    )
    params.update(overrides)
    spec = params.pop("spec", None) or filters.build(record)
    with subset["database"].read_cursor() as con:
        return frame_canonical.build_response(
            con, record, spec, subset["settings"], timer=Timer(), **params
        )


def test_the_full_selection_response_fits_the_wire_budget(subset):
    """The whole response, envelope included, measured as the route sends it."""
    from calosrv.query import reconstruct

    body = _response(subset)
    assert density.wire_size(body) < 100_000
    expected = reconstruct.choose_kernel(MODE_CONTINUOUS, body["frame"]["n_events"])
    assert body["frame"]["reconstruction"]["kernel"] == expected.name
    native = _response(subset, display=MODE_NATIVE)
    assert density.wire_size(native) < 100_000


def test_a_sampled_continuous_preview_is_approximate_and_fits_the_budget(subset, monkeypatch):
    """A smoke test of the drag preview in Continuous Field at production scale.

    Marked approximate, its sub-cell factor capped, its kernel chosen from the
    event count of the event table - the only count a bundle carries, sampled
    or not - and inside the wire budget.
    """
    from calosrv.query import reconstruct, sampling

    monkeypatch.setattr(sampling, "SAMPLE_THRESHOLD_ROWS", 0)
    body = _response(subset, preview=True)
    assert body["meta"]["exact"] is False
    assert body["frame"]["subsample_k"] <= frame.PREVIEW_MAX_SUBSAMPLE
    n_events = body["frame"]["n_events"]
    record = subset["record"]
    with subset["database"].read_cursor() as con:
        exact = canonical.frame_statistics(con, record, filters.build(record).clamped(record))
    assert n_events == exact.n_events
    expected = reconstruct.choose_kernel(MODE_CONTINUOUS, exact.n_events)
    assert body["frame"]["reconstruction"]["kernel"] == expected.name
    assert density.wire_size(body) < 100_000


def _narrow_slice(subset, n_target=5):
    """A D window holding about ``n_target`` events, from the middle of the subset."""
    record = subset["record"]
    event = quote(naming.event_table(record.table_name))
    with subset["database"].read_cursor() as con:
        d = sorted(row[0] for row in con.execute(f"SELECT d FROM {event} WHERE d IS NOT NULL").fetchall())
    i = len(d) // 2
    return filters.build(record, d_min=float(d[i]), d_max=float(d[i + n_target - 1]))


@pytest.mark.parametrize("resolution", [300, 400, 512])
def test_a_cached_high_resolution_request_stays_inside_the_latency_budget(subset, resolution):
    """Plan section 10.6 at the resolutions the slider reaches, on a narrow slice.

    A narrow slice has a narrow X′Y′ window and so a fine display pitch: every
    guard attempt above the served R is large. Rendering them all, twice, took
    309 ms at R = 400 on the production N = 3 slice. The guard now steps past
    attempts whose rasters alone are over, and the whole-response re-render
    resumes where the first pass stopped.
    """
    spec = _narrow_slice(subset)
    _response(subset, spec=spec)  # warm the canonical cache
    timings, bodies = [], []
    for _ in range(3):
        body = _response(subset, spec=spec, resolution=resolution)
        assert body["meta"]["cached"] is True
        timings.append(body["meta"]["total_ms"])
        bodies.append(body)
    assert float(np.median(timings)) < 100.0, timings
    served = bodies[-1]["meta"]["resolution"]["r_x"]
    at_default = _response(subset, spec=spec)["meta"]["resolution"]["r_x"]
    assert served >= at_default, "asking for more detail must not serve less than the default"
    assert density.wire_size(bodies[-1]) < 100_000


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
                SELECT p.event_number, p.energy, p.fa_true_abs AS fa_true, f.d_entry,
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
