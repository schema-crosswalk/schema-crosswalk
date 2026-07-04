# schema-crosswalk

Grammar-constrained schema mapping engine. Point it at an arbitrary CSV/JSON source and a
fixed target schema: an **LLM proposes** a mapping constrained to a small, versioned grammar
of primitives, and a **deterministic engine executes** it. The LLM never writes or runs
code — it only selects and parameterizes primitives, so every mapping is auditable,
reproducible, and testable before it touches production data.

> **Status:** pre-alpha scaffolding. The public API and grammar are in place; execution logic
> is being implemented. See [`docs/design.md`](docs/design.md) for the full design.

## Why

- **Low-hallucination** — the model picks from a fixed grammar, never emits arbitrary code.
- **Deterministic** — same input + same mapping ⇒ byte-identical output, always.
- **Embeddable** — a library, not a platform. Drop it into Airflow, dbt, an agent, or a script.
- **Auditable** — every mapping is inspectable, versioned, and gated by confidence before use.

## Install

```bash
uv sync                      # dev setup from the lockfile
# or, as a dependency:
uv add schema-crosswalk
```

Model backends are optional extras — the core installs and runs without any of them:

```bash
uv add "schema-crosswalk[anthropic]"   # or [openai], [outlines], [xgrammar]
```

## Quickstart (target API)

```python
from schema_crosswalk import Crosswalk

cw = Crosswalk()                                  # configure a backend + cache
profile = cw.profile("customers.csv")             # infer source shape
mapping = cw.propose(profile, target_schema=SCHEMA)
report  = cw.validate(mapping, target_schema=SCHEMA)
records = cw.execute(mapping, "customers.csv")     # deterministic, no LLM
```

CLI:

```bash
uv run crosswalk primitives          # list the grammar primitives
uv run crosswalk profile customers.csv > profile.json
```

## Development

Tooling is standardized on `uv`, `ruff`, `mypy --strict`, and `pytest`. See
[`CLAUDE.md`](CLAUDE.md) for project invariants and conventions.

```bash
uv run ruff check .
uv run ruff format .
uv run mypy .
uv run pytest
```

## License

Apache-2.0. See [`LICENSE`](LICENSE).
