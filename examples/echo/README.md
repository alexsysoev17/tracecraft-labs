# ECHO — Semantic Cache Lab

Run `make echo`; for actual semantic similarity run `PYTHONPATH=src .venv/bin/python -m tracecraft experiment echo --mode local` after explicit `make models`. The ECHO page offers off/exact/semantic and a measured policy comparison.

The nine-request stream includes first request, exact repeat, safe paraphrase, other brand/version, changed number, negation, clarification and revoked access. Real local embedding similarity proposes a candidate; independent guards check applicability and evidence hashes. Threshold is calibrated on a separate tiny authored validation file. Every hit revalidates source accessibility and exact claims. Actions/new variants are not cached.

Reports: `reports/public/echo-fixture.json`, `echo-local.json`. Local demo observes two hits (exact + verified paraphrase); required unsafe cases miss. Fixture semantic has only exact hits, explicitly labeled. Reports count actual downstream extraction calls and embedding calls, and time the whole operation. They do not measure LLM savings or promise speedup.

Tests: `tests/test_echo.py`, `tests/test_adversarial_review.py`. Includes punctuation-sensitive exact keys, complete cached-answer support, scope/ACL/context boundaries, invalidation, single-flight concurrency and no error/partial admission. Single-flight is within the declared single server process. Tiny English-oriented guard coverage is not a universal semantic equivalence proof.
