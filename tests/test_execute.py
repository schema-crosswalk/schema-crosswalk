"""Executor truth tables, coercion cases, determinism, and structural-guard tests.

Each primitive is exercised on its happy path and across every failure-policy branch it
declares (design.md 13). ``_run`` builds a single-rule mapping so a handler can be probed in
isolation; ``field_status`` is left empty so every produced field is included.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import pytest

from schema_crosswalk.execute import (
    RecordFailure,
    execute_record,
    execute_records,
    structural_check,
)
from schema_crosswalk.models import FieldStatus, MappingDocument, Primitive, Rule


def _mapping(*rules: Rule, field_status: dict[str, Any] | None = None) -> MappingDocument:
    return MappingDocument(
        grammar_version=1,
        semantics_version=1,
        target_schema_id="test",
        source_fingerprint="sha256:test",
        rules=list(rules),
        field_status=field_status or {},
    )


def _run(
    primitive: Primitive,
    sources: list[str],
    params: dict[str, Any],
    record: dict[str, Any],
    *,
    target: str = "out",
) -> Any:
    rule = Rule(
        target_field=target, primitive=primitive, sources=sources, params=params, confidence=1.0
    )
    return execute_record(_mapping(rule), record)[target]


# --- rename_field --------------------------------------------------------------------


def test_rename_field_copies_verbatim() -> None:
    assert _run(Primitive.RENAME_FIELD, ["a"], {}, {"a": "00123"}) == "00123"


def test_rename_field_missing_becomes_null() -> None:
    assert _run(Primitive.RENAME_FIELD, ["a"], {}, {}) is None


# --- cast_type + coercion table (design.md 5.2) --------------------------------------


@pytest.mark.parametrize(
    ("to", "value", "expected"),
    [
        ("integer", "42", 42),
        ("integer", " 42 ", 42),
        ("integer", 3.0, 3),
        ("integer", True, 1),
        ("number", "3.5", 3.5),
        ("number", 7, 7.0),
        ("string", 12, "12"),
        ("string", True, "true"),
        ("boolean", "Yes", True),
        ("boolean", "n", False),
        ("boolean", 0, False),
        ("date", "2024-01-02", date(2024, 1, 2)),
        ("datetime", "2024-01-02T03:04:05", datetime(2024, 1, 2, 3, 4, 5)),
    ],
)
def test_cast_type_coercion_table(to: str, value: Any, expected: Any) -> None:
    assert _run(Primitive.CAST_TYPE, ["a"], {"to": to}, {"a": value}) == expected


def test_cast_epoch_seconds_to_datetime_utc() -> None:
    out = _run(Primitive.CAST_TYPE, ["a"], {"to": "datetime", "unit": "seconds"}, {"a": 1704067200})
    assert out == datetime(2024, 1, 1, 0, 0, 0)


def test_cast_epoch_millis_to_datetime_utc() -> None:
    out = _run(
        Primitive.CAST_TYPE, ["a"], {"to": "datetime", "unit": "millis"}, {"a": 1704067200000}
    )
    assert out == datetime(2024, 1, 1, 0, 0, 0)


def test_cast_null_passes_through() -> None:
    assert _run(Primitive.CAST_TYPE, ["a"], {"to": "integer"}, {"a": None}) is None


def test_cast_on_error_null_is_default() -> None:
    # The classic "12abc" footgun is rejected, not silently truncated.
    assert _run(Primitive.CAST_TYPE, ["a"], {"to": "integer"}, {"a": "12abc"}) is None


def test_cast_on_error_default() -> None:
    params = {"to": "integer", "on_error": "default", "default": -1}
    assert _run(Primitive.CAST_TYPE, ["a"], params, {"a": "N/A"}) == -1


def test_cast_on_error_fail_aborts_record() -> None:
    with pytest.raises(RecordFailure):
        _run(Primitive.CAST_TYPE, ["a"], {"to": "integer", "on_error": "fail"}, {"a": "N/A"})


# --- normalize_string ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("ops", "value", "expected"),
    [
        (["trim"], "  hi  ", "hi"),
        (["upper"], "hi", "HI"),
        (["title"], "aLICE smith", "Alice Smith"),
        (["collapse_whitespace"], "  a   b  ", "a b"),
        (["strip_punctuation"], "a.b,c!", "abc"),
        (["digits_only"], "(00) 44-123", "0044123"),
        (["collapse_whitespace", "title"], "  aLICE  smith ", "Alice Smith"),
    ],
)
def test_normalize_string_ops(ops: list[str], value: str, expected: str) -> None:
    assert _run(Primitive.NORMALIZE_STRING, ["a"], {"ops": ops}, {"a": value}) == expected


def test_normalize_string_null_passes_through() -> None:
    assert _run(Primitive.NORMALIZE_STRING, ["a"], {"ops": ["trim"]}, {"a": None}) is None


# --- arithmetic ----------------------------------------------------------------------


def test_arithmetic_cents_to_dollars() -> None:
    params = {"ops": [{"op": "divide", "operand": 100}], "round": 2}
    assert _run(Primitive.ARITHMETIC, ["a"], params, {"a": "1299"}) == 12.99


def test_arithmetic_chain() -> None:
    params = {"ops": [{"op": "add", "operand": 10}, {"op": "multiply", "operand": 2}]}
    assert _run(Primitive.ARITHMETIC, ["a"], params, {"a": 5}) == 30.0


def test_arithmetic_divide_by_zero_null() -> None:
    params = {"ops": [{"op": "divide", "operand": 0}]}
    assert _run(Primitive.ARITHMETIC, ["a"], params, {"a": 5}) is None


def test_arithmetic_non_numeric_on_error_default() -> None:
    params = {"ops": [{"op": "add", "operand": 1}], "on_error": "default", "default": 0}
    assert _run(Primitive.ARITHMETIC, ["a"], params, {"a": ""}) == 0


def test_arithmetic_non_numeric_on_error_fail() -> None:
    params = {"ops": [{"op": "add", "operand": 1}], "on_error": "fail"}
    with pytest.raises(RecordFailure):
        _run(Primitive.ARITHMETIC, ["a"], params, {"a": "x"})


# --- map_enum_value ------------------------------------------------------------------


def test_map_enum_value_hit() -> None:
    params = {"mapping": {"M": "male", "F": "female"}}
    assert _run(Primitive.MAP_ENUM_VALUE, ["a"], params, {"a": "F"}) == "female"


def test_map_enum_value_case_insensitive() -> None:
    params = {"mapping": {"M": "male", "F": "female"}, "case_insensitive": True}
    assert _run(Primitive.MAP_ENUM_VALUE, ["a"], params, {"a": "f"}) == "female"


def test_map_enum_unmatched_null() -> None:
    params = {"mapping": {"M": "male"}}
    assert _run(Primitive.MAP_ENUM_VALUE, ["a"], params, {"a": "Z"}) is None


def test_map_enum_unmatched_passthrough() -> None:
    params = {"mapping": {"M": "male"}, "unmatched": "passthrough"}
    assert _run(Primitive.MAP_ENUM_VALUE, ["a"], params, {"a": "Z"}) == "Z"


def test_map_enum_unmatched_default() -> None:
    params = {"mapping": {"M": "male"}, "unmatched": "default", "default": "unknown"}
    assert _run(Primitive.MAP_ENUM_VALUE, ["a"], params, {"a": "Z"}) == "unknown"


def test_map_enum_unmatched_fail() -> None:
    params = {"mapping": {"M": "male"}, "unmatched": "fail"}
    with pytest.raises(RecordFailure):
        _run(Primitive.MAP_ENUM_VALUE, ["a"], params, {"a": "Z"})


# --- concat_fields -------------------------------------------------------------------


def test_concat_fields_joins() -> None:
    out = _run(Primitive.CONCAT_FIELDS, ["a", "b"], {"separator": " "}, {"a": "x", "b": "y"})
    assert out == "x y"


def test_concat_fields_skip_null_drops_missing() -> None:
    out = _run(Primitive.CONCAT_FIELDS, ["a", "b"], {"separator": "-"}, {"a": "x"})
    assert out == "x"  # b absent and skip_null default True


def test_concat_fields_keep_null_as_empty() -> None:
    out = _run(
        Primitive.CONCAT_FIELDS, ["a", "b"], {"separator": "-", "skip_null": False}, {"a": "x"}
    )
    assert out == "x-"


# --- split_field ---------------------------------------------------------------------


def test_split_field_delimiter() -> None:
    out = _run(Primitive.SPLIT_FIELD, ["a"], {"delimiter": "@", "index": 1}, {"a": "user@host"})
    assert out == "host"


def test_split_field_pattern() -> None:
    out = _run(Primitive.SPLIT_FIELD, ["a"], {"pattern": r"\s*,\s*", "index": 2}, {"a": "a, b ,c"})
    assert out == "c"


def test_split_field_index_out_of_range_null() -> None:
    out = _run(Primitive.SPLIT_FIELD, ["a"], {"delimiter": "@", "index": 5}, {"a": "user@host"})
    assert out is None


def test_split_field_index_out_of_range_fail() -> None:
    params = {"delimiter": "@", "index": 5, "on_missing_index": "fail"}
    with pytest.raises(RecordFailure):
        _run(Primitive.SPLIT_FIELD, ["a"], params, {"a": "user@host"})


# --- coalesce ------------------------------------------------------------------------


def test_coalesce_first_non_null() -> None:
    out = _run(Primitive.COALESCE, ["a", "b", "c"], {}, {"a": None, "b": "", "c": "z"})
    assert out == "z"  # None skipped, "" treated as null by default


def test_coalesce_empty_string_not_null() -> None:
    params = {"treat_empty_string_as_null": False}
    out = _run(Primitive.COALESCE, ["a", "b"], params, {"a": None, "b": ""})
    assert out == ""


def test_coalesce_default_when_all_null() -> None:
    out = _run(Primitive.COALESCE, ["a", "b"], {"default": "fallback"}, {})
    assert out == "fallback"


# --- default_value -------------------------------------------------------------------


def test_default_value_constant_no_source() -> None:
    assert _run(Primitive.DEFAULT_VALUE, [], {"value": "US"}, {}) == "US"


def test_default_value_fills_only_when_missing() -> None:
    assert _run(Primitive.DEFAULT_VALUE, ["a"], {"value": "US"}, {"a": "CA"}) == "CA"
    assert _run(Primitive.DEFAULT_VALUE, ["a"], {"value": "US"}, {}) == "US"


def test_default_value_always_overrides() -> None:
    params = {"value": "US", "only_when_missing": False}
    assert _run(Primitive.DEFAULT_VALUE, ["a"], params, {"a": "CA"}) == "US"


# --- nested_extract / nested_flatten -------------------------------------------------


def test_nested_extract_path() -> None:
    record = {"a": {"b": [{"c": 42}]}}
    assert _run(Primitive.NESTED_EXTRACT, ["a"], {"path": "b[0].c"}, record) == 42


def test_nested_extract_missing_null() -> None:
    assert _run(Primitive.NESTED_EXTRACT, ["a"], {"path": "b.z"}, {"a": {}}) is None


def test_nested_extract_missing_fail() -> None:
    params = {"path": "b.z", "on_missing": "fail"}
    with pytest.raises(RecordFailure):
        _run(Primitive.NESTED_EXTRACT, ["a"], params, {"a": {}})


def test_nested_flatten_is_deterministic_json() -> None:
    record = {"a": {"y": 1, "x": 2}}
    assert _run(Primitive.NESTED_FLATTEN, ["a"], {}, record) == '{"x":2,"y":1}'


# --- composition, gating, determinism ------------------------------------------------


def test_composition_drops_intermediate() -> None:
    rules = (
        Rule(
            target_field="__name",
            primitive=Primitive.CONCAT_FIELDS,
            sources=["f", "l"],
            params={"separator": " "},
            confidence=0.9,
        ),
        Rule(
            target_field="full_name",
            primitive=Primitive.NORMALIZE_STRING,
            sources=["__name"],
            params={"ops": ["title"]},
            confidence=0.9,
        ),
    )
    out = execute_record(_mapping(*rules), {"f": "ada", "l": "lovelace"})
    assert out == {"full_name": "Ada Lovelace"}


def test_needs_review_field_omitted_by_default() -> None:
    rule = Rule(
        target_field="x", primitive=Primitive.RENAME_FIELD, sources=["a"], params={}, confidence=0.2
    )
    mapping = _mapping(rule, field_status={"x": FieldStatus.NEEDS_REVIEW})
    assert execute_record(mapping, {"a": 1}) == {}
    assert execute_record(mapping, {"a": 1}, allow_unreviewed=True) == {"x": 1}


def test_execute_is_deterministic() -> None:
    rule = Rule(
        target_field="t",
        primitive=Primitive.CAST_TYPE,
        sources=["a"],
        params={"to": "datetime", "unit": "seconds"},
        confidence=0.9,
    )
    mapping = _mapping(rule)
    record = {"a": 1704067200}
    first = json.dumps(execute_record(mapping, record), default=str, sort_keys=True)
    second = json.dumps(execute_record(mapping, record), default=str, sort_keys=True)
    assert first == second


def test_fail_policy_skips_record_but_continues() -> None:
    rule = Rule(
        target_field="n",
        primitive=Primitive.CAST_TYPE,
        sources=["a"],
        params={"to": "integer", "on_error": "fail"},
        confidence=0.9,
    )
    result = execute_records(_mapping(rule), [{"a": "1"}, {"a": "bad"}, {"a": "3"}])
    assert result.report.records_in == 3
    assert result.report.records_out == 2
    assert result.report.records_failed == 1
    assert result.records == [{"n": 1}, {"n": 3}]
    assert result.report.errors[0].record_index == 1


# --- structural_check ----------------------------------------------------------------


def test_structural_check_accepts_valid_rule() -> None:
    rule = Rule(
        target_field="x", primitive=Primitive.RENAME_FIELD, sources=["a"], params={}, confidence=1.0
    )
    assert structural_check(_mapping(rule)) == []


def test_structural_check_rejects_bad_version() -> None:
    m = _mapping().model_copy(update={"grammar_version": 99})
    assert any("grammar_version" in e for e in structural_check(m))


def test_structural_check_rejects_arity() -> None:
    rule = Rule(
        target_field="x",
        primitive=Primitive.CONCAT_FIELDS,
        sources=["a"],  # needs >= 2
        params={},
        confidence=1.0,
    )
    assert any("expects" in e for e in structural_check(_mapping(rule)))


def test_structural_check_rejects_bad_params() -> None:
    rule = Rule(
        target_field="x",
        primitive=Primitive.CAST_TYPE,
        sources=["a"],
        params={"to": "not-a-type"},
        confidence=1.0,
    )
    assert structural_check(_mapping(rule)) != []


def test_structural_check_rejects_forward_composition_ref() -> None:
    rule = Rule(
        target_field="x",
        primitive=Primitive.RENAME_FIELD,
        sources=["__later"],
        params={},
        confidence=1.0,
    )
    assert any("forward ref" in e for e in structural_check(_mapping(rule)))
