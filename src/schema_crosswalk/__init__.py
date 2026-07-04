"""schema-crosswalk: grammar-constrained schema mapping engine.

An LLM proposes a mapping constrained to a fixed primitive grammar; a deterministic engine
executes it. See ``docs/design.md`` for the architecture and ``CLAUDE.md`` for conventions.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("schema-crosswalk")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0+unknown"

from .crosswalk import Crosswalk

__all__ = ["Crosswalk", "__version__"]
