"""Validator + per-field confidence. [PURE]

Runs structural validation (envelope + param JSON Schema + arity + backward-only composition
+ target coverage), safety validation, and the per-field confidence de-rating that drives
review gating (design.md 7). The proposer output is never trusted regardless of backend.
"""

from __future__ import annotations

from typing import Any

from .execute import structural_check
from .models import FieldStatus, MappingDocument, Rule, SampleView, ValidationReport

DEFAULT_REVIEW_THRESHOLD = 0.7

# The intermediate-field prefix (design.md 6.3); mirrors execute.runtime._INTERMEDIATE_PREFIX.
_INTERMEDIATE_PREFIX = "__"
# Primitives whose confidence is mildly de-rated as they span more source fields (design.md 7.3).
_ARITY_PENALIZED = {"concat_fields", "coalesce"}
_ARITY_PENALTY_PER_EXTRA = 0.98


def structural_errors(mapping: MappingDocument, target_schema: dict[str, Any]) -> list[str]:
    """Return structural validation errors (empty list = structurally valid).

    Layers target-schema coverage (design.md 7.1.5) on top of the schema-free
    :func:`~schema_crosswalk.execute.structural_check` (versions, arity, param schemas,
    backward-only composition).
    """
    errors = list(structural_check(mapping))

    properties: dict[str, Any] = target_schema.get("properties", {})
    required: list[str] = target_schema.get("required", [])

    produced: set[str] = set()
    for rule in mapping.rules:
        target = rule.target_field
        if target.startswith(_INTERMEDIATE_PREFIX):
            continue  # not a target-schema field; exempt from coverage
        produced.add(target)
        if target not in properties:
            errors.append(f"target_field {target!r} is not a property of the target schema")

    unmapped = set(mapping.unmapped_target_fields)
    for field in required:
        if field not in produced and field not in unmapped:
            errors.append(
                f"required target field {field!r} is neither produced nor listed as unmapped"
            )
    return errors


def validate_mapping(
    mapping: MappingDocument,
    target_schema: dict[str, Any],
    *,
    sample: SampleView | None = None,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> ValidationReport:
    """Validate a mapping and compute per-field status + confidence.

    Structural failures produce ``ok=False`` (the document is not runnable). When a ``sample``
    is provided, confidence is de-rated by executor-verifiable signals (design.md 7.3): a rule's
    adjusted confidence is never higher than its weakest input's, so a confident final rename can
    no longer launder a weak intermediate.
    """
    errors = structural_errors(mapping, target_schema)
    ok = not errors

    rule_by_target = {rule.target_field: rule for rule in mapping.rules}
    sample_fields = set(sample.values) if sample is not None else None

    confidence_by_field: dict[str, float] = {}
    memo: dict[str, float] = {}
    for rule in mapping.rules:
        target = rule.target_field
        if target.startswith(_INTERMEDIATE_PREFIX):
            continue
        confidence_by_field[target] = _adjusted(target, rule_by_target, sample_fields, memo)

    field_status = _gate(mapping, target_schema, confidence_by_field, review_threshold)
    return ValidationReport(
        ok=ok,
        errors=errors,
        field_status=field_status,
        confidence_by_field=confidence_by_field,
    )


def _adjusted(
    target: str,
    rule_by_target: dict[str, Rule],
    sample_fields: set[str] | None,
    memo: dict[str, float],
) -> float:
    """Adjusted confidence for ``target``, resolving ``source_factor`` through composition."""
    if target in memo:
        return memo[target]
    rule = rule_by_target.get(target)
    if rule is None:
        return 1.0  # not produced here; caller handles unmapped gating separately
    memo[target] = 0.0  # guard against a cyclic mapping (structural check rejects real cycles)

    source_factor = 1.0
    for src in rule.sources:
        if src.startswith(_INTERMEDIATE_PREFIX):
            source_factor *= _adjusted(src, rule_by_target, sample_fields, memo)
        elif sample_fields is not None and src not in sample_fields:
            # present sources, and every source when no sample is given, stay at 1.0
            source_factor *= 0.3

    extra = max(0, len(rule.sources) - 2)
    arity_penalty = (
        _ARITY_PENALTY_PER_EXTRA**extra if rule.primitive.value in _ARITY_PENALIZED else 1.0
    )

    value = rule.confidence * source_factor * arity_penalty
    memo[target] = value
    return value


def _gate(
    mapping: MappingDocument,
    target_schema: dict[str, Any],
    confidence_by_field: dict[str, float],
    threshold: float,
) -> dict[str, FieldStatus]:
    """Per-field gating (design.md 7.3): auto_apply / needs_review / unmapped."""
    properties: dict[str, Any] = target_schema.get("properties", {})
    required = set(target_schema.get("required", []))
    unmapped = set(mapping.unmapped_target_fields)

    status: dict[str, FieldStatus] = {}
    for field in properties:
        if field in confidence_by_field:
            adjusted = confidence_by_field[field]
            status[field] = (
                FieldStatus.AUTO_APPLY if adjusted >= threshold else FieldStatus.NEEDS_REVIEW
            )
        elif field in unmapped:
            status[field] = FieldStatus.NEEDS_REVIEW if field in required else FieldStatus.UNMAPPED
        else:
            status[field] = FieldStatus.UNMAPPED
    return status
