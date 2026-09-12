"""DuckDB access layer.

Two structural rules hold across this package and are the reason it exists as a
package rather than a single module:

1. ``naming.py`` is the only place an experiment name becomes SQL identifier
   text. DuckDB cannot parameterise identifiers, so interpolation is
   unavoidable; confining it to one validated function makes the injection
   surface auditable in one file.
2. No SQL string lives outside ``calosrv/db/ddl.py`` and ``calosrv/query/``.
   Route modules build a filter specification and call a query module.
"""

from __future__ import annotations

from .connection import Database, get_database

__all__ = ["Database", "get_database"]
