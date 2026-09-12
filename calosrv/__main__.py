"""``python -m calosrv`` - boot the diagnostic server under uvicorn."""

from __future__ import annotations

import uvicorn

from .config import load_settings
from .logging_setup import configure_logging


def main() -> int:
    settings = load_settings()
    configure_logging()
    # The banner itself is emitted from the application lifespan, once the
    # DuckDB connection has actually accepted the settings, so that what is
    # logged is what the database applied rather than what was merely requested.
    uvicorn.run(
        "calosrv.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_config=None,
        access_log=False,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
