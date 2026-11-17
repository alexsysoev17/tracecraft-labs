# Independent implementation review

This is an assessment by a separate delegated agent that did not implement source changes. It is independent of the implementation role, but remains part of the same agent session. It is not an external human audit, a certification, or an endorsement by another organization. No paid model calls or publication were performed.

The evidence and preserved initial/final phases are in [independent-review.json](../reports/public/independent-review.json). Findings are based on source inspection, new adversarial probes, an isolated fresh-process fixture demo, and rerun project checks—not the test count alone.

## Initial verdict

There is substantial engineering here. The six laboratories have genuinely different responsibilities and working implementations: scoped retrieval; durable tool execution and approval; paired regression gating; trace diagnosis; guarded answer reuse; and source-based evaluation. The small shared stack fits a reproducible local research application. This is stronger than six themed wrappers around one chatbot.

The initial implementation is not yet a strong evaluation portfolio. Three new evaluator probes incorrectly passed: a palette answer containing only “The”; a conflict answer with no supported claims; and an invented fireproof certification labeled as abstention. These defects undermine what the CANON pass count and SENTINEL gate mean. A second probe showed persisted passage vectors being reused after the encoder configuration changed. Those are implementation issues, not matters that better wording alone resolves.

## Findings that require resolution

1. **IR-001: evaluation false positives.** `allowed_claims` was unused; supported extraction could be an arbitrary fragment, conflict claims were optional, and abstention content escaped attribution checks. Require the expected answer content and a verifiable refusal/conflict contract. Preserve the negative examples as evaluator tests and rerun reports.
2. **IR-002: stale computed state after encoder changes.** Vector keys, ECHO namespaces, and calibration identity used model revision without encoder configuration. A controlled same-model/new-configuration probe reused old passage vectors. Include the configuration fingerprint in every relevant key and verify unchanged configuration still survives restart.
3. **IR-003: unsupported installed distribution.** `pyproject.toml` exposed a console script but omitted dependencies and non-Python resources. Relocating the package to a site-packages layout made even `--help` fail on `configs/embedding.json`. A real wheel build could not run because sandbox DNS prevented fetching its build backend. Either support a tested wheel or remove the misleading entrypoint and clearly state checkout-only distribution. A reliable checkout is sufficient for these local labs.

## What is already credible

Negative tests exercise stale approvals, corrupted artifacts, access revocation, malformed tools, concurrent resumes, private export rejection and genuinely modified bad answers. The reports distinguish fixtures from real embeddings, keep missing costs null, preserve observed failures and disclose synthetic data. Gold is not indexed. RELAY's transactional local effect ledger and content-bound review are concrete engineering choices. ECHO checks scope and source dependencies at reuse, rather than treating cosine similarity as permission. LENS does not promote observed failures directly into gold.

The independent initial rerun passed `make test`, `make check`, and `make privacy-check`; 111 tests passed with one upstream warning. A copied source tree in a new process, using a fresh database, completed all six fixture demonstrations. That copied-tree test reused the installed dependency environment and is not a new clean-install claim. See the structured report for exact qualifications.

## Limits that remain meaningful

The data and evaluation questions are public, synthetic, machine-authored and already inspected. Repairing known failures improves correctness but does not create an untouched holdout. The initial 29/32 result does not establish real-customer, live-model or human-design quality. LENS mainly classifies known errors and controlled injected faults; RELAY remains an explicit workflow. These are valid demonstrations with bounded claims.

CI is configured for Linux but has not been observed running remotely. Version-pinned lockfiles improve repeatability, but package integrity hashes and immutable action revisions are absent. Compact statements, broadly untyped dictionary contracts, shared checkout paths and large service modules increase maintenance effort; passing mypy does not imply strict type coverage. This review did not independently rerun the browser or real encoder during its initial phase.

## Three material improvements

- Fix evaluation completeness before treating a higher pass rate as stronger evidence. The new adversarial probes must fail, valid examples must still pass, and report fingerprints must identify the updated evaluator.
- Include encoder configuration in persisted-vector, semantic-cache and calibration identity; test both configuration changes and unchanged restart reuse.
- Deliver one honest, tested installation route and evidence tied to the final source. Keep dependency locks and CI synchronized, retain baseline failures, and distinguish repair/regression cases from independently collected future evaluation data.

## Final reassessment

The three original findings are resolved within the directly rechecked scope. All three evaluator exploits now fail, while constructed source-faithful supported, conflict and refusal controls pass. The evaluator records version `canon-evidence-checks/2`. This verifies the extractive contract; it does not establish general semantic evaluation.

A separate controlled-vector probe confirms that changing only the encoder configuration recomputes passage vectors and changes ECHO cache and calibration identity. Reopening storage with an unchanged configuration reuses passage vectors with the expected scores. This checks state invalidation using controlled vectors, not new real-model quality.

The misleading project/console-script packaging metadata is removed. `pyproject.toml` now describes a checkout application using the Makefile and `PYTHONPATH=src`. That is a sufficient supported distribution scope for these local labs. Final README wording still needs to reflect that decision; no successful wheel installation is claimed.

The focused CANON/ECHO/adversarial/configuration suite passed all 35 tests in 3.42 seconds. The structured report records the rechecked file hashes and direct-probe outcomes. No implementation fingerprint changed during the direct probes. This phase does **not** certify the final whole-project delivery: Atlas quality work, final documentation, fresh-copy validation and regenerated public report fingerprints are the integrator’s remaining work. The initial findings and original test evidence above remain preserved.
