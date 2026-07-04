"""Validator + per-field confidence. [PURE]

Runs structural validation (envelope + param JSON Schema + arity + backward-only composition
+ target coverage), safety validation, and the per-field confidence de-rating that drives
review gating (design.md 7). The proposer output is never trusted regardless of backend.
"""

from __future__ import annotations

from typing import Any

from .models import MappingDocument, SampleView, ValidationReport

DEFAULT_REVIEW_THRESHOLD = 0.7


def validate_mapping(
    mapping: MappingDocument,
    target_schema: dict[str, Any],
    *,
    sample: SampleView | None = None,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> ValidationReport:
    """Validate a mapping and compute per-field status + confidence.

    Structural failures produce ``ok=False`` (the document is not runnable). When a ``sample``
    is provided, confidence is de-rated by executor-verifiable signals (design.md 7.3).
    """
    raise NotImplementedError


def structural_errors(mapping: MappingDocument, target_schema: dict[str, Any]) -> list[str]:
    """Return structural validation errors (empty list = structurally valid)."""
    raise NotImplementedError
