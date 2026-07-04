"""Validator: structural coverage, composition-confidence monotonicity, gating (design.md 7)."""

from __future__ import annotations

from typing import Any

from schema_crosswalk import validate
from schema_crosswalk.models import FieldStatus, MappingDocument, Rule, SampleView

_TARGET: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["out"],
    "properties": {"out": {"type": "string"}, "opt": {"type": "string"}},
}


def _doc(rules: list[Rule], **kw: Any) -> MappingDocument:
    return MappingDocument(
        grammar_version=1,
        semantics_version=1,
        target_schema_id="t",
        source_fingerprint="sha256:x",
        rules=rules,
        **kw,
    )


def _rule(target: str, primitive: str, sources: list[str], conf: float, **params: Any) -> Rule:
    # Parse from JSON-shaped input so the primitive string coerces to the enum, matching how
    # real MappingDocuments arrive (and keeping the static type honest).
    return Rule.model_validate(
        {
            "target_field": target,
            "primitive": primitive,
            "sources": sources,
            "params": params,
            "confidence": conf,
        }
    )


def test_target_field_not_in_schema_is_structural_error() -> None:
    doc = _doc([_rule("bogus", "rename_field", ["a"], 0.9)])
    errors = validate.structural_errors(doc, _TARGET)
    assert any("not a property" in e for e in errors)


def test_required_field_must_be_produced_or_unmapped() -> None:
    doc = _doc([_rule("opt", "rename_field", ["a"], 0.9)])
    errors = validate.structural_errors(doc, _TARGET)
    assert any("required target field 'out'" in e for e in errors)
    # Declaring it unmapped clears the structural error.
    doc2 = _doc([_rule("opt", "rename_field", ["a"], 0.9)], unmapped_target_fields=["out"])
    assert not any(
        "required target field 'out'" in e for e in validate.structural_errors(doc2, _TARGET)
    )


def test_composition_confidence_never_exceeds_weakest_input() -> None:
    # out = rename(__mid); __mid = rename(a) with low confidence. A confident final rename
    # must not launder the weak intermediate (design.md 6.3, 7.3).
    doc = _doc(
        [
            _rule("__mid", "rename_field", ["a"], 0.4),
            _rule("out", "rename_field", ["__mid"], 0.99),
        ]
    )
    report = validate.validate_mapping(doc, _TARGET, sample=SampleView(values={"a": ["x"]}))
    assert report.confidence_by_field["out"] <= 0.4 + 1e-9
    assert report.field_status["out"] is FieldStatus.NEEDS_REVIEW


def test_absent_source_derates_confidence_with_sample() -> None:
    doc = _doc([_rule("out", "rename_field", ["missing_col"], 0.95)])
    report = validate.validate_mapping(doc, _TARGET, sample=SampleView(values={"other": ["x"]}))
    # source_factor 0.3 for an absent source: 0.95 * 0.3 < threshold -> needs_review.
    assert report.confidence_by_field["out"] < 0.7
    assert report.field_status["out"] is FieldStatus.NEEDS_REVIEW


def test_no_sample_does_not_punish_absent_sources() -> None:
    doc = _doc([_rule("out", "rename_field", ["anything"], 0.95)])
    report = validate.validate_mapping(doc, _TARGET)
    assert report.confidence_by_field["out"] == 0.95
    assert report.field_status["out"] is FieldStatus.AUTO_APPLY


def test_unmapped_optional_field_is_unmapped_required_is_review() -> None:
    doc = _doc([_rule("out", "rename_field", ["a"], 0.9)])
    report = validate.validate_mapping(doc, _TARGET, sample=SampleView(values={"a": ["x"]}))
    assert report.field_status["opt"] is FieldStatus.UNMAPPED

    doc2 = _doc([_rule("opt", "rename_field", ["a"], 0.9)], unmapped_target_fields=["out"])
    report2 = validate.validate_mapping(doc2, _TARGET, sample=SampleView(values={"a": ["x"]}))
    assert report2.field_status["out"] is FieldStatus.NEEDS_REVIEW  # required + unmapped


def test_validate_is_deterministic() -> None:
    doc = _doc([_rule("out", "rename_field", ["a"], 0.9)])
    sample = SampleView(values={"a": ["x"]})
    assert validate.validate_mapping(doc, _TARGET, sample=sample).model_dump() == (
        validate.validate_mapping(doc, _TARGET, sample=sample).model_dump()
    )
