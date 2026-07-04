# Design Doc: schema-crosswalk

**Status:** Draft v0.2 — Phase 0 deliverable
**Owner:** [you]
**Last updated:** 2026-07-03
**Companion to:** [`prd.md`](../prd.md)

This document turns the PRD into an implementable design. It finalizes the
primitive grammar and its JSON Schema contracts, defines the mapping proposal
format, specifies deterministic execution semantics, and fixes the public API
surface (library, MCP server, CLI). It resolves the PRD's Section 11 open
questions where a decision is required to build Phase 1.

### Changelog

**v0.2** — folded in the v0.1 design review. Material changes:

1. **Added a transform primitive class** (`normalize_string`, `arithmetic`) —
   v0.1 had no value-transform op, so the first real file would produce mostly
   unmapped fields (§4).
2. **Per-field confidence gating** replaces document-level `min()`; intended
   nulls no longer penalized; composition no longer launders confidence (§7.3).
3. **Cache reuse is gated by a value-coverage guard**, closing the silent
   enum/format corruption path a shape-only fingerprint allowed (§8.3).
4. **`propose()` now consumes sample values** and requires target field
   descriptions/examples; proposing from shape alone was the accuracy ceiling (§9).
5. **Review artifact and schema-drift flow are now specified** — the review
   experience is the product, and drift is the PRD's headline problem (§10).
6. **Conservative, ID-safe type inference; RE2 instead of a ReDoS linter;
   executor `semantics_version` separate from `grammar_version`** (§5, §7.2, §11).

---

## 1. Scope of this document

In scope (Phase 0 → unblocks Phases 1–4):

- The versioned **primitive grammar** and per-primitive **JSON Schema** param contracts.
- The **mapping document** format (`propose` output / `execute` input).
- **Deterministic execution semantics**: evaluation order, type system, coercion, error handling.
- **Confidence** model and human-review gating.
- **Schema fingerprint** + value-coverage guard and cache contract.
- The **backend abstraction** for constrained decoding (Outlines / XGrammar / native structured output).
- The **review artifact** and **schema-drift** flow.
- **Public interfaces**: Python core, MCP tools, CLI.

Out of scope (deferred, per PRD Section 3 / 6): connector catalog, scheduling,
UI, streaming/CDC, XML/Parquet/Avro, PII redaction (a sampling/redaction *knob*
is in scope; full detection is not), mapping-pack registry.

Explicit non-goals for v1 (were ambiguous in v0.1):

- **No multi-row reshaping.** One source record → one output record. No
  row filtering, pivot/unpivot, explode, dedupe, or aggregation. These are a
  large, legitimate class of "mapping" that v1 deliberately excludes; called out
  so the coverage boundary is honest.
- **Nested targets are limited** to the dotted-path assembly convention in §5.3,
  not arbitrary nested schemas.

---

## 2. Resolved decisions (answers to PRD §11 open questions)

| # | Question | Decision for v1 | Rationale |
|---|---|---|---|
| 1 | The *actual* primitives | Ship the **11 primitives** in §4 (PRD's 7, with `nested_extract`/`nested_flatten` split, plus `coalesce`, `normalize_string`, `arithmetic`). All generic, independently specified — no proprietary logic. | Covers observed real-world need (esp. string/number normalization) without exposing internal IP; grammar is versioned so it can grow. |
| 2 | Confidence mechanism | **Per-field**: model self-report de-rated by executor-verifiable signals on the sample, gated per target field (§7.3). Learned classifier deferred. | Cheapest to ship; document-level gating flags everything; self-report alone is uncalibrated so we bound it with checks the executor can verify. |
| 3 | Language/runtime | **Python 3.11+** first. TS port post-v1; kept viable by keeping all contracts as language-neutral JSON Schema. | Matches ecosystem (Outlines/XGrammar/pandas) and PRD lean. |
| 4 | License | **Apache-2.0** (already in repo `LICENSE`). | Patent-grant clarity; ecosystem norm. |
| 5 | Golden dataset source | **Synthetic + public open-data seed**, never production data. `datasets/` fixtures of hand-authored source→target pairs; contributors add more. | PRD §10 confidentiality risk; keeps eval publishable. |

Additional decisions:

- **Package name:** `schema_crosswalk` (PyPI: `schema-crosswalk`). CLI: `crosswalk`.
- **Two version axes, both pinned in every mapping doc:**
  - `grammar_version` (integer, starts at `1`) — the set of primitives + their param schemas.
  - `semantics_version` (integer, starts at `1`) — coercion tables, normalize/arithmetic behavior, parse rules (§11). A bug fix to coercion bumps *this*, so a pinned mapping's output never silently changes.
- **No LLM in the execution path, ever.** The proposer is the only component that calls a model. Profiler, validator, executor, cache, and drift-differ are pure and deterministic.
- **Determinism ≠ accuracy.** The deterministic executor guarantees a mapping is *reproducible and auditable*, not *correct*. Accuracy rests on the proposer + confidence model (§7, §9), which is where the real risk lives.

---

## 3. System overview

```
                  ┌──────────────────┐
 source file  →   │ Schema Profiler  │  infer shape (ID-safe) → fingerprint → cache lookup
 (CSV/JSON)       └───────┬──────────┘
                          │ hit → value-coverage guard ─ pass → reuse
                          │                            └ fail → treat as miss / re-review
                          │ near-miss (same target, similar source) → DriftReport
                          │ miss
                          ▼
                  ┌──────────────────┐
                  │ Mapping Proposer │  LLM, constrained via BackendAdapter; sees sample VALUES
                  └───────┬──────────┘
                          │ MappingDocument (JSON)
                          ▼
                  ┌──────────────────┐
                  │ Validator        │  JSON Schema + semantic checks + per-field de-rating
                  └───────┬──────────┘
                          │  partition by per-field confidence
             ┌────────────┼───────────────┐
             ▼            ▼                ▼
        auto_apply    needs_review     unmapped
             │            │
             │            ▼
             │       ┌──────────────┐  ReviewPackage → human decision → ApprovalRecord
             │       │ Review flow  │  (edits, per-field approve/reject)
             │       └──────┬───────┘
             ▼              ▼
                  ┌──────────────────┐
                  │ Execution Engine │  pure interpreter over primitives; no LLM
                  └───────┬──────────┘
                          ▼
                  records matching target schema  +  ExecutionReport
```

| Component | Module | Purity |
|---|---|---|
| Schema Profiler | `crosswalk.profile` | pure |
| Fingerprint + drift differ | `crosswalk.fingerprint` | pure |
| Mapping Proposer | `crosswalk.propose` | **impure (LLM)** |
| Validator + confidence | `crosswalk.validate` | pure |
| Review packaging | `crosswalk.review` | pure |
| Execution Engine | `crosswalk.execute` | pure |
| Cache + value-coverage guard | `crosswalk.cache` | pure (I/O to store) |
| Backend adapters | `crosswalk.backends.*` | impure (LLM) |

---

## 4. The primitive grammar (v1, `grammar_version: 1`)

A primitive is a named transform with a strict parameter schema. Each primitive
declares its **source arity** and produces **exactly one target field**.
Multi-output needs (name → first/last) are expressed as multiple rules or via
composition (§6.3), keeping every rule a single auditable `sources → target` unit.

### 4.1 Primitive catalog

| Primitive | Source arity | Purpose |
|---|---|---|
| `rename_field` | 1 | Copy a source field to a target field unchanged. |
| `cast_type` | 1 | Coerce a value to a target scalar type (§5.2). |
| `normalize_string` | 1 | Apply an ordered list of **enumerated** string ops (trim, case, collapse, strip). |
| `arithmetic` | 1 | Apply an ordered list of **enumerated** numeric ops (+ − × ÷, round) with constant operands. |
| `map_enum_value` | 1 | Map source categoricals to target enum values via lookup table. |
| `concat_fields` | N (≥2) | Join source fields into one string with a separator. |
| `split_field` | 1 | Extract one component of a string split by delimiter/regex. |
| `coalesce` | N (≥2) | First non-null of an ordered list of sources, with optional default. |
| `default_value` | 0 or 1 | Emit a constant, or fill when the (optional) source is null/missing. |
| `nested_extract` | 1 | Pull a value from a nested path (`a.b[0].c`) in a structured source. |
| `nested_flatten` | 1 | Serialize a nested object/array to a JSON string for a flat target. |

`normalize_string` and `arithmetic` are the v0.2 additions. They close the
biggest v0.1 gap: value normalization (whitespace/case) and unit conversion
(cents→dollars, kg→lbs, epoch→seconds) are table stakes for file ingestion and
were previously inexpressible. Both use **closed enumerations of operations with
constant operands — never formula/template/eval strings** (§4.3). Anything
beyond this list goes through the extension process in §11.

### 4.2 JSON Schema contracts

The registry (`crosswalk/grammar/v1/*.json`) is the single source of truth; the
tables below are its human-readable form.

**Rule envelope** (one entry in `MappingDocument.rules`):

```json
{
  "$id": "crosswalk:v1:rule",
  "type": "object",
  "required": ["target_field", "primitive", "sources", "params", "confidence"],
  "additionalProperties": false,
  "properties": {
    "target_field": { "type": "string", "minLength": 1 },
    "primitive": {
      "enum": ["rename_field","cast_type","normalize_string","arithmetic","map_enum_value",
               "concat_fields","split_field","coalesce","default_value",
               "nested_extract","nested_flatten"]
    },
    "sources": { "type": "array", "items": { "type": "string" },
      "description": "Source field refs (dotted paths). May reference an earlier rule's target_field (composition)." },
    "params": { "type": "object" },
    "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
    "rationale": { "type": "string", "description": "Optional model explanation; ignored by executor." }
  },
  "allOf": [ { "$ref": "crosswalk:v1:params-dispatch" } ]
}
```

`params-dispatch` is an `if/then` chain keying on `primitive`, selecting the
param sub-schema and enforcing source arity. New/changed sub-schemas:

```jsonc
// normalize_string — sources: exactly 1
{
  "type": "object", "required": ["ops"], "additionalProperties": false,
  "properties": {
    "ops": {
      "type": "array", "minItems": 1,
      "items": { "enum": ["trim","ltrim","rtrim","lower","upper","title",
                          "collapse_whitespace","strip_punctuation","digits_only"] }
    }
  }
}

// arithmetic — sources: exactly 1 (numeric after coercion)
{
  "type": "object", "required": ["ops"], "additionalProperties": false,
  "properties": {
    "ops": {
      "type": "array", "minItems": 1,
      "items": {
        "type": "object", "required": ["op","operand"], "additionalProperties": false,
        "properties": {
          "op": { "enum": ["add","subtract","multiply","divide"] },
          "operand": { "type": "number" }
        }
      }
    },
    "round": { "type": "integer", "description": "Decimal places for final result; omit for no rounding." },
    "on_error": { "enum": ["null","fail","default"], "default": "null" },
    "default": {}
  }
}

// cast_type — sources: exactly 1  (adds `unit` for integer→datetime)
{
  "type": "object", "required": ["to"], "additionalProperties": false,
  "properties": {
    "to": { "enum": ["string","integer","number","boolean","date","datetime"] },
    "format": { "type": "string", "description": "strptime/strftime pattern for date|datetime" },
    "unit": { "enum": ["seconds","millis"], "description": "For integer→datetime epoch conversion." },
    "on_error": { "enum": ["null","fail","default"], "default": "null" },
    "default": {}
  }
}
```

Unchanged from v0.1 (see §4.2 history): `rename_field`, `map_enum_value`,
`concat_fields`, `split_field`, `coalesce`, `default_value`, `nested_extract`,
`nested_flatten`. `split_field` uses a **non-backtracking regex engine** (§7.2)
rather than the v0.1 linter.

### 4.3 Design rules for the grammar

- **Closed schemas** (`additionalProperties: false`) everywhere — the model
  cannot smuggle free-form fields past validation.
- **No expression strings.** No primitive accepts a formula, template, or code.
  `normalize_string`/`arithmetic` are enumerated op lists with constant operands.
  `split_field.pattern` is a regex run by a non-backtracking engine, not eval'd.
- **Explicit failure policy** on every lossy op (`on_error`, `unmatched`,
  `on_missing`) — behavior on bad data is declared, not implicit.

---

## 5. Data model and type system

### 5.1 Target schema

Supplied by the caller as JSON Schema (draft 2020-12 subset). v1 supports an
object of scalar-typed fields plus `required` and `enum`. **Field `description`
is required and `examples` strongly encouraged** — the proposer maps largely by
name + description + example, so terse, undocumented schemas map poorly (§9).
Nested targets use the dotted-path convention (§5.3).

### 5.2 Scalar type system

Canonical types: `string`, `integer`, `number`, `boolean`, `date`, `datetime`,
`null` → Python `str`, `int`, `float`, `bool`, `date`, `datetime`, `None`.

**Coercion table for `cast_type`** (deterministic; the only implicit-conversion
site). Governed by `semantics_version` so fixes never silently change pinned
mappings.

| to \ from | string | integer | number | boolean | date/datetime |
|---|---|---|---|---|---|
| string | ident | `str(n)` | repr-stable | `"true"/"false"` | ISO-8601 (or `format`) |
| integer | strict parse¹ | ident | trunc iff integral, else `on_error` | 1/0 | `on_error` |
| number | strict parse | widen | ident | 1.0/0.0 | `on_error` |
| boolean | truthy set² | !=0 | !=0 | ident | `on_error` |
| date/datetime | parse (`format`/ISO) | epoch via `unit` | `on_error` | `on_error` | date↔datetime |

¹ Rejects `"12abc"`; whitespace trimmed first. ² Fixed, case-insensitive:
`{true,t,yes,y,1}`→true; `{false,f,no,n,0}`→false; else `on_error`. On failure
the declared `on_error` policy applies; `fail` aborts the record (§8/§6.2).

### 5.3 ID-safe type inference

The profiler's inference is **conservative to prevent data loss** — the classic
CSV footgun of coercing `"00123"`, zip codes, and phone numbers to int. Rules:

- A column stays `string` (never inferred as `integer`/`number`) if **any**
  sampled value has a leading zero, is longer than 15 digits, contains a
  separator (`-`, `(`, space) in a digit context, or the column name matches an
  ID/code/zip/phone heuristic.
- Inference only widens to a numeric/temporal type when **every** non-null
  sampled value parses cleanly under that type.
- Ambiguity is recorded on the field (`inferred_type` + `type_confidence` +
  `alternatives`) and surfaced to the proposer, which may still emit an explicit
  `cast_type` — but the *default* is lossless string.

### 5.4 Nested output assembly

Target fields may use dotted paths and `[i]` indices (`address.geo[0].lat`).
When `assemble_nested=True`, the executor folds the flat output record into the
nested structure after all rules run. Arbitrary nested *schemas* (oneOf, nested
arrays of objects with per-element rules) remain post-v1.

---

## 6. Mapping document & execution semantics

### 6.1 MappingDocument

```json
{
  "grammar_version": 1,
  "semantics_version": 1,
  "target_schema_id": "customer.v3",
  "source_fingerprint": "sha256:…",
  "rules": [ /* rule envelopes (§4.2) */ ],
  "unmapped_target_fields": ["…"],
  "field_status": { "<target_field>": "auto_apply | needs_review | unmapped" },
  "metadata": {
    "proposer": { "backend": "anthropic", "model": "claude-…", "created_at": "…" },
    "confidence_by_field": { "<target_field>": 0.0 }
  }
}
```

`unmapped_target_fields` and `field_status` are **first-class, required**.
Fields the grammar cannot express are listed explicitly — never silently dropped
or guessed with free-form code (PRD §5.4).

### 6.2 Evaluation model

The executor processes one source record at a time, maintaining an **output
record** (initially empty) reading from an **immutable source record**. Rules
run in listed order; each rule:

1. Resolves each `sources[i]`: source record first, then the already-produced
   output record (composition, §6.3).
2. Applies the primitive to the resolved input(s) with `params`.
3. Writes the result to `output[target_field]`.

Determinism: **same source record + same MappingDocument (+ pinned
`semantics_version`) ⇒ byte-identical output.** Every op is a pure function of
its resolved inputs and static params. No wall-clock/RNG/locale/ambient state;
dates parse/format in UTC unless `format` says otherwise.

### 6.3 Composition (the escape hatch)

A rule may reference a **prior** rule's `target_field` as a source. Rules named
with a leading `__` are **intermediate**: dropped before the output is validated
against the target schema. The validator enforces backward-only references, so
the rule list is a topologically-ordered DAG by construction. Now that
`normalize_string`/`arithmetic` exist, composition is genuinely useful, e.g.
concat first+last → normalize to title case:

```json
[
  {"target_field":"__name","primitive":"concat_fields","sources":["fname","lname"],"params":{"separator":" "},"confidence":0.9},
  {"target_field":"full_name","primitive":"normalize_string","sources":["__name"],"params":{"ops":["collapse_whitespace","title"]},"confidence":0.9}
]
```

Confidence propagates through composition (§7.3), so a weak intermediate can no
longer be laundered by a confident final rename.

---

## 7. Validation & confidence

### 7.1 Structural validation (hard gate)

1. `grammar_version` and `semantics_version` are implemented by this executor.
2. Every rule validates against the envelope + param sub-schema.
3. Source arity matches the primitive.
4. Composition refs are backward-only and resolvable.
5. Every non-`__` `target_field` exists in the target schema; every `required`
   target field is produced or listed in `unmapped_target_fields`.

Any failure ⇒ document **rejected** (not runnable).

### 7.2 Safety validation

- `split_field.pattern` runs under a **non-backtracking regex engine** (RE2 via
  `google-re2`; pure-Python fallback caps input length and runs under a step
  budget). This replaces the v0.1 nested-quantifier linter, which both missed
  real ReDoS and false-positived benign patterns.
- `map_enum_value`/`enum` tables capped (default 10k entries).
- `normalize_string`/`arithmetic` op-list length capped (default 16).

### 7.3 Confidence model (per-field)

Per-rule confidence starts as the model's self-report, then is **de-rated** by
deterministic signals computed on the source sample:

```
adjusted(rule) = self_reported
               × source_factor        (see below — resolves through composition)
               × applicability_factor (see below — does NOT punish intended nulls)
               × arity_penalty        (mild penalty for concat/coalesce over many fields)
```

- **`source_factor`** — for each source: if it is a real source field present on
  the sample → 1.0; absent → 0.3. If a source is a `__tmp` field, use *that
  rule's* `adjusted` value as the factor (confidence propagates through
  composition; §6.3). A rule's adjusted value is thus never higher than its
  weakest input's.
- **`applicability_factor`** — fraction of sample rows where the op is *both
  applicable and succeeds*. Critically, rows where the input is null/absent **and
  the target field is nullable** are excluded from the denominator — a
  legitimately sparse, nullable column is no longer penalized as "failing." Only
  present-but-uncoercible values (e.g. `"N/A"` → integer) count against it.

**Gating is per target field, not per document:**

- `field_status[f] = auto_apply` if `adjusted ≥ review_threshold` (default **0.7**).
- `field_status[f] = needs_review` if below threshold, **or** the field is
  `required` and `unmapped`.
- `field_status[f] = unmapped` if no rule produces it.

High-confidence fields auto-apply while only weak fields go to review — so a
40-field schema with three uncertain columns doesn't route the *entire* mapping
to a human (the v0.1 `min()` failure that made auto-apply near-impossible).
`confidence_by_field` is reported for observability; there is no single
document-level gate.

Rationale: uncalibrated self-report is turned into a partially-grounded signal
the executor can cheaply verify on the sample, without a trained classifier
(deferred per §2).

---

## 8. Schema profiler, fingerprint, cache & drift

### 8.1 Profiling

Per field infer: name/path, ID-safe inferred type (§5.3) with `type_confidence`,
nullability, and — for JSON — nested structure. For value-dependent columns also
capture **value facets**: for low-cardinality columns, the distinct value set
(capped, e.g. ≤200); for date-like columns, detected format(s) and parse rate.
Sample default 1,000 rows, streamed. A `sample_values` slice (redactable, §9) is
retained for the proposer.

### 8.2 Fingerprint

```
fingerprint = "sha256:" + hex(sha256(canonical_json(sorted([
    {"path": f.path, "type": f.inferred_type, "nullable": f.nullable} for f in fields
]))))
```

Shape-only: sorted paths + types + nullability. Insensitive to row order/count;
contains no cell values — safe to log/store. **But shape-only is deliberately
*not* sufficient for reuse** — see the value-coverage guard, which is the fix for
the v0.1 silent-corruption hole.

### 8.3 Cache contract + value-coverage guard

Key: `(fingerprint, target_schema_id, grammar_version, semantics_version)`.
Value: a validated `MappingDocument` + its `ApprovalRecord` (§10).

- **Hit** ⇒ run the **value-coverage guard** on the *new* file's sample before
  reuse. The guard re-checks the assumptions a shape-only fingerprint can't see:
  - every `map_enum_value` rule covers all distinct sample values, or its
    `unmatched` policy is non-lossy (`passthrough`), else that field → `needs_review`;
  - every `cast_type`/`split_field` with a `format`/`pattern` still parses the
    sample above a threshold, else → `needs_review`.
  If all guards pass → reuse (the cost win). If any fails → that field is
  re-reviewed (or re-proposed), the rest still reused. This closes the path where
  two files with identical columns but a new enum vocabulary silently null the
  new values.
- Backend is a `CacheStore` interface (`get/put`); ships with a local
  filesystem/JSON store. SQLite/remote are pluggable.
- Only **approved** documents are cached; review-pending decisions are never
  silently reused.
- **Caching helps only recurring drops from the *same* source.** Because the
  premise is heterogeneous sources, cold hit-rate is low by construction; the win
  is amortization over repeat drops of a known shape, not "near-zero for
  everything." (Corrects the v0.1 framing.)

### 8.4 Schema-drift flow

Drift is the PRD's headline problem ("breaks silently on schema drift"), so it is
a first-class flow rather than an undifferentiated cache miss. On a fingerprint
miss, the differ looks for a **neighbor**: a prior *approved* mapping for the same
`target_schema_id` whose source has high field-path overlap (Jaccard ≥ 0.6). If
found, it emits a **DriftReport** instead of a cold re-propose:

```json
{
  "against": "sha256:… (last approved)",
  "added_fields": ["…"], "removed_fields": ["…"],
  "renamed_candidates": [{"from":"…","to":"…","similarity":0.9}],
  "retyped_fields": [{"path":"…","was":"integer","now":"string"}],
  "proposed_delta": { /* only the rules that must change */ }
}
```

The human re-approves a *delta* (what changed vs. last time), not a mapping from
scratch — surfacing drift explicitly instead of silently re-mapping under a new
fingerprint.

---

## 9. Proposer inputs & backend abstraction

### 9.1 Proposer inputs (accuracy-critical)

`propose()` receives, in addition to the source shape:

- **Redacted sample values** per source column (default: a few rows). Recognizing
  that `"M"/"F"` is an enum, or a column is a date, requires seeing values, not
  just types — shape-only proposals were the v0.1 accuracy ceiling.
- **Target field descriptions + examples** (§5.1), required/encouraged.

Sample values may contain sensitive data. A `value_exposure` knob controls what
leaves the process: `full | hashed | redacted | none`. `none` degrades accuracy
and is warned about. Full PII detection/redaction remains post-v1 (PRD §6); this
is only the exposure control.

### 9.2 BackendAdapter

We do not reinvent constrained decoding (PRD §9):

```python
class BackendAdapter(Protocol):
    def propose(self, *, source_profile: SourceProfile, sample_values: SampleView,
                target_schema: dict, prompt_ctx: PromptContext) -> MappingDocument: ...
```

The adapter constrains generation to the grammar's JSON Schema. Ship:
`AnthropicAdapter`/`OpenAIAdapter` (native structured output / tool-use),
`OutlinesAdapter`/`XGrammarAdapter` (local/OSS models, for the "small/local
models" goal, PRD §2). **Every adapter's output must still pass the Validator** —
the proposer is never trusted, regardless of backend or constraint mechanism.

---

## 10. Review artifact & approval

The review experience is the product (auditability + human-in-the-loop), so it is
specified, not hand-waved as "routed to review."

### 10.1 ReviewPackage

Produced whenever any `field_status == needs_review`:

```json
{
  "mapping_ref": "…",
  "items": [{
    "target_field": "…",
    "target_description": "…",
    "proposed_rule": { /* rule envelope */ },
    "adjusted_confidence": 0.55,
    "derating_reasons": ["applicability_factor=0.6: 'N/A' not coercible to integer"],
    "source_samples": [{ "source_field": "…", "values": ["…"] }],
    "alternatives": [ /* other plausible rules, if the proposer offered them */ ]
  }],
  "unmapped_required": ["…"]
}
```

Each item carries the evidence a reviewer needs: the proposed op, *why* it was
flagged (de-rating reasons), and the source values in question.

### 10.2 ApprovalRecord

A human decision is captured and stored with the mapping in the cache:

```json
{
  "mapping_ref": "…",
  "decided_by": "…", "decided_at": "…",
  "field_decisions": { "<target_field>": { "action": "approve|edit|reject", "edited_rule": {} } },
  "resulting_status": "approved"
}
```

v1 ships the review *artifacts and the API to apply a decision* (library/CLI/MCP),
not a GUI. Edited rules re-enter the Validator before approval — a human edit
can't bypass structural or safety checks. Only `approved` documents are cached
and reusable.

---

## 11. Version & grammar evolution

Two axes, both append-only and pinned per mapping:

- **`grammar_version`** — adding a primitive. Process: try composition first
  (§6.3) and document why it's insufficient → propose the primitive with JSON
  Schema + failure semantics + golden fixtures in a design PR → bump.
- **`semantics_version`** — any change to coercion (§5.2), normalize/arithmetic
  behavior, or parse rules, *including bug fixes*. Old mappings keep running under
  their pinned semantics; the executor refuses to reinterpret an older document
  under newer semantics, and the cache key includes both axes (§8.3).

This keeps determinism stable across upgrades: a mapping's output is a function
of `(source, rules, grammar_version, semantics_version)` and nothing else.

---

## 12. Public interfaces

### 12.1 Python core

```python
from schema_crosswalk import Crosswalk

cw = Crosswalk(backend=AnthropicAdapter(model="claude-…"),
               cache=FileCacheStore("./.crosswalk-cache"),
               review_threshold=0.7, value_exposure="redacted")

profile = cw.profile("customers.csv")                  # SourceProfile (+ fingerprint, value facets)
result  = cw.propose(profile, target_schema=SCHEMA)    # MappingDocument | DriftReport (cache/drift-aware)
report  = cw.validate(result, target_schema=SCHEMA)    # ValidationReport (+ field_status)
pkg     = cw.review_package(result)                    # ReviewPackage | None
result  = cw.apply_decision(result, ApprovalRecord(...))
records = cw.execute(result, "customers.csv")          # Iterator[dict] + ExecutionReport
```

`execute` runs only `auto_apply`/`approved` fields by default; `needs_review`
fields are omitted (or nulled) unless `allow_unreviewed=True`. It refuses an
unvalidated document.

### 12.2 MCP server

Thin wrappers over the core, JSON in/out:

| Tool | Input | Output |
|---|---|---|
| `list_primitives` | `{grammar_version?}` | catalog + param schemas |
| `propose_mapping` | `{source_profile, sample_values, target_schema}` | `MappingDocument` \| `DriftReport` |
| `validate_mapping` | `{mapping, target_schema}` | `ValidationReport` |
| `review_package` | `{mapping}` | `ReviewPackage` |
| `apply_decision` | `{mapping, approval_record}` | updated `MappingDocument` |
| `execute_mapping` | `{mapping, records}` **or** `{mapping, source_ref}` | `{records \| output_ref, ExecutionReport}` |

`execute_mapping` accepts inline records for **bounded** agent payloads, or a
`source_ref` (path/URI) for real files, streaming to `output_ref` via the library
path. This removes the v0.1 limitation where MCP couldn't execute over an actual
file — the agent-pipeline persona (PRD §4) needs the file path.

### 12.3 CLI

```
crosswalk profile   customers.csv                                   > profile.json
crosswalk propose   --profile profile.json --schema customer.v3.json > mapping.json   # may emit drift.json
crosswalk validate  --mapping mapping.json --schema customer.v3.json
crosswalk review    --mapping mapping.json                          > review.json
crosswalk approve   --mapping mapping.json --decision decision.json  > approved.json
crosswalk execute   --mapping approved.json customers.csv --out out.jsonl
crosswalk primitives --grammar-version 1
```

Non-zero exit on validation failure or when any field is `needs_review` (fails
closed in CI/pipelines) unless `--allow-unreviewed`.

---

## 13. Testing & golden-dataset harness

- **Unit**: each primitive against a truth table incl. every failure-policy
  branch; coercion table exhaustively; ID-safe inference against known footguns
  (leading zeros, zips, phones, epoch ints).
- **Property**: `execute(m, X) == execute(m, X)` (determinism); composition
  confidence never exceeds weakest input; value-coverage guard rejects an
  uncovered enum.
- **Golden regression** (PRD §6): `datasets/<case>/` holds
  `source.{csv,json}`, `target_schema.json`, `mapping.json`, `expected.jsonl`,
  plus a `drift/` variant for the drift flow. Doubles as the seed eval set (§2
  decision 5). All fixtures synthetic/public — no production data.
- **Contract**: every backend adapter must produce a document that passes the
  Validator on the fixture suite.

Metrics wired to PRD §8: execution-error rate; field-mapping accuracy vs. golden
truth; cache hit-rate + guard-rejection rate + cost-per-new-shape;
review-vs-auto ratio over time; drift-diff acceptance rate.

---

## 14. Risks & mitigations (design-level)

| Risk | Mitigation in this design |
|---|---|
| Grammar too narrow | Transform primitives (§4) + composition escape hatch (§6.3) + versioned extension (§11). Multi-row reshape explicitly out of scope (§1) so the boundary is honest. |
| Model bypasses grammar | Closed schemas, no expression strings, Validator gate independent of backend (§9.2), RE2 non-backtracking regex (§7.2). |
| Silent bad data | Per-op failure policies; ID-safe inference (§5.3); value-coverage guard on cache reuse (§8.3); unmapped fields surfaced, not guessed. |
| Confidence theater | Per-field self-report de-rated by executor-verifiable signals that don't punish intended nulls (§7.3); fail-closed CLI. |
| Poor mapping accuracy | Proposer sees sample values + requires target descriptions (§9.1). |
| Cache silently reuses wrong mapping | Value-coverage guard + both version axes in the cache key (§8.3). |
| Schema drift missed | First-class DriftReport delta re-approval (§8.4). |
| Fingerprint leaks data | Shape-only, no cell values (§8.2); `value_exposure` knob governs sample values to the proposer (§9.1). |
| Confidentiality (PRD §10) | Grammar/semantics here are independently specified & generic; **still gate publication on legal/eng sign-off before release.** |

---

## 15. Milestone mapping

| PRD Phase | This doc unblocks |
|---|---|
| 0 | §4 grammar + §4.2 JSON Schema contracts (this document). |
| 1 | §6 executor, §7 validator, §8.1 profiler (ID-safe), §5 type system, §9 one backend. |
| 2 | §12.2 MCP (+ `source_ref`) + §12.3 CLI. |
| 3 | §8.2–8.4 fingerprint + value-coverage guard + drift + §7.3 confidence/review + §10 review artifacts. |
| 4 | §13 golden harness + seed eval set. |
| 5 (stretch) | Mapping-pack registry (out of scope here). |

---
*Draft for iteration. §4 (grammar) and §7.3 (confidence) remain the sections most
likely to change once real source samples are run through the proposer.*
