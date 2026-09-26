"""The five display channels on the laboratory and canonical paths.

Scales and code layouts per channel, conservation of the energy-weighted CAM
sums against a direct scan of the archived hits, and the /api/projections
parameter contract (coord_system / model / channel, the deprecated mode alias).
"""

from __future__ import annotations

import pytest

from calosrv.db import archive, ddl
from calosrv.encode import quantize
from calosrv.grid.resolution import MODE_CONTINUOUS, MODE_NATIVE, plan_resolution
from calosrv.query import density, filters, panels, projections

CAM_CHANNELS = ("gradcam", "gradcam_energy", "shapcam", "shapcam_energy")


def _hit_sums(cursor, ingested, model: str, coord: str, slab_iz: int, slab: bool):
    """Direct sums over the archived hits: E*GradCAM, E*Shap+, E*Shap-."""
    hits = archive.relation(ingested["settings"], ingested["table"])
    frame = ddl.NETWORK_FRAME[coord]
    gc = ddl.csv_model_column(model, frame, "gradcam")
    sc = ddl.csv_model_column(model, frame, "shapcam")
    where = ""
    if slab:
        # The laboratory entrance slab: the first slab_iz + 1 populated layers.
        where = (f"WHERE z <= (SELECT max(z) FROM (SELECT DISTINCT z FROM {hits} "
                 f"ORDER BY z LIMIT {slab_iz + 1}))")
    return cursor.execute(
        f"SELECT sum(energy * CAST({gc} AS DOUBLE)), "
        f"sum(energy * greatest(CAST({sc} AS DOUBLE), 0)), "
        f"sum(energy * least(CAST({sc} AS DOUBLE), 0)) FROM {hits} {where}"
    ).fetchone()


@pytest.fixture(scope="module")
def lab_bundles(ingested):
    from calosrv.db import registry

    with ingested["database"].read_cursor() as con:
        record = registry.require_ready(con, ingested["table"])
        spec = filters.build(record)
        return {m: projections.fetch_native(con, record, spec, model=m) for m in ddl.MODELS}


@pytest.mark.parametrize("model", ddl.MODELS)
@pytest.mark.parametrize("display,r", [(MODE_NATIVE, 150), (MODE_CONTINUOUS, 50),
                                       (MODE_CONTINUOUS, 150), (MODE_CONTINUOUS, 300),
                                       (MODE_CONTINUOUS, 400)])
def test_lab_energy_weighted_cam_is_conserved(cursor, ingested, record, lab_bundles, model, display, r):
    plan = plan_resolution(record.lattice, display, r)
    slab_iz = record.lattice.slab_iz
    for channel in ("gradcam_energy", "shapcam_energy"):
        rendered = panels.render_all(lab_bundles[model], plan, channel=channel)
        for name, slab in (("xy", True), ("yz", False), ("xz", False)):
            eg, esp, esn = _hit_sums(cursor, ingested, model, "lab", slab_iz, slab)
            payload = rendered[name]
            if channel == "gradcam_energy":
                assert payload["total"] == pytest.approx(eg, rel=1e-9), (name, display, r)
            else:
                scale = payload["scale"]
                assert scale["positive_total"] == pytest.approx(esp, rel=1e-9), name
                assert scale["negative_total"] == pytest.approx(esn, rel=1e-9), name
                assert payload["total"] == pytest.approx(esp + esn, rel=1e-9, abs=1e-15), name


def test_lab_channel_scales_follow_the_contract(record, lab_bundles):
    plan = plan_resolution(record.lattice, MODE_NATIVE, 150)
    bundle = lab_bundles["energy"]
    gradcam = panels.render_all(bundle, plan, channel="gradcam")["xy"]
    assert (gradcam["scale"]["scale"], gradcam["scale"]["vmin"], gradcam["scale"]["vmax"]) == ("linear", 0.0, 1.0)
    assert gradcam["scale"]["quantity"] == "gradcam"
    assert gradcam["scale"]["clipped_low"] == gradcam["scale"]["clipped_high"] == 0

    shap = panels.render_all(bundle, plan, channel="shapcam")["xy"]
    assert (shap["scale"]["scale"], shap["scale"]["vmin"], shap["scale"]["vmax"]) == ("linear", -1.0, 1.0)
    assert shap["scale"]["diverging"] is True and shap["scale"]["unit"] == "attribution"

    ge = panels.render_all(bundle, plan, channel="gradcam_energy")
    assert ge["xy"]["scale"]["scale"] == "log10" and ge["xy"]["scale"]["vmin"] == -3.0
    assert ge["xy"]["scale"]["floor"] == "transparent" and ge["xy"]["scale"]["ref_unit"] == "GeV"
    assert ge["xy"]["below_code"] == 1 and ge["xy"]["min_code"] == 2
    assert ge["yz"]["scale"]["ref"] == ge["xz"]["scale"]["ref"], "depth panels share one peak"
    assert ge["yz"]["scale"]["shared_with"] == "yz+xz"

    se = panels.render_all(bundle, plan, channel="shapcam_energy")["xz"]
    assert se["scale"]["scale"] == "signed_log10" and se["scale"]["diverging"] is True
    assert se["split_code"] == se["scale"]["split_code"] == quantize.SPLIT_CODE == 129
    assert se["min_code"] == 2 and se["below_code"] == 1
    assert se["topk_unit"] == "GeV"
    assert any(t["value"] < 0 for t in se["topk"]), "signed top-k keeps negative extremes"


def test_the_signed_log_code_layout_round_trips():
    import numpy as np

    ratio = np.array([[-1.0, -1e-3, -2e-4, 0.0, 2e-4, 1e-3, 1.0, 0.03]])
    populated = np.ones(ratio.shape, dtype=bool)
    populated[0, 3] = True
    codes = quantize.quantize_signed_log(ratio, populated, 3.0)
    assert codes.tolist() == [[2, 128, 1, 1, 1, 129, 255, int(codes[0, 7])]]
    back = quantize.dequantize_signed_log(codes, 3.0)
    assert back[0, 0] == pytest.approx(-1.0) and back[0, 6] == pytest.approx(1.0)
    assert back[0, 1] == pytest.approx(-1e-3) and back[0, 5] == pytest.approx(1e-3)
    assert back[0, 7] == pytest.approx(0.03, rel=0.03)
    empty = quantize.quantize_signed_log(ratio, np.zeros(ratio.shape, dtype=bool), 3.0)
    assert (empty == 0).all()


def test_a_populated_bin_with_zero_attention_is_below_the_floor_not_empty():
    import numpy as np
    from calosrv.encode import scale as scale_mod

    ratio = np.array([[0.0, 0.5, np.nan]])
    populated = np.array([[True, True, False]])
    scale = scale_mod.extensive_cam_scale(ratio, populated, 2.0, "GeV", "gradcam_energy")
    codes = quantize.quantize(ratio, scale, below_code=1, populated_mask=populated)
    assert codes.tolist()[0][0] == 1 and codes.tolist()[0][2] == 0 and codes.tolist()[0][1] > 1


# ------------------------------------------------------------ canonical --


@pytest.mark.parametrize("model", ddl.MODELS)
def test_canonical_energy_weighted_cam_is_conserved_on_the_raw_grid(cursor, ingested, record, model):
    from calosrv.api import frame_canonical
    from calosrv.models.common import Timer

    spec = filters.build(record)
    eg, esp, esn = _hit_sums(cursor, ingested, model, "lab", record.lattice.slab_iz, slab=False)
    for channel, expected in (("gradcam_energy", eg), ("shapcam_energy", esp + esn)):
        for display in (MODE_NATIVE, MODE_CONTINUOUS):
            body = frame_canonical.build_response(
                cursor, record, spec, ingested["settings"], resolution=150, display=display,
                channel=channel, weighting="energy", rho_norm="selection", preview=False,
                timer=Timer(), model=model,
            )
            for name in ("yz", "xz"):
                panel = body["panels"][name]
                inside_plus_outside = panel["cam_total_all"] + panel["cam_total_outside_grid"]
                assert inside_plus_outside == pytest.approx(
                    expected, rel=1e-9, abs=1e-15), (channel, display, name)
            assert body["meta"]["model"] == model and body["meta"]["cam"]["model"] == model


def test_a_signed_mask_reports_the_masked_value_of_largest_magnitude():
    """Shap-CAM: a hidden full-scale negative attribution must not read as 'modest'."""
    import numpy as np

    attention = np.array([[0.01, -1.0], [0.3, np.nan]])
    mask = np.array([[True, True], [False, True]])
    hits = np.ones_like(attention)
    signed = density._attention_mask(mask, attention, hits, False, 3.0, signed=True, what="attribution")
    assert signed["max_attention"] == -1.0 and signed["max_is_magnitude"] is True
    assert "attribution is not drawn" in signed["rule"]
    plain = density._attention_mask(mask, attention, hits, False, 3.0)
    assert plain["max_attention"] == 0.01 and plain["max_is_magnitude"] is False


@pytest.mark.parametrize("builder", ["canonical", "trans"])
@pytest.mark.parametrize("rho_norm", ["selection", "dataset"])
@pytest.mark.parametrize("channel", ["density", "gradcam", "shapcam", "gradcam_energy", "shapcam_energy"])
def test_the_colour_reference_notice_names_each_channels_own_reference(
    cursor, ingested, record, builder, rho_norm, channel,
):
    """Only density follows rho_norm: a CAM panel must not claim a peak-density reference."""
    from calosrv.api import frame_canonical, frame_shower
    from calosrv.models.common import Timer

    common = dict(resolution=150, display=MODE_CONTINUOUS, channel=channel, weighting="energy",
                  rho_norm=rho_norm, preview=False, timer=Timer(), model="segmentation")
    spec = filters.build(record)
    if builder == "canonical":
        body = frame_canonical.build_response(cursor, record, spec, ingested["settings"], **common)
    else:
        body = frame_shower.build_response(cursor, record, spec, ingested["settings"], kind="trans", **common)
    text = " ".join(n["text"] for n in body["meta"]["notices"])
    if channel != "density":
        assert "peak density on the raw" not in text
        assert "whole dataset's raw 20 mm-grid peak" not in text
    if channel == "density":
        assert ("own peak density on the raw" in text) == (rho_norm == "selection")
    elif channel.endswith("_energy"):
        cam = "Grad-CAM" if channel.startswith("gradcam") else "Shap-CAM"
        assert f"own peak of Σ E·{cam} on the raw" in text
        assert ("density channel only" in text) == (rho_norm == "dataset")
    else:
        bounds = "0 to 1" if channel == "gradcam" else "−1 to +1"
        assert f"fixed {bounds} scale" in text
        scope = "this selection's" if rho_norm == "selection" else "the whole dataset's"
        assert f"10⁻³ of {scope} raw-grid peak density" in text
