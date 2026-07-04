"""Review packaging + approval. [PURE]

Turns a validated mapping with ``needs_review`` fields into a :class:`ReviewPackage`, and
applies a human :class:`ApprovalRecord` back onto the mapping. Edited rules re-enter the
validator before approval — a human edit cannot bypass structural/safety checks (design.md 10).
"""

from __future__ import annotations

from .models import ApprovalRecord, MappingDocument, ReviewPackage, SampleView


def build_review_package(
    mapping: MappingDocument,
    *,
    target_schema: dict[str, object] | None = None,
    sample: SampleView | None = None,
) -> ReviewPackage | None:
    """Return a :class:`ReviewPackage` if any field needs review, else ``None``."""
    raise NotImplementedError


def apply_decision(
    mapping: MappingDocument,
    approval: ApprovalRecord,
) -> MappingDocument:
    """Apply per-field decisions (approve/edit/reject) and return the updated mapping."""
    raise NotImplementedError
