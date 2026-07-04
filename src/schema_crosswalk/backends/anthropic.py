"""Anthropic backend (native structured output / tool use). [IMPURE: LLM]

Constrains Claude to emit a grammar-valid rule list via a forced tool call, then assembles a
:class:`MappingDocument`. The document is *not* trusted here — it is stamped with authoritative
version pins in :mod:`schema_crosswalk.propose` and must pass the Validator before use
(design.md 9.2).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from schema_crosswalk import grammar
from schema_crosswalk.models import (
    FieldStatus,
    MappingDocument,
    MappingMetadata,
    ProposerInfo,
    Rule,
    SampleView,
    SourceProfile,
)

from . import BackendNotInstalled

try:
    import anthropic

    _AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the extra installed
    _AVAILABLE = False

DEFAULT_MODEL = "claude-opus-4-8"
_TOOL_NAME = "emit_mapping"

_SYSTEM = """\
You map arbitrary source data onto a fixed target schema by SELECTING and PARAMETERIZING \
primitives from a small, versioned grammar. You never write code, formulas, or templates — \
you only choose primitives and fill their params.

Rules:
- Emit exactly one rule per target field you can express. Read from source columns by name.
- Compose with intermediates: a rule whose target_field starts with "__" is dropped from the \
output and may be referenced as a source by any LATER rule (backward references only).
- If the grammar cannot express a field, OMIT it and list it in unmapped_target_fields — never \
guess or invent a value.
- Set confidence in [0,1] honestly per rule; the engine de-rates it and routes weak fields to \
human review.
- Map by target field name + description + examples and by the SAMPLE VALUES shown; e.g. a \
column of "M"/"F" is an enum, a column of epoch integers needs a cast_type with unit.
"""


class AnthropicAdapter:
    """Proposes mappings via the Anthropic API with schema-constrained tool output."""

    def __init__(self, model: str = DEFAULT_MODEL, **client_kwargs: Any) -> None:
        if not _AVAILABLE:
            raise BackendNotInstalled("anthropic", "anthropic")
        self.model = model
        self._client = anthropic.Anthropic(**client_kwargs)

    def propose(
        self,
        *,
        source_profile: SourceProfile,
        sample_values: SampleView,
        target_schema: dict[str, Any],
    ) -> MappingDocument:
        prompt = _build_prompt(source_profile, sample_values, target_schema)
        response = self._client.messages.create(
            model=self.model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=_SYSTEM,
            tools=[_tool_schema()],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
            messages=[{"role": "user", "content": prompt}],
        )
        payload = _extract_tool_input(response)
        return _assemble(payload, source_profile, target_schema, self.model)


def _tool_schema() -> dict[str, Any]:
    primitives = grammar.primitive_names()
    return {
        "name": _TOOL_NAME,
        "description": "Emit the grammar-constrained mapping from source columns to the target.",
        "input_schema": {
            "type": "object",
            "properties": {
                "rules": {
                    "type": "array",
                    "description": "Rules in execution order; intermediates ('__' targets) first.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "target_field": {"type": "string"},
                            "primitive": {"type": "string", "enum": primitives},
                            "sources": {"type": "array", "items": {"type": "string"}},
                            "params": {"type": "object"},
                            "confidence": {"type": "number"},
                            "rationale": {"type": "string"},
                        },
                        "required": [
                            "target_field",
                            "primitive",
                            "sources",
                            "params",
                            "confidence",
                        ],
                    },
                },
                "unmapped_target_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Target fields the grammar cannot express — never guessed.",
                },
            },
            "required": ["rules", "unmapped_target_fields"],
        },
    }


def _build_prompt(profile: SourceProfile, sample: SampleView, target_schema: dict[str, Any]) -> str:
    catalog = {
        name: {
            "summary": grammar.load_manifest()["primitives"][name]["summary"],
            "arity": grammar.source_arity(name),
            "params": grammar.load_param_schema(name),
        }
        for name in grammar.primitive_names()
    }
    columns = [
        {
            "name": f.path,
            "inferred_type": f.inferred_type.value,
            "nullable": f.nullable,
            "alternatives": [a.value for a in f.alternatives],
            "sample": sample.values.get(f.path, []),
        }
        for f in profile.fields
    ]
    parts = [
        "# Grammar (primitives you may select)",
        json.dumps(catalog, indent=2, default=str),
        "\n# Target schema (map onto these fields)",
        json.dumps(target_schema, indent=2),
        "\n# Source columns (shape + sample values)",
        json.dumps(columns, indent=2, default=str),
        "\nCall emit_mapping with the rules that produce the target fields.",
    ]
    return "\n".join(parts)


def _extract_tool_input(response: Any) -> dict[str, Any]:
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == _TOOL_NAME:
            return dict(block.input)
    raise ValueError(
        f"Anthropic response did not include a '{_TOOL_NAME}' tool call "
        f"(stop_reason={getattr(response, 'stop_reason', None)!r})"
    )


def _assemble(
    payload: dict[str, Any],
    profile: SourceProfile,
    target_schema: dict[str, Any],
    model: str,
) -> MappingDocument:
    rules = [Rule.model_validate(r) for r in payload.get("rules", [])]
    confidence_by_field = {
        r.target_field: r.confidence for r in rules if not r.target_field.startswith("__")
    }
    field_status = {field: FieldStatus.AUTO_APPLY for field in confidence_by_field}
    return MappingDocument(
        grammar_version=grammar.CURRENT_GRAMMAR_VERSION,
        semantics_version=grammar.CURRENT_SEMANTICS_VERSION,
        target_schema_id=str(target_schema.get("$id", "unknown")),
        source_fingerprint=profile.fingerprint,
        rules=rules,
        unmapped_target_fields=list(payload.get("unmapped_target_fields", [])),
        field_status=field_status,
        metadata=MappingMetadata(
            proposer=ProposerInfo(backend="anthropic", model=model, created_at=datetime.now(UTC)),
            confidence_by_field=confidence_by_field,
        ),
    )
