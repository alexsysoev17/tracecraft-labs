# ATLAS — Hybrid Retrieval Lab

Run `make atlas` or `PYTHONPATH=src .venv/bin/python -m tracecraft experiment atlas --mode local` after `make models`. Open the ATLAS page to compare the same query across BM25, cosine and RRF; click a source to inspect provenance. Try `LF-MOSS-42`, a logo-spacing paraphrase, an absent question and the unresolved packaging-ribbon conflict.

Reports: `reports/public/atlas-fixture.json`, `atlas-local.json`. Tests: `tests/test_atlas.py`, shared CANON evaluator and scope/security tests. The local run uses real E5 embeddings. Fixture dense/hybrid are explicitly unavailable. RRF ranks positions; BM25 sorts ascending. Mandatory explicit constraints and linked exceptions are added outside top-k examples.

Final original-suite answer checks: 32/32 for lexical/dense/hybrid. The separate withheld follow-up remains 7/12 under all four methods, with five missing-attribute answers falsely labeled supported; see [limitations](../../LIMITATIONS.md) and [quality phases](../../reports/public/independent-quality.json). `make eval-independent` reproduces the independent sets after model preparation. High retrieval recall does not establish answer correctness. Output is extracted source text, not generative reasoning. Scope is filtered before ranking and negative examples are never promoted to authoritative claims.
