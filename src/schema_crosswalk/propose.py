"""Mapping Proposer. [IMPURE: LLM]

The only component that calls a model. It hands the source profile, redacted sample values,
and target schema to a :class:`~schema_crosswalk.backends.BackendAdapter`, which constrains
generation to the grammar JSON Schema. The returned document must still pass the Validator —
the proposer is never trusted (design.md 9).
"""

from __future__ import annotations

from typing import Any

from .backends import BackendAdapter
from .models import MappingDocument, SampleView, SourceProfile


def propose_mapping(
    backend: BackendAdapter,
    profile: SourceProfile,
    target_schema: dict[str, Any],
    *,
    sample: SampleView | None = None,
) -> MappingDocument:
    """Ask ``backend`` to propose a grammar-constrained mapping for ``profile`` -> schema."""
    raise NotImplementedError
