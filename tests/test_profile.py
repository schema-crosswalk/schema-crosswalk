"""Schema profiler: ID-safe inference footguns + determinism (design.md 5.3, 8.1)."""

from __future__ import annotations

from schema_crosswalk import profile
from schema_crosswalk.models import ScalarType


def _infer(rows: list[dict[str, object]], column: str):  # type: ignore[no-untyped-def]
    prof = profile.profile_records(rows)
    return next(f for f in prof.fields if f.path == column)


def test_leading_zero_stays_string_with_integer_alternative() -> None:
    field = _infer([{"id": "001"}, {"id": "002"}, {"id": "003"}], "id")
    assert field.inferred_type is ScalarType.STRING
    assert ScalarType.INTEGER in field.alternatives
    assert field.type_confidence < 1.0


def test_phone_with_separators_stays_string() -> None:
    field = _infer([{"phone": "555-1234"}, {"phone": "555-9876"}], "phone")
    assert field.inferred_type is ScalarType.STRING


def test_column_name_heuristic_forces_string() -> None:
    # Clean small integers, but a zip column must never be coerced (leading-zero risk).
    field = _infer([{"zip_code": "12345"}, {"zip_code": "94107"}], "zip_code")
    assert field.inferred_type is ScalarType.STRING


def test_clean_integers_widen() -> None:
    field = _infer([{"n": "10"}, {"n": "-3"}, {"n": "0"}], "n")
    assert field.inferred_type is ScalarType.INTEGER
    assert field.type_confidence == 1.0


def test_epoch_ints_widen_to_integer() -> None:
    field = _infer([{"ts": "1704067200"}, {"ts": "1704153600"}], "ts")
    assert field.inferred_type is ScalarType.INTEGER


def test_floats_widen_to_number() -> None:
    field = _infer([{"x": "1.5"}, {"x": "2"}, {"x": "-0.25"}], "x")
    assert field.inferred_type is ScalarType.NUMBER


def test_native_json_types_are_trusted() -> None:
    assert _infer([{"b": True}, {"b": False}], "b").inferred_type is ScalarType.BOOLEAN
    assert _infer([{"n": 1}, {"n": 2}], "n").inferred_type is ScalarType.INTEGER
    assert _infer([{"n": 1.5}, {"n": 2}], "n").inferred_type is ScalarType.NUMBER


def test_nullability_from_blank_and_missing() -> None:
    field = _infer([{"c": "x"}, {"c": ""}, {}], "c")
    assert field.nullable is True


def test_low_cardinality_facet_captured() -> None:
    field = _infer([{"g": "M"}, {"g": "F"}, {"g": "M"}], "g")
    assert field.facets is not None
    assert field.facets.distinct_values == ["F", "M"]


def test_profiling_is_deterministic() -> None:
    rows = [{"id": "001", "n": "5"}, {"id": "002", "n": "6"}]
    assert profile.profile_records(rows).model_dump() == profile.profile_records(rows).model_dump()


def test_sample_values_are_deduped_and_capped() -> None:
    rows = [{"g": "M"}, {"g": "M"}, {"g": "F"}, {"g": ""}]
    sample = profile.sample_values(rows, per_column=5)
    assert sample.values["g"] == ["M", "F"]  # deduped, blanks skipped
