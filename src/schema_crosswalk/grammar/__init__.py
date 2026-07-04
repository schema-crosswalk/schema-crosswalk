"""Grammar loader. [PURE]

The JSON Schema files under ``v1/`` are the single source of truth for the primitive
grammar (see ``docs/design.md`` 4). This module only reads and caches them; it never
mutates them, and Python code must not encode grammar facts that contradict the JSON.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

CURRENT_GRAMMAR_VERSION = 1
CURRENT_SEMANTICS_VERSION = 1

JsonSchema = dict[str, Any]


def _read_json(version: int, *parts: str) -> dict[str, Any]:
    resource = resources.files(__package__).joinpath(f"v{version}", *parts)
    with resource.open("r", encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)
    return data


@cache
def load_manifest(version: int = CURRENT_GRAMMAR_VERSION) -> dict[str, Any]:
    """Return the grammar manifest (primitive set + source arity)."""
    return _read_json(version, "manifest.json")


@cache
def load_rule_schema(version: int = CURRENT_GRAMMAR_VERSION) -> JsonSchema:
    """Return the JSON Schema for a single mapping-rule envelope."""
    return _read_json(version, "rule.json")


@cache
def load_param_schema(primitive: str, version: int = CURRENT_GRAMMAR_VERSION) -> JsonSchema:
    """Return the JSON Schema for a primitive's ``params`` object."""
    return _read_json(version, "params", f"{primitive}.json")


def primitive_names(version: int = CURRENT_GRAMMAR_VERSION) -> list[str]:
    """Return the primitive names declared by the manifest, in declaration order."""
    manifest = load_manifest(version)
    primitives: dict[str, Any] = manifest["primitives"]
    return list(primitives)


def source_arity(primitive: str, version: int = CURRENT_GRAMMAR_VERSION) -> tuple[int, int | None]:
    """Return ``(min, max)`` source arity for a primitive; ``max`` is ``None`` if unbounded."""
    manifest = load_manifest(version)
    arity: list[int | None] = manifest["primitives"][primitive]["arity"]
    return arity[0], arity[1]  # type: ignore[return-value]


def load_all(version: int = CURRENT_GRAMMAR_VERSION) -> dict[str, JsonSchema]:
    """Return every param schema keyed by primitive name (used by validators and tests)."""
    return {name: load_param_schema(name, version) for name in primitive_names(version)}
