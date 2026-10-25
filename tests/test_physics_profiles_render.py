"""C7 profiles: the payload rendered from given sums, and the NumPy reference the API tests share.

The rendering tests build :class:`calosrv.query.profiles.ProfileSums` by hand,
so they run without a database: the empty selection, the y range and its
clipping disclosure, normalisation closure and the comb verdict.

:func:`reference` is the brute force the API modules hold the route to: it
reads the profile (or layer) rows and the event table directly, builds every
selected shower's dense fractional profile - zeros where a shower never
reached a bin - and computes the mean, SD, cluster-robust Student-t envelope
and the pooled ratio with its event-clustered interval by explicit loops over
showers and events, not from per-bin sums.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

import contract_check
from calosrv.db import ddl, naming
from calosrv.db.naming import quote
from calosrv.db.registry import ExperimentRecord
from calosrv.query import profiles
from calosrv.stats import gaussian
from calosrv.text import signed_hyphens

SHOWER_COLUMNS = {"a": ("e_dep_a", "w_neg_energy_a"), "b": ("e_dep_b", "w_neg_energy_b")}


# ---------------------------------------------------------- the reference --

def reference(con, name: str, showers: list[tuple[int, str]], where: str, params: dict[str, Any],
              axis: str, notebook: bool = False) -> dict[str, Any]:
    """Every selected shower's dense profile on one axis (``w``, ``r`` or ``kt``)."""
    event = quote(naming.event_table(name))
    units: dict[tuple[int, int], float] = {}
    for b, s in showers:
        e_col, neg_col = SHOWER_COLUMNS[s]
        for ev, e, neg in con.execute(
                f"SELECT event_number, {e_col}, coalesce({neg_col}, 0) FROM {event} "
                f"WHERE {where} AND {e_col} > 0", params).fetchall():
            norm = e - neg if notebook else e
            if norm > 1e-12 * e:
                units[(int(ev), b)] = float(norm)
    if axis == "kt":
        rows = con.execute(f"SELECT event_number, shower, kt, e_dep, 0.0 "
                           f"FROM {quote(naming.layers_table(name))}").fetchall()
    else:
        code = ddl.PROFILE_AXIS_W if axis == "w" else ddl.PROFILE_AXIS_R
        rows = con.execute(f"SELECT event_number, shower, bin, e, e_wneg "
                           f"FROM {quote(naming.profiles_table(name))} WHERE axis = {code}").fetchall()
    keys = sorted(units)
    index = {k: i for i, k in enumerate(keys)}
    mine = [r for r in rows if (int(r[0]), int(r[1])) in index]
    lo = min((int(r[2]) for r in mine), default=0)
    hi = max((int(r[2]) for r in mine), default=0)
    numer = np.zeros((len(keys), hi - lo + 1))
    for ev, sh, j, e, e_wneg in mine:
        numer[index[(int(ev), int(sh))], int(j) - lo] += (e - e_wneg) if notebook else e
    norms = np.array([units[k] for k in keys])
    return {"lo": lo, "numer": numer, "norms": norms, "events": np.array([k[0] for k in keys]),
            "e_all": None}


def expected(ref: dict[str, Any], bins: list[int], width_mm: float) -> dict[str, np.ndarray]:
    """Mean, SD, envelope and pooled line on ``bins``, in % per cm, by explicit loops."""
    n_units = ref["numer"].shape[0]
    numer = np.zeros((n_units, len(bins)))
    for i, j in enumerate(bins):
        col = j - ref["lo"]
        if 0 <= col < ref["numer"].shape[1]:
            numer[:, i] = ref["numer"][:, col]
    norms = ref["norms"]
    f = numer / norms[:, None]
    scale = 100.0 * 10.0 / width_mm
    mean = f.mean(axis=0)
    out: dict[str, Any] = {"n": n_units, "mean": mean * scale}
    events = sorted(set(ref["events"].tolist()))
    g = len(events)
    out["g"] = g
    if n_units >= 2:
        out["sd"] = f.std(axis=0, ddof=1) * scale
    if g >= 2:
        where = {e: i for i, e in enumerate(events)}
        c_e = np.zeros((g, len(bins)))
        m_e = np.zeros(g)
        num_e = np.zeros((g, len(bins)))
        den_e = np.zeros(g)
        for i, ev in enumerate(ref["events"]):
            k = where[int(ev)]
            c_e[k] += f[i]
            m_e[k] += 1
            num_e[k] += numer[i]
            den_e[k] += norms[i]
        t = gaussian.t_quantile_975(g - 1)
        resid = c_e - m_e[:, None] * mean[None, :]
        se = np.sqrt(g / (g - 1) * (resid ** 2).sum(axis=0)) / n_units
        out["half95"] = t * se * scale
        ratio = num_e.sum(axis=0) / den_e.sum()
        se_r = np.sqrt(((num_e - ratio[None, :] * den_e[:, None]) ** 2).sum(axis=0)
                       / (g * (g - 1) * den_e.mean() ** 2))
        out["pooled"] = ratio * scale
        out["pooled_lo"] = (ratio - t * se_r) * scale
        out["pooled_hi"] = (ratio + t * se_r) * scale
    else:
        out["pooled"] = numer.sum(axis=0) / norms.sum() * scale if n_units else None
    return out


def window_bins(key: str, block: dict[str, Any]) -> list[int]:
    """The bin indices an axis block draws, recovered from its edges."""
    pitch_cm = block["pitch_mm"] / 10.0
    first = block["edges_cm"][0] / pitch_cm + (0.5 if key == "kt" else 0.0)
    lo = int(round(first))
    return list(range(lo, lo + len(block["mean"])))


def approx(values, rel: float = 2e-5, abs_: float = 1e-9):
    return pytest.approx([None if v is None else float(v) for v in values], rel=rel, abs=abs_)


def assert_axis_matches(key: str, block: dict[str, Any], ref: dict[str, Any]) -> None:
    """The route's arrays against the brute force on the bins it draws."""
    want = expected(ref, window_bins(key, block), float(block["pitch_mm"]))
    assert block["mean"] == approx(want["mean"])
    if want["n"] >= 2:
        assert block["band"]["lo"] == approx(want["mean"] - want["sd"])
        assert block["band"]["hi"] == approx(want["mean"] + want["sd"])
    else:
        assert block["band"] is None
    if want["g"] >= 2:
        assert block["envelope"]["lo"] == approx(want["mean"] - want["half95"])
        assert block["envelope"]["hi"] == approx(want["mean"] + want["half95"])
        assert block["pooled"]["ci95_lo"] == approx(want["pooled_lo"])
        assert block["pooled"]["ci95_hi"] == approx(want["pooled_hi"])
    else:
        assert block["envelope"] is None
        assert all(v is None for v in block["pooled"]["ci95_lo"])
    assert block["pooled"]["value"] == approx(want["pooled"])


def strings(value: Any):
    """Every string in a payload, keys excluded."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def assert_typography(payload: dict[str, Any]) -> None:
    """No rendered sentence signs a number with the ASCII hyphen (CLAUDE.md section 2)."""
    for text in strings(payload):
        assert not signed_hyphens(text), text


# ------------------------------------------------------- rendering, no DB --

def _record() -> ExperimentRecord:
    return ExperimentRecord(
        table_name="synthetic_profiles", status="ready",
        schema_name="standalone_hits", schema_version=3,
        capabilities={"footprint_mm": [48.27, 48.6],
                      "profiles": {"k": 6, "k_z": 2, "w_bin_mm": 20.5, "r_bin_mm": 10.0, "r_bins": 50,
                                   "comb": {"w": 0.4, "r": 0.7, "threshold": -0.1}}},
    )


def _axis(bins, energy_rows: np.ndarray, norms: np.ndarray) -> profiles.AxisSums:
    """Unit-form sums of per-shower energies ``energy_rows[shower, bin]``."""
    f = energy_rows / norms[:, None]
    present = (energy_rows > 0).sum(axis=0)
    return profiles.AxisSums(
        bins=np.asarray(bins), sn=energy_rows.sum(axis=0), snn=(energy_rows ** 2).sum(axis=0),
        snd=(energy_rows * norms[:, None]).sum(axis=0), c=f.sum(axis=0), q=(f ** 2).sum(axis=0),
        cc=None, mc=None, n_present=present)


def _totals(axes: dict[str, profiles.AxisSums], norms: np.ndarray, **kw) -> profiles.ProfileSums:
    n = int(norms.size)
    return profiles.ProfileSums(
        n_showers=n, n_events=n, n_dropped=0, m2=float(n), den=float(norms.sum()),
        den2=float((norms ** 2).sum()), n_single_cell=kw.get("single", 0), e_all=float(norms.sum()),
        e_neg=kw.get("e_neg", 0.0), clustered=False, axes=axes)


def _payload(totals: profiles.ProfileSums, depth: str = "w") -> dict[str, Any]:
    body = profiles.render(_record(), totals, shower="a", depth=depth, notebook=False)
    return {"meta": {}, **body,
            "filter": {"e1": [0.0, 20.0], "e2": [None, None], "d": [None, None],
                       "include_undefined_d": False}}


def test_empty_selection_renders_nulls_and_says_so():
    none = np.zeros(0)
    empty = profiles.AxisSums(bins=np.zeros(0, dtype=np.int64), sn=none, snn=none, snd=none, c=none,
                              q=none, cc=None, mc=None, n_present=np.zeros(0, dtype=np.int64))
    payload = _payload(profiles.ProfileSums(0, 0, 0, 0.0, 0.0, 0.0, 0, 0.0, 0.0, False,
                                            {"w": empty, "r": empty}))
    contract_check.check(payload, "profiles")
    assert payload["ensemble"]["label"] == "no showers" and payload["ensemble"]["provisional"]
    for block in payload["axes"].values():
        assert all(v is None for v in block["mean"]) and block["band"] is None
        assert (block["y"]["lo"], block["y"]["hi"]) == (0.0, 1.0)
    assert not any(m["drawn"] for m in payload["marks"] if m["key"] != "mean")
    assert "nothing is drawn" in payload["notes"][0]


def test_curves_and_outside_fractions_close_to_one():
    rng = np.random.default_rng(7)
    n = 30
    norms = rng.uniform(1.0, 5.0, n)
    w_bins = np.arange(-3, 40)
    w = rng.dirichlet(np.ones(w_bins.size), n) * norms[:, None]
    r_bins = np.arange(0, 51)                       # bin 50 is the overflow
    r = rng.dirichlet(np.ones(r_bins.size), n) * norms[:, None]
    payload = _payload(_totals({"w": _axis(w_bins, w, norms), "r": _axis(r_bins, r, norms)}, norms))
    contract_check.check(payload, "profiles")
    for key, block in payload["axes"].items():
        width_cm = block["pitch_mm"] / 10.0
        out = block["outside"]
        pooled = sum(v * width_cm for v in block["pooled"]["value"]) / 100.0
        mean = sum(v * width_cm for v in block["mean"]) / 100.0
        assert pooled + out["below_fraction"] + out["above_fraction"] == pytest.approx(1.0, abs=1e-5)
        assert mean + out["mean_below_fraction"] + out["mean_above_fraction"] == pytest.approx(1.0, abs=1e-5)
    assert payload["axes"]["r"]["outside"]["above_fraction"] > 0          # the overflow bin
    assert payload["axes"]["w"]["w_zero_rule"]["energy_fraction_below"] > 0
    assert 0.0 in payload["axes"]["w"]["edges_cm"]                        # no bin straddles w = 0


def test_y_range_follows_the_lines_and_counts_what_it_clips():
    norms = np.ones(3)
    rows = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 0.2]])   # widely spread showers
    bins = [0, 1, 2]
    payload = _payload(_totals({"w": _axis(bins, rows, norms), "r": _axis(bins, rows, norms)}, norms))
    for block in payload["axes"].values():
        y = block["y"]
        peak = max(max(v for v in block["mean"] if v is not None),
                   max(v for v in block["pooled"]["value"] if v is not None))
        assert y["lo"] == 0.0 and peak <= y["hi"] < 2.0 * peak
        over = [i for i, v in enumerate(block["band"]["hi"]) if v is not None and v > y["hi"]]
        under = [i for i, v in enumerate(block["band"]["lo"]) if v is not None and v < 0]
        assert block["band"]["over"] == over and y["clipped"]["band"] == len(over) > 0
        assert block["band"]["under"] == under and y["clipped"]["band_below_zero"] == len(under) > 0
        assert y["provisional"] is True
    assert any("clipped at the axis" in note for note in payload["notes"])
    assert_typography(payload)


def test_an_alternating_profile_is_called_a_comb():
    n = 40
    norms = np.ones(n)
    bins = np.arange(0, 51)
    pattern = np.where(bins % 2 == 0, 1.0, 0.1)
    rows = np.tile(pattern / pattern.sum(), (n, 1))
    payload = _payload(_totals({"w": _axis(bins, rows, norms), "r": _axis(bins, rows, norms)}, norms))
    comb = payload["axes"]["r"]["comb"]
    assert comb["combed"] is True and comb["lag1"] < -0.1 and comb["k"] == 6 and comb["k_z"] == 2
    assert comb["ingest_lag1"] == 0.7
    assert any("alternates bin to bin" in note for note in payload["notes"])
    assert payload["axes"]["r"]["splat"]["gap_free"] is True
    assert math.isclose(payload["axes"]["r"]["splat"]["spacing_mm"], 8.1)
