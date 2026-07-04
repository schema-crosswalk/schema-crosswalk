# PRD: Open-Source Grammar-Constrained Schema Mapping Engine

**Status:** Draft v0.1 — for iteration
**Owner:** [you]
**Last updated:** 2026-07-03

---

## 1. Problem Statement

Teams ingesting data from heterogeneous, uncontrolled sources (SFTP drops, S3 buckets, Snowflake shares) in loose formats (CSV, JSON) need to transform that data into a specific, fixed target schema before it's usable downstream (analytics platform, warehouse table, application). Today this is solved by:

- **Hand-written transform scripts** — brittle, slow to build per-source, breaks silently on schema drift.
- **Generic LLM code-generation** — an LLM writes arbitrary Python/SQL to do the transform. Flexible, but unpredictable: hallucinated logic, non-reproducible output, hard to audit, unsafe to run unsandboxed.
- **Heavyweight commercial mapping tools** (Informatica, Talend, Altova MapForce) or **platform-locked AI mapping** (Airbyte, Fivetran, SnapLogic) — capable, but require adopting a full platform, and are optimized for API-source ingestion, not arbitrary file-based mapping into a specific, opinionated internal schema.

There is no lightweight, open-source, embeddable library that lets an engineer say: *"map this arbitrary CSV/JSON into this target schema, using an LLM to propose the mapping, but constrain what the LLM can propose to a small, auditable set of primitives, and execute deterministically."*

## 2. Goals

- Provide a **reliable, low-hallucination** way to generate schema mappings from arbitrary source data to a fixed target schema.
- Separate **LLM responsibility (propose a mapping)** from **execution responsibility (run it deterministically)** — the LLM never writes or runs arbitrary code.
- Be **embeddable**, not a platform: usable inside existing pipelines (Airflow, dbt, Airbyte, custom scripts) or standalone.
- Be **auditable**: every generated mapping is inspectable, versionable, and testable before it touches production data.
- Be **model-agnostic and cheap**: because the task is constrained, it should run well on small/local models, not require frontier-model calls per file.

## 3. Non-Goals (v1)

- Not a full ELT platform. No connector catalog, scheduling, orchestration, or UI — this is a library/engine, not Airbyte/Fivetran.
- Not a general-purpose code-generation agent. The LLM never emits arbitrary code; it only selects/parameterizes from a defined primitive grammar.
- Not initially handling streaming/CDC — v1 is batch, file-based (CSV/JSON in, structured record out).
- Not competing with dbt for warehouse-native SQL modeling — this sits upstream of that.

## 4. Target Users

| Persona | Need |
|---|---|
| Data/platform engineer at a SaaS company | Onboarding new enterprise customers whose data always arrives in a different shape, needs mapping into one internal schema |
| Engineer building an agent/data pipeline | Wants a trustworthy "raw data → structured schema" building block to plug into LangGraph/CrewAI/MCP pipelines |
| Data engineering team doing migrations | One-off or recurring mapping of legacy exports into a new system's schema |

## 5. Core Concepts

### 5.1 Primitive Grammar
A small, fixed, versioned set of transformation operations the LLM is allowed to propose. Starting set (extend from your production experience — placeholder, refine with real primitives):

1. `rename_field`
2. `cast_type`
3. `map_enum_value`
4. `concat_fields`
5. `split_field`
6. `default_value`
7. `nested_flatten` / `nested_extract`

Each primitive has a strict parameter schema (JSON Schema). The LLM's output is validated against this schema before anything runs — this is where existing constrained-decoding tooling (Outlines/XGrammar/native structured outputs) is used, not reinvented.

### 5.2 Mapping Proposal
Given `(source_sample, target_schema)`, the LLM proposes a list of `{primitive, params, source_field(s), target_field, confidence}` objects.

### 5.3 Deterministic Execution Engine
A server-side interpreter (no LLM involved) that executes the validated primitive list against the full dataset. Same input + same mapping = same output, always. This is the reliability guarantee.

### 5.4 Confidence & Fallback
- Each proposed mapping carries a confidence score.
- Below a configurable threshold → flagged for human review, not silently applied.
- Fields the grammar genuinely can't express → explicitly surfaced as "unmapped," never guessed via free-form code.

### 5.5 Schema Fingerprint Cache
Hash the source schema shape; if seen before, reuse the prior mapping instead of re-invoking the LLM. Reduces cost and increases determinism over time.

## 6. Scope for v1 (MVP)

| Feature | In v1? |
|---|---|
| Fixed primitive grammar (~7 ops) + JSON Schema validation | ✅ |
| LLM mapping proposal (pluggable model backend) | ✅ |
| Deterministic execution engine | ✅ |
| Confidence scoring + human-review flag | ✅ |
| CSV + JSON source support | ✅ |
| Schema fingerprint caching | ✅ |
| MCP server exposing `propose_mapping`, `validate_mapping`, `execute_mapping` | ✅ |
| Golden-dataset regression testing harness | ✅ (lightweight) |
| Mapping-pack registry (community-contributed source→target templates) | ❌ post-v1 |
| PII detection/redaction | ❌ post-v1 |
| XML/Parquet/Avro support | ❌ post-v1 |
| Streaming/CDC support | ❌ post-v1 |
| Public benchmark (SchemaMapBench-style) | ❌ parallel/separate effort |

## 7. Architecture (high level)

```
                 ┌─────────────────────┐
 source file  →  │  Schema Profiler     │  (infers source shape, checks fingerprint cache)
 (CSV/JSON)      └─────────┬────────────┘
                            │ cache miss
                            ▼
                 ┌─────────────────────┐
                 │  Mapping Proposer    │  (LLM, constrained to primitive grammar via
                 │                      │   Outlines/XGrammar/native structured output)
                 └─────────┬────────────┘
                            │ proposed mapping (JSON)
                            ▼
                 ┌─────────────────────┐
                 │  Validator           │  (schema + confidence check)
                 └─────────┬────────────┘
                low conf   │  high conf
          ┌─────────────┐  │
          │ Human Review │  │
          └──────┬───────┘  │
                 ▼          ▼
                 ┌─────────────────────┐
                 │  Deterministic       │  (no LLM — pure interpreter over primitives)
                 │  Execution Engine    │
                 └─────────┬────────────┘
                            ▼
                    structured output
                    (matches target schema)
```

Exposed as:
- A Python library (core).
- An MCP server wrapping the same core (`propose_mapping`, `validate_mapping`, `execute_mapping`, `list_primitives`).
- CLI for local/batch use.

## 8. Success Metrics

- **Reliability:** % of mappings executed without runtime error on held-out real-world source samples.
- **Accuracy:** % of proposed field mappings matching human-verified ground truth (needs a small internal eval set — candidate seed for the future benchmark).
- **Cost:** LLM cost per *new* schema shape (should trend toward near-zero for repeat shapes via caching).
- **Adoption (OSS):** installs/downloads, MCP server usage, contributed primitives or mapping packs, issues/PRs from non-maintainers.
- **Trust signal:** % of mappings requiring human review vs. auto-applied (track over time — should decrease as primitive coverage matures, not because thresholds are loosened).

## 9. Differentiation / Positioning

| vs. | Why this isn't redundant |
|---|---|
| Outlines/Guidance/XGrammar | Those are constraint *mechanisms*; this is a domain-specific primitive vocabulary + execution/validation harness built on top of them, not a competing constraint engine. |
| dbt | dbt transforms already-structured warehouse tables via SQL; this operates upstream, turning arbitrary files into structured records in the first place. |
| Airbyte/Fivetran/SnapLogic | Those are full ELT platforms optimized for API-source extraction and increasingly bundle their own AI mapping — but require platform adoption. This is a small, embeddable, platform-agnostic primitive usable *inside* those pipelines or independently. |
| Generic LLM-codegen agents | Those let the LLM write/run arbitrary code (larger attack surface, non-reproducible). This restricts the LLM to selecting from a fixed, auditable grammar with deterministic server-side execution. |

## 10. Risks

- **Grammar coverage ceiling** — real-world mappings may need primitives beyond the initial ~7. Mitigation: versioned grammar extension process (see design doc), "compose primitives" escape hatch before adding new ones.
- **Competitive encroachment** — Airbyte/SnapLogic/Informatica are actively marketing "AI does mapping for you." Mitigation: stay narrow, embeddable, and platform-agnostic rather than competing on breadth.
- **IP/confidentiality** — anything open-sourced must be independently designed/generalized, not a direct extraction of proprietary code, logic, or customer-specific primitives. **Action: confirm with legal/eng leadership before publishing anything derived from a prior internal system.**
- **Adoption ceiling** — this is a narrower audience than a general agent framework; expect fewer stars, but potentially higher-intent contributors.

## 11. Open Questions

1. What are the *actual* 7 primitives from the production system, generalized enough to publish without exposing proprietary logic?
2. What's the confidence-scoring mechanism — model self-reported confidence, ensemble agreement, or a learned classifier?
3. Target language/runtime: Python-first? TypeScript port later for broader MCP ecosystem reach?
4. License: MIT/Apache-2.0 (recommend Apache-2.0 for patent grant clarity, consistent with most of this ecosystem).
5. Where does the initial golden dataset for eval come from, given production data can't be published?

## 12. Milestones (proposed)

| Phase | Deliverable |
|---|---|
| 0 | Design doc: finalized primitive grammar + JSON Schema contracts |
| 1 | Core library: proposer + validator + deterministic executor, CSV/JSON, single-model backend |
| 2 | MCP server wrapper + CLI |
| 3 | Schema fingerprint caching + confidence-based human review flow |
| 4 | Golden-dataset regression harness + initial public eval set |
| 5 (stretch) | Mapping-pack registry seed (2–3 common source formats) |

---
*This PRD is a starting point for iteration — sections 6, 9, and 12 are the ones most likely to change as real usage/feedback comes in.*