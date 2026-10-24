"""Write valid single-shower test files - hits and their aggregate - from committed data.

The real electron files are not in the repository, so the tests that must
always run build their own from the two-event demonstration file
``hits_all_models_dummy.csv``: each of its four showers becomes a template, and
each event of the output is one template shower, written in the 21-column
``standalone_hits`` v3 layout at a new incident momentum.

* Every coordinate is copied verbatim from the template row - the laboratory
  position, and the shower's own translated and local coordinates - so the
  frame contracts ingest verifies hold: P0 is one point per event, the local
  coordinates are the translated ones rotated by the shower's own R(θ, φ),
  and P0 is the energy-weighted centroid of the first layer, whose rows are
  all kept. The 'A+B' rows belong to both showers' first layer and to both
  templates, as ingest counts them.
* The momentum is drawn inside the population's 1 GeV bin, the bin is ⌊p⌋,
  and the energy is scaled by the momentum ratio (uniform within a shower,
  so the first-layer centroid does not move).
* Species are assigned deterministically: a quarter of the events carry one
  primary-tagged row (``is_secondary = 0``, no parent), the rest none, as on
  the real file.
* One extra event holds a single hit, placed at its own entry point: the
  producer's aggregate omits such events, and so does :func:`write_aggregated`.

:func:`write_aggregated` computes the 59-column aggregate with the producer's
own ``calc_all_features_v3`` (``tests/core_port.py``). Nothing here is a
measurement: the fixtures test shapes, gates and parity, never physics.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Sequence

import numpy as np

REPO = Path(__file__).resolve().parent.parent
TEMPLATE_CSV = REPO / "hits_all_models_dummy.csv"

#: Events per 1 GeV bin, one population per low-N rung, and the bins they sit in.
LOW_N_COUNTS: tuple[int, ...] = (1, 2, 7, 8, 14, 15, 19, 20, 200)
LOW_N_BINS: tuple[int, ...] = (3, 7, 12, 1, 15, 5, 19, 2, 10)

HIT_COLUMNS: tuple[str, ...] = (
    "event_number", "cellID", "x", "y", "z", "x_local", "y_local", "z_local",
    "x_trans", "y_trans", "z_trans", "energy", "earliest_contribution_time",
    "incoming_momentum", "incoming_theta", "incoming_phi", "incoming_momentum_bin",
    "particle_type", "is_secondary", "parent_type", "daughter_type",
)
_SPECIES = ("e-", "gamma", "e+", "gamma", "e-", "neutron", "proton")


def _templates(hits_per_shower: int) -> list[dict]:
    with TEMPLATE_CSV.open(newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = list(reader)
    col = {name: i for i, name in enumerate(header)}
    by_event: dict[str, list[list[str]]] = defaultdict(list)
    for row in rows:
        by_event[row[col["event_number"]]].append(row)
    templates = []
    for event_rows in by_event.values():
        for shower in ("A", "B"):
            members = [r for r in event_rows if r[col["particle_origin"]] in (shower, "A+B")]
            if not members:
                continue
            z0 = min(float(r[col["z"]]) for r in members)
            first = [r for r in members if float(r[col["z"]]) == z0]
            rest = sorted((r for r in members if float(r[col["z"]]) != z0),
                          key=lambda r: -float(r[col["energy"]]))[:hits_per_shower]
            templates.append({"shower": shower, "rows": first + rest, "col": col,
                              "first": len(first)})
    return templates


def _row(template: dict, source: list[str], event_number: int, p: float, scale: float,
         j: int, primary: bool, origin_hit: bool) -> list[str]:
    col, s = template["col"], template["shower"]
    frame = ("0.0",) * 6 if origin_hit else tuple(
        source[col[c]] for c in ("x_local", "y_local", "z_local", "x_trans", "y_trans", "z_trans"))
    time = source[col[f"earliest_contribution_time_{s}"]]
    if primary:
        species, secondary, parent, daughters = "e-", "0", "", "gamma;e-"
    else:
        species = _SPECIES[j % len(_SPECIES)]
        secondary = "1"
        parent = "gamma" if species in ("e-", "e+") else "e-"
        daughters = "" if j % 2 else "e-"
    return [
        str(event_number), source[col["cellID"]],
        source[col["x"]], source[col["y"]], source[col["z"]], *frame,
        repr(float(source[col["energy"]]) * scale), time,
        repr(p), source[col[f"incoming_theta_{s}"]], source[col[f"incoming_phi_{s}"]],
        str(int(p)), species, secondary, parent, daughters,
    ]


def write(
    path: Path,
    counts: Sequence[int] = LOW_N_COUNTS,
    bins: Sequence[int] = LOW_N_BINS,
    hits_per_shower: int = 25,
    seed: int = 20261025,
    single_hit_event: bool = True,
) -> dict:
    """Write the hit file; return ``{"n_events", "n_rows", "by_bin", "single_hit"}``."""
    templates = _templates(hits_per_shower)
    rng = np.random.default_rng(seed)
    event_number = 1
    n_rows = 0
    by_bin: dict[int, int] = defaultdict(int)
    with Path(path).open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HIT_COLUMNS)
        for count, k in zip(counts, bins):
            for _ in range(count):
                template = templates[(event_number - 1) % len(templates)]
                col = template["col"]
                p_old = float(template["rows"][0][col[f"incoming_momentum_{template['shower']}"]])
                p = float(k + rng.uniform(0.0, 1.0))
                primary_event = event_number % 4 == 0
                for j, source in enumerate(template["rows"]):
                    writer.writerow(_row(template, source, event_number, p, p / p_old, j,
                                         primary_event and j == 0, False))
                    n_rows += 1
                by_bin[k] += 1
                event_number += 1
        single = None
        if single_hit_event:
            template = templates[0]
            col = template["col"]
            source = max(template["rows"][:template["first"]], key=lambda r: float(r[col["energy"]]))
            p_old = float(source[col[f"incoming_momentum_{template['shower']}"]])
            p = 4.5
            writer.writerow(_row(template, source, event_number, p, p / p_old, 0, False, True))
            n_rows += 1
            by_bin[4] += 1
            single = event_number
            event_number += 1
    return {"n_events": event_number - 1, "n_rows": n_rows, "by_bin": dict(by_bin),
            "single_hit": single}


def write_aggregated(hits_csv: Path, path: Path) -> dict:
    """The 59-column aggregate of ``hits_csv``, as the producer writes it."""
    import pandas as pd

    import core_port

    # round_trip: pandas' default fast parser is not always correctly rounded,
    # and an ulp off in p would be a disagreement the fixture made up.
    df = pd.read_csv(hits_csv, float_precision="round_trip")
    sizes = df.groupby("event_number")["energy"].transform("size")
    features = core_port.calc_all_features_v3(df[sizes > 1])
    features["energy"] = (features["incoming_momentum"] >= 2.0).astype(int)
    features.to_csv(path, index=False)
    return {"n_events": int(len(features)), "n_dropped_single_hit": int((sizes == 1).sum())}


if __name__ == "__main__":  # pragma: no cover - manual use
    import sys

    target = Path(sys.argv[1] if len(sys.argv) > 1 else "single_shower_synthetic.csv")
    print(write(target))
    print(write_aggregated(target, target.with_name(target.stem + "_aggr.csv")))
