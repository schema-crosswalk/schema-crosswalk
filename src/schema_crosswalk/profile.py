"""Schema Profiler. [PURE]

Infers source shape with ID-safe type inference (design.md 5.3, 8.1) and computes the
fingerprint. No LLM, no network, no ambient state — same input ⇒ byte-identical output.

The inference is **conservative to prevent data loss**: a column only widens from ``string``
to a numeric/temporal type when *every* non-null sampled value parses cleanly under that type,
and never when a value has a leading zero, is over-long, contains a digit-context separator, or
the column name matches an ID/code/zip/phone heuristic. Ambiguity is recorded (``alternatives``)
and surfaced to the proposer rather than resolved by guessing.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any, Final

from .fingerprint import compute_fingerprint
from .models import FieldProfile, SampleView, ScalarType, SourceProfile, ValueFacets

# A column whose *name* matches one of these keeps its string type regardless of the values,
# guarding IDs / codes / postal / phone columns whose digits must not be coerced (design.md 5.3).
_ID_NAME_RE: Final = re.compile(
    r"(?:^|[_\s-])(id|code|zip|postal|postcode|phone|tel|fax|ssn|isbn|ean|upc|sku)s?"
    r"(?:$|[_\s-])",
    re.IGNORECASE,
)
_DIGIT_SEPARATOR_RE: Final = re.compile(r"\d[\s()-]\d")
_MAX_SAFE_DIGITS: Final = 15
_TRUE_TOKENS: Final = frozenset({"true", "t", "yes", "y", "1"})
_FALSE_TOKENS: Final = frozenset({"false", "f", "no", "n", "0"})
_DISTINCT_FACET_CAP: Final = 200
_LOW_CARDINALITY_MAX: Final = 50


def profile_file(path: str | Path, *, sample_rows: int = 1000) -> SourceProfile:
    """Profile a CSV/JSON/JSONL file into a :class:`SourceProfile` (shape, facets, fingerprint)."""
    records = _read_records(Path(path))
    return profile_records(records, sample_rows=sample_rows)


def profile_records(
    records: Iterable[Mapping[str, Any]], *, sample_rows: int = 1000
) -> SourceProfile:
    """Profile an in-memory record iterable (used by the MCP inline path)."""
    columns, seen = _collect_columns(records, sample_rows)
    fields = [_profile_column(name, values) for name, values in columns.items()]
    profile = SourceProfile(fields=fields, rows_sampled=seen, fingerprint="")
    profile.fingerprint = compute_fingerprint(profile)
    return profile


def sample_values(records: Iterable[Mapping[str, Any]], *, per_column: int = 5) -> SampleView:
    """Collect a small, redactable per-column value sample for the proposer (design.md 9.1)."""
    values: dict[str, list[Any]] = {}
    for record in records:
        for key, value in record.items():
            bucket = values.setdefault(key, [])
            if len(bucket) < per_column and not _is_null(value) and value not in bucket:
                bucket.append(value)
    return SampleView(values=values)


# --- internals -----------------------------------------------------------------------


def _collect_columns(
    records: Iterable[Mapping[str, Any]], sample_rows: int
) -> tuple[dict[str, list[Any]], int]:
    """Return ``{column: [values...]}`` in first-seen column order, plus the row count sampled.

    A column absent from a given row contributes a ``MISSING`` sentinel so nullability reflects
    ragged records, not just explicit nulls.
    """
    columns: dict[str, list[Any]] = {}
    seen = 0
    for record in records:
        if seen >= sample_rows:
            break
        seen += 1
        for key in record:
            columns.setdefault(key, [])
        for key, bucket in columns.items():
            bucket.append(record.get(key, _MISSING))
    return columns, seen


class _Missing:
    __slots__ = ()


_MISSING: Final = _Missing()


def _is_null(value: Any) -> bool:
    """A cell is null if absent, ``None``, or the empty/whitespace string (the CSV footgun)."""
    if value is _MISSING or value is None:
        return True
    return isinstance(value, str) and value.strip() == ""


def _profile_column(name: str, values: list[Any]) -> FieldProfile:
    non_null = [v for v in values if not _is_null(v)]
    nullable = len(non_null) < len(values)
    inferred, confidence, alternatives = _infer_type(name, non_null)
    facets = _facets(non_null, inferred)
    return FieldProfile(
        path=name,
        inferred_type=inferred,
        type_confidence=confidence,
        nullable=nullable,
        alternatives=alternatives,
        facets=facets,
    )


def _infer_type(name: str, non_null: list[Any]) -> tuple[ScalarType, float, list[ScalarType]]:
    """Return ``(inferred_type, confidence, alternatives)`` under ID-safe rules (design.md 5.3)."""
    if not non_null:
        return ScalarType.STRING, 1.0, []

    # typed JSON scalars carry no coercion footgun, so trust them
    native = _native_type(non_null)
    if native is not None:
        return native, 1.0, []

    strings = [str(v) for v in non_null]
    numeric_blocked = bool(_ID_NAME_RE.search(name)) or any(_blocks_numeric(s) for s in strings)

    if not numeric_blocked and all(_is_intlike(s) for s in strings):
        return ScalarType.INTEGER, 1.0, []
    if not numeric_blocked and all(_is_floatlike(s) for s in strings):
        return ScalarType.NUMBER, 1.0, []
    if all(_is_boollike(s) for s in strings):
        return ScalarType.BOOLEAN, 1.0, []
    if all(_is_datetimelike(s) for s in strings):
        return ScalarType.DATETIME, 1.0, []
    if all(_is_datelike(s) for s in strings):
        return ScalarType.DATE, 1.0, []

    # values that look numeric but were blocked: offer the type back so the proposer may still
    # choose an explicit cast_type, without the profiler risking the lossy coercion itself
    alternatives: list[ScalarType] = []
    if numeric_blocked and all(_is_floatlike(s) for s in strings):
        alternatives.append(
            ScalarType.INTEGER if all(_is_intlike(s) for s in strings) else ScalarType.NUMBER
        )
    confidence = 0.7 if alternatives else 1.0
    return ScalarType.STRING, confidence, alternatives


def _native_type(non_null: list[Any]) -> ScalarType | None:
    """Map already-typed JSON scalars to a canonical type; ``None`` if any value is a string."""
    if any(isinstance(v, str) for v in non_null):
        return None
    if all(isinstance(v, bool) for v in non_null):
        return ScalarType.BOOLEAN
    if all(isinstance(v, (bool, int)) for v in non_null):
        return ScalarType.INTEGER
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non_null):
        return ScalarType.NUMBER
    if all(isinstance(v, datetime) for v in non_null):
        return ScalarType.DATETIME
    if all(isinstance(v, date) for v in non_null):
        return ScalarType.DATE
    return None


def _blocks_numeric(s: str) -> bool:
    """True if a string value must keep the column ``string`` (design.md 5.3 loss guards)."""
    stripped = s.strip()
    digits = stripped.lstrip("+-")
    if len(digits) > 1 and digits[0] == "0" and digits.isdigit():
        return True  # zip / phone / zero-padded id — leading zeros are significant
    if sum(c.isdigit() for c in stripped) > _MAX_SAFE_DIGITS:
        return True  # would lose precision as an int
    return bool(_DIGIT_SEPARATOR_RE.search(stripped))  # phone / formatted number


def _is_intlike(s: str) -> bool:
    t = s.strip()
    if not t:
        return False
    body = t[1:] if t[0] in "+-" else t
    return body.isdigit()


def _is_floatlike(s: str) -> bool:
    t = s.strip()
    if not t:
        return False
    try:
        float(t)
    except ValueError:
        return False
    return t.lower() not in {"nan", "inf", "-inf", "+inf", "infinity"}


def _is_boollike(s: str) -> bool:
    t = s.strip().lower()
    return t in _TRUE_TOKENS or t in _FALSE_TOKENS


def _is_datelike(s: str) -> bool:
    try:
        date.fromisoformat(s.strip())
    except ValueError:
        return False
    return True


def _is_datetimelike(s: str) -> bool:
    t = s.strip().replace("Z", "+00:00")
    try:
        datetime.fromisoformat(t)
    except ValueError:
        return False
    return True


def _facets(non_null: list[Any], inferred: ScalarType) -> ValueFacets | None:
    """Value facets for cache/proposer guards: low-cardinality distinct set + parse rate."""
    if not non_null:
        return None
    distinct = list(dict.fromkeys(str(v) for v in non_null))
    facets = ValueFacets()
    populated = False
    if len(distinct) <= _LOW_CARDINALITY_MAX:
        facets.distinct_values = sorted(distinct)[:_DISTINCT_FACET_CAP]
        populated = True
    if inferred in (ScalarType.DATE, ScalarType.DATETIME):
        facets.detected_formats = ["iso-8601"]
        facets.parse_rate = 1.0
        populated = True
    return facets if populated else None


def _read_records(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    if suffix == ".jsonl":
        with path.open("r", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]
    if suffix == ".json":
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ValueError(f"{path}: JSON source must be an array of records")
        return data
    raise ValueError(f"{path}: unsupported source extension {suffix!r}")
