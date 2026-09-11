"""Command line surface.

CLAUDE.md section 3 fixes the contract: ``--input`` / ``--output`` with explicit
fallback defaults, non-interactive execution, clean exit code 0.
"""

from __future__ import annotations

import argparse
from pathlib import Path

#: Shipped dataset, used when ``--input`` is omitted.
DEFAULT_INPUT = "proton_standalone_N10000_M0_1GeV_reg_s1_v2.csv"
DEFAULT_OUTPUT = "dashboard.html"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_dashboard.py",
        description=(
            "Compile a standalone interactive diagnostic dashboard for "
            "calorimeter shower reconstruction. Reads raw hit-level CSV data "
            "and writes a self-contained HTML file with no server component."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=(
            "Supplying both a standalone and a 2combined file enables the "
            "overlap analysis path, including the separation distance D."
        ),
    )
    parser.add_argument(
        "--input",
        "-i",
        nargs="+",
        default=[DEFAULT_INPUT],
        metavar="CSV",
        help="One or more input CSV files. The schema of each is detected.",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=DEFAULT_OUTPUT,
        metavar="HTML",
        help="Destination HTML file.",
    )
    parser.add_argument(
        "--cdn",
        action="store_true",
        help=(
            "Load plotly.js from a CDN instead of embedding it. Cuts the output "
            "from roughly 4.5 MB to 350 kB, but the dashboard then requires "
            "network access to open."
        ),
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=2_000_000,
        metavar="ROWS",
        help=(
            "Rows per read_csv chunk. Keeps the 22.7 M-row 2combined file "
            "streaming rather than resident."
        ),
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=0,
        metavar="N",
        help=(
            "Cap the number of events retained, for a faster build during "
            "development. 0 keeps every event."
        ),
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress the build report on stdout.",
    )
    return parser


def parse_args(argv=None) -> argparse.Namespace:
    """Parse arguments and normalise paths.

    Input paths are resolved relative to the current directory, then, if that
    misses, relative to the repository root, so the defaults work from either.
    """
    args = build_parser().parse_args(argv)
    repo_root = Path(__file__).resolve().parent.parent

    resolved: list[Path] = []
    for raw in args.input:
        candidate = Path(raw)
        if not candidate.exists():
            fallback = repo_root / raw
            if fallback.exists():
                candidate = fallback
        resolved.append(candidate)

    args.input = resolved
    args.output = Path(args.output)
    return args
