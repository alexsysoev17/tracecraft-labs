PYTHON ?= python3
PY := .venv/bin/python
RUN := PYTHONPATH=src $(PY) -m tracecraft

.PHONY: setup demo serve test check models eval-local eval-independent eval-live privacy-check atlas relay sentinel lens echo canon
setup:
	$(PYTHON) -c "import sys; assert sys.version_info >= (3,12), 'Python 3.12+ required: make setup PYTHON=/path/to/python3.12'"
	$(PYTHON) -m venv .venv
	$(PY) -m pip install -r requirements-fixture.lock

demo:
	$(RUN) demo

serve:
	$(RUN) serve

test:
	PYTHONPATH=src $(PY) -m pytest -q

check:
	$(PY) -m ruff check src tests scripts
	$(PY) -m mypy src/tracecraft
	$(PY) -m compileall -q src

models:
	$(PY) -m pip install -r requirements-local.lock
	$(RUN) models

eval-local:
	$(PY) scripts/local_smoke.py
	$(RUN) experiment all --mode local

# This reproduces both successful repairs and five known answerability failures.
# A completed command is not an all-green quality gate; inspect its counts.
eval-independent:
	PYTHONPATH=src $(PY) tests/test_independent_quality.py --report runtime/independent-reproduction.json --label reproduction
	PYTHONPATH=src $(PY) tests/test_independent_quality.py --report runtime/independent-challenge-reproduction.json --label challenge-reproduction --cases reports/public/independent-quality-challenge2-cases.json --expected-cases-sha256 d6397950e6b378cf201c8b6a3ebc3c50ddc10029e00e29a4f7d4272e67fe2563

eval-live:
	$(RUN) live $(LIVE_ARGS)

privacy-check:
	$(RUN) privacy-check

atlas relay sentinel lens echo canon:
	$(RUN) experiment $@
