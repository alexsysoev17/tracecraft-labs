# SENTINEL — Regression Lab

SENTINEL executes baseline and candidate adapters, preserves both outputs and evaluates them with CANON's shared evidence checks. The intentionally broken adapter changes an actual assertion to an unsupported color and removes its citation. The gate detects the resulting output; a configuration never writes its own score.

Run independently after setup:

```sh
make sentinel
PYTHONPATH=src .venv/bin/python -m tracecraft experiment sentinel --mode fixture
PYTHONPATH=src .venv/bin/python examples/sentinel/run.py
.venv/bin/python -m pytest tests/test_sentinel.py -q
```

The API entry point is `POST /api/sentinel` with `{"candidate":"broken","mode":"fixture"}`. Use `candidate:"normal"` to compare lexical retrieval with the compact full rule pack. `POST /api/experiments/sentinel` performs both and exercises a deliberately mismatched manifest.

Every comparison records dataset/split hashes, the actual corpus fingerprint, evaluator/rubric, generation settings, budgets, repeats, embedding identity, code revision and dirty-tree state. One factor is declared: `adapter` for the broken candidate or `method` for the normal comparison. Any other condition difference produces `NOT_COMPARABLE`.

The initial integration experiment detected the broken candidate as `REGRESSION`. The normal comparison also returned `REGRESSION`: both normal configurations retained critical failures already visible in CANON. After source selection and evaluator repairs, the final original-suite normal comparison passes 32/32 for both configurations and receives `PASS`. The broken candidate scores 5/32 against 32/32, with 27 regressions. The deliberately changed corpus fingerprint remains `NOT_COMPARABLE`. The separate withheld challenge still has five failures out of twelve and is not covered by this original-suite gate; see [quality phases](../../reports/public/independent-quality.json).

The gate has five decisions. `PASS` means all covered candidate checks passed without observed regression; it does not establish statistical improvement. `REGRESSION` also covers critical candidate violations, even if they existed in the baseline. Existing noncritical failures or incomplete checks yield `INCONCLUSIVE`; entirely unexecuted candidates yield `NOT_RUN`. Missing/skipped checks never count as success. No result automatically promotes a configuration to production.

Reports expose per-case comparisons, failed checks, categories, repeats, counts, uncertainty and all attempt latencies/usage. All data are synthetic, all fixture outputs are deterministic extraction, and no live-model reliability or ROI is claimed.
