"""Regenerate the two-shower API golden snapshot.

The wave that taught the Page 1 views one shower per event rewrote code every
two-shower response runs through - ``query/summary.py``,
``query/shower_frames.py``, ``api/frame_shower.py``, ``query/window_axis.py``,
``query/event_inspector.py`` - and had to leave that output byte-identical.
``tests/make_golden.py`` pins only the lab ``render_all`` panels, centroids
and shower axes. This snapshot pins the whole served JSON of the two-shower
views on the demonstration dataset, through the HTTP API alone, so that
``tests/test_golden_two_shower.py`` fails on any change to it:

* ``/api/projections`` in the lab, per-shower translated and local frames,
  for the density channel and one attention channel (energy-weighted
  Shap-CAM), over the full selection (N = 2) and a one-event selection; the
  per-shower frames and the lab frame over an empty selection as well;
* ``/api/window-axis`` on both depth panels, over the whole face and over a
  narrow window, for the full and the one-event selection;
* ``/api/event/pick`` (seeded) for both selections, and ``/api/event`` for
  showers A and B of the picked event.

**Masked.** Timing (every key ending in ``_ms``), the ``cached`` flags and the
cache counters, which depend on request order and the clock, and the measured
byte counts quoted in sentences ('measured 101,234 bytes'), which carry the
timing fields' own digits and so jitter by a few bytes from run to run.

**Stored.** Every response in full, except the bulky machine-only parts: a
base64 raster (``data``), and any list outside ``overlays``, ``selection``
and ``centroids`` that holds no prose and whose canonical JSON is at least
256 bytes (edge arrays, top-k cells, profiles), is replaced by the sha256 of
its canonical masked JSON and its length. Every sentence, notice, overlay,
summary and scalar is therefore diffed readably; a hashed part that moves is
named by its path. Floats are compared exactly (``repr`` round-trips).

**Provenance.** The snapshot was first generated from 747baba, the last
commit before the single-shower wave - a whole-package export of that commit
and the arrangement of ``data/dev/design/two-page/harness/snapshot.sh`` (the
wave's files from 747baba, the rest from bfff858) gave the same bytes, and
two runs of each agreed exactly. The committed file is the current tree's
output, which differs from the 747baba snapshot only by the changes listed
in :data:`DELIBERATE`. Run it only when the two-shower output is *meant* to
change, and add the change to that list::

    .venv/bin/python tests/make_golden_two_shower.py
    .venv/bin/python tests/make_golden_two_shower.py --package-root DIR --output FILE

``--package-root`` boots another copy of the package (it must hold
``calosrv/``) so a snapshot of an older tree can be compared with this one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

GOLDEN = Path(__file__).resolve().parent / "golden" / "two_shower_api.json"
SEED_FILE = REPO_ROOT / "hits_all_models_dummy.parquet"

#: The two-shower output this snapshot deliberately departs from 747baba in,
#: each with the commit or review finding that asked for it.
DELIBERATE = (
    "bfff858 (wave-1 integration): the Local frame carries frame.negative_w, /api/statistics' "
    "C9 block for the same selection.",
    "G1-2: overlays.pointing.note labels the residual SD '(1 d.o.f., weak)' at N = 2 and "
    "'(weak)' below 20, and states a one-event residual ('One event, so no dispersion: ...') "
    "without the general claim that incident directions point at the detector origin.",
    "G1-3: an empty per-shower frame selection labels centroids.frame_mean 'No event in the "
    "selection: no centroid', with null a, b, sd, ci95_half and dof_note instead of 'N = 1: a "
    "single event's own centroids', and drops the 'With 0 event(s) ... weak evidence' notice.",
    "Fix round C, decision D-3 (P-16) and R-2: /api/event's window is the widest energy-weighted "
    "0.1st-99.9th percentile range of the shower's cells (floor 150 mm, window.percentiles in place "
    "of window.pad), frames.<f>.outside_window counts the cells beyond it and window.rule names "
    "them; a grid raster's window-bound end snaps inward; window.rule and scale.rule say 'every "
    "panel of this event' instead of 'all nine panels'. /api/projections, /api/window-axis and "
    "/api/event/pick are unchanged.",
)

#: The demonstration file holds two events (E1 2.71 and 17.88 GeV).
FULL: dict[str, Any] = {}
ONE_EVENT = {"e1_min": 0.0, "e1_max": 10.0}
EMPTY = {"e1_min": 5.0, "e1_max": 6.0}
SELECTIONS = {"full": FULL, "one": ONE_EVENT}

#: The one attention channel: signed, energy-weighted, so both planes are read.
CAM_CHANNEL = "shapcam_energy"

#: Lists holding no prose are hashed from this canonical size, outside the readable subtrees.
HASH_MIN_BYTES = 256
#: Top-level blocks always stored in full.
READABLE = ("overlays", "selection", "centroids")

_TIMING_KEYS = {"cached", "cache"}
_BYTES = re.compile(r"\d[\d,]*(?=[ -]bytes?\b)")


def requests_for(table: str) -> list[tuple[str, dict[str, Any]]]:
    """Every request of the snapshot except ``/api/event``, which needs the pick."""
    out: list[tuple[str, dict[str, Any]]] = []
    for selection in SELECTIONS.values():
        for coord in ("lab", "trans", "local"):
            for channel in ("density", CAM_CHANNEL):
                out.append(("/api/projections", {"coord_system": coord, "channel": channel, **selection}))
    for coord in ("lab", "trans", "local"):
        out.append(("/api/projections", {"coord_system": coord, **EMPTY}))
    for selection in SELECTIONS.values():
        for panel in ("xz", "yz"):
            out.append(("/api/window-axis", {"panel": panel, "t_min": -1e5, "t_max": 1e5, **selection}))
    for panel in ("xz", "yz"):
        out.append(("/api/window-axis", {"panel": panel, "t_min": -400.0, "t_max": 400.0}))
    for selection in SELECTIONS.values():
        out.append(("/api/event/pick", {"seed": 7, **selection}))
    return [(url, {"table_name": table, **params}) for url, params in out]


def key_of(url: str, params: dict[str, Any]) -> str:
    shown = {k: v for k, v in params.items() if k != "table_name"}
    return f"{url} {json.dumps(shown, sort_keys=True)}"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def mask(value: Any) -> Any:
    """Replace what jitters between runs, keeping every key so the key set stays pinned."""
    if isinstance(value, dict):
        return {
            k: "<masked>" if (k.endswith("_ms") or k in _TIMING_KEYS) else mask(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [mask(v) for v in value]
    if isinstance(value, str) and "byte" in value:
        return _BYTES.sub("#", value)
    return value


def _prose(value: Any) -> bool:
    """Whether ``value`` holds a sentence anywhere: a string with a space in it."""
    if isinstance(value, dict):
        return any(_prose(v) for v in value.values())
    if isinstance(value, list):
        return any(_prose(v) for v in value)
    return isinstance(value, str) and " " in value


def _digest(value: Any) -> dict[str, Any]:
    return {"sha256": hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest(),
            "n": len(value)}


def compact(value: Any, readable: bool = False, key: str | None = None) -> Any:
    """Hash the bulky machine-only parts; keep everything a reader would diff."""
    if isinstance(value, dict):
        return {k: compact(v, readable, k) for k, v in value.items()}
    if isinstance(value, list):
        if (not readable and not _prose(value)
                and len(canonical_json(value).encode("utf-8")) >= HASH_MIN_BYTES):
            return _digest(value)
        return [compact(v, readable) for v in value]
    if key == "data" and isinstance(value, str) and len(value) > 64:
        return _digest(value)
    return value


def compact_response(body: Any) -> Any:
    if not isinstance(body, dict):
        return body
    return {k: compact(v, readable=k in READABLE, key=k) for k, v in body.items()}


def snapshot(client) -> dict[str, Any]:
    """Every request of the snapshot through ``client``, masked and compacted, by request key."""
    experiments = client.get("/api/experiments").json()["experiments"]
    table = next(e["table_name"] for e in experiments if e["status"] == "ready")
    out: dict[str, Any] = {}

    def fetch(url: str, params: dict[str, Any]) -> Any:
        response = client.get(url, params=params)
        body = mask(response.json())
        out[key_of(url, params)] = {"status": response.status_code, "body": compact_response(body)}
        return body

    picked = None
    for url, params in requests_for(table):
        body = fetch(url, params)
        if url == "/api/event/pick" and picked is None:
            picked = body["event_number"]
    for shower in ("a", "b"):
        fetch("/api/event", {"table_name": table, "event_number": picked, "shower": shower})
    return out


def boot_and_snapshot(data_dir: Path) -> dict[str, Any]:
    """Boot the app as the ``client`` fixture does and take the snapshot."""
    os.environ.setdefault("CALOSRV_ALLOW_RAM_STORAGE", "1")
    os.environ["CALOSRV_DATA_DIR"] = str(data_dir)
    os.environ["DUCKDB_MEMORY_GB"] = "2"
    os.environ["CALOSRV_SEED_FILE"] = str(SEED_FILE)
    for name in ("CALOSRV_AUTO_INGEST_DIR", "CALOSRV_AUTO_INGEST_SETTLE_S", "CALOSRV_CONFIG_PATH",
                 "CALOSRV_DEFAULT_DATASET", "CALOSRV_DEFAULT_COORD_SYSTEM", "CALOSRV_DEFAULT_MODEL",
                 "CALOSRV_DEFAULT_CHANNEL", "CALOSRV_DEFAULT_DISPLAY_MODE", "CALOSRV_DEFAULT_RHO_NORM"):
        os.environ.pop(name, None)

    from fastapi.testclient import TestClient

    from calosrv.app import create_app
    from calosrv.config import load_settings

    with TestClient(create_app(load_settings())) as client:
        for _ in range(240):
            payload = client.get("/api/experiments").json()
            if any(e["status"] == "ready" for e in payload["experiments"]):
                break
            time.sleep(0.25)
        return snapshot(client)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--package-root", type=Path, default=REPO_ROOT,
                        help="directory holding the calosrv package to boot (default: this checkout)")
    parser.add_argument("--output", type=Path, default=GOLDEN, help=f"where to write (default: {GOLDEN})")
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="scratch directory for the throwaway database (default: a new temp dir)")
    args = parser.parse_args()
    if not SEED_FILE.is_file():
        print(f"missing {SEED_FILE}", file=sys.stderr)
        return 1
    root = args.package_root.resolve()
    sys.path.insert(0, str(root))
    import calosrv

    if not Path(calosrv.__file__).resolve().is_relative_to(root):
        print(f"calosrv imported from {calosrv.__file__}, not {root}", file=sys.stderr)
        return 1
    data_dir = args.data_dir or Path(tempfile.mkdtemp(prefix="calosrv-golden-two-"))
    data_dir.mkdir(parents=True, exist_ok=True)
    snap = boot_and_snapshot(data_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snap, sort_keys=True, indent=1, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(f"wrote {args.output} ({args.output.stat().st_size:,} bytes, {len(snap)} responses)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
