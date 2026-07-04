"""Fingerprint is shape-only, deterministic, and order/count-insensitive (design.md 8.2)."""

from __future__ import annotations

from schema_crosswalk.fingerprint import compute_fingerprint, field_overlap
from schema_crosswalk.models import FieldProfile, ScalarType, SourceProfile


def _profile(fields: list[FieldProfile], rows: int = 3) -> SourceProfile:
    return SourceProfile(fields=fields, rows_sampled=rows, fingerprint="")


def _f(path: str, t: ScalarType = ScalarType.STRING, *, nullable: bool = False) -> FieldProfile:
    return FieldProfile(path=path, inferred_type=t, type_confidence=1.0, nullable=nullable)


def test_fingerprint_is_prefixed_sha256() -> None:
    fp = compute_fingerprint(_profile([_f("a")]))
    assert fp.startswith("sha256:")
    assert len(fp) == len("sha256:") + 64


def test_fingerprint_is_field_order_insensitive() -> None:
    a = _profile([_f("a", ScalarType.INTEGER), _f("b")])
    b = _profile([_f("b"), _f("a", ScalarType.INTEGER)])
    assert compute_fingerprint(a) == compute_fingerprint(b)


def test_fingerprint_is_insensitive_to_row_count() -> None:
    assert compute_fingerprint(_profile([_f("a")], rows=1)) == compute_fingerprint(
        _profile([_f("a")], rows=999)
    )


def test_fingerprint_changes_with_type_or_nullability() -> None:
    base = compute_fingerprint(_profile([_f("a", ScalarType.STRING)]))
    retyped = compute_fingerprint(_profile([_f("a", ScalarType.INTEGER)]))
    nullable = compute_fingerprint(_profile([_f("a", ScalarType.STRING, nullable=True)]))
    assert base != retyped
    assert base != nullable


def test_field_overlap_jaccard() -> None:
    a = _profile([_f("x"), _f("y")])
    b = _profile([_f("y"), _f("z")])
    assert field_overlap(a, b) == 1 / 3
    assert field_overlap(a, a) == 1.0
    assert field_overlap(_profile([]), _profile([])) == 1.0
