<div align="center">

# 🔀 schema-crosswalk

**Grammar-constrained schema mapping — an LLM *proposes*, a deterministic engine *executes*.**

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Status](https://img.shields.io/badge/status-pre--alpha-orange.svg)](#status)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Types: mypy strict](https://img.shields.io/badge/types-mypy%20strict-2a6db2.svg)](https://mypy-lang.org/)

[Why](#why) · [Install](#install) · [Quickstart](#quickstart) · [The primitive grammar](#the-primitive-grammar) · [Design doc](docs/design.md)

</div>

---

`schema-crosswalk` is an open-source, embeddable engine that maps arbitrary CSV/JSON source
data into a fixed target schema. An **LLM proposes** a mapping constrained to a small,
versioned grammar of primitives; a **deterministic engine executes** it. The LLM never writes
or runs code — it only selects and parameterizes primitives, so every mapping is auditable,
reproducible, and testable before it touches production data.

## Status

> **Pre-alpha.** The primitive grammar and the public API surface are in place; the
> deterministic executor and the model backends are being implemented. The
> [Quickstart](#quickstart) Python example below is the **target API** — treat it as the
> shape we are building toward, not a promise of what runs today.

| Component | State | Ships in |
|---|---|---|
| Grammar manifest (`crosswalk primitives`) | ✅ works today | — |
| Schema profiler (`profile`) | 🚧 in progress | Phase 1 |
| Validator (`validate`) | 🚧 in progress | Phase 1 |
| Executor (`execute`) | 🚧 in progress | Phase 1 |
| Review / approve flow (`review`, `approve`) | 🚧 in progress | Phase 2 |
| Mapping proposer + backends (`propose`) | 🚧 in progress | Phase 2 |

See [`docs/design.md`](docs/design.md) for the full architecture and [`prd.md`](prd.md) for
product intent.

## Why

- **Low-hallucination** — the model picks from a fixed grammar, never emits arbitrary code.
- **Deterministic** — same input + same mapping ⇒ byte-identical output, always.
- **Embeddable** — a library, not a platform. Drop it into Airflow, dbt, an agent, or a script.
- **Auditable** — every mapping is inspectable, versioned, and gated by confidence before use.

### How it works

The **only** component that calls a model is the proposer. Everything downstream —
profile, validate, review, execute, cache — is pure and deterministic.

```
 source file      ┌──────────────────┐
 (CSV/JSON)   →   │ Schema Profiler  │  infer shape (ID-safe) → fingerprint → cache lookup
                  └───────┬──────────┘
                          │ miss
                          ▼
                  ┌──────────────────┐
                  │ Mapping Proposer │  LLM, constrained by a BackendAdapter; sees sample VALUES
                  └───────┬──────────┘
                          │ MappingDocument (JSON, pinned to grammar + semantics versions)
                          ▼
                  ┌──────────────────┐
                  │ Validator        │  JSON Schema + semantic checks + per-field confidence
                  └───────┬──────────┘
             ┌────────────┼───────────────┐
             ▼            ▼                ▼
        auto_apply    needs_review     unmapped
             │            │  (ReviewPackage → human decision → ApprovalRecord)
             ▼            ▼
                  ┌──────────────────┐
                  │ Execution Engine │  pure interpreter over primitives — no LLM, ever
                  └───────┬──────────┘
                          ▼
              records matching target schema  +  ExecutionReport
```

Two version axes are pinned in every mapping — `grammar_version` (the set of primitives) and
`semantics_version` (coercion / normalize / arithmetic / parse behavior, bumped even for bug
fixes). A pinned mapping's output therefore never changes silently.

## Install

```bash
# As a dependency in your project:
uv add schema-crosswalk

# For local development, from a checkout:
uv sync
```

Model backends are **optional extras** — the core installs and runs (profile / validate /
execute) without any of them:

```bash
uv add "schema-crosswalk[anthropic]"   # or [openai], [outlines], [xgrammar]
```

## Quickstart

**Target API** — the end-to-end workflow the library is being built toward:

```python
from schema_crosswalk import Crosswalk

cw = Crosswalk()                                     # configure a backend + cache
profile = cw.profile("customers.csv")                # infer source shape (ID-safe)
mapping = cw.propose(profile, target_schema=SCHEMA)  # LLM picks primitives
report  = cw.validate(mapping, target_schema=SCHEMA) # structural + confidence gating
records = cw.execute(mapping, "customers.csv")       # deterministic, no LLM
```

**CLI.** The grammar manifest is live today:

```bash
uv run crosswalk primitives          # list the 11 grammar primitives
uv run crosswalk primitives --json   # emit the raw manifest as JSON
```

The remaining subcommands are wired into the CLI and land with the executor:

```bash
uv run crosswalk profile  customers.csv > profile.json                        # planned
uv run crosswalk propose  profile.json --target schema.json > mapping.json    # planned
uv run crosswalk validate mapping.json --target schema.json                   # planned
uv run crosswalk execute  mapping.json customers.csv > out.jsonl              # planned
```

## The primitive grammar

An LLM proposal may only use these **11 primitives** (`grammar_version: 1`). Each is a named
transform with a strict, closed parameter schema — no primitive accepts a formula, template,
or eval-able string, so a proposal can never smuggle in code.

| Primitive | Sources | Purpose |
|---|:---:|---|
| `rename_field` | 1 | Copy a source field to a target field unchanged. |
| `cast_type` | 1 | Coerce a value to a target scalar type. |
| `normalize_string` | 1 | Apply an ordered list of enumerated string ops (trim, case, collapse, strip). |
| `arithmetic` | 1 | Apply an ordered list of enumerated numeric ops (+ − × ÷, round) with constant operands. |
| `map_enum_value` | 1 | Map source categoricals to target enum values via a lookup table. |
| `concat_fields` | 2+ | Join source fields into one string with a separator. |
| `split_field` | 1 | Extract one component of a string split by delimiter/regex. |
| `coalesce` | 2+ | First non-null of an ordered list of sources, with optional default. |
| `default_value` | 0–1 | Emit a constant, or fill when the optional source is null/missing. |
| `nested_extract` | 1 | Pull a value from a nested path (`a.b[0].c`) in a structured source. |
| `nested_flatten` | 1 | Serialize a nested object/array to a JSON string for a flat target. |

The JSON Schema files under [`src/schema_crosswalk/grammar/`](src/schema_crosswalk/grammar/)
are the single source of truth for the grammar; code and docs mirror them. Every param schema
is closed (`additionalProperties: false`), and every lossy op declares an explicit failure
policy (`on_error` / `unmatched` / `on_missing`) — behavior on bad data is declared, never
implicit. Fields the grammar can't express are surfaced as `unmapped`; low-confidence fields go
to `needs_review`. See [`docs/design.md`](docs/design.md) §4–§7 for the full contracts.

## Development

Tooling is standardized on `uv`, `ruff`, `mypy --strict`, and `pytest`. See
[`CLAUDE.md`](CLAUDE.md) for project invariants and [`docs/design.md`](docs/design.md) for the
architecture.

```bash
uv sync                  # create/refresh the venv from the lockfile
uv run ruff check .      # lint
uv run ruff format .     # format
uv run mypy .            # type-check (strict)
uv run pytest            # tests
```

Run all four green before every commit.

## Contributing

Read [`docs/design.md`](docs/design.md) first — it is the source of truth for the grammar and
execution semantics. A few ground rules:

- **A grammar change is a four-part PR**: the JSON Schema under `crosswalk/grammar/vN/`, a
  golden fixture exercising it, the matching `docs/design.md` update, and the appropriate
  `grammar_version` / `semantics_version` bump — all in the same PR.
- **No LLM in the execution path, ever.** Only the proposer and backends may call a model.
- **All fixtures are synthetic or from public open data** — never production or customer data.

## License

[Apache-2.0](LICENSE).
