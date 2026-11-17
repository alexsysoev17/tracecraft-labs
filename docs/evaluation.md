# Evaluation protocol

Dataset: 32 machine-authored, source-checked public questions, two synthetic brands, Russian/English, 16 disjoint scenario families across development/validation/test. This is an exploratory public test, not an independent hidden holdout. Gold contains source spans, expected status, acceptable claims, prohibitions and severity. It never enters the retrieval index.

The shared CANON evaluator checks schema, exact snapshot/scope, required references, quote existence, full extractive assertion support, prohibited claims and abstention/conflict status separately. An existing citation alone is not support. General free-form prose requires separate review; no uncalibrated LLM judge is presented as gold. Human rework and visual suitability are NOT_RUN.

Each runner retains actual outputs, IDs, source/model/evaluator/configuration hashes, code fingerprint, repetition index, elapsed time and usage. Counts distinguish passed, failed and skipped. Retrieval recall/MRR use annotated evidence; answer checks operate on output. The small-sample interval is exploratory and repeats do not become independent cases. Model prices and missing usage are null.

SENTINEL checks manifests before comparison: dataset/split/corpus, mode, evaluator, budgets, prompt/tool/model settings and code source fingerprint. Only the declared factor may change. Its intentionally broken adapter actually removes citations and changes a claim; the scorer does not read a preassigned failed flag. The normal comparison changes retrieval method. Gates are PASS, REGRESSION, INCONCLUSIVE, NOT_COMPARABLE or NOT_RUN. Existing critical failures block the candidate, even without new regressions. Nothing automatically becomes production/stable.

ECHO calibrates a threshold on `cache-validation.json`, then measures the same nine-request stream under off/exact/semantic with isolated namespaces. It counts real downstream extraction and embedding calls; no artificial sleep is used. This stream is an authored demonstration, with a simple safe paraphrase shared in spirit with calibration, not evidence of generalization to a hidden cache test set. Off is an actual computation control, and the report does not promise latency improvement.

Run `make demo` for fixtures, `make eval-local` after explicit `make models`, or one `PYTHONPATH=src .venv/bin/python -m tracecraft experiment <module> --mode local`. No live benchmark was run. `make eval-live` is a separately authorized bounded smoke, not a substitute for the comparison suite.

## Independent review and preserved phases

Final original CANON results are 32/32 for all four methods. That visible suite is regression coverage, not an unseen quality estimate. Separate agents performed source-first question authoring and implementation/security review; they are same-session agents, not external human reviewers.

[Quality evidence](../reports/public/independent-quality.json) preserves the initial frozen 26-case set, all intermediate failures and final outputs. Of 23 high-certainty scored questions, 20 initially and 23 finally pass; three remain unscored. Fixes saw these questions, so the final result is a disclosed regression result. A second 12-case challenge was withheld from the implementer until final code freeze and was not tuned after disclosure. Baseline and final both pass 7/12 for every retrieval method. The five failures have valid citations but fail to establish requested attributes absent from the guides. The challenge author knew earlier behavior, so this is not independent of all development history.

Run `make eval-independent` (no model download required) to reproduce both sets into `runtime/independent-reproduction.json` and `runtime/independent-challenge-reproduction.json`. These files do not overwrite preserved review phases. Successful command completion does not mean quality PASS: the five remaining failures are an expected limitation showcase.

[Implementation review](independent-review.md) and [security evidence](../reports/public/independent-security.json) record three and six original defects respectively, now repaired and rechecked within stated scopes. The evaluator changed after false-positive findings; before/after benchmark numbers therefore do not isolate a single answer-system intervention. Final delivery test counts are in [verification](../reports/public/verification.json).
