"""Golden rule #1: no LLM in the execution path — enforced at the import graph.

Only ``crosswalk.propose`` and ``crosswalk.backends.*`` may reach a model. This test
statically walks the transitive first-party import graph of the pure, LLM-free surface
(``profile``, ``fingerprint``, ``validate``, ``review``, ``execute``, ``cache``, and the
``models`` / ``grammar`` they rest on) and asserts none of it — directly or transitively —
imports ``propose``, ``backends``, or any optional model SDK.

The scan is static (``ast``): it does not import the modules, so it is deterministic and
cannot be fooled by import ordering or by an impure module already sitting in
``sys.modules`` from another test.
"""

from __future__ import annotations

import ast
from collections import deque
from pathlib import Path

PACKAGE = "schema_crosswalk"
PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "src" / PACKAGE

# The LLM-free surface. Every module here — and everything it transitively imports within
# the package — must stay clear of the forbidden set below.
PURE_ROOTS = (
    "schema_crosswalk.models",
    "schema_crosswalk.grammar",
    "schema_crosswalk.profile",
    "schema_crosswalk.fingerprint",
    "schema_crosswalk.validate",
    "schema_crosswalk.review",
    "schema_crosswalk.execute",
    "schema_crosswalk.cache",
)

# Reaching any of these (by dotted prefix) from the pure surface is a boundary violation.
FORBIDDEN_PREFIXES = (
    "schema_crosswalk.propose",
    "schema_crosswalk.backends",
    "anthropic",
    "openai",
    "outlines",
    "xgrammar",
)


def _module_name(path: Path) -> str:
    """Dotted module name for a ``.py`` file under the package root."""
    rel = path.relative_to(PACKAGE_ROOT.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _package_of(module: str, path: Path) -> str:
    """The package a module lives in (itself if it is a package ``__init__``)."""
    return module if path.name == "__init__.py" else module.rsplit(".", 1)[0]


def _build_module_index() -> dict[str, Path]:
    """Map every first-party dotted module name to its source file."""
    return {_module_name(p): p for p in PACKAGE_ROOT.rglob("*.py")}


def _import_targets(tree: ast.AST, pkg: str) -> set[str]:
    """Dotted targets referenced by a module, with relative imports resolved to absolute."""
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                # ``from . import x`` / ``from .runtime import y`` — anchor to the package,
                # walking up one level for each extra dot.
                anchor = pkg.split(".")
                anchor = anchor[: len(anchor) - (node.level - 1)]
                base = ".".join([*anchor, node.module] if node.module else anchor)
            if base:
                targets.add(base)
            # ``from pkg import name`` may pull in a submodule, not just an attribute; record
            # ``pkg.name`` too so both the module and its submodules are checked and followed.
            for alias in node.names:
                targets.add(f"{base}.{alias.name}" if base else alias.name)
    return targets


def _seed(index: dict[str, Path]) -> list[str]:
    """Expand the pure roots to concrete modules: packages contribute every file beneath."""
    seeds: list[str] = []
    for root in PURE_ROOTS:
        prefix = f"{root}."
        seeds.extend(name for name in index if name == root or name.startswith(prefix))
    return seeds


def test_pure_surface_never_imports_an_llm() -> None:
    index = _build_module_index()
    for root in PURE_ROOTS:
        assert root in index, f"pure root {root!r} not found under {PACKAGE_ROOT}"

    # BFS over the first-party import graph, tracking how we reached each module so a
    # violation can report the full chain.
    parent: dict[str, str | None] = {name: None for name in _seed(index)}
    queue: deque[str] = deque(parent)

    while queue:
        module = queue.popleft()
        path = index[module]
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for target in _import_targets(tree, _package_of(module, path)):
            if target.startswith(FORBIDDEN_PREFIXES):
                chain = _format_chain(module, parent) + f" -> {target}"
                raise AssertionError(
                    f"LLM-free surface reaches a model-capable module (golden rule #1):\n  {chain}"
                )
            # Follow first-party edges only; stdlib / pydantic / jsonschema are irrelevant.
            first_party = _resolve_first_party(target, index)
            if first_party is not None and first_party not in parent:
                parent[first_party] = module
                queue.append(first_party)


def _resolve_first_party(target: str, index: dict[str, Path]) -> str | None:
    """Resolve a dotted import to a first-party module file, or ``None`` if external.

    ``from pkg.mod import thing`` yields the candidate ``pkg.mod.thing`` (a possible
    submodule) as well as ``pkg.mod``; try the longest match first so we follow the most
    specific real module.

    The top-level ``schema_crosswalk`` package ``__init__`` is deliberately excluded: it is
    the public facade — the one place allowed to wire the LLM-free modules to ``propose`` /
    ``backends`` — and every intra-package import executes it, so following it would make the
    boundary check vacuous. A future ``schema-crosswalk-core`` split swaps out this facade
    while the submodules checked here stay put, so their source purity is what matters.
    """
    if not target.startswith(f"{PACKAGE}.") and target != PACKAGE:
        return None
    if target == PACKAGE:
        return None
    parts = target.split(".")
    for end in range(len(parts), 0, -1):
        candidate = ".".join(parts[:end])
        if candidate in index:
            return candidate
    return None


def _format_chain(module: str, parent: dict[str, str | None]) -> str:
    chain = [module]
    cur = parent[module]
    while cur is not None:
        chain.append(cur)
        cur = parent[cur]
    return " -> ".join(reversed(chain))
