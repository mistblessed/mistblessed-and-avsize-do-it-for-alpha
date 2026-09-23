# Independent holdout review

The existing generated corpora and regression tests are development data. Do not
reuse their texts as an independent holdout. Keep the reviewed corpus outside this
repository, and do not show it to the model or person implementing detection.

## Collection

1. A separate reviewer writes at least 10 unseen, synthetic, positive documents
   for each of the 17 `Kind` values in `src/alfa_pii/domain.py` (at least 170
   positive documents in total). Add at least 20 hard negative documents.
2. Mix sentence structures, casing, spacing, punctuation, Unicode, and multiple
   entities. Vary context as well as values; replacing digits in one template
   does not create independent examples.
3. Annotate every PII span before viewing detector output. A second reviewer
   checks the complete text and every start/end offset. Never use real customer
   records or data copied from a real person.
4. Store one UTF-8 JSON object per line. Offsets are Python Unicode code-point
   indexes, zero-based and end-exclusive:

```json
{"id":"example-001","category":"EMAIL","text":"Email: qa@example.org","entities":[{"kind":"EMAIL","start":7,"end":21}]}
{"id":"example-002","category":"NEGATIVE","text":"The order number is 1234.","entities":[]}
```

`category` is a reviewer label; `entities` holds all expected spans, including
multiple kinds in one document. Use `NEGATIVE` only when `entities` is empty.

## Checks

Run these from the project root, with the private input and reports outside the
project directory:

```cmd
.venv\Scripts\python.exe tools\validate_holdout.py --corpus "D:\private\reviewed-holdout.jsonl"
.venv\Scripts\python.exe tools\quality.py --corpus "D:\private\reviewed-holdout.jsonl" --output "D:\private\holdout-quality.json" --require-95
```

The validator checks schema, exact duplicate texts and IDs, offset ranges,
overlaps, 10 positive documents per kind, and 20 negative documents. It prints
counts only. It cannot determine whether a label is semantically correct or
prove that the corpus was independently reviewed.

Record who reviewed the corpus and when, the exact code revision, the commands,
and aggregate results. Disclose only aggregate metrics initially. If a failing
example is shared with the implementation team, move that example into regression
tests and replace it in the private holdout before another independent run.
