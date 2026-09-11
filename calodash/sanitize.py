"""Validation and removal of unphysical records.

The shipped dataset is clean: it contains no NaN, no infinity and no
non-positive energy, so every rule below legitimately removes zero rows. The
report still records each rule's count explicitly, because a sanitisation step
that silently does nothing is indistinguishable from one that silently failed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class SanitationReport:
    """Per-rule audit of what was removed and what units were observed."""

    rows_in: int = 0
    rows_out: int = 0
    dropped: dict[str, int] = field(default_factory=dict)
    unit_checks: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def rows_dropped(self) -> int:
        return self.rows_in - self.rows_out

    def lines(self) -> list[str]:
        out = [f"  rows in : {self.rows_in:,}", f"  rows out: {self.rows_out:,}"]
        for rule, count in self.dropped.items():
            out.append(f"    - {rule:<34s} {count:>8,d}")
        for name, verdict in self.unit_checks.items():
            out.append(f"  {name:<20s} {verdict}")
        out.extend(f"  ! {w}" for w in self.warnings)
        return out


#: Columns that must be finite for a hit to be usable.
_NUMERIC = ("x", "y", "z", "energy")


def sanitize(hits: pd.DataFrame, kinematic_columns) -> tuple[pd.DataFrame, SanitationReport]:
    """Drop unphysical hits and verify unit consistency.

    Rules, applied in order and counted separately:

    ``non_numeric``    a coordinate or energy that would not parse as a number
    ``nan_or_inf``     NaN or +/-inf in any coordinate or energy
    ``energy_le_zero`` a deposit of zero or negative energy
    ``z_negative``     a hit behind the interaction point
    """
    report = SanitationReport(rows_in=len(hits))
    frame = hits.copy()

    columns = [c for c in _NUMERIC + tuple(kinematic_columns) if c in frame.columns]

    # Explicit numeric casting. ``errors='coerce'`` turns anything unparseable
    # into NaN so the next rule removes it, rather than raising mid-build. The
    # count records values that were not already missing, which is the only way
    # to tell a malformed field from a genuinely absent one.
    coerced = 0
    for column in columns:
        original_missing = frame[column].isna()
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        coerced += int((frame[column].isna() & ~original_missing).sum())
    report.dropped["non_numeric (coerced)"] = coerced

    finite = np.ones(len(frame), dtype=bool)
    for column in columns:
        finite &= np.isfinite(frame[column].to_numpy(dtype="float64"))
    report.dropped["nan_or_inf"] = int((~finite).sum())
    frame = frame[finite]

    positive = frame["energy"].to_numpy() > 0.0
    report.dropped["energy_le_zero"] = int((~positive).sum())
    frame = frame[positive]

    forward = frame["z"].to_numpy() >= 0.0
    report.dropped["z_negative"] = int((~forward).sum())
    frame = frame[forward]

    report.rows_out = len(frame)
    _check_units(frame, kinematic_columns, report)

    if report.rows_out == 0:
        raise ValueError(
            "Sanitisation removed every row. Check that the input file holds "
            "hit-level calorimeter data with positive energies."
        )

    return frame.reset_index(drop=True), report


def _check_units(frame: pd.DataFrame, kinematic_columns, report: SanitationReport) -> None:
    """Verify mm / GeV / radian consistency and record what was observed.

    These are assertions about scale, not about exact values: a file in cm or
    MeV would be silently misrendered otherwise, since nothing else in the
    pipeline carries units.
    """
    span_mm = float(
        max(
            frame["x"].max() - frame["x"].min(),
            frame["y"].max() - frame["y"].min(),
        )
    )
    report.unit_checks["spatial"] = f"transverse span {span_mm:,.1f} mm"
    if not 100.0 <= span_mm <= 100_000.0:
        report.warnings.append(
            f"Transverse span of {span_mm:,.1f} suggests coordinates are not in mm."
        )

    e_max = float(frame["energy"].max())
    report.unit_checks["energy"] = f"max hit deposit {e_max:.4g} GeV"
    if e_max > 1000.0:
        report.warnings.append(
            f"Maximum hit energy {e_max:.4g} looks like MeV rather than GeV."
        )

    for column in kinematic_columns:
        if column.startswith("incoming_theta") and column in frame.columns:
            theta_max = float(frame[column].abs().max())
            report.unit_checks[column] = f"max |theta| {theta_max:.3f} rad"
            if theta_max > np.pi:
                report.warnings.append(
                    f"{column} exceeds pi ({theta_max:.3f}); values may be in degrees."
                )
