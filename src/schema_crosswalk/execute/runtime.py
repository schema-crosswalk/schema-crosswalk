"""Executor runtime vocabulary shared across the engine. [PURE]

The error hierarchy, the ``MISSING`` sentinel (an absent source key, distinct from a present
``None``), the handler type, and the small constants every submodule needs. Kept dependency-free
so ``coerce``/``primitives``/``guard``/``engine`` can all import from here without cycles.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any, Final

# A primitive handler maps (resolved source inputs, params) -> the produced value.
PrimitiveHandler = Callable[[list[Any], Mapping[str, Any]], Any]

_INTERMEDIATE_PREFIX: Final = "__"
_MAX_REGEX_INPUT: Final = 100_000  # length cap for the pure-Python split fallback (design.md 7.2)

# JSONPath-lite tokenizer (``a.b[0].c``): shared by nested read (extract) and write (assembly).
_PATH_TOKEN_RE: Final = re.compile(r"\[(\d+)\]|([^.\[\]]+)")


class _MissingType:
    """Singleton marking a source key that is absent (distinct from a present ``None``)."""

    _instance: _MissingType | None = None

    def __new__(cls) -> _MissingType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "MISSING"


MISSING: Final = _MissingType()


def is_nullish(value: Any) -> bool:
    """True for an absent (``MISSING``) or explicitly null input."""
    return value is MISSING or value is None


class ExecutionEngineError(Exception):
    """Base class for executor errors."""


class UnsupportedVersionError(ExecutionEngineError):
    """The mapping pins a grammar/semantics version this executor does not implement."""


class CoercionError(ExecutionEngineError):
    """A value could not be coerced to the requested scalar type (design.md 5.2)."""


class RecordFailure(ExecutionEngineError):
    """A ``fail`` failure-policy fired; the current record is aborted (design.md 6.2)."""

    def __init__(self, target_field: str, message: str) -> None:
        super().__init__(message)
        self.target_field = target_field
        self.message = message
