"""Placeholder until the per-shower frames land (step 5b)."""
from ..errors import ValidationError


def build_response(*_args, kind: str, **_kwargs):
    raise ValidationError(f"coord_system={kind!r} is not available yet.", field="coord_system")
