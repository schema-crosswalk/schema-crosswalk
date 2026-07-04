"""Proposer orchestration: authoritative version/fingerprint stamping + Validator contract.

Uses a fake :class:`BackendAdapter` so no network or model SDK is needed — the real Anthropic
adapter's only extra responsibility is turning a model response into this same document shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from schema_crosswalk import grammar, profile, validate
from schema_crosswalk.models import MappingDocument, SampleView, SourceProfile
from schema_crosswalk.propose import propose_mapping

_CASE = Path(__file__).resolve().parents[1] / "datasets" / "customers"


class _FakeBackend:
    """Returns the golden rules but with deliberately wrong envelope pins, to prove propose
    re-stamps them authoritatively rather than trusting the model."""

    def __init__(self, doc: MappingDocument) -> None:
        self._doc = doc

    def propose(
        self,
        *,
        source_profile: SourceProfile,
        sample_values: SampleView,
        target_schema: dict[str, Any],
    ) -> MappingDocument:
        return self._doc.model_copy(
            update={
                "grammar_version": 999,
                "semantics_version": 999,
                "target_schema_id": "wrong",
                "source_fingerprint": "sha256:stale",
            }
        )


def _golden_doc() -> MappingDocument:
    return MappingDocument.model_validate_json((_CASE / "mapping.json").read_text())


def test_propose_stamps_authoritative_envelope() -> None:
    prof = profile.profile_file(_CASE / "source.csv")
    target = json.loads((_CASE / "target_schema.json").read_text())
    backend = _FakeBackend(_golden_doc())

    doc = propose_mapping(backend, prof, target, sample=SampleView())

    assert doc.grammar_version == grammar.CURRENT_GRAMMAR_VERSION
    assert doc.semantics_version == grammar.CURRENT_SEMANTICS_VERSION
    assert doc.target_schema_id == "customer.v1"  # from the schema's $id
    assert doc.source_fingerprint == prof.fingerprint  # not the model's stale value


def test_proposed_document_passes_the_validator() -> None:
    """The backend contract (CLAUDE.md): a proposed document must pass the Validator."""
    records = _records()
    prof = profile.profile_records(records)
    target = json.loads((_CASE / "target_schema.json").read_text())
    sample = profile.sample_values(records)

    doc = propose_mapping(_FakeBackend(_golden_doc()), prof, target, sample=sample)
    report = validate.validate_mapping(doc, target, sample=sample)
    assert report.ok, report.errors


def _records() -> list[dict[str, Any]]:
    import csv

    with (_CASE / "source.csv").open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))
