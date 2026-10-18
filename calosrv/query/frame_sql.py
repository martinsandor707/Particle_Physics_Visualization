"""The SE(3) element of every co-registered frame, as SQL over the event table.

``grid/frame.py`` defines the three frames in NumPy: a rotation ``R`` and an
anchor ``a`` taken to the origin, ``p' = R (p - a)``. The accumulation scans
run inside DuckDB, so the same element is needed there, and it is built in one
place: a CTE named ``fr`` that emits, per shower (the per-shower frames) or per
event (the D-frame), the nine entries of ``R`` and the three coordinates of
``a``, and one expression builder that applies the motion to a laboratory
point. The canonical scan, the two per-shower scans and the ingest checks all
read the frame from here, so SQL and NumPy cannot drift apart - a test pins
the two against each other on the fixture.

**Two anchor definitions for the D-frame.** The back-projected 3-D centroid
(the definition the frame shipped with, ``backprojected``) or the shower's
own entry point P0 back-projected the short distance to the front face
(``p0``, the reference notebook's origin). Measured on the production file the
two differ by a median 46 mm per shower, p90 133 mm, with 47% of showers more
than one cell footprint apart; the ingest report and every canonical response
carry the figure, so the choice is a stated, measured one.

The per-shower frames use the file's own P0 (``p0a*``, ``p0b*`` in the event
table, recovered at ingest as ``x - x_trans`` and verified rigid) and the
shower's own ``(theta, phi)``; their rotation entries are written exactly as
the local scan always wrote them, so the rotated sub-deposits are unchanged
bit for bit.
"""

from __future__ import annotations

from ..grid.frame import KIND_LOCAL, KIND_TRANS

ANCHOR_BACKPROJECTED = "backprojected"
ANCHOR_P0 = "p0"
ANCHORS: tuple[str, ...] = (ANCHOR_BACKPROJECTED, ANCHOR_P0)

#: Coordinate sources of a per-shower scan: the file's own columns, or the
#: motion applied to the laboratory lattice inside the scan.
SOURCE_FILE = "file"
SOURCE_COMPUTED = "computed"
SOURCES: tuple[str, ...] = (SOURCE_FILE, SOURCE_COMPUTED)

#: The nine rotation entries and the anchor, in the order every CTE emits them.
FRAME_COLUMNS: tuple[str, ...] = (
    "r11", "r12", "r13", "r21", "r22", "r23", "r31", "r32", "r33", "ax", "ay", "az",
)

#: Every per-event column the back-projected D-frame needs; ``d`` is included so
#: the frame-bearing set is a subset of the filtered set even when
#: ``include_undefined_d`` is on.
_BACKPROJECTED_COLUMNS = (
    "cax", "cay", "caz", "cbx", "cby", "cbz",
    "theta_a", "phi_a", "theta_b", "phi_b", "d",
)
_P0_COLUMNS = (
    "p0ax", "p0ay", "p0az", "p0bx", "p0by", "p0bz",
    "theta_a", "phi_a", "theta_b", "phi_b", "d",
)


def check_anchor(anchor: str) -> str:
    if anchor not in ANCHORS:
        raise ValueError(f"unknown anchor {anchor!r}; expected one of {', '.join(ANCHORS)}")
    return anchor


def frame_columns(anchor: str = ANCHOR_BACKPROJECTED) -> tuple[str, ...]:
    """The event-table columns a D-frame with this anchor reads."""
    return _P0_COLUMNS if check_anchor(anchor) == ANCHOR_P0 else _BACKPROJECTED_COLUMNS


def frame_defined(anchor: str = ANCHOR_BACKPROJECTED) -> str:
    """``AND``-joined ``IS NOT NULL`` over :func:`frame_columns`."""
    return " AND ".join(f"{c} IS NOT NULL" for c in frame_columns(anchor))


def entry_sql(anchor: str = ANCHOR_BACKPROJECTED) -> str:
    """``xa, ya, xb, yb``: the two front-face entry points of an event, per the anchor.

    Both definitions back-project a point along the shower's incident
    direction to the front face ``$zf``::

        entry = c - (c_z - zf) * tan(theta) * (cos phi, sin phi)

    with ``c`` the dataset's 3-D centroid (``backprojected``) or the shower's
    first-layer entry point P0 (``p0``), whose depth is that layer's z, so the
    drift is a layer or two at most.
    """
    if check_anchor(anchor) == ANCHOR_P0:
        a, b = ("p0ax", "p0ay", "p0az"), ("p0bx", "p0by", "p0bz")
    else:
        a, b = ("cax", "cay", "caz"), ("cbx", "cby", "cbz")
    return f"""
    {a[0]} - ({a[2]} - $zf) * tan(theta_a) * cos(phi_a) AS xa,
    {a[1]} - ({a[2]} - $zf) * tan(theta_a) * sin(phi_a) AS ya,
    {b[0]} - ({b[2]} - $zf) * tan(theta_b) * cos(phi_b) AS xb,
    {b[1]} - ({b[2]} - $zf) * tan(theta_b) * sin(phi_b) AS yb"""


def both_entries_sql() -> str:
    """Both definitions' entry points side by side, for the anchor residual."""
    return f"""
    cax - (caz - $zf) * tan(theta_a) * cos(phi_a) AS xa_c,
    cay - (caz - $zf) * tan(theta_a) * sin(phi_a) AS ya_c,
    cbx - (cbz - $zf) * tan(theta_b) * cos(phi_b) AS xb_c,
    cby - (cbz - $zf) * tan(theta_b) * sin(phi_b) AS yb_c,
    p0ax - (p0az - $zf) * tan(theta_a) * cos(phi_a) AS xa_p,
    p0ay - (p0az - $zf) * tan(theta_a) * sin(phi_a) AS ya_p,
    p0bx - (p0bz - $zf) * tan(theta_b) * cos(phi_b) AS xb_p,
    p0by - (p0bz - $zf) * tan(theta_b) * sin(phi_b) AS yb_p"""


def canonical_frame_cte(event_table: str, where: str, anchor: str = ANCHOR_BACKPROJECTED) -> str:
    """The D-frame per event: ``fr(event_number, r11 .. r33, ax, ay, az)``.

    The rotation is :func:`~calosrv.grid.frame.rotation_matrix` at
    ``theta = 0`` with the A->B azimuth ``psi``: the notebook's rotation with
    the tilt removed. Its z entries are written as the literals 0 and 1, so a
    consumer that multiplies by them adds an exact zero and the two-dimensional
    scan is unchanged bit for bit. ``$zf`` must be bound by the caller.
    """
    return f"""ev AS (
        SELECT event_number, {entry_sql(anchor)}
        FROM {event_table}
        WHERE {where} AND {frame_defined(anchor)}
    ), fr AS (
        SELECT event_number,
               cos(psi) AS r11, sin(psi) AS r12, 0.0::DOUBLE AS r13,
               -sin(psi) AS r21, cos(psi) AS r22, 0.0::DOUBLE AS r23,
               0.0::DOUBLE AS r31, 0.0::DOUBLE AS r32, 1.0::DOUBLE AS r33,
               (xa + xb) / 2 AS ax, (ya + yb) / 2 AS ay, CAST($zf AS DOUBLE) AS az
        FROM (SELECT event_number, xa, ya, xb, yb, atan2(yb - ya, xb - xa) AS psi FROM ev)
    )"""


def shower_frame_cte(event_table: str, where: str, kind: str) -> str:
    """A per-shower frame: ``fr(event_number, b, r11 .. r33, ax, ay, az)``, ``b`` 0 for A, 1 for B.

    *trans*: the identity about the shower's own P0. *local*: the notebook's
    ``R(theta, phi)`` about P0, its entries written exactly as the local scan
    always wrote them for its sub-deposit offsets.
    """
    if kind == KIND_TRANS:
        def rotation(_t: str, _f: str) -> str:
            return ("1.0::DOUBLE AS r11, 0.0::DOUBLE AS r12, 0.0::DOUBLE AS r13, "
                    "0.0::DOUBLE AS r21, 1.0::DOUBLE AS r22, 0.0::DOUBLE AS r23, "
                    "0.0::DOUBLE AS r31, 0.0::DOUBLE AS r32, 1.0::DOUBLE AS r33")
    elif kind == KIND_LOCAL:
        def rotation(t: str, f: str) -> str:
            return (f"cos({t}) * cos({f}) AS r11, cos({t}) * sin({f}) AS r12, -sin({t}) AS r13, "
                    f"-sin({f}) AS r21, cos({f}) AS r22, 0.0::DOUBLE AS r23, "
                    f"sin({t}) * cos({f}) AS r31, sin({t}) * sin({f}) AS r32, cos({t}) AS r33")
    else:  # pragma: no cover - guarded by the callers
        raise ValueError(f"not a per-shower frame: {kind!r}")
    rows = []
    for b, shower in ((0, "a"), (1, "b")):
        t = f"CAST(theta_{shower} AS DOUBLE)"
        f = f"CAST(phi_{shower} AS DOUBLE)"
        rows.append(
            f"SELECT event_number, {b} AS b, {rotation(t, f)}, "
            f"CAST(p0{shower}x AS DOUBLE) AS ax, CAST(p0{shower}y AS DOUBLE) AS ay, "
            f"CAST(p0{shower}z AS DOUBLE) AS az "
            f"FROM {event_table} WHERE {where} AND d IS NOT NULL"
        )
    return "fr AS (\n        " + "\n        UNION ALL\n        ".join(rows) + "\n    )"


def transform_sql(x: str, y: str, z: str | None, prefix: str = "") -> tuple[str, str, str]:
    """``(x', y', z')`` of the laboratory point ``(x, y, z)`` under the frame row ``prefix``.

    ``x``, ``y`` and ``z`` are SQL expressions for the point's laboratory
    coordinates; with ``z=None`` the depth term is omitted (the D-frame keeps
    its layer index and has zero z entries anyway).
    """
    p = prefix
    dx, dy = f"({x} - {p}ax)", f"({y} - {p}ay)"
    dz = None if z is None else f"({z} - {p}az)"
    if dz is None:
        return (
            f"{p}r11 * {dx} + {p}r12 * {dy}",
            f"{p}r21 * {dx} + {p}r22 * {dy}",
            f"{p}r31 * {dx} + {p}r32 * {dy}",
        )
    return (
        f"{p}r11 * {dx} + {p}r12 * {dy} + {p}r13 * {dz}",
        f"{p}r21 * {dx} + {p}r22 * {dy} + {p}r23 * {dz}",
        f"{p}r31 * {dx} + {p}r32 * {dy} + {p}r33 * {dz}",
    )
