"""Lightweight structural guard (design.md 7.1, subset). [PURE]

A target-schema-free check so ``execute`` fails closed on a malformed document without needing
the full confidence validator: version pins, known primitives, source arity, per-primitive
param JSON Schema, and backward-only composition refs.
"""

from __future__ import annotations

from jsonschema.validators import Draft202012Validator

from schema_crosswalk import grammar
from schema_crosswalk.models import MappingDocument

from .runtime import _INTERMEDIATE_PREFIX


def structural_check(mapping: MappingDocument) -> list[str]:
    """Return structural errors that make a mapping un-runnable (empty list = runnable)."""
    errors: list[str] = []
    if mapping.grammar_version != grammar.CURRENT_GRAMMAR_VERSION:
        errors.append(
            f"grammar_version {mapping.grammar_version} not implemented "
            f"(this executor implements {grammar.CURRENT_GRAMMAR_VERSION})"
        )
    if mapping.semantics_version != grammar.CURRENT_SEMANTICS_VERSION:
        errors.append(
            f"semantics_version {mapping.semantics_version} not implemented "
            f"(this executor implements {grammar.CURRENT_SEMANTICS_VERSION})"
        )
    if errors:
        return errors  # version mismatch: don't reinterpret under wrong semantics

    seen_targets: set[str] = set()
    for i, rule in enumerate(mapping.rules):
        where = f"rules[{i}] ({rule.target_field})"
        lo, hi = grammar.source_arity(rule.primitive.value)
        n = len(rule.sources)
        if n < lo or (hi is not None and n > hi):
            bound = f"{lo}+" if hi is None else (str(lo) if lo == hi else f"{lo}-{hi}")
            errors.append(f"{where}: {rule.primitive.value} expects {bound} sources, got {n}")
        schema = grammar.load_param_schema(rule.primitive.value)
        for err in Draft202012Validator(schema).iter_errors(rule.params):
            loc = "/".join(str(p) for p in err.absolute_path) or "params"
            errors.append(f"{where}: {loc}: {err.message}")
        for src in rule.sources:
            if src.startswith(_INTERMEDIATE_PREFIX) and src not in seen_targets:
                errors.append(f"{where}: source {src!r} is not a prior rule target (forward ref)")
        seen_targets.add(rule.target_field)
    return errors
