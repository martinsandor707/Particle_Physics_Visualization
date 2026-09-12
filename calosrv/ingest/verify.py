"""Post-ingest assertions.

An ingest that quietly loses rows is worse than one that fails, because nothing
downstream can tell. These checks run after the derived tables are built and
either pass or attach a warning to the experiment record, so a dataset that
behaved unexpectedly is visible in the interface rather than only in a log.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from ..db import naming
from ..db.naming import quote
from . import csv_spec

log = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    ok: bool = True
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, str] = field(default_factory=dict)

    def fail(self, key: str, message: str) -> None:
        self.ok = False
        self.checks[key] = "FAIL"
        self.warnings.append(message)
        log.error("Verification failed - %s: %s", key, message)

    def warn(self, key: str, message: str) -> None:
        self.checks[key] = "WARN"
        self.warnings.append(message)
        log.warning("Verification warning - %s: %s", key, message)

    def passed(self, key: str) -> None:
        self.checks.setdefault(key, "PASS")


def verify(
    con: duckdb.DuckDBPyConnection,
    name: str,
    source: Path | None,
    expect_rows: int | None = None,
) -> VerificationResult:
    """Check the ingested tables against the source file and each other."""
    result = VerificationResult()
    hit_physical = naming.hit_table(name)
    proj_physical = naming.proj_table(name)
    event_physical = naming.event_table(name)

    n_hits = int(con.execute(f"SELECT count(*) FROM {quote(hit_physical)}").fetchone()[0])
    n_proj = int(con.execute(f"SELECT count(*) FROM {quote(proj_physical)}").fetchone()[0])
    n_events = int(
        con.execute(f"SELECT count(*) FROM {quote(event_physical)}").fetchone()[0]
    )

    # 1. Every data row of the source must have reached the hit table.
    if expect_rows is None and source is not None and source.is_file():
        expect_rows = csv_spec.count_data_rows(source)
    if expect_rows is not None:
        if n_hits == expect_rows:
            result.passed("row_count")
        else:
            result.fail(
                "row_count",
                f"The source file holds {expect_rows:,} data rows but "
                f"{hit_physical} holds {n_hits:,}.",
            )
    if n_hits == 0:
        result.fail("non_empty", f"{hit_physical} is empty after ingestion.")
        return result

    # 2. The projection table may legitimately be smaller (sanitisation removes
    #    unphysical rows) but never larger, and losing a large fraction is a
    #    sign the input is not what it claims to be.
    if n_proj > n_hits:
        result.fail(
            "projection_size",
            f"{proj_physical} has more rows ({n_proj:,}) than {hit_physical} "
            f"({n_hits:,}).",
        )
    else:
        dropped = n_hits - n_proj
        if dropped and dropped / n_hits > 0.05:
            result.warn(
                "projection_size",
                f"Sanitisation removed {dropped:,} of {n_hits:,} rows "
                f"({100.0 * dropped / n_hits:.2f}%) as unphysical.",
            )
        else:
            result.passed("projection_size")

    # 3. Event counts must agree between the two derived tables.
    n_proj_events = int(
        con.execute(
            f"SELECT count(DISTINCT event_number) FROM {quote(proj_physical)}"
        ).fetchone()[0]
    )
    if n_proj_events == n_events:
        result.passed("event_count")
    else:
        result.warn(
            "event_count",
            f"{event_physical} summarises {n_events:,} events but "
            f"{proj_physical} contains {n_proj_events:,}.",
        )

    # 4. Undefined separation distance. Not an error - these are degenerate
    #    events where shower A deposited nothing - but it must be surfaced,
    #    because they are silently excluded by any D filter and their number is
    #    correlated with the overlap regime under study.
    n_no_d = int(
        con.execute(
            f"SELECT count(*) FROM {quote(event_physical)} WHERE d IS NULL"
        ).fetchone()[0]
    )
    if n_no_d:
        result.warn(
            "undefined_separation",
            f"{n_no_d:,} of {n_events:,} events have no defined A-B separation "
            "and are excluded from D-filtered views.",
        )
    else:
        result.passed("undefined_separation")

    # 5. Lattice indices must stay inside the measured lattice.
    row = con.execute(
        f"SELECT max(ix), max(iy), max(iz) FROM {quote(proj_physical)}"
    ).fetchone()
    lat = con.execute(
        'SELECT nx, ny, nz FROM "experiment" WHERE table_name = ?', [name]
    ).fetchone()
    if lat and all(v is not None for v in lat) and all(v is not None for v in row):
        if row[0] < lat[0] and row[1] < lat[1] and row[2] < lat[2]:
            result.passed("lattice_bounds")
        else:
            result.fail(
                "lattice_bounds",
                f"Projection indices ({row[0]}, {row[1]}, {row[2]}) exceed the "
                f"measured lattice ({lat[0]}, {lat[1]}, {lat[2]}).",
            )

    # 6. Deposited energy must be strictly positive and finite in aggregate.
    e_dep = con.execute(
        f"SELECT sum(e_dep), count(*) FILTER (WHERE NOT isfinite(e_dep)) "
        f"FROM {quote(event_physical)}"
    ).fetchone()
    if e_dep[0] is None or not (e_dep[0] > 0) or e_dep[1]:
        result.fail(
            "energy_sanity",
            f"Total deposited energy is not a usable positive finite value "
            f"(sum={e_dep[0]}, non-finite events={e_dep[1]}).",
        )
    else:
        result.passed("energy_sanity")

    log.info(
        "Verification for %r: %s (%s)",
        name,
        "PASSED" if result.ok else "FAILED",
        ", ".join(f"{k}={v}" for k, v in sorted(result.checks.items())),
    )
    return result
