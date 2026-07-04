"""The 11 grammar primitives as pure handlers. [PURE]

Each handler is a pure function of its resolved inputs and static params (design.md 4.1); the
:data:`HANDLERS` table is the single place execution logic is registered. Handlers that can
raise :class:`RecordFailure` read the target field from ``params["__target__"]``, injected by
the engine so a ``fail`` policy can name the field it aborted on.
"""

from __future__ import annotations

import json
import re
import string
from collections.abc import Callable, Mapping
from typing import Any, Final

from schema_crosswalk.models import Primitive

from . import coerce
from .runtime import (
    _MAX_REGEX_INPUT,
    _PATH_TOKEN_RE,
    MISSING,
    CoercionError,
    PrimitiveHandler,
    RecordFailure,
    is_nullish,
)


def _target(params: Mapping[str, Any]) -> str:
    tf = params.get("__target__")
    return tf if isinstance(tf, str) else "<unknown>"


def _apply_error_policy(target_field: str, params: Mapping[str, Any], exc: CoercionError) -> Any:
    """Resolve an ``on_error`` policy (null|fail|default) after a coercion failure."""
    policy = params.get("on_error", "null")
    if policy == "null":
        return None
    if policy == "default":
        return params.get("default")
    raise RecordFailure(target_field, str(exc))


def _rename_field(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    value = inputs[0]
    return None if value is MISSING else value


def _cast_type(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    value = inputs[0]
    if is_nullish(value):
        return None
    try:
        return coerce.coerce(value, params["to"], fmt=params.get("format"), unit=params.get("unit"))
    except CoercionError as exc:
        return _apply_error_policy(_target(params), params, exc)


_PUNCT_TABLE: Final = {ord(c): None for c in string.punctuation}
_WS_RE: Final = re.compile(r"\s+")

_NORMALIZE_OPS: Final[dict[str, Callable[[str], str]]] = {
    "trim": str.strip,
    "ltrim": str.lstrip,
    "rtrim": str.rstrip,
    "lower": str.lower,
    "upper": str.upper,
    "title": str.title,
    "collapse_whitespace": lambda s: _WS_RE.sub(" ", s).strip(),
    "strip_punctuation": lambda s: s.translate(_PUNCT_TABLE),
    "digits_only": lambda s: "".join(ch for ch in s if ch.isdigit()),
}


def _normalize_string(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    value = inputs[0]
    if is_nullish(value):
        return None
    text = value if isinstance(value, str) else coerce.to_string(value)
    for op in params["ops"]:
        text = _NORMALIZE_OPS[op](text)
    return text


def _arithmetic(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    value = inputs[0]
    if is_nullish(value):
        return None
    try:
        acc = coerce.to_number(value)
        for step in params["ops"]:
            operand = step["operand"]
            op = step["op"]
            if op == "add":
                acc += operand
            elif op == "subtract":
                acc -= operand
            elif op == "multiply":
                acc *= operand
            elif op == "divide":
                if operand == 0:
                    raise CoercionError("division by zero")
                acc /= operand
    except CoercionError as exc:
        return _apply_error_policy(_target(params), params, exc)
    if "round" in params:
        acc = round(acc, params["round"])
    return acc


def _map_enum_value(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    value = inputs[0]
    table: Mapping[str, Any] = params["mapping"]
    key = None if value is MISSING else value
    if isinstance(key, str) and params.get("case_insensitive", False):
        lowered = {k.lower(): v for k, v in table.items()}
        if key.lower() in lowered:
            return lowered[key.lower()]
    elif isinstance(key, str) and key in table:
        return table[key]
    policy = params.get("unmatched", "null")
    if policy == "null":
        return None
    if policy == "passthrough":
        return key
    if policy == "default":
        return params.get("default")
    raise RecordFailure(_target(params), f"unmapped enum value {value!r}")


def _concat_fields(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    separator = params.get("separator", " ")
    skip_null = params.get("skip_null", True)
    parts: list[str] = []
    for value in inputs:
        if is_nullish(value):
            if skip_null:
                continue
            parts.append("")
        else:
            parts.append(coerce.to_string(value))
    return separator.join(parts)


def _regex_split(pattern: str, text: str) -> list[str]:
    try:  # non-backtracking engine when available (design.md 7.2)
        import re2

        return list(re2.split(pattern, text))
    except ImportError:
        if len(text) > _MAX_REGEX_INPUT:
            text = text[:_MAX_REGEX_INPUT]
        return re.split(pattern, text)


def _split_field(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    value = inputs[0]
    if is_nullish(value):
        return None
    text = value if isinstance(value, str) else coerce.to_string(value)
    if "pattern" in params:
        parts = _regex_split(params["pattern"], text)
    else:
        parts = text.split(params["delimiter"])
    index = params["index"]
    if index < len(parts):
        return parts[index]
    if params.get("on_missing_index", "null") == "fail":
        raise RecordFailure(_target(params), f"split index {index} out of range")
    return None


def _coalesce(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    treat_empty = params.get("treat_empty_string_as_null", True)
    for value in inputs:
        if value is MISSING or value is None:
            continue
        if treat_empty and value == "":
            continue
        return value
    return params.get("default")


def _default_value(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    constant = params["value"]
    if not inputs:  # arity 0: always emit the constant
        return constant
    value = inputs[0]
    if params.get("only_when_missing", True):
        return constant if is_nullish(value) else value
    return constant


def _navigate(root: Any, path: str) -> Any:
    current = root
    if current is MISSING:
        raise KeyError(path)
    for match in _PATH_TOKEN_RE.finditer(path):
        index, key = match.group(1), match.group(2)
        current = current[int(index)] if index is not None else current[key]
    return current


def _nested_extract(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    value = inputs[0]
    fail = params.get("on_missing", "null") == "fail"
    try:
        return _navigate(value, params["path"])
    except (KeyError, IndexError, TypeError) as exc:
        if fail:
            raise RecordFailure(_target(params), f"path {params['path']!r}: {exc}") from exc
        return None


def _nested_flatten(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    value = inputs[0]
    if is_nullish(value):
        return None
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


HANDLERS: dict[Primitive, PrimitiveHandler] = {
    Primitive.RENAME_FIELD: _rename_field,
    Primitive.CAST_TYPE: _cast_type,
    Primitive.NORMALIZE_STRING: _normalize_string,
    Primitive.ARITHMETIC: _arithmetic,
    Primitive.MAP_ENUM_VALUE: _map_enum_value,
    Primitive.CONCAT_FIELDS: _concat_fields,
    Primitive.SPLIT_FIELD: _split_field,
    Primitive.COALESCE: _coalesce,
    Primitive.DEFAULT_VALUE: _default_value,
    Primitive.NESTED_EXTRACT: _nested_extract,
    Primitive.NESTED_FLATTEN: _nested_flatten,
}
