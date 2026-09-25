"""Write a valid 99-column hits_all_models CSV with chosen event counts per D slice.

The demonstration file holds two events, both far apart, so no D slice of it
exercises the energy panel's low-N ladder. This generator clones those two
events into as many events as asked, at chosen separations, each with its own
incident momenta, and writes a file that passes ingest verification:

* every field is copied verbatim from its template row except
  ``event_number``, ``centroid_AB_distance``, the incident momenta, the three
  ``energy_*_true`` columns (the own shower's momentum, as verification
  demands) and ``energy``, which is scaled by the same factor as the shower's
  momentum so the reconstructed energies spread the way real ones do;
* each template is cut to its highest-energy hits of each shower, so the file
  stays small (a few MB for three hundred events).

Nothing here is a model output: the network columns keep the template's
values, so the fixture tests payload shape and budget, never physics.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Sequence

import numpy as np

REPO = Path(__file__).resolve().parent.parent
TEMPLATE_CSV = REPO / "hits_all_models_dummy.csv"

#: Events per slice, one population per low-N rung of the energy panel
#: (moments, curve, histogram, core refit, robust width) and a large one.
LOW_N_COUNTS: tuple[int, ...] = (1, 2, 7, 8, 14, 15, 19, 20, 200)

#: The separation each population sits at: 50 mm apart, the last far out.
LOW_N_D: tuple[float, ...] = (25.0, 75.0, 125.0, 175.0, 225.0, 275.0, 325.0, 375.0, 600.0)

_FRAMES = ("absolute", "trans", "local")


def _templates(path: Path, hits_per_shower: int):
    with path.open(newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        rows = list(reader)
    col = {name: i for i, name in enumerate(header)}
    by_event: dict[str, list[list[str]]] = defaultdict(list)
    for row in rows:
        by_event[row[col["event_number"]]].append(row)
    templates = []
    for event_rows in by_event.values():
        a = [r for r in event_rows if r[col["particle_origin"]] == "A"]
        b = [r for r in event_rows if r[col["particle_origin"]] != "A"]
        pick = []
        for group in (a, b):
            group.sort(key=lambda r: -float(r[col["energy"]]))
            pick += group[:hits_per_shower]
        templates.append(pick)
    return header, col, templates


def write(
    path: Path,
    counts: Sequence[int] = LOW_N_COUNTS,
    separations: Sequence[float] = LOW_N_D,
    hits_per_shower: int = 12,
    seed: int = 20260926,
) -> dict:
    """Write the file; return ``{"n_events", "n_rows", "counts", "separations"}``."""
    header, col, templates = _templates(TEMPLATE_CSV, hits_per_shower)
    rng = np.random.default_rng(seed)
    event_number = 1
    n_rows = 0
    with Path(path).open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for count, d in zip(counts, separations):
            for j in range(count):
                template = templates[(event_number - 1) % len(templates)]
                first = template[0]
                p_old = {"A": float(first[col["incoming_momentum_A"]]),
                         "B": float(first[col["incoming_momentum_B"]])}
                p_new = {"A": float(rng.uniform(2.0, 18.0)), "B": float(rng.uniform(2.0, 18.0))}
                # Spread within the slice, never across an edge.
                separation = d + float(rng.uniform(-20.0, 20.0))
                for source in template:
                    row = list(source)
                    shower = "A" if row[col["particle_origin"]] == "A" else "B"
                    scale = p_new[shower] / p_old[shower]
                    row[col["event_number"]] = str(event_number)
                    row[col["centroid_AB_distance"]] = repr(separation)
                    row[col["incoming_momentum_A"]] = repr(p_new["A"])
                    row[col["incoming_momentum_B"]] = repr(p_new["B"])
                    for frame in _FRAMES:
                        row[col[f"energy_{frame}_true"]] = repr(p_new[shower])
                    row[col["energy"]] = repr(float(row[col["energy"]]) * scale)
                    writer.writerow(row)
                    n_rows += 1
                event_number += 1
    return {"n_events": event_number - 1, "n_rows": n_rows, "counts": list(counts),
            "separations": list(separations)}


if __name__ == "__main__":  # pragma: no cover - manual use
    import sys

    target = Path(sys.argv[1] if len(sys.argv) > 1 else "hits_all_models_synthetic.csv")
    print(write(target))
