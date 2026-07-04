"""Public facade (design.md 12.1).

``Crosswalk`` wires the pure modules and the (optional) LLM backend into the documented
workflow: profile -> propose -> validate -> review -> execute. The orchestration lives here;
the per-step logic lives in the individual modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import profile as _profile
from . import propose as _propose
from . import review as _review
from . import validate as _validate
from .backends import BackendAdapter
from .cache import CacheStore
from .execute import ExecutionResult
from .models import (
    ApprovalRecord,
    MappingDocument,
    ReviewPackage,
    SampleView,
    SourceProfile,
    ValidationReport,
)
from .validate import DEFAULT_REVIEW_THRESHOLD


class Crosswalk:
    """Entry point tying the engine components together."""

    def __init__(
        self,
        *,
        backend: BackendAdapter | None = None,
        cache: CacheStore | None = None,
        review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
        value_exposure: str = "redacted",
    ) -> None:
        self.backend = backend
        self.cache = cache
        self.review_threshold = review_threshold
        self.value_exposure = value_exposure

    def profile(self, source: str | Path, *, sample_rows: int = 1000) -> SourceProfile:
        return _profile.profile_file(source, sample_rows=sample_rows)

    def propose(
        self,
        profile: SourceProfile,
        *,
        target_schema: dict[str, Any],
        sample: SampleView | None = None,
    ) -> MappingDocument:
        if self.backend is None:
            raise ValueError("Crosswalk.propose requires a backend to be configured.")
        return _propose.propose_mapping(self.backend, profile, target_schema, sample=sample)

    def validate(
        self,
        mapping: MappingDocument,
        *,
        target_schema: dict[str, Any],
        sample: SampleView | None = None,
    ) -> ValidationReport:
        return _validate.validate_mapping(
            mapping, target_schema, sample=sample, review_threshold=self.review_threshold
        )

    def review_package(
        self,
        mapping: MappingDocument,
        *,
        target_schema: dict[str, Any] | None = None,
        sample: SampleView | None = None,
    ) -> ReviewPackage | None:
        return _review.build_review_package(mapping, target_schema=target_schema, sample=sample)

    def apply_decision(self, mapping: MappingDocument, approval: ApprovalRecord) -> MappingDocument:
        return _review.apply_decision(mapping, approval)

    def execute(
        self,
        mapping: MappingDocument,
        source: str | Path,
        *,
        assemble_nested: bool = False,
        allow_unreviewed: bool = False,
    ) -> ExecutionResult:
        from . import profile as _profile
        from .execute import execute_records

        records = _profile._read_records(Path(source))
        return execute_records(
            mapping,
            records,
            assemble_nested=assemble_nested,
            allow_unreviewed=allow_unreviewed,
        )
