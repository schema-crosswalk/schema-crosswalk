"""Schema Profiler. [PURE]

Infers source shape with ID-safe type inference (design.md 5.3, 8.1) and computes the
fingerprint. No LLM, no network, no ambient state.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .models import SampleView, SourceProfile


def profile_file(path: str | Path, *, sample_rows: int = 1000) -> SourceProfile:
    """Profile a CSV/JSON file into a :class:`SourceProfile` (shape + facets + fingerprint)."""
    raise NotImplementedError


def profile_records(
    records: Iterable[Mapping[str, Any]], *, sample_rows: int = 1000
) -> SourceProfile:
    """Profile an in-memory record iterable (used by the MCP inline path)."""
    raise NotImplementedError


def sample_values(records: Iterable[Mapping[str, Any]], *, per_column: int = 5) -> SampleView:
    """Collect a small, redactable per-column value sample for the proposer (design.md 9.1)."""
    raise NotImplementedError
