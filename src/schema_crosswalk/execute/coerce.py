"""Scalar coercion table. [PURE]

The only implicit-conversion site (design.md 5.2), governed by ``semantics_version`` so a fix
never silently changes a pinned mapping's output. All temporal work is done in UTC and yields
naive values, so serialized output carries no timezone offset. Every failure raises
:class:`CoercionError`; callers map that to their declared ``on_error`` policy.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Final

from .runtime import CoercionError

_TRUTHY: Final = frozenset({"true", "t", "yes", "y", "1"})
_FALSY: Final = frozenset({"false", "f", "no", "n", "0"})


def _epoch_to_datetime(value: int, unit: str) -> datetime:
    seconds = value / 1000 if unit == "millis" else value
    return datetime.fromtimestamp(seconds, UTC).replace(tzinfo=None)


def to_integer(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise CoercionError(f"non-integral number {value!r} to integer")
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError as exc:
            raise CoercionError(f"cannot parse {value!r} as integer") from exc
    raise CoercionError(f"cannot coerce {type(value).__name__} to integer")


def to_number(value: Any) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        try:
            return float(text)
        except ValueError as exc:
            raise CoercionError(f"cannot parse {value!r} as number") from exc
    raise CoercionError(f"cannot coerce {type(value).__name__} to number")


def to_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUTHY:
            return True
        if text in _FALSY:
            return False
        raise CoercionError(f"cannot parse {value!r} as boolean")
    raise CoercionError(f"cannot coerce {type(value).__name__} to boolean")


def to_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _to_date(value: Any, fmt: str | None) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            if fmt is not None:
                return datetime.strptime(text, fmt).date()
            return date.fromisoformat(text)
        except ValueError as exc:
            raise CoercionError(f"cannot parse {value!r} as date") from exc
    raise CoercionError(f"cannot coerce {type(value).__name__} to date")


def _to_datetime(value: Any, fmt: str | None, unit: str | None) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, bool):
        raise CoercionError("cannot coerce boolean to datetime")
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, int):
        return _epoch_to_datetime(value, unit or "seconds")
    if isinstance(value, str):
        text = value.strip()
        try:
            if fmt is not None:
                return datetime.strptime(text, fmt)
            return datetime.fromisoformat(text)
        except ValueError as exc:
            raise CoercionError(f"cannot parse {value!r} as datetime") from exc
    raise CoercionError(f"cannot coerce {type(value).__name__} to datetime")


def coerce(value: Any, to: str, *, fmt: str | None = None, unit: str | None = None) -> Any:
    """Coerce ``value`` to a canonical scalar type. Raises :class:`CoercionError` on failure."""
    if to == "string":
        return to_string(value)
    if to == "integer":
        return to_integer(value)
    if to == "number":
        return to_number(value)
    if to == "boolean":
        return to_boolean(value)
    if to == "date":
        return _to_date(value, fmt)
    if to == "datetime":
        return _to_datetime(value, fmt, unit)
    raise CoercionError(f"unknown target type {to!r}")
