# CANON — Brand Knowledge Benchmark

CANON defines what correct work with a brand guide means. ATLAS supplies answers; one shared evaluator checks them; SENTINEL reuses that evaluator for comparisons. The benchmark does not assign itself scores and does not send gold into retrieval.

Run an independent experiment after setup:

```sh
make canon
PYTHONPATH=src .venv/bin/python -m tracecraft experiment canon --mode fixture
PYTHONPATH=src .venv/bin/python examples/canon/run.py
PYTHONPATH=src .venv/bin/python examples/canon/run.py --mode local
.venv/bin/python -m pytest tests/test_canon.py -q
```

The local command needs the explicitly prepared embedding model. Without it, dense/hybrid return `NOT_RUN` and skipped cases; they never silently become lexical search. The first command executes actual SQLite retrieval and deterministic extraction on synthetic data. It does not call a generative model.

The API entry point is `POST /api/canon` with `{"mode":"fixture","method":"lexical"}`. The dashboard's CANON page shows slices, outputs, retrieval recall, answer checks, uncertainty, latency and usage. `POST /api/experiments/canon` compares lexical, compact full rule pack, dense and hybrid. The no-context generative baseline is explicitly `NOT_RUN` unless separately authorized.

Initial measured integration run: lexical and full rule pack each passed 29 of 32 cases, with three real failures retained. Prepared E5 dense and hybrid also passed 29 of 32. Dense retrieval recall@k was 1.0 on the 29 questions with evidence labels, while answer evaluation still failed three cases. This is direct evidence that retrieval success is not answer success. The current reproducible report is authoritative if implementation or data changes.

Those historical failures were repaired. Final original-suite results are 32/32 for all four configurations. The first independently authored set moves from 20/23 to 23/23 after disclosure, with three uncertain cases unscored. A second 12-case challenge withheld until final code freeze remains 7/12 for every method: five absent requested attributes incorrectly receive supported answers. See [preserved phases](../../reports/public/independent-quality.json) and run `make eval-independent` (no model download required); command completion does not imply every quality case passed.

Historical failure details: Russian warranty inflection was missed by the extractive selector; the denied partner question drew unrelated packaging rules; an example question's generic word “approved” drew the same unresolved packaging conflict. No private token was returned. The failures concern answer selection and abstention. Gold was not changed to match those outputs.

Checks distinguish schema, exact scope/version, citation existence, quote location, assertion support, required evidence/exception coverage and abstention. An existing citation cannot validate a fabricated claim. Free-form model prose requires semantic review and is not awarded a pass by string or embedding similarity. The suite includes negative checks for leaked synthetic ACL data and extra uncited assertions.

These are small public authored cases, not an independent production reliability estimate. Gold has no expert review. Wilson intervals group by original case; repeats are not new independent tasks. Unknown monetary cost remains `null`, and human rework is `NOT_RUN`.
