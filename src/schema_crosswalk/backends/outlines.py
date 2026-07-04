"""Outlines backend (grammar-constrained decoding for local/OSS models). [IMPURE: LLM]"""

from __future__ import annotations

from typing import Any

from schema_crosswalk.models import MappingDocument, SampleView, SourceProfile

from . import BackendNotInstalled

try:
    import outlines  # noqa: F401

    _AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the extra installed
    _AVAILABLE = False


class OutlinesAdapter:
    """Proposes mappings via Outlines-constrained decoding on a local model."""

    def __init__(self, model: str, **model_kwargs: Any) -> None:
        if not _AVAILABLE:
            raise BackendNotInstalled("outlines", "outlines")
        self.model = model
        self._model_kwargs = model_kwargs

    def propose(
        self,
        *,
        source_profile: SourceProfile,
        sample_values: SampleView,
        target_schema: dict[str, Any],
    ) -> MappingDocument:
        raise NotImplementedError
