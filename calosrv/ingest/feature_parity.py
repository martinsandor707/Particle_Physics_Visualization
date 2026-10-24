"""Feature parity: the features rebuilt from hits against the producer's aggregate.

A single-shower hit experiment stores Group-1 sums, from which
``group1.feature_sql`` rebuilds every feature of ``core.calc_all_features_v3``;
an aggregated experiment stores the producer's own values of the same
features. For the same events the two must agree, and this compares them in
one query, event by event.

Each difference is relative to the larger of the two values *and* the
dataset's median magnitude of that feature. Without the floor, a translated or
local centroid that is zero up to rounding (≈ 10⁻¹² mm) on both sides would
report a meaningless relative error of order one.

Run on the real files with ``python -m calosrv.ingest --compare-features HITS
EVENTS`` - serially, as every full-dataset DuckDB job.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import duckdb
import numpy as np

from ..db import group1, naming, registry
from ..db.ddl import FEATURE_SUFFIX, KIND_SINGLE_EVENTS, KIND_SINGLE_HITS
from ..db.naming import quote
from ..errors import IngestError

TOLERANCE = 1e-9

#: Base columns compared exactly (energy to rounding): the same name in both tables.
_BASE = ("e1", "theta_a", "phi_a", "e1_bin", "n_hits")


@dataclass
class ParityReport:
    n_shared: int = 0
    n_hits_only: int = 0
    n_events_only: int = 0
    base_equal: dict[str, bool] = field(default_factory=dict)
    energy_max_rel: float | None = None
    max_rel: dict[str, float] = field(default_factory=dict)
    worst_event: dict[str, int] = field(default_factory=dict)
    tolerance: float = TOLERANCE

    @property
    def ok(self) -> bool:
        return (self.n_shared > 0 and all(self.base_equal.values())
                and (self.energy_max_rel or 0.0) <= 1e-12
                and all(v <= self.tolerance for v in self.max_rel.values()))

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["ok"] = self.ok
        return data


def compare(con: duckdb.DuckDBPyConnection, hits_name: str, events_name: str,
            tolerance: float = TOLERANCE) -> ParityReport:
    """Compare every rebuilt feature of ``hits_name`` with ``events_name``'s."""
    hits = registry.require_ready(con, hits_name)
    events = registry.require_ready(con, events_name)
    if hits.kind != KIND_SINGLE_HITS or events.kind != KIND_SINGLE_EVENTS:
        raise IngestError(
            f"Feature parity compares a single-shower hit experiment with an aggregated one; "
            f"got {hits_name!r} ({hits.kind}) and {events_name!r} ({events.kind}).")
    h, e = quote(naming.event_table(hits_name)), quote(naming.event_table(events_name))
    counts = con.execute(
        f"SELECT (SELECT count(*) FROM {h} JOIN {e} USING (event_number)),"
        f"       (SELECT count(*) FROM {h} ANTI JOIN {e} USING (event_number)),"
        f"       (SELECT count(*) FROM {e} ANTI JOIN {h} USING (event_number))"
    ).fetchone()
    report = ParityReport(*(int(v) for v in counts), tolerance=tolerance)
    if report.n_shared == 0:
        return report

    mine, theirs = [], []
    for code, suffix in FEATURE_SUFFIX.items():
        for feature in group1.FEATURES:
            column = f"{feature}{suffix}"
            mine.append(f"{group1.feature_sql(feature, code, alias='h')} AS m__{column}")
            theirs.append(f"e.{column} AS t__{column}")
    base = ", ".join(f"h.{c} AS hb__{c}, e.{c} AS eb__{c}" for c in _BASE)
    data = con.execute(
        f"SELECT h.event_number, {base}, h.e_dep AS hb__e_dep, e.e_dep AS eb__e_dep, "
        f"{', '.join(mine)}, {', '.join(theirs)} "
        f"FROM {h} h JOIN {e} e USING (event_number) ORDER BY h.event_number"
    ).fetchnumpy()
    ids = np.asarray(data["event_number"])
    for c in _BASE:
        a, b = np.asarray(data[f"hb__{c}"], dtype=float), np.asarray(data[f"eb__{c}"], dtype=float)
        report.base_equal[c] = bool(np.array_equal(a, b))
    a, b = np.asarray(data["hb__e_dep"], dtype=float), np.asarray(data["eb__e_dep"], dtype=float)
    report.energy_max_rel = float(np.max(np.abs(a - b) / np.maximum(np.abs(b), 1e-300)))
    for code, suffix in FEATURE_SUFFIX.items():
        for feature in group1.FEATURES:
            column = f"{feature}{suffix}"
            m = np.asarray(np.ma.filled(np.ma.asarray(data[f"m__{column}"], dtype=float), np.nan))
            t = np.asarray(np.ma.filled(np.ma.asarray(data[f"t__{column}"], dtype=float), np.nan))
            both = np.isfinite(m) & np.isfinite(t)
            floor = float(np.median(np.abs(t[both]))) if both.any() else 0.0
            scale = np.maximum(np.maximum(np.abs(m), np.abs(t)), floor)
            rel = np.where(both, np.abs(m - t) / np.where(scale > 0, scale, 1.0), np.inf)
            # A value missing on one side only is a disagreement, not a skip.
            rel = np.where(~np.isfinite(m) & ~np.isfinite(t), 0.0, rel)
            worst = int(np.argmax(rel))
            report.max_rel[column] = float(rel[worst])
            report.worst_event[column] = int(ids[worst])
    return report
