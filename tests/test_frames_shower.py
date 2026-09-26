"""The translated and local frames: every shower co-registered on its own entry point.

The exact box-overlap splat against a brute-force overlap, the local frame's
rotated sub-deposits against a NumPy re-implementation, conservation of energy
and of every energy-weighted CAM sum against the archived hits, the single
scan, and the response contract (frame block, centroids, overlays, symbols).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from calosrv.db import archive, ddl, naming
from calosrv.db.naming import quote
from calosrv.grid import frame as frame_mod
from calosrv.query import canonical, density, filters, shower_frames

KINDS = ("trans", "local")


def _overlap(lo: np.ndarray, hi: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Brute-force overlap fraction of each box [lo, hi] with each bin, ``(boxes, bins)``."""
    left = np.maximum(lo[:, None], edges[None, :-1])
    right = np.minimum(hi[:, None], edges[None, 1:])
    return np.clip(right - left, 0.0, None) / (hi - lo)[:, None]


# ------------------------------------------------------- box overlap maths --


@pytest.mark.parametrize("width", [48.27, 48.6, 40.0, 21.3, 60.0])
def test_the_box_overlap_operator_is_the_exact_area_overlap(width):
    """Moments expanded by (A, B) equal the brute-force overlap, including the
    weight that falls off either end of the grid."""
    rng = np.random.default_rng(7)
    pitch, n_bins, half = 20.0, 30, 300.0
    centres = rng.uniform(-half - width, half + width, 20_000)
    values = rng.uniform(0.1, 2.0, centres.size)
    u = (centres - 0.5 * width + half) / pitch
    j0 = np.floor(u)
    phi = u - j0
    r = width / pitch - math.floor(width / pitch)
    key = (2 * j0 + (phi >= 1.0 - r)).astype(np.int64)
    lo, hi = int(key.min()), int(key.max())
    a_mat, b_mat = shower_frames.box_overlap_operator(n_bins, width, pitch, lo, hi)
    m0 = np.bincount(key - lo, values, hi - lo + 1)
    m1 = np.bincount(key - lo, values * phi, hi - lo + 1)
    splat = a_mat @ m0 + b_mat @ m1

    edges = np.linspace(-half, half, n_bins + 1)
    brute = (values[:, None] * _overlap(centres - 0.5 * width, centres + 0.5 * width, edges)).sum(0)
    np.testing.assert_allclose(splat, brute, rtol=1e-12, atol=1e-9)

    # Each box's weights sum to one when it lies wholly inside.
    inside = (centres - 0.5 * width >= -half) & (centres + 0.5 * width <= half)
    full = a_mat[:, key[inside] - lo] + b_mat[:, key[inside] - lo] * phi[inside]
    np.testing.assert_allclose(full.sum(0), 1.0, rtol=1e-12)
    assert (full >= -1e-15).all()


# ------------------------------------------------------------- fixtures --


@pytest.fixture(scope="module")
def shower(ingested):
    from calosrv.db import registry

    database, settings = ingested["database"], ingested["settings"]
    with database.read_cursor() as con:
        record = registry.require_ready(con, ingested["table"])
        spec = filters.build(record)
        footprint = canonical.cell_footprint(con, record)
        bundles = {}
        for kind in KINDS:
            for model in ddl.MODELS:
                bundles[kind, model] = shower_frames.bundle_for(
                    con, record, spec, settings, kind, footprint, False, 100.0, model)
    return {"record": record, "spec": spec, "footprint": footprint, "bundles": bundles,
            "settings": settings}


def _proj_rows(cursor, record, columns: str):
    proj = quote(naming.proj_table(record.table_name))
    return cursor.execute(f"SELECT {columns} FROM {proj} WHERE d IS NOT NULL ORDER BY ALL").fetchnumpy()


# ------------------------------------------------------------ translated --


def test_the_translated_panels_equal_a_brute_force_footprint_overlap(cursor, shower):
    bundle, _, grid, _, _ = shower["bundles"]["trans", "segmentation"]
    record = shower["record"]
    wx, wy = shower["footprint"]
    rows = _proj_rows(cursor, record, "xt, yt, kt, energy")
    xt = np.asarray(rows["xt"], dtype=np.float64)
    yt = np.asarray(rows["yt"], dtype=np.float64)
    kt = np.asarray(rows["kt"], dtype=np.int64)
    e = np.asarray(rows["energy"], dtype=np.float64)
    inside = ((xt - wx / 2 >= -grid.half_x) & (xt + wx / 2 <= grid.half_x)
              & (yt - wy / 2 >= -grid.half_y) & (yt + wy / 2 <= grid.half_y) & (kt < grid.n_z))
    ox = _overlap(xt - wx / 2, xt + wx / 2, grid.x_edges)
    oy = _overlap(yt - wy / 2, yt + wy / 2, grid.y_edges)
    slab = inside & (kt <= record.lattice.slab_iz)
    xy = np.einsum("h,hy,hx->yx", e[slab], oy[slab], ox[slab])
    xz = np.zeros(grid.shape_xz)
    yz = np.zeros(grid.shape_yz)
    for layer in range(grid.n_z):
        sel = inside & (kt == layer)
        xz[:, layer] = (e[sel, None] * ox[sel]).sum(0)
        yz[:, layer] = (e[sel, None] * oy[sel]).sum(0)
    scale = e.sum()
    np.testing.assert_allclose(bundle.xy.planes["e"], xy, rtol=0, atol=1e-12 * scale)
    np.testing.assert_allclose(bundle.xz.planes["e"], xz, rtol=0, atol=1e-12 * scale)
    np.testing.assert_allclose(bundle.yz.planes["e"], yz, rtol=0, atol=1e-12 * scale)
    assert bundle.energy_outside == pytest.approx(float(e[~inside].sum()), rel=1e-9, abs=1e-15)
    # The joint outside rule: every panel holds the same hits.
    assert bundle.yz.planes["e"].sum() == pytest.approx(bundle.xz.planes["e"].sum(), rel=1e-12)


# ----------------------------------------------------------------- local --


def test_the_local_panels_equal_the_rotated_sub_deposits_in_numpy(cursor, shower):
    record = shower["record"]
    bundle, _, grid, k, _ = shower["bundles"]["local", "segmentation"]
    wx, wy = shower["footprint"]
    wz = record.frame_bounds.layer_pitch_mm
    proj = quote(naming.proj_table(record.table_name))
    event = quote(naming.event_table(record.table_name))
    rows = cursor.execute(
        f"""SELECT p.xl, p.yl, p.zl, p.kt, p.energy,
                   CAST(CASE WHEN p.org = 0 THEN e.theta_a ELSE e.theta_b END AS DOUBLE) AS t,
                   CAST(CASE WHEN p.org = 0 THEN e.phi_a ELSE e.phi_b END AS DOUBLE) AS f
            FROM {proj} p JOIN {event} e USING (event_number) WHERE e.d IS NOT NULL"""
    ).fetchnumpy()
    xl, yl, zl = (np.asarray(rows[c], dtype=np.float64) for c in ("xl", "yl", "zl"))
    t, f = np.asarray(rows["t"]), np.asarray(rows["f"])
    e = np.asarray(rows["energy"], dtype=np.float64)
    kt = np.asarray(rows["kt"], dtype=np.int64)
    k_z = bundle.k_z
    offsets = [((a + 0.5) / k - 0.5, (b + 0.5) / k - 0.5, (c + 0.5) / k_z - 0.5)
               for a in range(k) for b in range(k) for c in range(k_z)]
    ct, st, cf, sf = np.cos(t), np.sin(t), np.cos(f), np.sin(f)
    z_edges = grid.axis("z").edges
    xz = np.zeros(grid.shape_xz)
    xy = np.zeros(grid.shape_xy)
    for fx, fy, fz in offsets:
        ox, oy, oz = fx * wx, fy * wy, fz * wz
        xs = xl + ct * cf * ox + ct * sf * oy - st * oz
        ys = yl - sf * ox + cf * oy
        zs = zl + st * cf * ox + st * sf * oy + ct * oz
        jx = np.floor((xs + grid.half_x) / grid.pitch).astype(int)
        jy = np.floor((ys + grid.half_y) / grid.pitch).astype(int)
        jz = np.floor((zs - z_edges[0]) / wz).astype(int)
        ok = (jx >= 0) & (jx < grid.n_x) & (jy >= 0) & (jy < grid.n_y) & (jz >= 0) & (jz < grid.n_z)
        np.add.at(xz, (jx[ok], jz[ok]), e[ok] / len(offsets))
        slab = ok & (kt <= record.lattice.slab_iz)
        np.add.at(xy, (jy[slab], jx[slab]), e[slab] / len(offsets))
    scale = e.sum()
    np.testing.assert_allclose(bundle.xz.planes["e"], xz, rtol=0, atol=1e-12 * scale)
    np.testing.assert_allclose(bundle.xy.planes["e"], xy, rtol=0, atol=1e-12 * scale)
    assert k >= frame_mod.MIN_SUBSAMPLE


@pytest.mark.parametrize("k,k_z", [(2, 1), (2, 2), (3, 2)])
def test_local_energy_is_conserved_for_any_sub_deposit_factor(cursor, shower, k, k_z):
    record, spec = shower["record"], shower["spec"]
    _, stats, grid, _, _ = shower["bundles"]["local", "segmentation"]
    bundle = shower_frames.fetch(cursor, record, spec, stats, grid, "local", shower["footprint"], k, k_z)
    proj = quote(naming.proj_table(record.table_name))
    expected, n = cursor.execute(f"SELECT sum(energy), count(*) FROM {proj} WHERE d IS NOT NULL").fetchone()
    assert bundle.total_energy + bundle.energy_outside == pytest.approx(expected, rel=1e-12)
    assert bundle.yz.planes["e"].sum() == pytest.approx(bundle.xz.planes["e"].sum(), rel=1e-12)
    assert bundle.n_hits == n


# --------------------------------------------------------- conservation --


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("model", ddl.MODELS)
def test_energy_weighted_cam_sums_match_the_archived_hits(cursor, ingested, shower, kind, model):
    """M-C for the per-shower frames: E x Grad-CAM, and the positive and
    negative parts of E x Shap-CAM separately, inside + outside the grid,
    equal the archive's own sums to 1e-9."""
    bundle = shower["bundles"][kind, model][0]
    hits = archive.relation(ingested["settings"], ingested["table"])
    frame = ddl.NETWORK_FRAME[kind]
    gc = ddl.csv_model_column(model, frame, "gradcam")
    sc = ddl.csv_model_column(model, frame, "shapcam")
    expected = cursor.execute(
        f"SELECT sum(energy), sum(energy * CAST({gc} AS DOUBLE)), "
        f"sum(energy * greatest(CAST({sc} AS DOUBLE), 0)), "
        f"sum(energy * least(CAST({sc} AS DOUBLE), 0)) FROM {hits} "
        "WHERE centroid_AB_distance IS NOT NULL"
    ).fetchone()
    got = [bundle.total_energy + bundle.energy_outside]
    for plane in ("eg", "esp", "esn"):
        got.append(float(bundle.xz.planes[plane].sum()) + bundle.plane_outside[plane])
    for value, reference in zip(got, expected):
        assert value == pytest.approx(reference, rel=1e-9, abs=1e-15)


def _bundle_of(shower, cursor, kind):
    if kind in KINDS:
        return shower["bundles"][kind, "energy"][0]
    from calosrv.query import canonical_cache

    return canonical_cache.bundle_for(cursor, shower["record"], shower["spec"], shower["settings"],
                                      canonical.cell_footprint(cursor, shower["record"]), False,
                                      100.0, "energy")[0]


@pytest.mark.parametrize("kind", [*KINDS, "canonical"])
@pytest.mark.parametrize("display", ["native", "continuous"])
@pytest.mark.parametrize("r", [50, 150, 300, 400])
def test_the_rendered_cam_parts_equal_the_raw_planes_in_the_window(cursor, shower, kind, display, r):
    """What is drawn conserves each part: at every R and in both displays, the
    rendered Σ E·Grad-CAM and the positive and negative Σ E·Shap-CAM equal the
    raw planes weighted by the render's own inside-weights (the window crop and
    the kernel's reach), sign for sign."""
    from calosrv.query import reconstruct, window

    bundle = _bundle_of(shower, cursor, kind)
    fit = window.fit_window(bundle)
    kernel = reconstruct.choose_kernel(display, bundle.n_events)
    for channel in ("gradcam_energy", "shapcam_energy"):
        out = density.render_canonical(bundle, fit, display, r, channel, kernel=kernel,
                                       symbols=getattr(bundle, "symbols", None))
        guard = out["guard"]
        plan = density.plan_canonical(fit, bundle.grid, display, guard["r"], guard["merge"], kernel,
                                      max(bundle.footprint), requested=r)
        for name in ("xy", "yz", "xz"):
            panel = out["panels"][name]
            planes = bundle.panel(name).planes
            row_map, col_map = density.axis_maps(bundle, fit.panel(name), plan, name)
            rows = reconstruct.inside_weights(row_map, planes["e"].shape[0])
            cols = reconstruct.inside_weights(col_map, planes["e"].shape[1])
            drawn = {part: float(rows @ planes[part] @ cols) for part in ("eg", "esp", "esn")}
            scale = panel["scale"]
            if channel == "gradcam_energy":
                assert panel["cam_total"] == pytest.approx(drawn["eg"], rel=1e-9, abs=1e-18)
            else:
                assert scale["positive_total"] == pytest.approx(drawn["esp"], rel=1e-9, abs=1e-18)
                assert scale["negative_total"] == pytest.approx(drawn["esn"], rel=1e-9, abs=1e-18)
                assert panel["cam_total"] == pytest.approx(drawn["esp"] + drawn["esn"], rel=1e-9, abs=1e-18)
                if planes["esn"].min() < 0:
                    assert scale["negative_total"] < 0


# ----------------------------------------------------------------- scan --


@pytest.mark.parametrize("kind", KINDS)
def test_each_query_scans_the_projection_table_once(cursor, shower, kind):
    bundle, _, grid, k, _ = shower["bundles"][kind, "segmentation"]
    plan = shower_frames.explain(cursor, shower["record"], shower["spec"], grid, kind,
                                 shower["footprint"], k, bundle.k_z)
    table = naming.proj_table(shower["record"].table_name)
    for part in plan.split("\n----\n"):
        assert part.count(table) == 1


# ----------------------------------------------------------- statistics --


def test_the_statistics_come_from_the_event_table(cursor, shower):
    stats = shower["bundles"]["trans", "segmentation"][1]
    event = quote(naming.event_table(shower["record"].table_name))
    n, hits, cax = cursor.execute(
        f"SELECT count(*), sum(n_hits), avg(cax_t) FROM {event} WHERE d IS NOT NULL").fetchone()
    assert stats.n_events == n and stats.n_hits == hits and stats.n_showers == 2 * n
    assert stats.mean["a"]["x"].mean == pytest.approx(cax, rel=1e-6)
    assert stats.phi_resultant["a"] is None or 0 <= stats.phi_resultant["a"] <= 1



@pytest.mark.parametrize("kind", KINDS)
def test_the_frame_mean_interval_is_student_t_on_the_ddof1_sd(cursor, shower, kind):
    """The whisker is t_{0.975, n-1} SD / sqrt(n) of the per-event centroids, SD with ddof = 1."""
    from calosrv.api import frame_shower
    from calosrv.stats import gaussian

    stats = shower["bundles"][kind, "segmentation"][1]
    mean = frame_shower._frame_mean(stats, kind)
    event = quote(naming.event_table(shower["record"].table_name))
    suffix = "_t" if kind == frame_mod.KIND_TRANS else "_l"
    for s in "ab":
        for axis in "xyz":
            column = f"c{s}{axis}{suffix}"
            values = cursor.execute(
                f"SELECT CAST({column} AS DOUBLE) AS v FROM {event} "
                f"WHERE d IS NOT NULL AND {column} IS NOT NULL").fetchnumpy()["v"]
            v = np.asarray(values, dtype=float)
            n = v.size
            assert n >= 2
            sd = float(np.std(v, ddof=1))
            assert mean[s][axis] == pytest.approx(float(v.mean()), rel=1e-9, abs=1e-9)
            assert mean["sd"][s][axis] == pytest.approx(sd, rel=1e-9)
            assert mean["ci95_half"][s][axis] == pytest.approx(
                gaussian.t_quantile_975(n - 1) * sd / math.sqrt(n), rel=1e-9)
    assert mean["n"] == stats.n_events and "Mean per-event centroid" in mean["label"]


@pytest.mark.parametrize("kind", KINDS)
def test_a_single_event_marker_is_labelled_as_that_events_own_centroid(cursor, shower, kind):
    from calosrv.api import frame_shower

    record = shower["record"]
    event = quote(naming.event_table(record.table_name))
    d0, d1 = (r[0] for r in cursor.execute(
        f"SELECT DISTINCT d FROM {event} WHERE d IS NOT NULL ORDER BY d LIMIT 2").fetchall())
    one = filters.build(record, d_min=float(d0), d_max=float(d0 + (d1 - d0) / 2))
    stats = shower_frames.shower_statistics(cursor, record, one, kind, "segmentation")
    assert stats.n_events == 1
    mean = frame_shower._frame_mean(stats, kind)
    assert mean["label"].startswith("This single event's own centroid")
    assert "not an ensemble mean" in mean["label"] and mean["dof_note"].startswith("N = 1")

def test_the_grid_is_the_datasets_not_the_selections(cursor, shower):
    record, settings, footprint = shower["record"], shower["settings"], shower["footprint"]
    narrow = filters.build(record, e1_max=float(record.e1_max) * 0.9)
    for kind in KINDS:
        full = shower["bundles"][kind, "segmentation"][2]
        _, _, grid, _, _ = shower_frames.bundle_for(
            cursor, record, narrow, settings, kind, footprint, False, 100.0)
        assert (grid.half_x, grid.half_y, grid.n_z) == (full.half_x, full.half_y, full.n_z)


def test_a_density_bundle_is_reused_across_models(cursor, shower):
    record, settings, footprint = shower["record"], shower["settings"], shower["footprint"]
    bundle, *_, cached = shower_frames.density_bundle_for(
        cursor, record, shower["spec"], settings, "trans", footprint, False, 100.0, "angle")
    assert cached is True
