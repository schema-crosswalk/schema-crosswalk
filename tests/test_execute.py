"""Placeholder for the execution-engine suite.

When execute.py is implemented, this becomes the per-primitive truth tables and the
determinism property tests (design.md 13). Skipped until then so the scaffold's test run
is green without asserting on unimplemented behavior.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="execution engine not implemented yet (scaffold)")


def test_execute_is_deterministic() -> None:
    raise AssertionError("placeholder")
