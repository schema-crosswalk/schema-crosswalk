"""CLI smoke tests: `primitives` works; unimplemented subcommands exit non-zero cleanly."""

from __future__ import annotations

import pytest

from schema_crosswalk.cli import main


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
    rc = main(["execute"])
    assert rc == 2
    assert "not implemented" in capsys.readouterr().err


def test_version_action_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
