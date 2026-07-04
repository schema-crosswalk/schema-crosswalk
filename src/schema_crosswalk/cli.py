"""``crosswalk`` command-line interface (design.md 12.3).

Subcommands mirror the library workflow: ``primitives``, ``profile``, ``propose`` (needs a
backend extra), ``validate``, and ``execute`` are implemented; ``review`` / ``approve`` are
scaffolded and land next.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__, execute, grammar, profile, validate
from .backends import BackendAdapter, BackendNotInstalled
from .models import MappingDocument

_NOT_IMPLEMENTED_EXIT = 2
_VALIDATION_EXIT = 1


def _load_schema(path: str) -> dict[str, object]:
    data: dict[str, object] = json.loads(Path(path).read_text(encoding="utf-8"))
    return data


def _cmd_primitives(args: argparse.Namespace) -> int:
    version = int(args.grammar_version)
    manifest = grammar.load_manifest(version)
    primitives: dict[str, dict[str, object]] = manifest["primitives"]
    if args.json:
        json.dump(manifest, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    print(f"schema-crosswalk grammar v{version} — {len(primitives)} primitives\n")
    for name, info in primitives.items():
        lo, hi = grammar.source_arity(name, version)
        arity = f"{lo}+" if hi is None else (str(lo) if lo == hi else f"{lo}-{hi}")
        print(f"  {name:<16} sources={arity:<4} {info['summary']}")
    return 0


def _cmd_execute(args: argparse.Namespace) -> int:
    mapping = MappingDocument.model_validate_json(Path(args.mapping).read_text(encoding="utf-8"))
    errors = execute.structural_check(mapping)
    if errors:
        print("mapping is not runnable:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return _VALIDATION_EXIT
    report = execute.execute_file(
        mapping,
        args.source,
        args.out,
        assemble_nested=args.assemble_nested,
        allow_unreviewed=args.allow_unreviewed,
    )
    print(
        f"executed {report.records_in} records -> {report.records_out} written, "
        f"{report.records_failed} failed ({args.out})",
        file=sys.stderr,
    )
    return _VALIDATION_EXIT if report.records_failed else 0


def _cmd_profile(args: argparse.Namespace) -> int:
    prof = profile.profile_file(args.source, sample_rows=args.sample_rows)
    print(prof.model_dump_json(indent=2))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    mapping = MappingDocument.model_validate_json(Path(args.mapping).read_text(encoding="utf-8"))
    target = _load_schema(args.target)
    sample = None
    if args.source is not None:
        sample = profile.sample_values(profile._read_records(Path(args.source)))
    report = validate.validate_mapping(mapping, target, sample=sample)
    print(report.model_dump_json(indent=2))
    return 0 if report.ok else _VALIDATION_EXIT


def _cmd_propose(args: argparse.Namespace) -> int:
    from . import propose as _propose

    backend = _build_backend(args.backend, args.model)
    records = profile._read_records(Path(args.source))
    prof = profile.profile_records(records, sample_rows=args.sample_rows)
    sample = profile.sample_values(records)
    target = _load_schema(args.target)
    mapping = _propose.propose_mapping(backend, prof, target, sample=sample)
    print(mapping.model_dump_json(indent=2))
    return 0


def _build_backend(name: str, model: str | None) -> BackendAdapter:
    if name != "anthropic":
        raise SystemExit(f"unknown backend {name!r} (available: anthropic)")
    from .backends.anthropic import DEFAULT_MODEL, AnthropicAdapter

    try:
        return AnthropicAdapter(model=model or DEFAULT_MODEL)
    except BackendNotInstalled as exc:
        raise SystemExit(str(exc)) from exc


def _todo(name: str) -> int:
    print(
        f"`crosswalk {name}` is scaffolded but not implemented yet.",
        file=sys.stderr,
    )
    return _NOT_IMPLEMENTED_EXIT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crosswalk", description="Grammar-constrained schema mapping."
    )
    parser.add_argument("--version", action="version", version=f"schema-crosswalk {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prim = sub.add_parser("primitives", help="List the grammar primitives.")
    p_prim.add_argument("--grammar-version", default=grammar.CURRENT_GRAMMAR_VERSION)
    p_prim.add_argument("--json", action="store_true", help="Emit the raw manifest as JSON.")
    p_prim.set_defaults(func=_cmd_primitives)

    p_prof = sub.add_parser("profile", help="Profile a source file into a SourceProfile.")
    p_prof.add_argument("source", help="Source file (.csv | .json | .jsonl).")
    p_prof.add_argument("--sample-rows", type=int, default=1000)
    p_prof.set_defaults(func=_cmd_profile)

    p_prop = sub.add_parser(
        "propose", help="Propose a mapping from a source file (needs a backend)."
    )
    p_prop.add_argument("source", help="Source file (.csv | .json | .jsonl).")
    p_prop.add_argument("--target", required=True, help="Target JSON Schema file.")
    p_prop.add_argument(
        "--backend", default="anthropic", help="Backend adapter (default: anthropic)."
    )
    p_prop.add_argument("--model", default=None, help="Model id (default: the backend's default).")
    p_prop.add_argument("--sample-rows", type=int, default=1000)
    p_prop.set_defaults(func=_cmd_propose)

    p_val = sub.add_parser("validate", help="Validate a mapping against a target schema.")
    p_val.add_argument("--mapping", required=True, help="Path to a MappingDocument JSON file.")
    p_val.add_argument("--target", required=True, help="Target JSON Schema file.")
    p_val.add_argument(
        "--source", default=None, help="Optional source file for confidence de-rating."
    )
    p_val.set_defaults(func=_cmd_validate)

    for name, help_text in [
        ("review", "Emit a ReviewPackage for a mapping."),
        ("approve", "Apply an approval decision to a mapping."),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.set_defaults(func=lambda _a, _n=name: _todo(_n))

    p_exec = sub.add_parser("execute", help="Execute a mapping over a source file.")
    p_exec.add_argument("source", help="Source file (.csv | .json | .jsonl).")
    p_exec.add_argument("--mapping", required=True, help="Path to a MappingDocument JSON file.")
    p_exec.add_argument("--out", required=True, help="Output JSONL path.")
    p_exec.add_argument(
        "--allow-unreviewed",
        action="store_true",
        help="Include fields whose status is not auto_apply.",
    )
    p_exec.add_argument(
        "--assemble-nested",
        action="store_true",
        help="Fold dotted target paths into nested output.",
    )
    p_exec.set_defaults(func=_cmd_execute)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
