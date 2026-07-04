# CLAUDE.md — schema-crosswalk

Guidance for Claude Code (and humans) working in this repo. Read this before writing code.

## Project overview

`schema-crosswalk` is an open-source, embeddable engine that maps arbitrary CSV/JSON
source data into a fixed target schema. An **LLM proposes** a mapping constrained to a
small, versioned grammar of primitives; a **deterministic engine executes** it. The LLM
never writes or runs code — it only selects and parameterizes primitives.

- **`docs/design.md` is the source of truth** for architecture, the primitive grammar, and
  execution semantics. Read the relevant section before touching grammar, the executor, the
  validator, or the cache. `prd.md` holds product intent.
- Python 3.11+, package `schema_crosswalk`, CLI `crosswalk`, license Apache-2.0.

## Golden rules (project invariants — do not violate)

1. **No LLM in the execution path — ever.** Only `crosswalk.propose` and
   `crosswalk.backends.*` may call a model. Everything downstream is pure.
2. **Pure modules stay pure and deterministic.** `profile`, `fingerprint`, `validate`,
   `review`, `execute`, `cache` must not read wall-clock, RNG, locale, network, env, or any
   ambient state. Same input ⇒ byte-identical output. Parse/format dates in UTC unless an
   explicit `format` says otherwise.
3. **JSON Schema is the single source of truth** for the grammar. The files under
   `crosswalk/grammar/vN/` define primitives; code and docs mirror them, never the reverse.
4. **Closed schemas only.** Every param schema uses `additionalProperties: false`. Never add
   a primitive or param that accepts a formula, template, or eval-able string.
5. **Two version axes, both pinned in every mapping.** Bump `grammar_version` when adding a
   primitive; bump `semantics_version` for *any* behavior change to coercion / normalize /
   arithmetic / parsing — **including bug fixes**. A pinned mapping's output must never change
   silently. The cache key includes both axes.
6. **Fail closed.** Fields the grammar can't express are surfaced as `unmapped`; low-confidence
   fields go to `needs_review`. Never silently drop, guess, or free-form-code a field.

## Environment & commands

Use `uv` for everything. Do not invoke bare `python`/`pip`/`pytest`.

```bash
uv sync                      # create/refresh the venv from the lockfile
uv run crosswalk <cmd>       # run the CLI (profile | propose | validate | review | approve | execute | primitives)
uv run pytest                # run tests
uv run pytest -k <expr>      # run a subset
uv run ruff check .          # lint
uv run ruff format .         # format
uv run mypy .                # type-check (strict)
uv add <pkg>                 # add a dependency (updates pyproject + lockfile)
```

Run `ruff check`, `ruff format`, `mypy`, and `pytest` before every commit.

## Project layout

```
crosswalk/
  profile.py       # Schema Profiler — infer shape (ID-safe), value facets        [PURE]
  fingerprint.py   # fingerprint + schema-drift differ                            [PURE]
  propose.py       # Mapping Proposer — orchestrates a backend                    [IMPURE: LLM]
  validate.py      # structural + safety validation + per-field confidence        [PURE]
  review.py        # ReviewPackage / ApprovalRecord assembly                      [PURE]
  execute.py       # deterministic interpreter over primitives                    [PURE]
  cache.py         # CacheStore + value-coverage guard                            [PURE + I/O to store]
  backends/        # BackendAdapter impls (anthropic, openai, outlines, xgrammar) [IMPURE: LLM]
  grammar/vN/      # JSON Schema contracts — SOURCE OF TRUTH
  cli.py           # `crosswalk` entrypoint
tests/             # unit, property, contract tests
datasets/          # golden fixtures (synthetic/public only)
docs/              # design.md (source of truth)
```

Respect the pure/impure boundary above. If a "pure" module needs I/O or a model, the design
is wrong — stop and reconsider rather than reaching across the boundary.

## Python style

- Python 3.11+ idioms. `from __future__ import annotations` at the top of every module.
- **Full type hints on all public functions and class attributes.**
- Model the documented contracts (`MappingDocument`, `SourceProfile`, `ReviewPackage`,
  `ApprovalRecord`, `DriftReport`, rule envelopes) as **`pydantic` models** (or `dataclasses`
  where no validation is needed) — not loose `dict`s. JSON in/out goes through these models.
- `pathlib.Path` over `os.path`. f-strings over `%`/`.format`. No mutable default args.
- Raise specific exceptions; never bare `except:`. Failure policy is explicit and declared
  (see the `on_error` / `unmatched` / `on_missing` params), not swallowed.
- Small, single-purpose pure functions. Keep the executor's per-primitive logic isolated and
  individually testable.
- Match the surrounding code's conventions once the codebase exists.

## Typing (strict)

- `uv run mypy .` must pass with `--strict`; it is enforced in CI.
- 100% typed public API. Avoid `Any`; use `TypedDict`/`pydantic`/`Literal` for JSON payloads
  and enums.
- No `# type: ignore` without a trailing reason comment.
- Use `typing.Protocol` for the pluggable seams — `BackendAdapter`, `CacheStore` — so
  implementations stay swappable and testable with fakes.

## Testing

- pytest, tests mirror the module layout under `tests/`.
- **Every primitive** gets a truth table exercising each failure-policy branch
  (`on_error`/`unmatched`/`on_missing` = null | fail | default | passthrough).
- The coercion table (design §5.2) is tested exhaustively, incl. ID-safe inference footguns
  (leading zeros, zip/phone, epoch ints).
- **Property tests** for: determinism (`execute(m, X) == execute(m, X)`),
  composition-confidence monotonicity (a rule is never more confident than its weakest input),
  and value-coverage-guard rejection (an uncovered enum is rejected, not silently nulled).
- **Golden regression** under `datasets/<case>/`: `source.{csv,json}`, `target_schema.json`,
  `mapping.json`, `expected.jsonl`, plus a `drift/` variant. Harness runs validate + execute
  and diffs against `expected.jsonl`.
- **All fixtures are synthetic or from public open data — never production or customer data.**
- **Contract tests**: every `BackendAdapter` must produce a document that passes the Validator
  on the fixture suite.

## Dependencies

- Keep the core dependency set minimal.
- Model backends are **optional extras**: `schema-crosswalk[anthropic]`, `[openai]`,
  `[outlines]`, `[xgrammar]`. The core library must import and run (profile/validate/execute)
  without any backend installed.
- Regex uses a non-backtracking engine (`google-re2`) with a length-/step-capped pure-Python
  fallback — never an unbounded backtracking pattern on untrusted input.
- Add deps with `uv add`; don't hand-edit the lockfile.

## Commits & PRs

- Imperative, scoped subject lines (e.g. `execute: handle null in coalesce`).
- `ruff check`, `ruff format`, `mypy`, `pytest` all green before committing.
- **A grammar change is not complete without**, in the same PR: updated JSON Schema under
  `crosswalk/grammar/vN/`, a golden fixture exercising it, the matching `docs/design.md`
  update, and the appropriate `grammar_version` / `semantics_version` bump.
