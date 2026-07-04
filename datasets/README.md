# Golden datasets

Regression + seed-eval fixtures for the mapping engine (design.md 13). Every case is a
directory:

```
datasets/
  <case-name>/
    source.csv | source.json     # input records
    target_schema.json           # JSON Schema of the desired output
    mapping.json                 # the MappingDocument to execute
    expected.jsonl               # one expected output record per line
    drift/                       # optional: a drifted source + expected re-approval delta
      source.csv
      expected_drift.json
```

The harness runs `validate` + `execute` on each case and diffs the output against
`expected.jsonl`.

**All fixtures must be synthetic or from public open data — never production or customer
data.**
