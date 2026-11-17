"""Deterministic evidence checks. Fluent prose still needs a calibrated reviewer."""
import re
from typing import Any

from pydantic import ValidationError

from tracecraft.core.models import Answer, EvalCase, EvalResult, Scope

EVALUATOR_VERSION = 'canon-evidence-checks/2'
RUBRIC = {
    'schema': 'Output must parse as the strict Answer contract.',
    'status': 'Supported/unknown/conflict must match the case expectation.',
    'evidence_access': 'Every cited record must be allowed in the exact brand, snapshot and ACL scope.',
    'quote_location': 'Every claimed quote must exist in the cited record.',
    'claim_support': 'Extractive claims must be contained in their quote; other prose requires human review.',
    'expected_evidence': 'The required evidence and exceptions must be cited; string likeness alone is insufficient.',
    'required_content': 'Each annotated gold span must actually appear in a claim citing that source; a bare citation or token is not an answer.',
    'refusal_content': 'Deterministic abstentions must use the audited refusal template, with no additional assertions.',
    'forbidden_claims': 'Known forbidden assertions must not appear in the answer.',
    'abstention': 'Unknown cases must not make affirmative unsupported claims.',
    'version': 'No answer citation can cross the selected corpus snapshot.',
    'limitations': 'These checks establish consistency with synthetic sources, not truth outside the corpus.',
}

def normalized(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip().casefold()

def evaluate(case: EvalCase, answer: Answer | dict[str, Any], atlas, scope: Scope) -> EvalResult:
    """Compare behavior and source support, never a candidate-provided score."""
    raw = answer.model_dump() if isinstance(answer, Answer) else answer
    try:
        parsed = Answer.model_validate(raw)
    except (ValidationError, TypeError) as error:
        return EvalResult(case_id=case.id, passed=False, checks={'schema': False}, answer=raw,
                          latency_ms=0, error=f'invalid_answer_schema:{type(error).__name__}')
    if parsed.retrieval and parsed.retrieval.status.lower() not in {'ready','ok'}:
        return EvalResult(case_id=case.id, passed=None, checks={'execution': 'NOT_RUN'}, answer=raw,
                          latency_ms=parsed.latency_ms, error=parsed.retrieval.reason or parsed.retrieval.status)
    checks: dict[str, Any] = {'schema': True, 'status': parsed.status == case.expected_status}
    cited = {i: atlas.evidence(scope, i) for i in parsed.evidence_ids}
    checks['evidence_access'] = all(e is not None for e in cited.values())
    checks['version'] = all(e is not None and e.snapshot == scope.snapshot and e.brand == scope.brand
                            for e in cited.values())
    checks['claim_citations'] = all(c.evidence_id in cited and cited[c.evidence_id] is not None for c in parsed.claims)
    checks['quote_location'] = all(cited.get(c.evidence_id) is not None and c.quote.strip()
                                   and c.quote in cited[c.evidence_id].text for c in parsed.claims)
    support = []
    for claim in parsed.claims:
        evidence = cited.get(claim.evidence_id)
        support.append(bool(evidence and claim.quote in evidence.text and normalized(claim.text)
                            and normalized(claim.text) in normalized(claim.quote)))
    checks['claim_support'] = all(support)
    checks['expected_evidence'] = set(case.evidence_ids) <= set(parsed.evidence_ids)
    checks['required_content'] = all(
        any(claim.evidence_id == span['evidence_id'] and normalized(span['quote']) in normalized(claim.text)
            for claim in parsed.claims) for span in case.gold_spans)
    checks['cited_sources_have_claims'] = set(parsed.evidence_ids) <= {c.evidence_id for c in parsed.claims}
    checks['forbidden_claims'] = not any(normalized(bad) in normalized(parsed.text) for bad in case.forbidden_claims)
    checks['abstention'] = case.expected_status != 'insufficient_evidence' or (
        parsed.status == 'insufficient_evidence' and not parsed.claims and not parsed.evidence_ids)
    checks['supported_has_claims'] = parsed.status not in {'supported','conflict'} or bool(parsed.claims)
    free_prose = parsed.generation_kind not in {
        'extractive', 'fixture-extractive', 'fixture', 'deterministic_extractive', 'local_extractive'
    }
    if not free_prose and parsed.status == 'insufficient_evidence':
        checks['refusal_content'] = parsed.text == 'No applicable rule found in the permitted snapshot.'
    # A reference may exist while an assertion contradicts it; evidence_access alone never passes a case.
    checks['all_claims_visible'] = all(normalized(c.text) in normalized(parsed.text) for c in parsed.claims)
    remainder = normalized(parsed.text)
    for claim in parsed.claims:
        remainder = remainder.replace(normalized(claim.text), '')
    if parsed.status == 'conflict':
        remainder = remainder.replace('sources conflict; a reviewed priority decision is required.', '')
    if parsed.status in {'supported','conflict'}:
        checks['all_assertions_attributed'] = not remainder.strip()
    failure = any(value is False for value in checks.values())
    if free_prose:
        checks['human_rubric_review'] = 'NOT_RUN'
    passed = False if failure else (None if free_prose else True)
    return EvalResult(case_id=case.id, passed=passed, checks=checks, answer=raw,
                      latency_ms=parsed.latency_ms,
                      error='free_form_semantic_review_required' if free_prose and not failure else None)

def retrieval_metrics(case: EvalCase, answer: Answer) -> dict[str, Any]:
    gold = set(case.evidence_ids)
    if not gold:
        return {'recall_at_k': None, 'reciprocal_rank': None, 'k': 0, 'context_recall': None}
    hits = answer.retrieval.hits if answer.retrieval else []
    ids = [hit.evidence.id for hit in hits]
    ranks = [i+1 for i, evidence_id in enumerate(ids) if evidence_id in gold]
    context = {e.id for e in answer.retrieval.context} if answer.retrieval else set()
    return {'recall_at_k': len(gold & set(ids))/len(gold), 'reciprocal_rank': 1/min(ranks) if ranks else 0.0,
            'k':len(ids), 'context_recall':len(gold & context)/len(gold)}
