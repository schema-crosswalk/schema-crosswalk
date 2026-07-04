"""Execution loops, source resolution, nested assembly, and JSONL I/O. [PURE]

The interpreter proper (design.md 6.2, 12.1): one immutable source record in, one output record
out, rules applied in listed order. Same source record + same mapping (+ pinned
``semantics_version``) => byte-identical output. No wall-clock/RNG/locale/ambient state.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from schema_crosswalk.models import ExecutionError, ExecutionReport, FieldStatus, MappingDocument

from .primitives import HANDLERS
from .runtime import (
    _INTERMEDIATE_PREFIX,
    _PATH_TOKEN_RE,
    MISSING,
    ExecutionEngineError,
    RecordFailure,
)


@dataclass
class ExecutionResult:
    records: list[dict[str, Any]] = field(default_factory=list)
    report: ExecutionReport = field(default_factory=ExecutionReport)


def _resolve(source: str, record: Mapping[str, Any], output: Mapping[str, Any]) -> Any:
    """Resolve a source ref: source record first, then the output record (composition)."""
    if source in record:
        return record[source]
    if source in output:
        return output[source]
    return MISSING


def _included(field_name: str, mapping: MappingDocument, allow_unreviewed: bool) -> bool:
    if field_name.startswith(_INTERMEDIATE_PREFIX):
        return False  # intermediate; dropped before output (design.md 6.3)
    if allow_unreviewed:
        return True
    status = mapping.field_status.get(field_name)
    return status is None or status == FieldStatus.AUTO_APPLY


def execute_record(
    mapping: MappingDocument,
    record: Mapping[str, Any],
    *,
    assemble_nested: bool = False,
    allow_unreviewed: bool = False,
) -> dict[str, Any]:
    """Apply the mapping to a single source record and return the output record.

    Raises :class:`RecordFailure` if any rule's ``fail`` policy fires.
    """
    output: dict[str, Any] = {}
    for rule in mapping.rules:
        inputs = [_resolve(src, record, output) for src in rule.sources]
        params = {**rule.params, "__target__": rule.target_field}
        output[rule.target_field] = HANDLERS[rule.primitive](inputs, params)

    result = {
        name: value for name, value in output.items() if _included(name, mapping, allow_unreviewed)
    }
    if assemble_nested:
        result = _assemble_nested(result)
    return result


def _assemble_nested(flat: Mapping[str, Any]) -> dict[str, Any]:
    """Fold dotted / ``[i]`` target paths into a nested structure (design.md 5.4)."""
    root: dict[str, Any] = {}
    for path, value in flat.items():
        tokens = [(m.group(1), m.group(2)) for m in _PATH_TOKEN_RE.finditer(path)]
        _set_path(root, tokens, value)
    return root


def _set_path(
    root: dict[str, Any], tokens: list[tuple[str | None, str | None]], value: Any
) -> None:
    cursor: Any = root
    for pos, (index, key) in enumerate(tokens):
        last = pos == len(tokens) - 1
        nxt_index = tokens[pos + 1][0] if not last else None
        if index is not None:
            idx = int(index)
            while len(cursor) <= idx:
                cursor.append(None)
            if last:
                cursor[idx] = value
            else:
                if not isinstance(cursor[idx], (dict, list)):
                    cursor[idx] = [] if nxt_index is not None else {}
                cursor = cursor[idx]
        else:
            assert key is not None
            if last:
                cursor[key] = value
            else:
                if key not in cursor or not isinstance(cursor[key], (dict, list)):
                    cursor[key] = [] if nxt_index is not None else {}
                cursor = cursor[key]


def execute_records(
    mapping: MappingDocument,
    records: Iterable[Mapping[str, Any]],
    *,
    assemble_nested: bool = False,
    allow_unreviewed: bool = False,
) -> ExecutionResult:
    """Apply the mapping to an iterable of records, collecting an :class:`ExecutionReport`."""
    result = ExecutionResult()
    for i, record in enumerate(records):
        result.report.records_in += 1
        try:
            out = execute_record(
                mapping,
                record,
                assemble_nested=assemble_nested,
                allow_unreviewed=allow_unreviewed,
            )
        except RecordFailure as exc:
            result.report.records_failed += 1
            result.report.errors.append(
                ExecutionError(record_index=i, target_field=exc.target_field, message=exc.message)
            )
            continue
        result.records.append(out)
        result.report.records_out += 1
    return result


def _read_records(path: Path) -> Iterator[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as fh:
            yield from csv.DictReader(fh)
    elif suffix == ".jsonl":
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)
    elif suffix == ".json":
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ExecutionEngineError(f"{path}: JSON source must be an array of records")
        yield from data
    else:
        raise ExecutionEngineError(f"{path}: unsupported source extension {suffix!r}")


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def dumps_record(record: Mapping[str, Any]) -> str:
    """Serialize an output record to a canonical single-line JSON string (one JSONL row).

    Compact separators + insertion (rule) order + ISO-8601 for temporal values, so output is
    stable and byte-diffable against golden ``expected.jsonl`` fixtures.
    """
    return json.dumps(record, default=_json_default, ensure_ascii=False, separators=(",", ":"))


def execute_file(
    mapping: MappingDocument,
    path: str | Path,
    out_path: str | Path,
    *,
    assemble_nested: bool = False,
    allow_unreviewed: bool = False,
) -> ExecutionReport:
    """Stream-execute a source file to a JSONL output file; returns the report."""
    src = Path(path)
    dst = Path(out_path)
    report = ExecutionReport()
    with dst.open("w", encoding="utf-8") as out:
        for i, record in enumerate(_read_records(src)):
            report.records_in += 1
            try:
                mapped = execute_record(
                    mapping,
                    record,
                    assemble_nested=assemble_nested,
                    allow_unreviewed=allow_unreviewed,
                )
            except RecordFailure as exc:
                report.records_failed += 1
                report.errors.append(
                    ExecutionError(
                        record_index=i, target_field=exc.target_field, message=exc.message
                    )
                )
                continue
            out.write(dumps_record(mapped))
            out.write("\n")
            report.records_out += 1
    return report
