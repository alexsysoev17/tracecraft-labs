# LENS — Failure Forensics

LENS reads stored execution spans and ties each diagnostic statement to the observations that support it. A hypothesis is not promoted to a cause merely because it is plausible. Recorded replay displays events and performs zero tool or model calls.

```bash
make lens
# Equivalent after setup:
PYTHONPATH=src .venv/bin/python -m tracecraft experiment lens --mode fixture
```

Open the LENS page after `make demo`. Choose an existing run or inject an isolated public-demo fault. Inspect the chronological spans, classification, evidence IDs and bounded correction. Create an evaluation-case draft: expected behavior and gold remain unset until a separate review.

## Scenario and measurements

The default experiment submits a genuinely malformed typed tool proposal to RELAY. Code rejects it before execution. LENS repeats the guarded operation in another run and labels the observed failure reproduced only when its signature and supporting spans are present. A corrected proposal is then executed and checked. This is a tool-proposal failure caught by the guard, not a claim that the entire system crashed.

Additional isolated faults are expired persisted deadline, omitted evidence, wrong snapshot and repeated event. Repeated event is a useful negative control: duplicate prevention can leave no incident, and LENS does not invent a failure. Source absence by itself is a hypothesis: it can mean absent data, denied data or a retrieval miss.

External trace import accepts `tracecraft.trace/1` with typed `tracecraft.span/1` spans. It rejects duplicate IDs, mixed runs, missing parents, cycles, excess size and unknown schema versions. Imported IDs are remapped, known secret fields are redacted, and origin is forced to `external` even if the payload says synthetic. External traces cannot be exported by the public HTML exporter. This redaction is defense in depth, not proof that arbitrary text is free of private information.

Results: `reports/public/lens.json` after the runner writes the report. `Lens.report_html(run_id)` emits escaped HTML for synthetic runs. `Lens.replay` is a recorded observation, never a new live benchmark. Run `.venv/bin/python -m pytest tests/test_lens.py` for scope, schema, fault, review and replay checks.

## Limits

The taxonomy is a deterministic evidence classifier, not a calibrated LLM judge. Unknown or missing evidence remains uncertain. Reproducing one injected failure does not establish general diagnostic accuracy. A case draft is not executable regression gold; even a reviewed expected-behavior statement requires a suitable evaluator. No hidden internal model reasoning is captured or interpreted.
