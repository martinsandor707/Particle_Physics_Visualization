"""The model-analysis worker: one analysis at a time, off the ingest worker and the write lock.

An analysis refits ten XGBoost models (seconds each on 100,000 events), so it
runs on a single-slot worker of its own - never on the ingest worker, which
would hold every upload behind it, and never under the write lock, which
would stall every write in the process. It reads the event table through a
read cursor, computes with half the cores (``config.model_threads``) so the
server keeps answering, and takes the write lock only for the one transaction
that stores the result (``store.write``).

**When it runs.** After an aggregate experiment becomes ready (an ingest or a
rebuild: :func:`after_ready`, called by ``ingest/jobs.py``), at boot for every
ready experiment whose stored analysis is missing or stale (:func:`boot`,
called by the application's lifespan, never at import), on the Admin Settings
panel's Rescan models (``POST /api/admin/model-runs/scan``,
:meth:`ModelRunStore.scan`) and on its Re-analyse button. The list itself
(``GET /api/admin/model-runs``, :meth:`ModelRunStore.report`) is read-only: it
re-pairs and compares the cheap part of the stamp, may report an analysis
stale, and never queues one. A run first reads the event table and compares
the whole stamp, value hash included (``store.stale_reasons``): a current
analysis is not recomputed unless Re-analyse forces it, so a rebuild that
changes nothing costs one read.

**Queueing** is a test-and-set under one lock (:meth:`ModelRunStore._submit`):
an analysis already queued or running is never queued twice nor reset to
"queued", whichever of the boot check, a scan, the ingest hook and Re-analyse
gets there first.

**Status** lives in memory, per experiment, for the capability block and the
Admin Settings list: ``unpaired`` (with the pairing's reason), ``not_ready``,
``queued``, ``running`` (with its step), ``done``, ``failed`` (with the error;
not retried by a rescan while its inputs are unchanged, only by Re-analyse,
a restart or a changed input) and ``stale`` (a stored analysis found out of
date and not queued: by the list's read-only check, or when a run was
discarded because the experiment changed under it). A state is tied to the
registry row's ``created_at``: an experiment replaced by a new ingest is a new
experiment, and a deleted one is forgotten (:func:`forget`).

**Shutdown** waits for the worker (:meth:`ModelRunStore.shutdown`): the run in
progress stops at its next step boundary, so it never queries a database the
application is closing.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from typing import Any


from ..db import ddl, registry
from ..db.connection import Database
from ..db.registry import ExperimentRecord
from ..text import typographic
from . import discovery, pairing as pairing_mod, store
from .analysis import N_STEPS, STEPS
from .pairing import TASK_LABELS, Pairing

log = logging.getLogger(__name__)

STATUS_UNPAIRED = "unpaired"
STATUS_NOT_READY = "not_ready"
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_STALE = "stale"

STATUSES: tuple[str, ...] = (STATUS_UNPAIRED, STATUS_NOT_READY, STATUS_QUEUED, STATUS_RUNNING,
                             STATUS_DONE, STATUS_FAILED, STATUS_STALE)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(moment: dt.datetime | None) -> str | None:
    return moment.isoformat(timespec="seconds") if moment else None


@dataclass
class RunState:
    """One aggregate experiment's analysis, as the capability block and Admin Settings read it."""

    table_name: str
    display_name: str
    created_at: dt.datetime | None
    pairing: Pairing
    status: str
    reason: str | None = None
    error: str | None = None
    step: int = 0
    step_label: str = ""
    stale_reasons: list[str] = field(default_factory=list)
    #: The stored rows (``store.read_runs``) of a done analysis.
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    queued_at: dt.datetime | None = None
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None
    duration_s: float | None = None
    timings: dict[str, float] = field(default_factory=dict)
    force: bool = False
    rerun: bool = False
    #: The stamp the current run is computing from, and the one a failed run was attempted
    #: on, so an unchanged input is not retried in a loop by every rescan.
    attempt_stamp: store.Stamp | None = None
    failed_stamp: store.Stamp | None = None

    @property
    def current(self) -> bool:
        return self.status == STATUS_DONE

    def gate_reason(self) -> str | None:
        """The capability reason while the gate is shut; ``None`` when it is open."""
        reason = self._gate_reason()
        return typographic(reason) if reason is not None else None

    def _gate_reason(self) -> str | None:
        if self.status == STATUS_DONE:
            return None
        if self.status == STATUS_UNPAIRED:
            return f"No XGBoost models pair with this experiment: {self.reason}"
        if self.status == STATUS_NOT_READY:
            return f"The XGBoost analysis waits for the experiment: {self.reason}"
        if self.status == STATUS_QUEUED:
            why = f" ({'; '.join(self.stale_reasons)})" if self.stale_reasons else ""
            return f"XGBoost analysis queued{why}; the cards open when it is done."
        if self.status == STATUS_RUNNING:
            return (f"Analysing: {self.step} of {N_STEPS} steps ({self.step_label}). The cards "
                    "open when it is done.")
        if self.status == STATUS_FAILED:
            return f"The XGBoost analysis failed: {self.error}"
        return (f"The stored XGBoost analysis is stale ({'; '.join(self.stale_reasons)}); "
                "Rescan models or Re-analyse in Admin Settings › Model runs queues it.")

    def model_runs(self) -> list[dict[str, Any]]:
        """The capability block's ``model_runs``: one entry per paired task, empty when unpaired."""
        if not self.pairing.paired:
            return []
        out = []
        for task in discovery.TASKS:
            model = self.pairing.models[task]
            stored = self.runs.get(task) if self.status == STATUS_DONE else None
            out.append({
                "task": task,
                "species": self.pairing.species,
                "seed": self.pairing.seed,
                "model_file": model.relative,
                "labels": [store.LABEL_KEY[label] for label in TASK_LABELS[task]],
                "n_holdout": int(stored["n_val"]) if stored else None,
                "split_reproduced": bool(stored["split_reproduced"]) if stored else None,
                "status": self.status,
            })
        return out

    def as_dict(self) -> dict[str, Any]:
        """One row of the Admin Settings list."""
        progress = (self.step / N_STEPS) if self.status == STATUS_RUNNING else (
            1.0 if self.status == STATUS_DONE else 0.0)
        runs = []
        for task in discovery.TASKS:
            stored = self.runs.get(task)
            if stored is None:
                continue
            runs.append({
                "task": task, "model_file": stored["model_file"], "sha256": stored["sha256"][:12],
                "n_rows": int(stored["n_rows"]), "n_train": int(stored["n_train"]),
                "n_holdout": int(stored["n_val"]),
                "split": _split_brief(stored),
                "analysis_version": int(stored["analysis_version"]),
                "created_at": stored["created_at"].isoformat() if stored.get("created_at") else None,
            })
        return {
            "table_name": self.table_name,
            "display_name": self.display_name,
            **self.pairing.as_dict(),
            "status": self.status,
            "reason": self.gate_reason(),
            "error": self.error,
            "step": self.step,
            "steps": N_STEPS,
            "step_label": self.step_label,
            "progress": round(progress, 4),
            "stale_reasons": list(self.stale_reasons),
            "runs": runs,
            "queued_at": _iso(self.queued_at),
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            "duration_s": None if self.duration_s is None else round(self.duration_s, 2),
            "timings": dict(self.timings),
        }


def _split_brief(stored: dict[str, Any]) -> dict[str, Any]:
    """The Admin Settings list's split check: the 42 ratio against the others' maximum."""
    split = (stored.get("details") or {}).get("split") or {}
    return {"reproduced": bool(stored["split_reproduced"]),
            "ratio_42": stored["split_ratio_42"],
            "max_others": split.get("max_others"),
            "seed_of_max": split.get("seed_of_max"),
            "n_others": len(split.get("seeds_others") or []),
            "margin": split.get("margin")}


class ModelRunStore:
    """The worker and the per-experiment states."""

    def __init__(self, database: Database) -> None:
        self._db = database
        self._settings = database.settings
        self._lock = threading.RLock()
        self._states: dict[str, RunState] = {}
        self._catalogue: discovery.Catalogue | None = None
        self._closing = threading.Event()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="calosrv-modelruns")

    # ------------------------------------------------------------ reads --

    @property
    def catalogue(self) -> discovery.Catalogue | None:
        return self._catalogue

    def rescan(self) -> discovery.Catalogue:
        self._catalogue = discovery.scan(self._settings.model_dir)
        return self._catalogue

    def lookup(self, record: ExperimentRecord) -> RunState | None:
        """The state of exactly this ingest of ``record``, or ``None``. No IO."""
        with self._lock:
            state = self._states.get(record.table_name)
        if state is None or state.created_at != record.created_at:
            return None
        return state

    def states(self) -> list[RunState]:
        with self._lock:
            return sorted(self._states.values(), key=lambda s: s.table_name)

    def busy(self) -> list[str]:
        with self._lock:
            return [s.table_name for s in self._states.values()
                    if s.status in (STATUS_QUEUED, STATUS_RUNNING)]

    # ----------------------------------------------------------- reconcile --

    def refresh(self, queue: bool = True) -> list[RunState]:
        """Rescan the models folder and re-pair every aggregate experiment.

        Each ready, paired experiment's stored stamp is compared with its
        inputs: a current analysis is ``done``, a missing or stale one is
        queued (``queue``) - unless the last attempt failed on exactly these
        inputs, which waits for Re-analyse rather than failing in a loop.
        With ``queue`` the whole stamp is compared, the feature and label
        values included (the boot check, Rescan models); without it, the
        cheap part only, and a missing or stale analysis is reported
        ``stale``, never queued (the Admin Settings list).
        """
        catalogue = self.rescan()
        with self._db.read_cursor() as con:
            records = [r for r in registry.list_experiments(con)
                       if r.kind == ddl.KIND_SINGLE_EVENTS]
            names = {r.table_name for r in records}
            for record in records:
                self._reconcile(con, record, catalogue, queue)
        with self._lock:
            for name in [n for n in self._states if n not in names]:
                if self._states[name].status not in (STATUS_QUEUED, STATUS_RUNNING):
                    del self._states[name]
        return self.states()

    def report(self) -> list[RunState]:
        """The Admin Settings list: re-pair and compare, read-only - nothing is queued."""
        return self.refresh(queue=False)

    def scan(self) -> list[RunState]:
        """Rescan models: re-pair, compare the whole stamp, queue every missing or stale analysis."""
        return self.refresh(queue=True)

    def forget(self, name: str) -> None:
        """Drop the state of a deleted experiment; a run on the worker discards itself."""
        with self._lock:
            state = self._states.get(name)
            if state is None:
                return
            if state.status in (STATUS_QUEUED, STATUS_RUNNING):
                # The worker re-reads the registry before reading or writing and finds it
                # gone; it must not queue the deleted experiment again.
                state.rerun = False
                return
            del self._states[name]

    def _state_for(self, record: ExperimentRecord, pairing: Pairing) -> RunState:
        with self._lock:
            state = self._states.get(record.table_name)
            if state is None or state.created_at != record.created_at:
                if state is not None and state.status in (STATUS_QUEUED, STATUS_RUNNING):
                    # A run of the replaced ingest is still on the worker: it checks
                    # the registry before writing and discards itself; run again after it.
                    state.rerun = True
                    state.created_at, state.pairing = record.created_at, pairing
                    return state
                state = RunState(record.table_name, record.display_name, record.created_at,
                                 pairing, STATUS_UNPAIRED)
                self._states[record.table_name] = state
            state.display_name = record.display_name
            state.pairing = pairing
            return state

    def _reconcile(self, con, record: ExperimentRecord, catalogue: discovery.Catalogue,
                   queue: bool) -> RunState:
        pairing = pairing_mod.pair(record, catalogue)
        state = self._state_for(record, pairing)
        with self._lock:
            if state.status in (STATUS_QUEUED, STATUS_RUNNING):
                return state
            if not record.is_ready:
                state.status, state.reason = STATUS_NOT_READY, f"its status is {record.status}."
                return state
            if not pairing.paired:
                state.status, state.reason, state.runs = STATUS_UNPAIRED, pairing.reason, {}
                return state
        runs = store.read_runs(con, record.table_name)
        try:
            expected = store.expected_stamp(con, record, pairing, values=queue)
        except Exception as exc:  # noqa: BLE001 - the check must never fail the list or the boot
            # The event table itself cannot be read (duckdb.Error, or values the analysis
            # cannot take): a failure on these models, shown and not retried until something
            # changes (Re-analyse, a rebuild, a restart).
            log.warning("Model-analysis check of %r could not read the event table: %s",
                        record.table_name, exc)
            with self._lock:
                if state.status not in (STATUS_QUEUED, STATUS_RUNNING):
                    state.status, state.runs = STATUS_FAILED, {}
                    state.error = f"the event table could not be read: {exc}"
                    state.failed_stamp = store.model_stamp(pairing)
            return state
        reasons = store.stale_reasons(expected, store.stored_stamp(runs))
        with self._lock:
            if state.status in (STATUS_QUEUED, STATUS_RUNNING):
                # Queued by another caller while the stamp was read: leave it to the worker.
                return state
            state.reason = None
            if not reasons:
                state.status, state.runs, state.stale_reasons = STATUS_DONE, runs or {}, []
                state.error = None
                if runs:
                    first = runs[discovery.TASKS[0]]
                    state.timings = dict(first.get("timings") or {})
                return state
            if state.status == STATUS_FAILED and expected.matches(state.failed_stamp):
                # The last attempt failed on exactly these inputs: shown, not retried.
                return state
            state.runs, state.stale_reasons = {}, [] if runs is None else reasons
            if not queue:
                state.status = STATUS_STALE
                state.stale_reasons = reasons
                return state
        self._submit(state, force=False)
        return state

    # -------------------------------------------------------------- submit --

    def submit(self, record: ExperimentRecord, force: bool = False) -> RunState:
        """Queue an analysis of ``record`` (Re-analyse, or after an ingest)."""
        catalogue = self.rescan()
        pairing = pairing_mod.pair(record, catalogue)
        state = self._state_for(record, pairing)
        with self._lock:
            if state.status not in (STATUS_QUEUED, STATUS_RUNNING):
                if not record.is_ready:
                    state.status, state.reason = STATUS_NOT_READY, f"its status is {record.status}."
                    return state
                if not pairing.paired:
                    state.status, state.reason, state.runs = STATUS_UNPAIRED, pairing.reason, {}
                    return state
        self._submit(state, force)
        return state

    def _submit(self, state: RunState, force: bool) -> bool:
        """Queue ``state``'s analysis: a test-and-set under one lock. Whether it was queued.

        An analysis already queued takes ``force`` and stays queued once; one
        running is asked to run again after it (``rerun``), never reset to
        "queued" under the worker.
        """
        with self._lock:
            if self._closing.is_set():
                return False
            if state.status == STATUS_RUNNING:
                state.rerun = True
                state.force = state.force or force
                return False
            if state.status == STATUS_QUEUED:
                state.force = state.force or force
                return False
            state.status, state.error, state.force = STATUS_QUEUED, None, force
            state.step, state.step_label = 0, ""
            state.queued_at, state.started_at, state.finished_at = _now(), None, None
            state.duration_s = None
            try:
                self._executor.submit(self._run, state.table_name)
            except RuntimeError:
                # The executor shut down between the check above and here.
                return False
        log.info("Model analysis of %r queued%s", state.table_name,
                 f" ({'; '.join(state.stale_reasons)})" if state.stale_reasons else "")
        return True

    # ----------------------------------------------------------------- run --

    def _progress(self, state: RunState, step: int, label: str) -> None:
        with self._lock:
            state.step, state.step_label = step, label

    def _run(self, name: str) -> None:
        with self._lock:
            state = self._states.get(name)
            if state is None or state.status != STATUS_QUEUED:
                return
            state.status, state.started_at = STATUS_RUNNING, _now()
            force, state.force = state.force, False
        clock = time.perf_counter()
        try:
            outcome = self._analyse(state, force)
        except Exception as exc:  # noqa: BLE001 - the worker must never die silently
            from .analysis import Cancelled

            if isinstance(exc, Cancelled):
                log.info("Model analysis of %r stopped: the server is shutting down", name)
                with self._lock:
                    state.status, state.error = STATUS_QUEUED, None
                return
            log.error("Model analysis of %r failed: %s\n%s", name, exc, traceback.format_exc())
            with self._lock:
                state.status, state.error = STATUS_FAILED, str(exc)
                state.runs, state.failed_stamp = {}, state.attempt_stamp
        else:
            with self._lock:
                if outcome is not None:
                    state.status, state.runs, state.error = STATUS_DONE, outcome, None
                    state.stale_reasons = []
        finally:
            with self._lock:
                state.finished_at = _now()
                state.duration_s = time.perf_counter() - clock
                if state.status == STATUS_RUNNING:
                    # Discarded: the experiment changed under the run.
                    state.status = STATUS_STALE
                    state.stale_reasons = ["the experiment changed while it was analysed"]
                again, again_force = state.rerun, state.force
                state.rerun, state.force = False, False
        if again and not self._closing.is_set():
            with self._db.read_cursor() as con:
                record = registry.get_experiment(con, name)
            if record is not None:
                self.submit(record, force=again_force)

    def _analyse(self, state: RunState, force: bool) -> dict[str, dict[str, Any]] | None:
        """Read, compare the stamp, compute, write. The stored rows, or ``None`` if discarded."""
        from . import analysis

        name = state.table_name
        self._progress(state, 1, STEPS[0])
        with self._lock:
            # Nothing is known of this attempt's inputs yet: a failure before the first
            # read records no stamp, rather than the previous attempt's.
            state.attempt_stamp = None
        with self._db.read_cursor() as con:
            record = registry.get_experiment(con, name)
            if record is None or not record.is_ready:
                with self._lock:
                    state.status = STATUS_NOT_READY
                    state.reason = "it is no longer ready." if record else "it was deleted."
                return None
            pairing = pairing_mod.pair(record, self.rescan())
            if not pairing.paired:
                with self._lock:
                    state.status, state.reason, state.pairing = STATUS_UNPAIRED, pairing.reason, pairing
                return None
            with self._lock:
                # Set before any step that can fail, so a failure is matched to its inputs.
                state.attempt_stamp = store.model_stamp(pairing)
            runs = store.read_runs(con, name)
            expected = store.expected_stamp(con, record, pairing)
            with self._lock:
                state.attempt_stamp = expected
            data = store.read_dataset(con, self._settings, record, pairing)
            expected = replace(expected, values=data.value_hash())
            reasons = store.stale_reasons(expected, store.stored_stamp(runs))
            with self._lock:
                state.attempt_stamp = expected
            if not reasons and not force:
                log.info("Model analysis of %r is current; nothing recomputed", name)
                return runs
            with self._lock:
                state.stale_reasons = [] if runs is None else reasons
        result = analysis.run(
            data, pairing.models, self._settings.model_threads,
            progress=lambda step, label: self._progress(state, step, label),
            should_stop=self._closing.is_set, first_step=1,
        )
        self._progress(state, N_STEPS, STEPS[-1])
        with self._db.write_lock() as con:
            current = registry.get_experiment(con, name)
            if (current is None or not current.is_ready
                    or current.created_at != record.created_at
                    or store.event_fingerprint(con, name) != (expected.n_rows, expected.fingerprint)):
                log.info("Model analysis of %r discarded: the experiment changed while it ran", name)
                with self._lock:
                    state.rerun = state.rerun or current is not None
                return None
            store.write(con, name, pairing, data, result, expected)
            runs = store.read_runs(con, name)
        with self._lock:
            state.timings = dict(result.timings)
            state.failed_stamp = None
        log.info("Model analysis of %r done in %.1f s (%d events, %d threads)", name,
                 sum(result.timings.values()), result.n_rows, result.nthread)
        return runs

    def shutdown(self) -> None:
        """Stop: cancel what is queued and wait for the run in progress to stop.

        The run stops at its next step boundary (``should_stop``), so the
        wait is at most one step - a fold refit, seconds on 100,000 events -
        and the caller can close the database after it with no query in
        flight.
        """
        self._closing.set()
        self._executor.shutdown(wait=True, cancel_futures=True)


# ------------------------------------------------------------ singleton --

_store: ModelRunStore | None = None
_store_lock = threading.Lock()


def get_model_runs(database: Database | None = None) -> ModelRunStore:
    """The process-wide store, created on the first call with a database."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                if database is None:
                    raise RuntimeError("get_model_runs() needs a Database on its first call.")
                _store = ModelRunStore(database)
    return _store


def current() -> ModelRunStore | None:
    """The store if the application started one; ``None`` in a bare query test."""
    return _store


def reset_model_runs() -> None:
    global _store
    if _store is not None:
        _store.shutdown()
        _store = None


def lookup(record: ExperimentRecord) -> RunState | None:
    """The capability block's view of ``record``'s analysis. No IO."""
    found = _store
    return found.lookup(record) if found is not None else None


def boot(database: Database) -> list[RunState]:
    """At startup: pair every aggregate experiment and queue the missing or stale analyses."""
    found = get_model_runs(database)
    try:
        return found.refresh(queue=True)
    except Exception:  # noqa: BLE001 - a broken models folder must never stop the boot
        log.exception("The model-analysis boot check failed; the XGBoost cards stay shut")
        return []


def forget(name: str) -> None:
    """Experiment ``name`` was deleted: drop its state. No IO."""
    found = _store
    if found is not None:
        found.forget(name)


def after_ready(name: str) -> RunState | None:
    """Experiment ``name`` became ready (ingest or rebuild): queue its analysis if it pairs.

    The record is read back from the registry, so the state is keyed by the
    row every later capability lookup reads.
    """
    found = _store
    if found is None:
        return None
    try:
        with found._db.read_cursor() as con:
            record = registry.get_experiment(con, name)
        if record is None or record.kind != ddl.KIND_SINGLE_EVENTS:
            return None
        return found.submit(record)
    except Exception:  # noqa: BLE001 - the ingest that called this has already succeeded
        log.exception("Could not queue the model analysis of %r", name)
        return None
