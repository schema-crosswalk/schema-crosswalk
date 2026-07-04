"""CLI smoke tests: `primitives` works; unimplemented subcommands exit non-zero cleanly."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from schema_crosswalk.cli import main

_DATASETS = Path(__file__).resolve().parents[1] / "datasets"


def test_primitives_lists_all_eleven(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["primitives"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "11 primitives" in out
    assert "rename_field" in out
    assert "nested_flatten" in out


def test_primitives_json(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["primitives", "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"grammar_version": 1' in out


def test_unimplemented_subcommand_exits_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["review"])
    assert rc == 2
    assert "not implemented" in capsys.readouterr().err


def test_profile_emits_id_safe_types(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["profile", str(_DATASETS / "customers" / "source.csv")])
    assert rc == 0
    profile = json.loads(capsys.readouterr().out)
    by_path = {f["path"]: f for f in profile["fields"]}
    # Leading-zero id/phone stay string (ID-safe); epoch/cents widen to integer.
    assert by_path["id"]["inferred_type"] == "string"
    assert by_path["phone"]["inferred_type"] == "string"
    assert by_path["price_cents"]["inferred_type"] == "integer"
    assert profile["fingerprint"].startswith("sha256:")


def test_validate_golden_mapping(capsys: pytest.CaptureFixture[str]) -> None:
    case = _DATASETS / "customers"
    rc = main(
        [
            "validate",
            "--mapping",
            str(case / "mapping.json"),
            "--target",
            str(case / "target_schema.json"),
        ]
    )
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True
    assert report["errors"] == []


def test_execute_golden_customers(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    case = _DATASETS / "customers"
    out = tmp_path / "out.jsonl"
    rc = main(
        [
            "execute",
            str(case / "source.csv"),
            "--mapping",
            str(case / "mapping.json"),
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    assert out.read_text(encoding="utf-8") == (case / "expected.jsonl").read_text(encoding="utf-8")
    assert "3 records -> 3 written, 0 failed" in capsys.readouterr().err


def test_execute_rejects_unrunnable_mapping(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "mapping.json"
    bad.write_text(
        json.dumps(
            {
                "grammar_version": 99,
                "semantics_version": 1,
                "target_schema_id": "x",
                "source_fingerprint": "sha256:x",
                "rules": [],
            }
        ),
        encoding="utf-8",
    )
    src = tmp_path / "in.csv"
    src.write_text("a\n1\n", encoding="utf-8")
    rc = main(["execute", str(src), "--mapping", str(bad), "--out", str(tmp_path / "o.jsonl")])
    assert rc == 1
    assert "not runnable" in capsys.readouterr().err


def test_version_action_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
