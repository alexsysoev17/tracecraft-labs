# RELAY — Agent Execution Lab

RELAY turns a narrow banner brief into a checked designer handoff. It does not render banner pixels, send messages or publish anything. Fixture/local execution is a deterministic workflow. The opt-in live adapter accepts actual model-proposed typed tools; the handoff tool itself remains a bounded, checked procedure.

```bash
make relay
# Equivalent after setup:
PYTHONPATH=src .venv/bin/python -m tracecraft experiment relay --mode fixture
```

Open the RELAY page after `make demo`. Supply an incomplete brief, fill the missing dimensions/copy, inspect the three artifacts, then approve the displayed input and artifact hashes. A changed brief invalidates the previous approval. The demo scope is assigned on the server; it is not production authentication.

## Checked behavior

`Relay.create` persists `queued` and then runs the bounded workflow. Missing fields pause at `awaiting_input`; a checked package pauses at `awaiting_approval`. Restart the server and resume the same run ID. The current state, artifacts, source hashes and approval survive process restart.

The package includes `requirements.json`, `questions.md` and `handoff.md`, with exact supplied copy, format and evidence references. Artifact contents, the input-specific idempotency ledger and checkpoint are committed in one SQLite transaction. Repeated resume creates no second effect. Filesystem export is a repeatable projection; it is not an exactly-once external effect guarantee.

Tool proposals pass JSON parsing, schema validation, value checks, scope checks, execution and artifact postconditions. The allowlist contains `search_rules`, `read_evidence`, `validate_requirements`, `request_clarification`, `draft_handoff` and `request_review`. No model tool can approve its own package.

The experiment reopens the SQLite store, resumes an incomplete brief, changes the copy, rejects the stale approval, approves the current package and checks repeat execution. The automated approval is labelled as a test action, not a real human review.

Results: `reports/public/relay.json` after the runner writes the report. Individual states/traces live in ignored `runtime/`. Run `.venv/bin/python -m pytest tests/test_relay.py` for negative and lifecycle checks.

## Limits

The fixture experiment establishes covered workflow mechanics on synthetic material, not LLM reliability. Live provider decisions have an adapter contract test with a fake provider; no paid model run is inferred from it. A full pixel design, visual quality assessment, real identity provider and external actions are outside this module. Conflicting rules stop for source review rather than being resolved by modification time. A crashed active computation may be reclaimed after its short lease or dead owner process is detected.
