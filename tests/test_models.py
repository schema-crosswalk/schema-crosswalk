"""Smoke tests: the documented contracts construct and round-trip through JSON."""

from __future__ import annotations

from schema_crosswalk.models import (
    FieldStatus,
    MappingDocument,
    Primitive,
    Rule,
)


def _sample_mapping() -> MappingDocument:
    return MappingDocument(
        grammar_version=1,
        semantics_version=1,
        target_schema_id="customer.v3",
        source_fingerprint="sha256:deadbeef",
        rules=[
            Rule(
                target_field="full_name",
                primitive=Primitive.CONCAT_FIELDS,
                sources=["first", "last"],
                params={"separator": " "},
                confidence=0.9,
            )
        ],
        field_status={"full_name": FieldStatus.AUTO_APPLY},
    )


def test_mapping_document_roundtrips_through_json() -> None:
    original = _sample_mapping()
    restored = MappingDocument.model_validate_json(original.model_dump_json())
    assert restored == original
    assert restored.rules[0].primitive is Primitive.CONCAT_FIELDS


def test_extra_fields_are_rejected() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Rule.model_validate(
            {
                "target_field": "x",
                "primitive": "rename_field",
                "sources": ["a"],
                "params": {},
                "confidence": 1.0,
                "surprise": "not allowed",
            }
        )
