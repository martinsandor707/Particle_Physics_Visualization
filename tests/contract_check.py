"""Payload contracts: one checked-in JSON schema per route, and a validator for them.

The schemas in ``tests/contracts/`` are the frozen shape every new route
returns. Pytest validates live responses against them, and the Node renderer
tests build their fixtures from the same files, so the backend and the
frontend cannot drift apart without a test saying which key moved.

The validator implements the subset of JSON Schema the contracts use - type,
properties, required, additionalProperties, propertyNames, items, minItems,
maxItems, enum, const, minimum, maximum, anyOf, not and local ``$ref`` - because the
project carries no ``jsonschema`` dependency and needs none for this.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CONTRACTS = Path(__file__).resolve().parent / "contracts"


@lru_cache(maxsize=None)
def load(name: str) -> dict[str, Any]:
    """The contract ``tests/contracts/<name>.json``."""
    return json.loads((CONTRACTS / f"{name}.json").read_text(encoding="utf-8"))


def names() -> list[str]:
    return sorted(p.stem for p in CONTRACTS.glob("*.json"))


_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
}


class ContractError(AssertionError):
    pass


def _resolve(ref: str, root: dict[str, Any]) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ContractError(f"only local $ref is supported, got {ref!r}")
    node: Any = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def errors(value: Any, schema: dict[str, Any], root: dict[str, Any] | None = None,
           path: str = "$") -> list[str]:
    """Every violation of ``schema`` by ``value``, as ``path: message`` strings."""
    root = schema if root is None else root
    if "$ref" in schema:
        return errors(value, _resolve(schema["$ref"], root), root, path)
    out: list[str] = []
    if "not" in schema and not errors(value, schema["not"], root, path):
        out.append(f"{path}: {value!r:.60} matches a forbidden schema")
    if "anyOf" in schema:
        branches = [errors(value, s, root, path) for s in schema["anyOf"]]
        if all(branches):
            best = min(branches, key=len)
            out.append(f"{path}: matches no anyOf branch (closest: {best[0]})")
        return out
    kinds = schema.get("type")
    if kinds is not None:
        kinds = [kinds] if isinstance(kinds, str) else kinds
        if not any(_TYPES[k](value) for k in kinds):
            return [f"{path}: expected {'|'.join(kinds)}, got {type(value).__name__} {value!r:.60}"]
    if "const" in schema and value != schema["const"]:
        out.append(f"{path}: expected {schema['const']!r}, got {value!r:.60}")
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{path}: {value!r:.60} not in {schema['enum']}")
    if _TYPES["number"](value):
        if "minimum" in schema and value < schema["minimum"]:
            out.append(f"{path}: {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            out.append(f"{path}: {value} > maximum {schema['maximum']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                out.append(f"{path}: missing required key {key!r}")
        names_schema = schema.get("propertyNames")
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            if names_schema is not None:
                out += errors(key, names_schema, root, f"{path}.<{key}>")
            if key in props:
                out += errors(item, props[key], root, f"{path}.{key}")
            elif extra is False:
                out.append(f"{path}: unexpected key {key!r}")
            elif isinstance(extra, dict):
                out += errors(item, extra, root, f"{path}.{key}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            out.append(f"{path}: {len(value)} items < minItems {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            out.append(f"{path}: {len(value)} items > maxItems {schema['maxItems']}")
        if "items" in schema:
            for i, item in enumerate(value):
                out += errors(item, schema["items"], root, f"{path}[{i}]")
    return out


def check(value: Any, name: str, at: str | None = None) -> None:
    """Assert ``value`` satisfies contract ``name`` (or its ``$defs`` entry ``at``)."""
    root = load(name)
    schema = root["$defs"][at] if at else root
    found = errors(value, schema, root)
    if found:
        raise ContractError(f"{len(found)} violation(s) of contract {name!r}"
                            + (f" ({at})" if at else "") + ":\n  " + "\n  ".join(found[:20]))
