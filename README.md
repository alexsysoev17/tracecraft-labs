# TRACECRAFT LABS

Six local laboratories for inspecting retrieval, execution, regressions, failures, answer reuse and brand-rule evaluation. Each has a working page, an independent CLI experiment, tests and recorded outputs. The shared task is preparing a sourced designer handoff from a brand corpus.

This is an exploratory research implementation. It is not a production service, a self-improving model, or a claim of measured business value.

**Read the independent findings alongside the demos:** [implementation review](docs/independent-review.md), [security regressions and rechecks](reports/public/independent-security.json), and [source-first quality challenges](reports/public/independent-quality.json). Separate delegated agents found nine engineering defects that were repaired and rechecked within the recorded scopes. Quality remains limited: a follow-up challenge withheld until the final code freeze still passes only **7 of 12 cases** under all four retrieval configurations.

| Laboratory | Working scenario | Reproduce | Report |
|---|---|---|---|
| ATLAS | BM25 / real CPU dense / RRF retrieval, scoped evidence and extractive answers | `make atlas` | [fixture](reports/public/atlas-fixture.json), [local](reports/public/atlas-local.json) |
| RELAY | Incomplete brief → clarification → durable designer package → bound review | `make relay` | [fixture](reports/public/relay-fixture.json), [local](reports/public/relay-local.json) |
| SENTINEL | Execute two configurations and reject actual defective outputs | `make sentinel` | [fixture](reports/public/sentinel-fixture.json), [local](reports/public/sentinel-local.json) |
| LENS | Trace-addressable fault → reproduction → draft regression case | `make lens` | [fixture](reports/public/lens-fixture.json), [local](reports/public/lens-local.json) |
| ECHO | Off / exact / semantic answer cache with scope and provenance checks | `make echo` | [fixture](reports/public/echo-fixture.json), [local](reports/public/echo-local.json) |
| CANON | 32 bilingual cases over two original fictional brand corpora | `make canon` | [fixture](reports/public/canon-fixture.json), [local](reports/public/canon-local.json) |

## Start locally

Python 3.12+ with SQLite FTS5 is required. No Node build or API key is needed. The supported distribution is a **source checkout**, with resources kept in their repository layout and commands run from the project root. Use the Makefile or `PYTHONPATH=src .venv/bin/python -m tracecraft`; no pip-installable wheel or installed console script is supported or claimed.

```sh
make setup PYTHON=python3.12
make demo
make serve
```

Open **http://127.0.0.1:8317**. Subsequent starts need only `make serve`. The server binds loopback and uses one process/database owner. Stop it with Ctrl-C. To run independent CLI experiments while serving, use a separate database:

```sh
PYTHONPATH=src .venv/bin/python -m tracecraft --db runtime/experiments.sqlite experiment all
```

```sh
make test
make check
make privacy-check
```

## Prepare genuine local embeddings

```sh
make models
make eval-local
```

This is an explicit download of the MIT-licensed `intfloat/multilingual-e5-small` ONNX model (approximately 470 MB), pinned to revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`. CPU execution was exercised on Apple Silicon. Subsequent inference uses local files only, validates hashes, and stores source/model-versioned vectors in SQLite. No CUDA requirement. Model preparation is not part of `make demo` or CI. Missing dependencies/weights produce an explicit blocked status, never a hidden lexical fallback.

## Read the results correctly

The final original CANON suite passes **32/32** for lexical, full-pack, dense and hybrid answers. That set was visible during development and is now a regression suite. It must be read together with the independent quality evidence:

| Evaluation set | Before → final | What this establishes |
|---|---|---|
| Original public CANON cases | Initial 29/32 → final 32/32 | Covered known cases now pass; the evaluator itself was also repaired, so this is not a clean population-quality comparison. |
| First independently authored, frozen 26-case set | 20/23 → 23/23 high-certainty cases; 3 remain unscored | Observed repairs on disclosed regressions; the set ceased being unseen after the first evaluation. |
| Follow-up 12-case challenge, withheld until final code freeze | 7/12 → 7/12 for all four methods | Five missing requested attributes still receive misleading `supported` answers. No improvement on this challenge. |

`make eval-independent` replays both independently authored sets with lexical and full-pack extraction; no model download is required. It writes to `runtime/independent-reproduction.json` and `runtime/independent-challenge-reproduction.json`. A completed command does not mean every quality case passed; inspect both reports. Real dense/hybrid reproduction commands are included in the independent quality report and require the explicitly prepared model.

The five unresolved cases ask for opacity, maximum logo width, a font redistribution license, campaign timezone and warranty compensation—none is supplied by the guides. Exact citations still accompany insufficient answers. See [LIMITATIONS](LIMITATIONS.md) and the [preserved quality report](reports/public/independent-quality.json), including the failed intermediate fixes. The review is same-session agent work, not external human certification or a statistically representative holdout. Hybrid is not declared a winner.

RELAY and LENS scenario checks pass. SENTINEL rejects the intentionally broken candidate (5/32 versus a 32/32 baseline, 27 regressions); the ordinary candidate now passes the original suite. A mismatched manifest remains `NOT_COMPARABLE`. ECHO measures actual extractive answer calls and end-to-end latency, with no artificial delays or LLM-cost savings claim. Current measurements and source fingerprints are in [RUNS_MANIFEST.json](RUNS_MANIFEST.json) and [reports/public](reports/public).

Delivery checks: [automated tests and static checks](reports/public/verification.json), [final fresh-checkout installation](reports/public/clean-install-review.json), [real embeddings across process restart](reports/public/local-smoke.json), [final focused browser checks](reports/public/browser-review.json) and [earlier desktop/mobile browser smoke](reports/public/browser-smoke.json). A compact [results summary](reports/public/summary.json) links measured laboratory runs. These checks establish the listed mechanics, not general LLM reliability. The [implementation review](reports/public/independent-review.json) and [security report](reports/public/independent-security.json) preserve initial findings, partial fixes and scoped rechecks separately from final delivery validation.

| Mode | Meaning |
|---|---|
| `fixture` | Deterministic workflow/extractive responses; real BM25; no generative model or semantic encoder |
| `local` | Real pinned embeddings and local calculations; answers remain extractive |
| `live` | Explicit opt-in provider requests with call/time/output limits; no live calls made during delivery |
| `replay` | Saved outputs and spans, no new model computation or external effects |

For a bounded live smoke, explicitly configure `TRACECRAFT_LIVE_API_KEY` and `TRACECRAFT_LIVE_MODEL` in the shell, then run `make eval-live LIVE_ARGS='--allow-live --max-calls 1 --max-seconds 30 --max-output-tokens 600'`. Add `--relay --max-calls 8` for model-selected tool proposals. Keys are never obtained from Codex or written to reports. Unknown cost is `null`. This command is a live smoke, not a completed live benchmark. The browser cannot trigger it.

## Data and provenance

Luma Field and Veyra Works are independently authored fictional brands. Public evaluation data is machine-authored, source-checked and exploratory, not expert-certified or secret holdout data. Gold cases are never indexed. Original supplied notes are not included.

Akella was inspected read-only. STC status: **MISSING_PRIVATE_SOURCE — not found, not imported, not verified**. The importer supports its actual catalog/record/evidence contract, checks paths and hashes, preserves review/authority/links, and writes only to ignored `private/`. Other private brand content was not imported.

```sh
AKELLA_ROOT=/your/explicit/akella/path PYTHONPATH=src .venv/bin/python -m tracecraft import-akella
PYTHONPATH=src .venv/bin/python -m tracecraft import-document --root /your/allowed/folder guide.pdf
```

TXT, Markdown and text-layer PDF are supported; image-only PDF reports `IMAGE_ONLY_PDF_NO_OCR`. Imports are private unreviewed snapshots, not automatically promoted to the public corpus or current app index.

[Architecture](docs/architecture.md) · [Source-to-design map](docs/source-to-design.md) · [Evaluation](docs/evaluation.md) · [Data card](docs/data-card.md) · [Inspiration and licensing](docs/inspiration.md) · [Case studies](docs/case-studies.md) · [Security](SECURITY.md) · [API](docs/api.md)

## Быстрый запуск

После первоначальной установки выполните `make serve` и откройте **http://127.0.0.1:8317**. В этой рабочей копии окружение и локальная модель уже подготовлены. `make demo` повторяет шесть демонстраций без ключей, `make eval-local` — прогоны с настоящими эмбеддингами. Для каждой лаборатории есть отдельная команда из таблицы выше.

Начните с [русского сценария демонстрации](docs/demo-script.md). Успешные автотесты проверяют механику. Исходный CANON теперь проходит 32/32, но отдельная проверка, скрытая до финальной фиксации кода, остаётся на 7/12: пять отсутствующих атрибутов ошибочно получают статус supported. См. независимые отчёты выше; рост на уже раскрытом наборе не доказывает обобщение. Платные вызовы, Git push и публикация не выполнялись.

## Prepare a review copy

```sh
.venv/bin/python scripts/export_public.py dist/public-review-new
```

This creates the requested fresh destination from an explicit file/directory allowlist; it fails if that destination already exists. The final delivery review copy is `dist/public-review-audited`; the older `dist/public-review` is a preserved earlier snapshot. It excludes private imports, runtime databases, model weights, environments and Git history. The delivered copy has been checked separately, including tracked files. Original source licensing remains an owner decision before publication; see [licensing](docs/licensing.md). The command does not publish anything.
