"""Fingerprint cache + value-coverage guard. [PURE except store I/O]

The cache is keyed on ``(fingerprint, target_schema_id, grammar_version, semantics_version)``
(design.md 8.3). Only approved documents are stored. A shape-only fingerprint hit is not
sufficient to reuse a mapping: the value-coverage guard re-checks value-dependent assumptions
(enum coverage, format parse rate) against the new sample before reuse.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .models import MappingDocument, SampleView


@dataclass(frozen=True)
class CacheKey:
    fingerprint: str
    target_schema_id: str
    grammar_version: int
    semantics_version: int


class CacheStore(Protocol):
    """Pluggable persistence for approved mapping documents."""

    def get(self, key: CacheKey) -> MappingDocument | None: ...

    def put(self, key: CacheKey, mapping: MappingDocument) -> None: ...


class FileCacheStore:
    """Local filesystem/JSON implementation of :class:`CacheStore`."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def get(self, key: CacheKey) -> MappingDocument | None:
        raise NotImplementedError

    def put(self, key: CacheKey, mapping: MappingDocument) -> None:
        raise NotImplementedError


@dataclass
class CoverageResult:
    """Outcome of the value-coverage guard for a candidate cached mapping."""

    ok: bool
    fields_needing_review: list[str]
    reasons: list[str]


def value_coverage_guard(mapping: MappingDocument, sample: SampleView) -> CoverageResult:
    """Re-check value-dependent assumptions of a cached mapping against a new sample."""
    raise NotImplementedError
