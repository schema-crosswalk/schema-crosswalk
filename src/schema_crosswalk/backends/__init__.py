"""Backend adapters for constrained decoding. [IMPURE: LLM]

Each adapter isolates one model provider / constraint mechanism behind :class:`BackendAdapter`.
The core library imports and runs without any adapter's SDK installed; adapters are optional
extras (``schema-crosswalk[anthropic]`` etc.) and raise :class:`BackendNotInstalled` if their
SDK is missing.
"""

from __future__ import annotations

from typing import Any, Protocol

from schema_crosswalk.models import MappingDocument, SampleView, SourceProfile


class BackendNotInstalled(ImportError):
    """Raised when a backend is used but its optional dependency is not installed."""

    def __init__(self, backend: str, extra: str) -> None:
        super().__init__(
            f"The '{backend}' backend requires an optional dependency. "
            f"Install it with: pip install 'schema-crosswalk[{extra}]'"
        )


class BackendAdapter(Protocol):
    """Constrains an LLM to emit a grammar-valid :class:`MappingDocument` (design.md 9.2)."""

    def propose(
        self,
        *,
        source_profile: SourceProfile,
        sample_values: SampleView,
        target_schema: dict[str, Any],
    ) -> MappingDocument: ...


__all__ = ["BackendAdapter", "BackendNotInstalled"]
