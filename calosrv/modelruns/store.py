"""The model-analysis tables: the read the analysis starts from, the one write, the stamp.

Six tables per experiment (``naming.xgb_tables``; their DDL is ``ddl.XGB_COLUMNS``):
``xgbrun_`` one row per task, ``xgbpred_`` the validation-split predictions,
``xgbfold_`` E1, ``xgbimp_`` E5, ``xgbbin_`` E3 and ``xgbtree_`` E4. They are
written together, under the write lock, in one transaction - drop, create,
insert, commit - so a reader sees the previous analysis or the new one, never
half of each, and a failed write leaves the previous one in place.

**The stamp.** A stored analysis is current while every input it was computed
from is unchanged: :data:`analysis.ANALYSIS_VERSION`, each model file's sha256,
the versions of XGBoost, scikit-learn, numpy and pandas, the experiment's
event count with a sha256 of its ``event_number`` column in order, and a
sha256 of every value the analysis read (:meth:`analysis.Dataset.value_hash`:
the momentum bins, the labels and each model's features). Any difference makes
it stale, and :func:`stale_reasons` says which.

The value hash needs the whole feature table read, so it is compared where an
analysis may be queued - the worker before it recomputes (after an ingest or a
rebuild, on Re-analyse), the boot check and ``POST /api/admin/model-runs/scan``
(:func:`expected_stamp` with ``values=True``) - and not by the Admin Settings
list's ``GET``, which compares the cheap part of the stamp only and queues
nothing.

A stored analysis that cannot be read - a table from a release whose columns
differ, a malformed row - reads as missing (:func:`read_runs` returns
``None``), so it is re-run rather than crashing the check.

Column names reach SQL only from the ``ddl`` vocabulary (the pairing's
mapped columns) and table names only through ``naming``.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
from dataclasses import dataclass, replace
from importlib import metadata
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from ..config import Settings
from ..db import archive, naming
from ..db.ddl import XGB_COLUMNS, create_xgb_table, drop_table
from ..db.naming import quote
from ..db.registry import ExperimentRecord
from .analysis import ANALYSIS_VERSION, BINARY, HYPERPARAMETERS, KFOLD, LABEL_KEY, SURROGATE
from .analysis import AnalysisResult, Dataset
from .discovery import TASKS
from .pairing import TASK_LABELS, Pairing, label_column

log = logging.getLogger(__name__)

#: Libraries whose version is part of the stamp, and the distributions that provide them.
LIBRARIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("xgboost", ("xgboost-cpu", "xgboost")),
    ("scikit-learn", ("scikit-learn",)),
    ("numpy", ("numpy",)),
    ("pandas", ("pandas",)),
)


def library_versions() -> dict[str, str]:
    """The installed versions, read from package metadata (nothing is imported)."""
    out: dict[str, str] = {}
    for key, distributions in LIBRARIES:
        for distribution in distributions:
            try:
                out[key] = metadata.version(distribution)
                break
            except metadata.PackageNotFoundError:
                continue
        else:
            out[key] = "absent"
    return out


@dataclass(frozen=True)
class Stamp:
    """What a stored analysis was computed from."""

    analysis_version: int
    sha256: tuple[tuple[str, str], ...]
    versions: tuple[tuple[str, str], ...]
    #: ``None`` when not yet read (the stamp of an attempt that failed before reading).
    n_rows: int | None
    fingerprint: str | None
    #: :meth:`analysis.Dataset.value_hash`; ``None`` when the check did not read the values.
    values: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"analysis_version": self.analysis_version, "sha256": dict(self.sha256),
                "versions": dict(self.versions), "n_rows": self.n_rows,
                "fingerprint": self.fingerprint, "values": self.values}

    def matches(self, other: Stamp | None) -> bool:
        """Equal in every field both stamps know: how a failed attempt is matched to its inputs.

        A field one of them did not read (``None``) is not compared, so a
        failure before the event table was read matches every later check of
        the same models and libraries, and the cheap check (no value hash)
        matches an attempt that read the values.
        """
        if other is None:
            return False
        for mine, theirs in ((self.analysis_version, other.analysis_version),
                             (self.sha256, other.sha256), (self.versions, other.versions),
                             (self.n_rows, other.n_rows), (self.fingerprint, other.fingerprint),
                             (self.values, other.values)):
            if mine is not None and theirs is not None and mine != theirs:
                return False
        return True


def stale_reasons(expected: Stamp, stored: Stamp | None) -> list[str]:
    """Why ``stored`` no longer describes the experiment and its models; empty when current."""
    if stored is None:
        return ["no stored analysis"]
    out: list[str] = []
    if stored.analysis_version != expected.analysis_version:
        out.append(f"analysis version {stored.analysis_version} against {expected.analysis_version}")
    old, new = dict(stored.sha256), dict(expected.sha256)
    for task in TASKS:
        if old.get(task) != new.get(task):
            out.append(f"the {task} model file changed (sha256 {str(old.get(task))[:12]} against "
                       f"{str(new.get(task))[:12]})")
    old_v, new_v = dict(stored.versions), dict(expected.versions)
    for key in sorted(set(old_v) | set(new_v)):
        if old_v.get(key) != new_v.get(key):
            out.append(f"{key} {old_v.get(key)} against {new_v.get(key)}")
    if stored.n_rows != expected.n_rows or stored.fingerprint != expected.fingerprint:
        out.append(f"the event table changed ({stored.n_rows:,} events analysed against "
                   f"{expected.n_rows:,} now)")
    elif expected.values is not None and stored.values != expected.values:
        out.append("the event table's feature or label values changed (same events, other "
                   "values)")
    return out


# ------------------------------------------------------------------ reads --


def table_exists(con: duckdb.DuckDBPyConnection, physical: str) -> bool:
    return bool(con.execute(
        "SELECT count(*) FROM duckdb_tables() WHERE table_name = ?", [physical]).fetchone()[0])


def event_fingerprint(con: duckdb.DuckDBPyConnection, name: str) -> tuple[int, str]:
    """``(n, sha256)`` of the event table's ``event_number`` column in ascending order."""
    raw = con.execute(
        f"SELECT event_number FROM {quote(naming.event_table(name))} ORDER BY event_number"
    ).fetchnumpy()["event_number"]
    ids = np.ascontiguousarray(np.asarray(raw, dtype="<i8"))
    return int(ids.size), hashlib.sha256(ids.tobytes()).hexdigest()


def model_stamp(pairing: Pairing) -> Stamp:
    """The part of the stamp known without reading the experiment: version, models, libraries."""
    return Stamp(
        analysis_version=ANALYSIS_VERSION,
        sha256=tuple((task, pairing.models[task].sha256) for task in TASKS),
        versions=tuple(sorted(library_versions().items())),
        n_rows=None, fingerprint=None,
    )


def expected_stamp(con: duckdb.DuckDBPyConnection, record: ExperimentRecord,
                   pairing: Pairing, values: bool = False) -> Stamp:
    """The stamp an analysis of the experiment as it is now would carry.

    ``values`` also reads the feature table and hashes it (a read of every
    feature, as the analysis makes); without it the value hash is ``None`` and
    is not compared.
    """
    n, fingerprint = event_fingerprint(con, record.table_name)
    digest = None
    if values:
        digest = read_dataset(con, None, record, pairing).value_hash()
    return replace(model_stamp(pairing), n_rows=n, fingerprint=fingerprint, values=digest)


def read_runs(con: duckdb.DuckDBPyConnection, name: str) -> dict[str, dict[str, Any]] | None:
    """The stored per-task rows, JSON columns parsed; ``None`` when there is no analysis.

    A table this release cannot read - written by a release whose columns
    differ - is no analysis either: the check re-runs it instead of failing.
    """
    physical = naming.xgb_table("run", name)
    columns = [c for c, _ in XGB_COLUMNS["run"]]
    try:
        if not table_exists(con, physical):
            return None
        rows = con.execute(f"SELECT {', '.join(columns)} FROM {quote(physical)}").fetchall()
    except duckdb.Error as exc:
        log.warning("The stored model analysis of %r cannot be read (%s); it is treated as "
                    "missing", name, exc)
        return None
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        data = dict(zip(columns, row))
        for key in ("labels", "label_columns", "features", "versions", "details", "timings"):
            try:
                data[key] = json.loads(data[key]) if data[key] else None
            except (TypeError, ValueError):
                data[key] = None
        out[data["task"]] = data
    return out or None


def stored_stamp(runs: dict[str, dict[str, Any]] | None) -> Stamp | None:
    """The stamp the stored rows carry; ``None`` when they are missing or malformed."""
    if not runs or any(task not in runs for task in TASKS):
        return None
    first = runs[TASKS[0]]
    try:
        return Stamp(
            analysis_version=int(first["analysis_version"]),
            sha256=tuple((task, str(runs[task]["sha256"])) for task in TASKS),
            versions=tuple(sorted((first["versions"] or {}).items())),
            n_rows=int(first["n_rows"]), fingerprint=str(first["event_fingerprint"]),
            values=(first.get("details") or {}).get("value_hash"),
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _filled(values: Any) -> np.ndarray:
    """A fetched column as float64 with NaN for NULL."""
    return np.ma.filled(np.ma.asarray(values).astype(np.float64), np.nan)


def archive_increasing(con: duckdb.DuckDBPyConnection, settings: Settings,
                       record: ExperimentRecord) -> bool | None:
    """Whether the archived file's event ids rise strictly in file order; ``None`` without one."""
    schema = record.schema
    manifest = archive.read_manifest(settings, record.table_name)
    if schema is None or manifest is None or not manifest.parts:
        return None
    parts = archive.part_paths(settings, record.table_name, manifest)
    key = quote(schema.event_key)
    ids = con.execute(f"SELECT {key} FROM {archive.relation_sql(parts)}").fetchnumpy()[schema.event_key]
    ids = _filled(ids)
    return bool(ids.size < 2 or np.all(np.diff(ids) > 0))


def read_dataset(con: duckdb.DuckDBPyConnection, settings: Settings | None, record: ExperimentRecord,
                 pairing: Pairing) -> Dataset:
    """The event table in ``event_number`` order, as :mod:`analysis` reads it.

    ``settings`` locates the archive whose event order is checked
    (``archive_increasing``); ``None`` skips that read, for the stamp's value
    hash, which needs the values only.

    Each model's features become a DataFrame named and ordered as the model's,
    so ``predict`` checks them against the booster. A feature the model calls
    ``int`` keeps its integer type unless it holds a NULL, which XGBoost then
    reads as missing (NaN), as it would a gap in the notebook's CSV.
    """
    wanted = ["event_number", "e1_bin"]
    for labels in TASK_LABELS.values():
        wanted += [label_column(label) for label in labels]
    for task in TASKS:
        wanted += [column for _, column in pairing.columns[task]]
    columns = list(dict.fromkeys(wanted))
    raw = con.execute(
        f"SELECT {', '.join(quote(c) for c in columns)} "
        f"FROM {quote(naming.event_table(record.table_name))} ORDER BY event_number"
    ).fetchnumpy()
    labels = {label: _filled(raw[label_column(label)])
              for task_labels in TASK_LABELS.values() for label in task_labels}
    features: dict[str, pd.DataFrame] = {}
    for task in TASKS:
        model = pairing.models[task]
        types = dict(zip(model.feature_names, model.feature_types))
        data: dict[str, np.ndarray] = {}
        for feature, column in pairing.columns[task]:
            values = np.ma.asarray(raw[column])
            if types.get(feature) == "int" and not np.ma.is_masked(values):
                data[feature] = np.asarray(values, dtype=np.int64)
            else:
                data[feature] = _filled(values)
        features[task] = pd.DataFrame(data, columns=list(model.feature_names))
    return Dataset(
        event_number=np.asarray(_filled(raw["event_number"]), dtype=np.int64),
        e1_bin=_filled(raw["e1_bin"]),
        labels=labels,
        features=features,
        archive_increasing=archive_increasing(con, settings, record) if settings is not None else None,
    )


# ------------------------------------------------------------------ write --


def _insert(con: duckdb.DuckDBPyConnection, physical: str, role: str, frame: pd.DataFrame) -> None:
    """Insert a DataFrame whose columns are the role's, in the DDL's order."""
    if frame.empty:
        return
    columns = [c for c, _ in XGB_COLUMNS[role]]
    view = f"xgb_{role}_frame"
    con.register(view, frame[columns])
    try:
        con.execute(f"INSERT INTO {quote(physical)} SELECT * FROM {view}")
    finally:
        con.unregister(view)


def _run_rows(name: str, pairing: Pairing, result: AnalysisResult, stamp: Stamp,
              increasing: bool | None, created_at: dt.datetime) -> pd.DataFrame:
    rows = []
    for task in TASKS:
        t = result.tasks[task]
        model = pairing.models[task]
        labels = list(TASK_LABELS[task])
        details: dict[str, Any] = {
            "model": model.header(),
            "surrogate_outputs": t.surrogate_outputs,
            "hyperparameters": HYPERPARAMETERS,
            "kfold": KFOLD,
            "surrogate": SURROGATE,
            "test_size": 0.2,
            "nulls": result.nulls,
            "split": t.split,
            "value_hash": stamp.values,
        }
        if t.output_order:
            details["output_order"] = t.output_order
        circular = {str(node["node_id"]): node["circular"] for node in t.tree if node.get("circular")}
        if circular:
            details["surrogate_circular"] = circular
        if task == "momentum":
            b = result.binary
            details["binary"] = {
                "design": BINARY, "pool_0": b.pool_0, "pool_1": b.pool_1, "fallback": b.fallback,
                "n_0": b.n_0, "n_1": b.n_1, "metrics": b.metrics,
            }
        rows.append({
            "task": task, "species": pairing.species, "seed": pairing.seed,
            "model_file": model.relative, "sha256": model.sha256,
            "labels": json.dumps(labels),
            "label_columns": json.dumps([label_column(label) for label in labels]),
            "features": json.dumps(list(model.feature_names)),
            "versions": json.dumps(dict(stamp.versions), sort_keys=True),
            "analysis_version": stamp.analysis_version,
            "n_rows": result.n_rows, "n_train": t.n_train, "n_val": t.n_val,
            "event_fingerprint": stamp.fingerprint,
            "archive_increasing": increasing,
            "split_ratio_42": t.split_ratios[42], "split_ratio_0": t.split_ratios.get(0),
            "split_ratio_7": t.split_ratios.get(7), "split_reproduced": t.split_reproduced,
            "surrogate_r2": t.surrogate_r2, "surrogate_mae": t.surrogate_mae,
            "details": json.dumps(details, sort_keys=True),
            "timings": json.dumps(result.timings, sort_keys=True),
            "nthread": result.nthread,
            "created_at": created_at,
        })
    frame = pd.DataFrame(rows)
    frame["archive_increasing"] = frame["archive_increasing"].astype("boolean")
    return frame


def _pred_rows(data: Dataset, result: AnalysisResult) -> pd.DataFrame:
    parts = []
    for task in TASKS:
        t = result.tasks[task]
        pred = t.val_pred.reshape(t.val_rows.size, -1)
        for k, label in enumerate(TASK_LABELS[task]):
            parts.append(pd.DataFrame({
                "task": task,
                "event_number": data.event_number[t.val_rows].astype(np.int32),
                "e1_bin": pd.array(np.where(np.isfinite(data.e1_bin[t.val_rows]),
                                            data.e1_bin[t.val_rows], np.nan)).astype("UInt8"),
                "label": LABEL_KEY[label],
                "y_true": data.labels[label][t.val_rows],
                "y_pred": pred[:, k],
            }))
    return pd.concat(parts, ignore_index=True)


def _fold_rows(result: AnalysisResult) -> pd.DataFrame:
    rows = [{"task": task, "fold": f["fold"], "n_train": f["n_train"], "n_val": f["n_val"],
             "metric": metric, "label": label, "value": value}
            for task in TASKS for f in result.tasks[task].folds
            for (metric, label), value in f["values"].items()]
    return pd.DataFrame(rows)


def _imp_rows(result: AnalysisResult) -> pd.DataFrame:
    rows = []
    for task in TASKS:
        t = result.tasks[task]
        for feature, (norm, gain, weight, cover) in t.importance.items():
            rows.append({"task": task, "source": "shipped", "fold": None, "feature": feature,
                         "gain_norm": norm, "raw_gain": gain, "raw_weight": weight,
                         "raw_cover": cover})
        for fold, gains in enumerate(t.fold_importance):
            for feature, norm in gains.items():
                rows.append({"task": task, "source": "fold", "fold": fold, "feature": feature,
                             "gain_norm": norm, "raw_gain": None, "raw_weight": None,
                             "raw_cover": None})
    frame = pd.DataFrame(rows)
    frame["fold"] = frame["fold"].astype("Int32")
    return frame


def _bin_rows(data: Dataset, result: AnalysisResult) -> pd.DataFrame:
    b = result.binary
    return pd.DataFrame({
        "ord": np.arange(b.rows.size, dtype=np.int32),
        "event_number": data.event_number[b.rows].astype(np.int32),
        "p": b.p, "y_true": b.y_true.astype(np.uint8), "y_pred_value": b.value,
        "y_pred": b.y_pred.astype(np.uint8),
    })


def _tree_rows(result: AnalysisResult) -> pd.DataFrame:
    rows = []
    for task in TASKS:
        for node in result.tasks[task].tree:
            for label, value in node["values"].items():
                rows.append({"task": task, "node_id": node["node_id"], "depth": node["depth"],
                             "children_left": node["children_left"],
                             "children_right": node["children_right"],
                             "feature": node["feature"], "threshold": node["threshold"],
                             "n_node_samples": node["n_node_samples"],
                             "impurity": node["impurity"], "label": label, "value": value,
                             "variance": node["variance"][label]})
    return pd.DataFrame(rows)


def write(con: duckdb.DuckDBPyConnection, name: str, pairing: Pairing, data: Dataset,
          result: AnalysisResult, stamp: Stamp) -> None:
    """Replace the experiment's six tables with this analysis, in one transaction."""
    tables = naming.xgb_tables(name)
    created_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    frames = {
        "run": _run_rows(name, pairing, result, stamp, data.archive_increasing, created_at),
        "pred": _pred_rows(data, result),
        "fold": _fold_rows(result),
        "imp": _imp_rows(result),
        "bin": _bin_rows(data, result),
        "tree": _tree_rows(result),
    }
    con.execute("BEGIN TRANSACTION")
    try:
        for role, physical in tables.items():
            con.execute(drop_table(physical))
            con.execute(create_xgb_table(physical, role))
            _insert(con, physical, role, frames[role])
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    log.info("Model analysis of %r stored (%s)", name,
             ", ".join(f"{role} {len(frame):,} rows" for role, frame in frames.items()))


# ------------------------------------------------------------ route reads --


def read_folds(con: duckdb.DuckDBPyConnection, name: str, task: str) -> list[tuple]:
    """``(fold, n_train, n_val, metric, label, value)`` rows of one task, fold-ordered."""
    return con.execute(
        f"SELECT fold, n_train, n_val, metric, label, value "
        f"FROM {quote(naming.xgb_table('fold', name))} WHERE task = ? ORDER BY fold, label, metric",
        [task]).fetchall()


def read_importance(con: duckdb.DuckDBPyConnection, name: str, task: str) -> list[tuple]:
    """``(source, fold, feature, gain_norm, raw_gain, raw_weight, raw_cover)`` rows of one task."""
    return con.execute(
        f"SELECT source, fold, feature, gain_norm, raw_gain, raw_weight, raw_cover "
        f"FROM {quote(naming.xgb_table('imp', name))} WHERE task = ? "
        "ORDER BY source, fold NULLS FIRST, feature", [task]).fetchall()


def read_binary(con: duckdb.DuckDBPyConnection, name: str) -> dict[str, np.ndarray]:
    """E3's rows in the notebook's shuffled order."""
    raw = con.execute(
        f"SELECT ord, event_number, p, y_true, y_pred_value, y_pred "
        f"FROM {quote(naming.xgb_table('bin', name))} ORDER BY ord").fetchnumpy()
    return {k: np.asarray(v) for k, v in raw.items()}


def read_tree(con: duckdb.DuckDBPyConnection, name: str, task: str) -> list[tuple]:
    """``(node_id, depth, left, right, feature, threshold, n, impurity, label, value, variance)``."""
    return con.execute(
        f"SELECT node_id, depth, children_left, children_right, feature, threshold, "
        f"n_node_samples, impurity, label, value, variance "
        f"FROM {quote(naming.xgb_table('tree', name))} WHERE task = ? ORDER BY node_id, label",
        [task]).fetchall()


def read_holdout(con: duckdb.DuckDBPyConnection, record: ExperimentRecord, task: str,
                 where_sql: str, params: dict[str, Any]) -> dict[str, np.ndarray]:
    """The validation rows of the selection: ``bin``, and ``true_<label>`` / ``pred_<label>``.

    ``where_sql`` is a :class:`~calosrv.query.filters.FilterSpec` body on the
    event table, aliased ``e``. One row per selected validation event; a value
    the analysis did not store reads as NaN.
    """
    pred = quote(naming.xgb_table("pred", record.table_name))
    event = quote(naming.event_table(record.table_name))
    labels = [LABEL_KEY[label] for label in TASK_LABELS[task]]
    pivots = []
    for label in labels:
        pivots.append(f"max(CASE WHEN x.label = '{label}' THEN x.y_true END) AS true_{label}")
        pivots.append(f"max(CASE WHEN x.label = '{label}' THEN x.y_pred END) AS pred_{label}")
    raw = con.execute(
        f"SELECT x.event_number, CAST(any_value(x.e1_bin) AS DOUBLE) AS bin, {', '.join(pivots)} "
        f"FROM {pred} x JOIN {event} e ON e.event_number = x.event_number "
        f"WHERE x.task = $task AND {where_sql} "
        "GROUP BY x.event_number ORDER BY x.event_number",
        {**params, "task": task},
    ).fetchnumpy()
    return {k: _filled(v) for k, v in raw.items()}


def count_selected(con: duckdb.DuckDBPyConnection, record: ExperimentRecord,
                   where_sql: str, params: dict[str, Any]) -> int:
    """Events of the selection, validation and training rows alike."""
    return int(con.execute(
        f"SELECT count(*) FROM {quote(naming.event_table(record.table_name))} e WHERE {where_sql}",
        params).fetchone()[0])
