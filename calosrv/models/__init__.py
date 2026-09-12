"""Request and response shapes for the HTTP layer.

Response bodies are assembled as plain dictionaries by the query modules, which
already own the vocabulary of the domain. What lives here is the small amount of
*input* validation FastAPI benefits from, plus the shared envelope every
response carries.
"""

from __future__ import annotations

from .common import ApiMeta, envelope
from .upload import UploadMode, UploadRequest

__all__ = ["ApiMeta", "envelope", "UploadMode", "UploadRequest"]
