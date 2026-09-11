"""HTML assembly.

The document skeleton, stylesheet and controller live as real files under
``assets/`` and are inlined here. Keeping them out of Python string literals
means each stays independently readable and editable, with working syntax
highlighting, instead of being buried in f-strings.
"""

from __future__ import annotations

from pathlib import Path

from .constants import BASELINE_WARNING, DASHBOARD_TITLE

ASSETS = Path(__file__).parent / "assets"

#: Pinned so a CDN build cannot silently drift to an incompatible major version.
CDN_URL = "https://cdn.plot.ly/plotly-3.0.1.min.js"


def _asset(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def plotly_script(embed: bool) -> tuple[str, str]:
    """Return the plotly ``<script>`` element and a description of its source.

    Embedding is the default: a CDN reference breaks the dashboard the moment it
    is opened without a network, which defeats the point of compiling a
    standalone file.
    """
    if not embed:
        return f'<script src="{CDN_URL}" charset="utf-8"></script>', f"CDN ({CDN_URL})"

    from plotly.offline import get_plotlyjs

    bundle = get_plotlyjs()
    return (
        f'<script type="text/javascript">{bundle}</script>',
        f"embedded ({len(bundle) / 1_048_576:.1f} MiB)",
    )


def render(payload_json: str, embed_plotly: bool = True) -> tuple[str, str]:
    """Compose the full HTML document.

    Returns the document and a short description of how plotly was supplied,
    for the build report.
    """
    script, source = plotly_script(embed_plotly)

    document = _asset("template.html")
    # Order matters: the payload and the plotly bundle both contain arbitrary
    # text, so they are substituted last and never re-scanned.
    for token, value in (
        ("__TITLE__", DASHBOARD_TITLE),
        ("__WARNING__", BASELINE_WARNING),
        ("__CSS__", _asset("dashboard.css")),
        ("__JS__", _asset("dashboard.js")),
        ("__PLOTLY__", script),
        ("__PAYLOAD__", payload_json),
    ):
        document = document.replace(token, value)

    return document, source


def write(path: Path, document: str) -> int:
    """Write the document and return its size in bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")
    return path.stat().st_size
