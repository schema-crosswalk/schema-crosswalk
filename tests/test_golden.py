"""Golden-regression harness (design.md 13).

Discovers every ``datasets/<case>/`` directory, runs the mapping over its source, and diffs
the executor output against ``expected.jsonl`` line by line. New cases are picked up simply
by adding a directory — no code change here.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from schema_crosswalk.execute import dumps_record, execute_records, structural_check
from schema_crosswalk.models import MappingDocument

_DATASETS = Path(__file__).resolve().parents[1] / "datasets"


def _cases() -> list[Path]:
    return sorted(p.parent for p in _DATASETS.glob("*/mapping.json"))


def _read_source(case: Path) -> list[dict[str, Any]]:
    csv_path = case / "source.csv"
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    with (case / "source.json").open("r", encoding="utf-8") as fh:
        data: list[dict[str, Any]] = json.load(fh)
    return data


@pytest.mark.parametrize("case", _cases(), ids=lambda p: p.name)
def test_golden_case(case: Path) -> None:
    mapping = MappingDocument.model_validate_json(
        (case / "mapping.json").read_text(encoding="utf-8")
    )
    assert structural_check(mapping) == [], "fixture mapping must be structurally runnable"

    result = execute_records(mapping, _read_source(case))
    assert result.report.records_failed == 0

    actual = [dumps_record(r) for r in result.records]
    expected = [
        line
        for line in (case / "expected.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert actual == expected
