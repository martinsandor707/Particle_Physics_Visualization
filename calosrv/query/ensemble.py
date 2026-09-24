"""The two ensemble shower axes, with their dispersion and their uncertainty.

In the laboratory frame no averaged direction is ever drawn: the incident
azimuth is uniform there (mean resultant length 0.012), so a mean would point
somewhere arbitrary. In the canonical frame the picture changes - the A-B
separation defines +x', and the directions become coherent (resultant length
0.78-0.82 for well-separated showers on the production data). Two axes are
therefore drawn, and CLAUDE.md section 2 then demands that each carries its
uncertainty rather than standing as a naked point estimate:

* the **axis** itself is the mean of the per-event projected slopes,
  ``s = u'_t / u'_z`` for the panel's transverse coordinate ``t``;
* a **dispersion band** shows the sample spread of those slopes (SD, ddof = 1),
  drawn as an uncapped shaded wedge - "where individual showers go";
* a **95% envelope** shows the uncertainty of the mean, ``t_{0.975, N-1} * SD /
  sqrt(N)``, drawn as a thin capped envelope - "how well the ensemble axis is
  known".

The two marks answer different questions and differ by ``sqrt N``, so each names
its quantity in its tooltip. The transverse resultant length ``R'`` and its
Rayleigh p-value are reported beside the axis; an axis whose direction is not
distinguishable from uniform (p > 0.05) is drawn faded, never hidden, because
the directive asks for exactly two.
"""

from __future__ import annotations

import math
from typing import Any

from ..grid import frame as frame_mod
from ..grid.frame import CanonicalGrid
from .canonical import FrameStats, ShowerDirection

#: Rayleigh p-value above which the ensemble axis is drawn faded.
FADE_P = 0.05


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def _shower_axes(
    shower: str,
    direction: ShowerDirection,
    origin_x: float | None,
    depth_max: float,
    n: int,
) -> dict[str, Any]:
    """Polylines for one shower on both depth panels, plus its labels."""
    out: dict[str, Any] = {
        "shower": shower,
        "n": n,
        "resultant_transverse": direction.resultant_transverse if n >= 2 else None,
        "rayleigh_p": direction.rayleigh_p if n >= 2 else None,
        "faded": False,
        "label": "",
        "yz": None,
        "xz": None,
    }
    if n <= 0 or origin_x is None or not _finite(origin_x):
        return out

    if n == 1:
        out["label"] = "single event, not an ensemble"
    elif n < frame_mod.PROVISIONAL_N:
        out["label"] = f"weak (N = {n})"
    p = out["rayleigh_p"]
    out["faded"] = n >= 2 and (p is None or p > FADE_P)

    t_value = frame_mod.t_quantile_975(n - 1) if n >= 2 else None

    for panel, index, origin in (("xz", 0, origin_x), ("yz", 1, 0.0)):
        slope = direction.slope_mean[index]
        if not _finite(slope):
            continue
        sd = direction.slope_sd[index] if n >= 2 else None
        line = [[0.0, origin], [depth_max, origin + slope * depth_max]]
        band = None
        envelope = None
        if _finite(sd):
            band = [[0.0, origin, origin],
                    [depth_max, origin + (slope - sd) * depth_max, origin + (slope + sd) * depth_max]]
            se = t_value * sd / math.sqrt(n)
            envelope = [[0.0, origin, origin],
                        [depth_max, origin + (slope - se) * depth_max, origin + (slope + se) * depth_max]]
        out[panel] = {
            "axis": line,
            "band": band,
            "envelope": envelope,
            "slope": slope,
            "slope_sd": sd,
            "dof_note": "1 d.o.f." if n == 2 else None,
        }
    return out


def ensemble_axes(stats: FrameStats, grid: CanonicalGrid) -> dict[str, Any]:
    """Payload block for the two ensemble axes and the anchors.

    Coordinates follow the depth panels' convention ``[z', transverse]``.
    """
    n = stats.n_events
    # The back face is the last sampling layer, in the same convention that
    # puts the front face at the first one (z' = 0): the axes, their bands and
    # the drawn face rule must all end at the same depth.
    depth_max = float(grid.z_coords[-1])
    d_mean = stats.d_entry.mean
    half = 0.5 * d_mean if _finite(d_mean) else None

    a = _shower_axes("a", stats.a, -half if half is not None else None, depth_max, n)
    b = _shower_axes("b", stats.b, half, depth_max, n)

    anchors: dict[str, Any] = {}
    if half is not None:
        sd = stats.d_entry.sd if n >= 2 else None
        se = stats.d_entry.se if n >= 2 else None
        t_value = frame_mod.t_quantile_975(n - 1) if n >= 2 else None
        for shower, sign in (("a", -1.0), ("b", 1.0)):
            centre = sign * half
            anchors[shower] = {
                "x": centre,
                "y": 0.0,
                # Sample dispersion of D_entry/2 across events: an uncapped bar.
                "spread": [centre - 0.5 * sd, centre + 0.5 * sd] if _finite(sd) else None,
                # Uncertainty of the mean anchor: quoted, not drawn as a whisker
                # here because the marker sits on a raster, not a value axis.
                "se95": 0.5 * t_value * se if _finite(se) and t_value else None,
                "n": n,
                "dof_note": "1 d.o.f." if n == 2 else None,
            }

    notes: list[str] = []
    if n == 0:
        notes.append("No selected event has a defined frame; no ensemble axis is drawn.")
    elif n == 1:
        notes.append(
            "One co-registered event: the dashed lines are that event's own incident "
            "directions, not an ensemble; no dispersion band can be drawn."
        )
    else:
        for shower, block in (("A", a), ("B", b)):
            r = block["resultant_transverse"]
            p = block["rayleigh_p"]
            if _finite(r) and _finite(p):
                verdict = "coherent" if p <= FADE_P else "not distinguishable from uniform"
                notes.append(
                    f"Shower {shower}: transverse direction resultant R̄′ = {r:.3f}, "
                    f"Rayleigh p = {p:.3g} over N = {n} — {verdict}."
                )
    return {
        "a": a,
        "b": b,
        "anchors": anchors,
        "depth_max": depth_max,
        "fade_p": FADE_P,
        "notes": notes,
    }
