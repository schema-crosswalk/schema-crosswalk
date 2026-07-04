"""``crosswalk`` command-line interface (design.md 12.3).

Subcommands mirror the library workflow. ``primitives`` is fully implemented (read-only,
reads the grammar); the data-path subcommands are wired but their engine steps are still
being implemented.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from . import __version__, grammar

_NOT_IMPLEMENTED_EXIT = 2


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

    for name, help_text in [
        ("profile", "Profile a source file into a SourceProfile."),
        ("propose", "Propose a mapping (requires a backend)."),
        ("validate", "Validate a mapping against a target schema."),
        ("review", "Emit a ReviewPackage for a mapping."),
        ("approve", "Apply an approval decision to a mapping."),
        ("execute", "Execute a mapping over a source file."),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.set_defaults(func=lambda _a, _n=name: _todo(_n))

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
