"""Deterministic execution engine. [PURE]

A pure interpreter over the validated primitive list. No LLM. Same source record + same
mapping (+ pinned semantics_version) => byte-identical output (design.md 6.2). Each primitive
is a pure function of its resolved inputs and static params; the dispatch table below is the
single place execution logic is registered.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import ExecutionReport, MappingDocument, Primitive

# A handler maps (resolved source inputs, params) -> the produced value.
PrimitiveHandler = Callable[[list[Any], Mapping[str, Any]], Any]


@dataclass
class ExecutionResult:
    records: list[dict[str, Any]] = field(default_factory=list)
    report: ExecutionReport = field(default_factory=ExecutionReport)


def _rename_field(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    raise NotImplementedError


def _cast_type(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    raise NotImplementedError


def _normalize_string(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    raise NotImplementedError


def _arithmetic(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    raise NotImplementedError


def _map_enum_value(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    raise NotImplementedError


def _concat_fields(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    raise NotImplementedError


def _split_field(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    raise NotImplementedError


def _coalesce(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    raise NotImplementedError


def _default_value(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    raise NotImplementedError


def _nested_extract(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    raise NotImplementedError


def _nested_flatten(inputs: list[Any], params: Mapping[str, Any]) -> Any:
    raise NotImplementedError


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


def execute_record(
    mapping: MappingDocument,
    record: Mapping[str, Any],
    *,
    assemble_nested: bool = False,
    allow_unreviewed: bool = False,
) -> dict[str, Any]:
    """Apply the mapping to a single source record and return the output record."""
    raise NotImplementedError


def execute_records(
    mapping: MappingDocument,
    records: Iterable[Mapping[str, Any]],
    *,
    assemble_nested: bool = False,
    allow_unreviewed: bool = False,
) -> ExecutionResult:
    """Apply the mapping to an iterable of records, collecting an :class:`ExecutionReport`."""
    raise NotImplementedError


def execute_file(
    mapping: MappingDocument,
    path: str | Path,
    out_path: str | Path,
    *,
    assemble_nested: bool = False,
    allow_unreviewed: bool = False,
) -> ExecutionReport:
    """Stream-execute a source file to a JSONL output file; returns the report."""
    raise NotImplementedError
