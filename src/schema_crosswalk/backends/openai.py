"""OpenAI backend (structured outputs). [IMPURE: LLM]"""

from __future__ import annotations

from typing import Any

from schema_crosswalk.models import MappingDocument, SampleView, SourceProfile

from . import BackendNotInstalled

try:
    import openai  # noqa: F401

    _AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the extra installed
    _AVAILABLE = False


class OpenAIAdapter:
    """Proposes mappings via the OpenAI API with schema-constrained output."""

    def __init__(self, model: str, **client_kwargs: Any) -> None:
        if not _AVAILABLE:
            raise BackendNotInstalled("openai", "openai")
        self.model = model
        self._client_kwargs = client_kwargs

    def propose(
        self,
        *,
        source_profile: SourceProfile,
        sample_values: SampleView,
        target_schema: dict[str, Any],
    ) -> MappingDocument:
        raise NotImplementedError
