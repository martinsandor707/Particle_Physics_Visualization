"""The per-shower column vocabulary: which event-table column holds what, per kind.

A two-shower event has showers A and B; a single-shower experiment has one,
stored under the shower-A names (``e1``, ``theta_a``, Group-1 ``*_a``). Every
query that works per shower reads its columns through :func:`of`, so the
names live in one place and are allowlisted literals - a request string never
becomes SQL (the rule at calosrv/db/ddl.py).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..db import ddl
from ..db.registry import ExperimentRecord
from ..errors import CapabilityError, ValidationError

#: The ``shower`` request parameter's values.
SHOWER_CHOICES: tuple[str, ...] = ("a", "b", "both")


@dataclass(frozen=True)
class ShowerColumns:
    """Where one shower's per-event values live in the event table."""

    key: str                     # "a" | "b"
    label: str                   # "Shower A", "Shower B", or "Shower" for a single shower
    b: int                       # index into the per-shower frame rows (0 A, 1 B)
    momentum: str                # incident momentum p (GeV)
    momentum_bin: str            # the producer's incoming_momentum_bin (exact integer)
    theta: str                   # incident polar angle (rad)
    phi: str                     # incident azimuth (rad), circular
    deposit: str                 # the shower's deposited energy (GeV)
    hits: str                    # the shower's hit rows
    shower_energy: str | None    # Group-1 deposit of the shower (derived v2 / single hits)
    w_neg_hits: str | None       # Group-1 hits at z_local < NEG_DEPTH_MM
    w_neg_energy: str | None     # Group-1 energy of those hits
    origin_sql: str | None       # projection-table predicate selecting the shower's hits
    present_sql: str             # event-table predicate: the shower deposited energy
    has_centroids: bool = True   # 3-D centroid and P0 columns (the aggregate has neither)
    primary_rows: str | None = None  # hit rows tagged is_secondary = 0 (single-shower hits)

    def group1(self, stem: str, frame: str | None = None) -> str:
        """A Group-1 column of this shower, e.g. ``sd_r_a_loc``."""
        return ddl.group1_column(stem, self.key, frame)

    def centroid(self, axis: str, frame: str = "abs") -> str:
        """This shower's 3-D centroid column, e.g. ``cax`` or ``cbz_t``."""
        if not self.has_centroids:
            raise ValueError(f"{self.label} has no centroid columns in this experiment kind")
        return ddl.centroid_column(self.key, axis, frame)

    def p0(self, axis: str) -> str:
        """This shower's entry-point column, e.g. ``p0ax``."""
        if not self.has_centroids:
            raise ValueError(f"{self.label} has no entry-point columns in this experiment kind")
        return ddl.p0_column(self.key, axis)


_TWO_A = ShowerColumns(
    key="a", label="Shower A", b=0,
    momentum="e1", momentum_bin="e1_bin", theta="theta_a", phi="phi_a",
    # The truth-segmentation deposit; the three frames' truth fractions agree.
    deposit=ddl.seg_stat_column("e_a_true", "lab"), hits="n_a_rows",
    shower_energy="e_dep_a", w_neg_hits="w_neg_hits_a", w_neg_energy="w_neg_energy_a",
    origin_sql=f"p.org = {ddl.ORIGIN_A}",
    present_sql="n_a_rows > 0",
)
_TWO_B = ShowerColumns(
    key="b", label="Shower B", b=1,
    momentum="e2", momentum_bin="e2_bin", theta="theta_b", phi="phi_b",
    deposit=ddl.seg_stat_column("e_b_true", "lab"), hits="(n_b_rows + n_ab_rows)",
    shower_energy="e_dep_b", w_neg_hits="w_neg_hits_b", w_neg_energy="w_neg_energy_b",
    # 'A+B' rows are counted with B, as in every per-shower split.
    origin_sql=f"p.org IN ({ddl.ORIGIN_B}, {ddl.ORIGIN_AB})",
    present_sql="(n_b_rows + n_ab_rows) > 0",
)
_SINGLE = ShowerColumns(
    key="a", label="Shower", b=0,
    momentum="e1", momentum_bin="e1_bin", theta="theta_a", phi="phi_a",
    deposit="e_dep", hits="n_hits",
    shower_energy="e_dep_a", w_neg_hits="w_neg_hits_a", w_neg_energy="w_neg_energy_a",
    origin_sql="TRUE",
    present_sql="n_hits > 0",
    primary_rows="n_primary_rows",
)
_EVENTS = ShowerColumns(
    key="a", label="Shower", b=0,
    momentum="e1", momentum_bin="e1_bin", theta="theta_a", phi="phi_a",
    deposit="e_dep", hits="n_hits",
    shower_energy=None, w_neg_hits=None, w_neg_energy=None,
    origin_sql=None,
    present_sql="n_hits > 0",
    has_centroids=False,
)


def primary_rows_column() -> str:
    """The primary-tagged row count column of single-shower hit experiments."""
    assert _SINGLE.primary_rows is not None
    return _SINGLE.primary_rows


def of(record: ExperimentRecord, choice: str = "both") -> tuple[ShowerColumns, ...]:
    """The showers a request selects, ``a``, ``b`` or ``both``.

    A single-shower experiment has one shower: ``both`` and ``a`` select it,
    ``b`` is refused naming the parameter. A choice outside
    :data:`SHOWER_CHOICES` is a malformed request, not a capability the data
    lacks, and is the plain validation error.
    """
    if choice not in SHOWER_CHOICES:
        raise ValidationError(
            f"shower must be one of {', '.join(SHOWER_CHOICES)}; got {choice!r}.", field="shower")
    kind = record.kind
    if kind == ddl.KIND_TWO_SHOWER:
        return {"a": (_TWO_A,), "b": (_TWO_B,), "both": (_TWO_A, _TWO_B)}[choice]
    single = _EVENTS if kind == ddl.KIND_SINGLE_EVENTS else _SINGLE
    if choice == "b":
        raise CapabilityError(
            f"shower=b is not available for experiment {record.table_name!r}: it holds one "
            "shower per event.",
            field="shower", capability="shower", kind=kind,
            reason="one shower per event", table_name=record.table_name,
        )
    return (single,)
