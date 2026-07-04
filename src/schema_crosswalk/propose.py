"""Mapping Proposer. [IMPURE: LLM]

The only component that calls a model. It hands the source profile, redacted sample values,
and target schema to a :class:`~schema_crosswalk.backends.BackendAdapter`, which constrains
generation to the grammar JSON Schema. The returned document must still pass the Validator —
the proposer is never trusted (design.md 9).
"""

from __future__ import annotations

from typing import Any

from . import grammar
from .backends import BackendAdapter
from .models import MappingDocument, SampleView, SourceProfile


def propose_mapping(
    backend: BackendAdapter,
    profile: SourceProfile,
    target_schema: dict[str, Any],
    *,
    sample: SampleView | None = None,
) -> MappingDocument:
    """Ask ``backend`` to propose a grammar-constrained mapping for ``profile`` -> schema.

    The version pins, source fingerprint, and target-schema id are stamped here
    authoritatively so a pinned mapping's identity never depends on what the model emitted
    (golden rule #5). Rule selection and field status come from the backend and are handed
    straight to the Validator, which is the real gate.
    """
    doc = backend.propose(
        source_profile=profile,
        sample_values=sample or SampleView(),
        target_schema=target_schema,
    )
    return doc.model_copy(
        update={
            "grammar_version": grammar.CURRENT_GRAMMAR_VERSION,
            "semantics_version": grammar.CURRENT_SEMANTICS_VERSION,
            "target_schema_id": str(target_schema.get("$id", doc.target_schema_id or "unknown")),
            "source_fingerprint": profile.fingerprint,
        }
    )
