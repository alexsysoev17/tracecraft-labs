# Six experiments, with inspectable limits

These cases describe executed scenarios on original synthetic brands, not production
outcomes. The saved fixture/local JSON is the evidence. The delivery includes no
paid generative benchmark, no expert-certified gold and no STC result. Timings are
read from the linked report rather than repeated here because reruns change them.
Counts below refer to the saved 32-case public corpus and nine-request cache control.
Regenerated reports and their manifests are authoritative.

## ATLAS — retrieval is not answer correctness

**Task.** Find applicable brand evidence for exact tokens, paraphrases, exceptions,
versions, conflicts and missing facts, then return a source-grounded result.

**Hypothesis and baseline.** Real multilingual dense retrieval or rank fusion may
recover evidence missed by lexical BM25. The baseline is lexical retrieval on the
same cases; parameters were not selected to force hybrid to win.

**Change and experiment.** Run lexical, dense and RRF hybrid with the same source
scope and deterministic extractive answer layer. `make atlas` executes the fixture
profile; `make eval-local` executes the prepared-model comparison.

**Observed result.** In the [local report](../reports/public/atlas-local.json), mean
retrieval recall is approximately 0.9828 for lexical, 1.0000 for dense and 0.9828 for
hybrid. All three answer configurations now pass 32 of 32 original cases. The initial
run passed 29/32; stemming and source selection were subsequently revised. A separate
withheld follow-up still passes only 7/12 under every method: exact citations do not
resolve missing requested attributes. See the [quality phases](../reports/public/independent-quality.json). In the
[fixture report](../reports/public/atlas-fixture.json), dense and hybrid are
`NOT_RUN`, with 32 skipped cases each; they are not disguised lexical runs.

**Evidence and limits.** Each row preserves context IDs, answer claims and checks.
Tests cover BM25 ordering, RRF, scope, links, conflicts and negative examples. This
is a small authored corpus and exact cosine search, not a retrieval-scale study.
No LLM reliability or universal hybrid advantage is established.

## RELAY — completion requires artifacts and bound review

**Task.** Convert an incomplete digital-banner brief into a usable designer package.

**Hypothesis and control.** Durable state, verified local effects and hash-bound
approval should preserve the task across reopening and reject stale review. The
control is the same run before clarification and before/after an intentional input
revision. There is no claimed comparison against an unstructured live agent.

**Change and experiment.** Supply missing dimensions, reopen storage, prepare a
package, revise the copy, attempt the old approval, approve the current package and
resume again. Run `make relay`.

**Observed result.** [Fixture](../reports/public/relay-fixture.json) and
[local](../reports/public/relay-local.json) reports pass all six scenario checks:
clarification, continuation after reopening, stale-approval rejection, valid
approval, no duplicate effect from repeated resume, and three verified artifacts.
The artifact names are `requirements.json`, `questions.md`, `handoff.md`. Two effects
represent the two deliberately prepared revisions, not duplicate execution.

**Evidence and limits.** Integration tests additionally cover concurrent resume,
cancellation, invalid arguments, deadline, changed source hashes and corrupted
artifacts. The experiment's approval is automated test behavior. Fixture/local mode
is an explicit workflow; actual live model tool decisions were not measured. No
banner pixels or external message/publication are produced, and the SQLite
transaction is not a guarantee about arbitrary external exactly-once effects.

## SENTINEL — expose a real defect and compare conditions

**Task.** Reject unsafe changes while preserving the outputs and conditions that
justify the gate.

**Hypothesis and baseline.** The shared evaluator should catch a candidate that
actually corrupts claims/citations. A separate normal comparison checks lexical
against the compact full rule pack without assuming an improvement.

**Change and experiment.** The broken adapter modifies a supported answer and its
citation IDs; the runner evaluates the resulting output. The normal experiment
changes only retrieval method. A third control changes an undeclared corpus
condition. Run `make sentinel`.

**Observed result.** The [fixture](../reports/public/sentinel-fixture.json) and
[local](../reports/public/sentinel-local.json) reports record 32/32 passing baseline
cases versus 5/32 for the broken candidate, with 27 newly regressed cases and a
`REGRESSION` gate. Both final normal configurations pass 32/32, have zero newly
regressed cases, and receive `PASS`. The altered-manifest control is `NOT_COMPARABLE`.
The earlier normal comparison was blocked by existing critical failures; that gate
policy is unchanged, while the covered outputs and evaluator have been repaired.

**Evidence and limits.** Candidate flags do not contain preassigned scores. Outputs,
checks, manifests, declared changes and gate reasons are saved. Repeats are not
independent tasks. A passing gate does not establish statistical improvement or
promote a production configuration. The independent follow-up failures lie outside
this original 32-case suite; its green gate cannot certify those questions.

## LENS — a finding needs observable evidence

**Task.** Turn a failed execution into an inspectable incident and a regression draft.

**Hypothesis and control.** Typed spans plus isolated reproduction can distinguish
an observed invalid-argument failure from a narrative guess. The comparison is a
malformed tool proposal, its reproduced failure, and a bounded corrected operation.

**Change and experiment.** Inject an invalid argument in a synthetic run, inspect
the failing span, reproduce it, validate a bounded correction and create a draft.
Replay the recording and compare effect counts. Run `make lens`.

**Observed result.** [Fixture](../reports/public/lens-fixture.json) and
[local](../reports/public/lens-local.json) reports pass six checks: failure observed,
failure reproduced, bounded correction verified, referenced spans exist, draft is
not gold, and replay has no effects. The incident report includes the actual
execution timeline and reproduction evidence.

**Evidence and limits.** Tests also cover timeout, stale snapshot, omitted evidence,
duplicate events, cross-scope trace denial and escaped HTML export. A missing-source
symptom remains a hypothesis until competing explanations are resolved. Expected
behavior in a draft needs separate review; an erroneous output is never made gold.
This controlled fault does not measure diagnosis accuracy on arbitrary incidents.

## ECHO — fewer answer calls did not establish a speed benefit

**Task.** Reuse supported answers while rejecting changed brand, version, numeric
conditions, negation, context and access.

**Hypothesis and baseline.** Semantic reuse may avoid an additional answer computation
beyond exact matching. The baseline is a real no-cache pass over the same sequence,
not an estimated timing or a deliberately slowed call.

**Change and experiment.** Run off/exact/semantic policies in fresh namespaces over
nine requests. Calibrate similarity against separate validation pairs, then apply
scope/content/provenance guards. Run `make echo` for fixtures and `make eval-local`
for real embeddings.

**Observed result.** The [local report](../reports/public/echo-local.json) records
0/1/2 hits for off/exact/semantic and 9/8/7 downstream extractive answer calls.
No mandatory-miss case was reused in that sequence. The semantic hit is additional
to the exact repeat. The [fixture report](../reports/public/echo-fixture.json) has
only exact reuse even under the semantic policy; unavailable embeddings are not
silently replaced. No general latency improvement is established: inspect the
measured totals, including lookup/verification, for each run.

**Evidence and limits.** Zero observed false hits in a tiny authored sequence is not
a safety guarantee. Tests add source-hash mutation, permission revocation, stale
claims, changed numbers, mutation requests, TTL, size and concurrency controls.
All reports contain zero LLM calls and unknown monetary cost (`null`). Saving an
extractive function call is not evidence of paid-model savings or ROI.

## CANON — define what correct brand use means

**Task.** Evaluate answers against explicitly scoped rules rather than generic
text similarity.

**Hypothesis and baseline.** A compact full pack or a different retriever can change
source coverage; each must still satisfy rule application, citation, access,
version, prohibition and abstention checks. Lexical retrieval is the baseline.

**Change and experiment.** Run 32 public Russian/English cases against lexical,
full-pack, dense and hybrid configurations with the same evaluator. Scenario
families are separated across development/validation/public-test splits. Gold spans
are checked against source documents and excluded from retrieval. Run `make canon`
or the local suite.

**Observed result.** The [final local report](../reports/public/canon-local.json)
has 32/32 passes for every configuration. The initial 29/32 failures concerned
Russian warranty inflection, a denied question selecting unrelated conflict, and a
negative example selecting that conflict. Those original cases are now regressions.
Independent review also repaired evaluator false positives; comparison is therefore
not a controlled estimate of general answer-quality improvement.

A separate source-first author froze 26 questions before inspecting the gold or
implementation. Of 23 high-certainty scored cases, 20 initially passed and 23 finally
passed; three ambiguous cases remain unscored. The questions were disclosed before
fixes, and failed intermediate changes remain in the
[quality report](../reports/public/independent-quality.json).

A second 12-case challenge was withheld until final code freeze. Both baseline and
final pass only 7/12 for all four methods. Five questions request absent opacity,
maximum logo width, font redistribution permission, campaign timezone or warranty
compensation. The system returns related source passages with valid citations but
incorrectly labels them `supported`. No tuning followed disclosure of that set.
Run `make eval-independent` to reproduce both sets; command completion is not a
quality pass. The no-context live baseline remains `NOT_RUN`.

**Evidence and limits.** Tests verify gold offsets/hashes, family separation, citation
support, unknown/denied/version handling and honest skipping. Gold is machine-authored
and source-checked, not expert reviewed. These public exploratory cases were available
during development; they are not a secret holdout, real STC validation, or evidence
of broad brand reasoning quality.

## What a reviewer can conclude

The repository demonstrates inspectable local mechanisms and reproducible failure
cases. It does not demonstrate autonomous self-improvement, weight training,
production readiness, reduced human rework, paid-model quality or commercial ROI.
The disclosed source-selection regressions improved, but the withheld follow-up did
not. The next question is whether explicit requested-attribute sufficiency can reject
those answers without erasing supported answers, measured on new source-first cases.
The recorded nine engineering fixes are scoped rechecks, not broad quality or
security certification.
