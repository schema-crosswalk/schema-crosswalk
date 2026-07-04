"""The grammar JSON files are the source of truth; assert they are well-formed."""

from __future__ import annotations

from typing import Any

import pytest
from jsonschema.validators import Draft202012Validator

from schema_crosswalk import grammar

EXPECTED_PRIMITIVES = {
    "rename_field",
    "cast_type",
    "normalize_string",
    "arithmetic",
    "map_enum_value",
    "concat_fields",
    "split_field",
    "coalesce",
    "default_value",
    "nested_extract",
    "nested_flatten",
}


def test_manifest_lists_all_primitives() -> None:
    assert set(grammar.primitive_names()) == EXPECTED_PRIMITIVES


def test_rule_schema_is_valid_draft202012() -> None:
    Draft202012Validator.check_schema(grammar.load_rule_schema())


@pytest.mark.parametrize("primitive", sorted(EXPECTED_PRIMITIVES))
def test_param_schema_is_valid_and_closed(primitive: str) -> None:
    schema: dict[str, Any] = grammar.load_param_schema(primitive)
    Draft202012Validator.check_schema(schema)
    # Closed schemas only — the model must not smuggle free-form fields past validation.
    assert schema.get("additionalProperties") is False


def test_load_all_returns_a_schema_per_primitive() -> None:
    loaded = grammar.load_all()
    assert set(loaded) == EXPECTED_PRIMITIVES


def test_every_primitive_declares_arity() -> None:
    for name in grammar.primitive_names():
        lo, hi = grammar.source_arity(name)
        assert lo >= 0
        assert hi is None or hi >= lo
