"""Deterministic execution engine. [PURE]

A pure interpreter over the validated primitive list — no LLM. Split into focused submodules:

- :mod:`.runtime`    — error hierarchy, the ``MISSING`` sentinel, shared constants.
- :mod:`.coerce`     — the scalar coercion table (design.md 5.2).
- :mod:`.primitives` — the 11 grammar primitives and the :data:`HANDLERS` dispatch table.
- :mod:`.guard`      — :func:`structural_check`, the lightweight fail-closed guard.
- :mod:`.engine`     — the record/records/file loops and JSONL serialization.

This package's public API is re-exported here so callers keep using ``schema_crosswalk.execute``.
"""

from __future__ import annotations

from .engine import (
    ExecutionResult,
    dumps_record,
    execute_file,
    execute_record,
    execute_records,
)
from .guard import structural_check
from .primitives import HANDLERS
from .runtime import (
    MISSING,
    CoercionError,
    ExecutionEngineError,
    PrimitiveHandler,
    RecordFailure,
    UnsupportedVersionError,
)

__all__ = [
    "HANDLERS",
    "MISSING",
    "CoercionError",
    "ExecutionEngineError",
    "ExecutionResult",
    "PrimitiveHandler",
    "RecordFailure",
    "UnsupportedVersionError",
    "dumps_record",
    "execute_file",
    "execute_record",
    "execute_records",
    "structural_check",
]
