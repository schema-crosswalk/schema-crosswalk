"""Typed data contracts for schema-crosswalk.

These pydantic models are the in-memory form of every JSON payload the engine exchanges
(design.md 6, 8, 10). JSON in/out goes through these models rather than loose dicts.
Rule ``params`` stays an open mapping here; it is validated against the grammar JSON Schema
in :mod:`schema_crosswalk.validate`, which is the source of truth for param shape.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    """Base with strict construction (unknown fields rejected)."""

    model_config = ConfigDict(extra="forbid")


class Primitive(StrEnum):
    RENAME_FIELD = "rename_field"
    CAST_TYPE = "cast_type"
    NORMALIZE_STRING = "normalize_string"
    ARITHMETIC = "arithmetic"
    MAP_ENUM_VALUE = "map_enum_value"
    CONCAT_FIELDS = "concat_fields"
    SPLIT_FIELD = "split_field"
    COALESCE = "coalesce"
    DEFAULT_VALUE = "default_value"
    NESTED_EXTRACT = "nested_extract"
    NESTED_FLATTEN = "nested_flatten"


class ScalarType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    NULL = "null"


class FieldStatus(StrEnum):
    AUTO_APPLY = "auto_apply"
    NEEDS_REVIEW = "needs_review"
    UNMAPPED = "unmapped"


class DecisionAction(StrEnum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"


# --- Mapping document (design.md 6.1) ------------------------------------------------


class Rule(_Model):
    target_field: str
    primitive: Primitive
    sources: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    confidence: float
    rationale: str | None = None


class ProposerInfo(_Model):
    backend: str
    model: str
    created_at: datetime


class MappingMetadata(_Model):
    proposer: ProposerInfo | None = None
    confidence_by_field: dict[str, float] = Field(default_factory=dict)


class MappingDocument(_Model):
    grammar_version: int
    semantics_version: int
    target_schema_id: str
    source_fingerprint: str
    rules: list[Rule] = Field(default_factory=list)
    unmapped_target_fields: list[str] = Field(default_factory=list)
    field_status: dict[str, FieldStatus] = Field(default_factory=dict)
    metadata: MappingMetadata = Field(default_factory=MappingMetadata)


# --- Source profile (design.md 8.1) --------------------------------------------------


class ValueFacets(_Model):
    """Value-dependent facets captured for cache reuse guards (design.md 8.1/8.3)."""

    distinct_values: list[str] | None = None
    detected_formats: list[str] = Field(default_factory=list)
    parse_rate: float | None = None


class FieldProfile(_Model):
    path: str
    inferred_type: ScalarType
    type_confidence: float
    nullable: bool
    alternatives: list[ScalarType] = Field(default_factory=list)
    facets: ValueFacets | None = None


class SourceProfile(_Model):
    fields: list[FieldProfile] = Field(default_factory=list)
    rows_sampled: int
    fingerprint: str


class SampleView(_Model):
    """Redactable per-column sample values passed to the proposer (design.md 9.1)."""

    values: dict[str, list[Any]] = Field(default_factory=dict)


# --- Validation & review (design.md 7, 10) -------------------------------------------


class ValidationReport(_Model):
    ok: bool
    errors: list[str] = Field(default_factory=list)
    field_status: dict[str, FieldStatus] = Field(default_factory=dict)
    confidence_by_field: dict[str, float] = Field(default_factory=dict)


class SourceSample(_Model):
    source_field: str
    values: list[Any] = Field(default_factory=list)


class ReviewItem(_Model):
    target_field: str
    target_description: str | None = None
    proposed_rule: Rule
    adjusted_confidence: float
    derating_reasons: list[str] = Field(default_factory=list)
    source_samples: list[SourceSample] = Field(default_factory=list)
    alternatives: list[Rule] = Field(default_factory=list)


class ReviewPackage(_Model):
    mapping_ref: str
    items: list[ReviewItem] = Field(default_factory=list)
    unmapped_required: list[str] = Field(default_factory=list)


class FieldDecision(_Model):
    action: DecisionAction
    edited_rule: Rule | None = None


class ApprovalRecord(_Model):
    mapping_ref: str
    decided_by: str
    decided_at: datetime
    field_decisions: dict[str, FieldDecision] = Field(default_factory=dict)
    resulting_status: str = "approved"


# --- Schema drift (design.md 8.4) ----------------------------------------------------


class RenameCandidate(_Model):
    from_field: str = Field(alias="from")
    to_field: str = Field(alias="to")
    similarity: float

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class RetypedField(_Model):
    path: str
    was: ScalarType
    now: ScalarType


class DriftReport(_Model):
    against: str
    added_fields: list[str] = Field(default_factory=list)
    removed_fields: list[str] = Field(default_factory=list)
    renamed_candidates: list[RenameCandidate] = Field(default_factory=list)
    retyped_fields: list[RetypedField] = Field(default_factory=list)
    proposed_delta: list[Rule] = Field(default_factory=list)


# --- Execution (design.md 12.1) ------------------------------------------------------


class ExecutionError(_Model):
    record_index: int
    target_field: str | None = None
    message: str


class ExecutionReport(_Model):
    records_in: int = 0
    records_out: int = 0
    records_failed: int = 0
    errors: list[ExecutionError] = Field(default_factory=list)
