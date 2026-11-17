# Architecture

TRACECRAFT is a local research application with six distinct scenarios, one public
corpus and a small shared execution/evaluation layer. FastAPI serves native
HTML/CSS/JavaScript and JSON endpoints on `127.0.0.1:8317`. No hosted service is
required for fixture mode. See [ADR 001](adr-001.md) for the intentional omission of
Qdrant, LangGraph and a frontend build pipeline. Distribution is a source checkout;
resources depend on repository layout. No wheel or installed console script is supported.

## Components and ownership

| Component | Responsibility | Durable evidence |
| --- | --- | --- |
| `core/models.py` | Strict source, scope, answer, run, trace, tool, artifact, approval, evaluation and cache contracts. | Versioned JSON objects. |
| `core/store.py` | SQLite WAL transactions, records, configuration hashes, source fingerprints and run metadata. | `runtime/tracecraft.sqlite`, ignored by public export. |
| `atlas/service.py` | Eligibility filtering, BM25/dense/RRF retrieval, mandatory constraints and extractive answers. | Retrieved IDs/ranks, exact answer context, claims and provenance. |
| `relay/service.py` | Bounded workflow, typed tool validation, clarification, durable continuation, approval and artifact postconditions. | Checkpoints, artifact content, effect/idempotency ledger and approvals. |
| `canon/` | Public dataset, shared evaluator and benchmark runner. | Per-case checks, outputs, slices, retrieval metrics and uncertainty. |
| `sentinel/service.py` | Invoke baseline/candidate adapters, compare conditions and apply a critical-failure gate. | Both sets of outputs, regressions, manifest differences and gate reason. |
| `lens/service.py` | Diagnose observed spans, isolate/reproduce faults and create review-required regression drafts. | Timeline, cited observations, reproduction checks and drafts. |
| `echo/service.py` | Exact/semantic answer caching, compatibility guards, admission, invalidation and measured controls. | Entries with source dependencies, cache decisions and actual call counts. |
| `core/reports.py` | Run allowlisted synthetic experiments and audit public exports. | `reports/public/<module>-<mode>.json`, `RUNS_MANIFEST.json`. |
| `api/app.py`, `web/` | Loopback boundary and six purpose-specific interactive views. | The UI displays real API results; it contains no fabricated benchmark metrics. |

The HTTP server owns its runtime database. The CLI server uses a lock file to reject
another server owner for that database. Run experiments before starting the server,
or select a different database with the global CLI `--db` option. This is a
single-machine profile; SQLite persistence is not a distributed execution guarantee.

## Data and retrieval

`datasets/public-demo/` contains original Luma Field and Veyra Works documents,
versioned chunks, case gold and cache validation pairs. Gold lives in `cases.json`
and is never indexed. A scope includes brand, snapshot, tenant/project, permissions,
principal, locale, context and ACL version. The browser can select permitted brands
and snapshots; the server assigns tenant, principal and permissions.

ATLAS filters eligibility before lexical/dense ranking and source preview. FTS5
indexes English/Russian Snowball 3.1.1 stems and BM25 sorts lower scores first. Dense search uses normalized 384-dimensional
`intfloat/multilingual-e5-small` embeddings at revision
`614241f622f53c4eeff9890bdc4f31cfecc418b3`, with ONNX Runtime's CPU execution provider.
`configs/embedding.json` pins the model, prefixes, pooling and limit. Preparation is
an explicit `make models` operation. Loading verifies the recorded model hashes;
inference has no automatic download or lexical substitution path. Vectors persist
in SQLite under model/configuration and source fingerprints. Exact cosine search is
appropriate for this small corpus; it is not a scaling result.

RRF combines ranks rather than treating BM25 and cosine as calibrated equivalents.
Applicable mandatory explicit rules and linked exceptions accompany ranked context.
Observed examples, rejected examples and unreviewed notes do not become mandatory
rules. Conflicting values are surfaced rather than resolved by modification time.
The current answer layer is deterministic extraction using heading/tag subject
anchors, distinct scoped body terms, a limited glossary, and format/action guards.
These heuristics still confuse a related source with an answer to a missing
attribute: the [withheld challenge](../reports/public/independent-quality.json)
retains five false-supported outputs out of twelve cases, despite valid citations.

## Execution and approval

Fixture/local RELAY is an explicit workflow, not autonomous planning. Its state
moves among queued, running, awaiting input, awaiting approval, succeeded, failed
and cancelled. Typed tools have separate proposal, schema, value, scope, execution
and postcondition checks. Unknown brief fields trigger clarification.

Artifact content, the local effect ledger and the checkpoint commit in a SQLite
transaction. Filesystem exports are repeatable projections of stored artifacts.
Resume and duplicate calls do not imply that arbitrary external effects would be
exactly once. No email, publication or external commitment tool is present.

Approval binds to the artifact package hash and input snapshot hash. Input changes,
source dependency changes, content corruption and expired deadlines invalidate
approval. Success requires the bound review and artifact checks. The experiment
runner's approval is an automated test action; the interactive approval is a local
human decision, not a corporate approval identity system.

## Evaluation and diagnostics

CANON's evaluator is shared by SENTINEL. Retrieval recall/rank, citation validity,
claim support, version/access, abstention and required behavior are separate checks.
Evaluator `canon-evidence-checks/2` adds required-content checks, claim requirements
for conflicts and canonical refusal checks after independent false-positive review.
A valid citation cannot excuse an unsupported assertion. Free-form generative
answers are not certified by string matching; they require further semantic review.

SENTINEL varies a declared adapter or retrieval method, preserves actual outputs,
and compares dataset/corpus/evaluator/budget/configuration/code conditions. Missing
checks are not passed. Critical candidate failures keep the gate closed even when
no case newly regressed. No gate automatically changes a production configuration.

LENS records externally observable steps, not hidden model reasoning. Symptoms,
hypotheses and reproduction-confirmed findings have distinct certainty values.
Recorded replay performs no external actions. A regression draft retains the
observed output while leaving expected behavior unapproved. Isolated synthetic fault
injection cannot be interpreted as general root-cause-diagnosis accuracy.

## Cache boundary

ECHO only admits supported read-only answers with validated claims and known source
dependencies. The exact namespace includes brand/snapshot, access/context, locale
and generation/retrieval configuration. Semantic lookup is restricted to compatible
scope, uses validation-calibrated similarity, then checks numbers, codes, negation,
objects and modifiers. At a hit, all nested retrieval context is rechecked for
access; source hashes, claims and dependency closure are validated. Invalidation is
namespace scoped, and encoder configuration participates in vector/cache/calibration keys.
TTL and cleanup do not replace invalidation. A per-key single-flight guard prevents
concurrent identical work in this process.

The reports compare real off/exact/semantic controls, including lookup/verification
and embedding work. They measure downstream extractive calls, not paid LLM savings.
Provider prompt caching and embedding reuse are distinct mechanisms.

## Modes, private input and export

| Mode | Executed behavior | Interpretation |
| --- | --- | --- |
| `fixture` | Real local BM25, deterministic extraction/workflow and tests; dense search explicitly unavailable. | Infrastructure behavior, not generative model quality. |
| `local` | Prepared real embeddings, persistent indexing and local computation; extractive answers. | Real measurements on synthetic data. |
| `live` | Explicitly authorized, bounded provider requests through the CLI. | Separate profile; not run in the delivered experiments. |
| `replay` | Read recorded results and spans without re-executing actions. | Historical observation, not fresh inference or benchmark timing. |

`data_origin`, `measurement_status` and `review_status` remain independent. Unknown
usage/cost is `null`. The live provider reads only explicit TRACECRAFT environment
variables; browser/CI paths do not initiate live calls.

The read-only importer checks allowed roots, symlinks, path traversal, size limits
and declared hashes. TXT/Markdown preserve offsets; text PDFs preserve page
provenance; image-only PDFs get an explicit unreadable status without hidden OCR.
Akella snapshots remain under ignored `private/`. The actual STC source was not
found (`MISSING_PRIVATE_SOURCE`); no real STC corpus was imported or benchmarked.

Public reports come only from synthetic experiment runners and pass origin,
restricted-evidence, sensitive-field and canary checks. Runtime, model weights,
original notes and private snapshots are excluded. These checks are a defined
export boundary and heuristic scan, not proof that every possible confidential
string can be recognized. See [SECURITY.md](../SECURITY.md) and
[LIMITATIONS.md](../LIMITATIONS.md) for the local trust model and remaining limits.
