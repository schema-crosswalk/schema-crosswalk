"""Anthropic adapter translation logic — everything up to the network boundary.

The live ``messages.create`` call is the [IMPURE] seam and is not exercised here; these tests
cover the deterministic parts: the grammar-constrained tool schema, the prompt payload, parsing
a tool response, and assembling a document that the Validator accepts. The module imports
cleanly without the ``anthropic`` SDK installed (the extra is optional).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from schema_crosswalk import grammar, profile, validate
from schema_crosswalk.backends import anthropic as backend
from schema_crosswalk.models import MappingDocument
from schema_crosswalk.propose import propose_mapping

_CASE = Path(__file__).resolve().parents[1] / "datasets" / "customers"


def test_tool_schema_enumerates_the_whole_grammar() -> None:
    schema = backend._tool_schema()
    item = schema["input_schema"]["properties"]["rules"]["items"]
    assert set(item["properties"]["primitive"]["enum"]) == set(grammar.primitive_names())
    assert item["required"] == ["target_field", "primitive", "sources", "params", "confidence"]
    assert schema["input_schema"]["required"] == ["rules", "unmapped_target_fields"]


def test_prompt_carries_schema_and_sampled_columns() -> None:
    records = _records()
    prof = profile.profile_records(records)
    sample = profile.sample_values(records)
    target = json.loads((_CASE / "target_schema.json").read_text())

    prompt = backend._build_prompt(prof, sample, target)

    assert "customer.v1" in prompt  # the target schema $id
    assert "price_cents" in prompt  # a source column name
    assert "1704067200" in prompt  # a sampled epoch value the model needs to see


def test_extract_tool_input_requires_the_tool_call() -> None:
    block = SimpleNamespace(type="tool_use", name="emit_mapping", input={"rules": []})
    response = SimpleNamespace(content=[block], stop_reason="tool_use")
    assert backend._extract_tool_input(response) == {"rules": []}

    text_only = SimpleNamespace(content=[SimpleNamespace(type="text")], stop_reason="end_turn")
    with pytest.raises(ValueError, match="emit_mapping"):
        backend._extract_tool_input(text_only)


def test_assemble_produces_a_validator_passing_document() -> None:
    records = _records()
    prof = profile.profile_records(records)
    sample = profile.sample_values(records)
    target = json.loads((_CASE / "target_schema.json").read_text())

    # A minimal, grammar-valid payload the model could plausibly return.
    payload: dict[str, Any] = {
        "rules": [
            {
                "target_field": "customer_id",
                "primitive": "rename_field",
                "sources": ["id"],
                "params": {},
                "confidence": 0.99,
            },
            {
                "target_field": "full_name",
                "primitive": "concat_fields",
                "sources": ["first", "last"],
                "params": {"separator": " ", "skip_null": True},
                "confidence": 0.9,
            },
            {
                "target_field": "gender",
                "primitive": "map_enum_value",
                "sources": ["gender"],
                "params": {"mapping": {"M": "male", "F": "female"}, "case_insensitive": True},
                "confidence": 0.9,
            },
            {
                "target_field": "country",
                "primitive": "default_value",
                "sources": [],
                "params": {"value": "US"},
                "confidence": 0.6,
            },
        ],
        "unmapped_target_fields": [],
    }
    doc = backend._assemble(payload, prof, target, "claude-opus-4-8")
    assert isinstance(doc, MappingDocument)
    assert doc.metadata.proposer is not None
    assert doc.metadata.proposer.backend == "anthropic"

    stamped = propose_mapping(_Fake(doc), prof, target, sample=sample)
    report = validate.validate_mapping(stamped, target, sample=sample)
    assert report.ok, report.errors


class _Fake:
    def __init__(self, doc: MappingDocument) -> None:
        self._doc = doc

    def propose(self, **_: Any) -> MappingDocument:
        return self._doc


def _records() -> list[dict[str, Any]]:
    import csv

    with (_CASE / "source.csv").open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))
