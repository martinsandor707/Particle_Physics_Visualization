"""The saved defaults, layered over the environment and the built-in view.

Resolution, highest first: what the Admin Settings panel saved (``config.json``
on the data volume), the ``CALOSRV_DEFAULT_*`` environment, and the built-in
view (:data:`~calosrv.admin.schema.BUILTIN`). A URL hash outranks all three,
but that is the browser's business: the server only says what an empty link
opens on.

Every resolved value carries the layer it came from, so the panel can say
"set here", "from environment" or "built-in" beside each control rather than
leave the operator guessing why a session opened where it did.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import threading
from pathlib import Path
from typing import Any

from ..config import Settings
from ..db import ddl
from ..errors import ValidationError
from ..fsutil import atomic_write_text
from ..grid.resolution import DISPLAY_MODES, MODE_CONTINUOUS, MODE_NATIVE
from ..query.density import NORMS
from ..query.experiments import FRAME_KINDS
from ..query.planes import CHANNELS
from . import schema

log = logging.getLogger(__name__)

#: Version of the ``config.json`` layout, for a future migration to key on.
FILE_VERSION = 1

SOURCE_ADMIN = "admin"
SOURCE_ENV = "env"
SOURCE_BUILTIN = "builtin"
#: The configured experiment is not ready, so another one is served instead.
SOURCE_FALLBACK = "fallback"

#: What the capability check compares each field with, in an experiment's
#: ``/api/experiments`` description.
_CAPABILITY = {
    "default_coord_system": "frames",
    "default_model": "models",
    "default_channel": "channels",
}


def own_display_mode(frame: str | None) -> str:
    """A frame's built-in display mode: the lab keeps its lattice, the others their kernel."""
    return MODE_NATIVE if frame in (None, "lab") else MODE_CONTINUOUS


class DefaultsStore:
    """The panel's saved defaults. One per app, shared by every request thread."""

    def __init__(self, settings: Settings) -> None:
        self.path: Path = settings.config_path
        self._lock = threading.Lock()
        self._env, problems = schema.clean_lenient(dict(settings.env_defaults))
        self._env_notices = [f"An environment default was ignored: {p}" for p in problems]
        for notice in self._env_notices:
            log.warning(notice)
        self._saved: dict[str, str] = {}
        self._updated_at: str | None = None
        self._file_notices: list[str] = []
        self.load()

    # ------------------------------------------------------------ the file --

    def load(self) -> None:
        """Read ``config.json``. Never raises: a broken file falls back, and says so."""
        with self._lock:
            self._saved, self._updated_at, self._file_notices = {}, None, []
            if not self.path.is_file():
                return
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or not isinstance(data.get("defaults", {}), dict):
                    raise ValueError("it is not a JSON object with a 'defaults' object")
            except (OSError, ValueError) as exc:
                aside = self._set_aside()
                where = f"it was moved to {aside.name}" if aside else "it was left in place"
                self._note(
                    f"The saved defaults in {self.path.name} could not be read ({exc}); "
                    f"{where}, and the environment and built-in defaults apply."
                )
                return
            kept, problems = schema.clean_lenient(data.get("defaults", {}))
            self._saved = kept
            stamp = data.get("updated_at")
            self._updated_at = stamp if isinstance(stamp, str) else None
            for problem in problems:
                self._note(f"A saved default was ignored: {problem}")

    def _set_aside(self) -> Path | None:
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        aside = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
        try:
            self.path.replace(aside)
        except OSError:
            return None
        return aside

    def _note(self, message: str) -> None:
        log.warning(message)
        self._file_notices.append(message)

    def update(self, patch: Any, experiments: list[dict[str, Any]]) -> None:
        """Merge the panel's save into the saved layer, validate it, write it.

        A ``null`` clears that field's override, so the layer beneath shows
        through. Raises a 422 ``ValidationError`` naming the field for an
        unknown value, an unregistered experiment, or a frame, model or channel
        the default experiment does not offer; nothing is written then.
        """
        cleaned = schema.clean(patch)
        registered = {e["table_name"] for e in experiments}
        wanted = cleaned.get("default_dataset")
        if wanted is not None and wanted not in registered:
            raise ValidationError(
                f"No experiment named {wanted!r} is registered.", field="default_dataset",
                available=sorted(registered),
            )
        with self._lock:
            merged = dict(self._saved)
            for key, value in cleaned.items():
                if value is None:
                    merged.pop(key, None)
                else:
                    merged[key] = value
            self._check_capabilities(merged, experiments)
            stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            body = {"schema_version": FILE_VERSION, "updated_at": stamp, "defaults": merged}
            atomic_write_text(self.path, json.dumps(body, indent=2, sort_keys=True) + "\n")
            self._saved, self._updated_at, self._file_notices = merged, stamp, []
        log.info("Admin defaults saved to %s: %s", self.path, merged or "(none)")

    def _check_capabilities(self, saved: dict[str, str], experiments: list[dict[str, Any]]) -> None:
        """Every saved frame, model and channel must be served by the default experiment."""
        layered = self._layered(saved, dict(self._env))
        experiment = _effective_experiment(layered["default_dataset"], experiments)
        if experiment is None:
            return
        for key, capability in _CAPABILITY.items():
            value = saved.get(key)
            offered = experiment.get(capability)
            if value is not None and offered is not None and value not in offered:
                raise ValidationError(
                    f"Experiment {experiment['table_name']!r} does not offer {value!r} "
                    f"(it offers {', '.join(offered)}).",
                    field=key,
                )

    # ------------------------------------------------------------ resolution --

    @staticmethod
    def _layered(saved: dict[str, str], env: dict[str, str]) -> dict[str, str | None]:
        return {
            key: saved.get(key, env.get(key, schema.BUILTIN[key])) for key in schema.FIELDS
        }

    def configured(self, key: str) -> str | None:
        """The value the layers give ``key``, before any readiness fallback."""
        with self._lock:
            return self._layered(self._saved, self._env)[key]

    def resolve(self, experiments: list[dict[str, Any]]) -> tuple[dict[str, dict], list[str]]:
        """Each field's effective value and source, plus notices for the panel."""
        with self._lock:
            saved, env = dict(self._saved), dict(self._env)
        resolved: dict[str, dict[str, Any]] = {}
        for key in schema.FIELDS:
            if key in saved:
                resolved[key] = {"value": saved[key], "source": SOURCE_ADMIN}
            elif key in env:
                resolved[key] = {"value": env[key], "source": SOURCE_ENV}
            else:
                resolved[key] = {"value": schema.BUILTIN[key], "source": SOURCE_BUILTIN}

        notices: list[str] = []
        ready = [e for e in experiments if e.get("status") == "ready"]
        dataset = resolved["default_dataset"]
        wanted = dataset["value"]
        if wanted is None:
            dataset["value"] = ready[0]["table_name"] if ready else None
        elif wanted not in {e["table_name"] for e in ready}:
            status = next((e.get("status") for e in experiments if e["table_name"] == wanted), None)
            served = ready[0]["table_name"] if ready else None
            why = f"is {status}" if status else "is not registered"
            notices.append(
                f"The default experiment {wanted!r} {why}; new sessions open on "
                f"{served!r} until it is ready." if served else
                f"The default experiment {wanted!r} {why}, and no experiment is ready yet."
            )
            resolved["default_dataset"] = {"value": served, "source": SOURCE_FALLBACK,
                                           "configured": wanted}

        display = resolved["default_display_mode"]
        display["effective"] = display["value"] or own_display_mode(
            resolved["default_coord_system"]["value"]
        )
        return resolved, notices

    def boot_block(self, experiments: list[dict[str, Any]]) -> dict[str, Any]:
        """The cold-boot view keyed by interface state names, for ``/api/experiments``.

        ``display`` stays ``None`` unless a mode was chosen: the interface then
        keeps every frame's own built-in mode.
        """
        resolved, notices = self.resolve(experiments)
        block: dict[str, Any] = {
            schema.STATE_KEYS[key]: resolved[key]["value"] for key in schema.FIELDS
        }
        block["notices"] = notices
        return block

    def admin_view(
        self, experiments: list[dict[str, Any]], auto_ingest: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Everything the Admin Settings panel shows."""
        resolved, notices = self.resolve(experiments)
        with self._lock:
            saved, env = dict(self._saved), dict(self._env)
            updated_at, file_notices = self._updated_at, list(self._file_notices)
        return {
            "config_path": str(self.path),
            "updated_at": updated_at,
            "defaults": resolved,
            "overrides": saved,
            "environment": env,
            "options": {
                "datasets": [
                    {
                        "table_name": e["table_name"],
                        "display_name": e.get("display_name") or e["table_name"],
                        "status": e.get("status"),
                        "n_events": e.get("n_events"),
                        "frames": e.get("frames"),
                        "models": e.get("models"),
                        "channels": e.get("channels"),
                    }
                    for e in experiments
                ],
                "coord_systems": list(FRAME_KINDS),
                "models": list(ddl.MODELS),
                "channels": list(CHANNELS),
                "display_modes": [None, *DISPLAY_MODES],
                "rho_norms": list(NORMS),
            },
            "auto_ingest": auto_ingest or {
                "enabled": False, "dir": None, "scanned_at": None, "entries": [],
            },
            "notices": [*self._env_notices, *file_notices, *notices],
        }


def _effective_experiment(
    wanted: str | None, experiments: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """The experiment a new session would open on: the wanted one if ready, else the oldest."""
    ready = [e for e in experiments if e.get("status") == "ready"]
    for experiment in ready:
        if experiment["table_name"] == wanted:
            return experiment
    return ready[0] if ready else None
