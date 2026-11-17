# Public fictional brand benchmark

Luma Field and Veyra Works are independently authored fictional brands. Their names, colors, layout constraints and sample campaigns were invented for this repository. These files contain no transformed client brand book. The `partner` ACL record and its token are also synthetic test data, not a real secret.

`corpus.json` contains 28 evidence records backed by four original Markdown documents. Each record has the document's SHA-256 and exact character span. Snapshot `v1` contains archived palette rules; `v2` contains current rules, an unresolved pair of reviewed packaging instructions, observed positive/negative examples, an unreviewed suggestion and a denied-access record. Rule/exception links retain joint meaning.

`cases.json` contains 32 questions in Russian and English. It is separate from the corpus and is never indexed or passed into ATLAS. Gold records have expected status, evidence IDs, exact source spans, permitted source assertions, forbidden assertions, severity and review state. Labels are **machine authored and source checked**, not expert validated.

| Split | Cases | Purpose |
|---|---:|---|
| development | 8 | Palette, typography and CTA mechanics |
| validation | 8 | Clearspace, transforms, minimum width and photography |
| test | 16 | Exceptions, warranty, version, conflict, unknown, denied source and examples versus norms |

Scenario families are disjoint between splits. Related phrasings within one family stay together. All splits are public, exploratory data. Repeated inspection during development makes them unsuitable for claims about an unseen holdout. No claim is made about STC, actual client data or the outside-world truth of these invented rules.

Regenerate from the hand-authored declarations:

```sh
python3 datasets/public-demo/build_dataset.py
PYTHONPATH=src .venv/bin/python -c 'from tracecraft.canon.service import validate_dataset; print(validate_dataset())'
```

Validation checks corpus hashes/offsets, gold spans, links, duplicate IDs and family leakage. The API never lets a browser set the `partner` permission. Raw public corpus JSON remains readable in the repository because the denied-access scenario is a simulation, not an access-control boundary for real private data.
