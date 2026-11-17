"""Source-first independent challenge set; its cases were frozen before code inspection.

Run outside pytest to retain complete observed/expected output, including honest failures:
    PYTHONPATH=src .venv/bin/python tests/test_independent_quality.py \
        --report reports/public/independent-quality-current.json --label current
The script only calls the public Atlas/Store interfaces. It never reads CANON gold or
uses CANON's evaluator. Local mode is opt-in and uses already installed weights only.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import socket
import tempfile
from unittest.mock import patch

import pytest

from tracecraft.atlas import Atlas
from tracecraft.core.embeddings import Encoder
from tracecraft.core.models import Scope
from tracecraft.core.store import ROOT as IMPLEMENTATION_ROOT, Store, source_fingerprint

REVIEW_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = REVIEW_ROOT / 'tests/independent_cases.json'
FROZEN_CASE_SHA256 = '5ae0491a41d8ed0df4124cae8c97596176e48fb3539a901ff8b130edaab85e1f'
CASE_SET = json.loads(CASE_PATH.read_text())
CASES = CASE_SET['cases']
STATUS_MAP = {
    'answered': {'supported'},
    'insufficient': {'insufficient_evidence', 'needs_review'},
    'conflict': {'conflict'},
    'answered_or_insufficient': {'supported', 'insufficient_evidence', 'needs_review'},
}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@contextmanager
def network_disabled():
    """Fail closed if a library tries to connect; no paid or network calls are allowed."""
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('Independent review forbids network')), \
         patch.object(socket, 'create_connection', side_effect=AssertionError('Independent review forbids network')):
        yield


def source_sections(brand, snapshot):
    path = REVIEW_ROOT / f'datasets/public-demo/{brand}-{snapshot}.md'
    text = path.read_text()
    headings = list(re.finditer(r'^## (.+)$', text, re.MULTILINE))
    return text, {
        match.group(1): text[match.end():headings[index + 1].start() if index + 1 < len(headings) else len(text)].strip()
        for index, match in enumerate(headings)
    }, _sha(path)


def assess(atlas, case, mode='fixture', method='lexical'):
    scope = Scope(brand=case['brand'], snapshot=case['snapshot'], locale=case['locale'])
    with network_disabled():
        answer = atlas.answer(case['query'], scope, method=method, mode=mode)
    text = answer.text.casefold()
    source, sections, source_sha = source_sections(case['brand'], case['snapshot'])
    covered = set()
    provenance_errors = []
    for claim in answer.claims:
        evidence = atlas.evidence(scope, claim.evidence_id)
        if evidence is None:
            provenance_errors.append(f'{claim.evidence_id}: evidence unavailable under public scope')
            continue
        if evidence.source_hash != source_sha:
            provenance_errors.append(f'{claim.evidence_id}: source hash does not match Markdown guide')
        if source[evidence.start:evidence.end] != evidence.text:
            provenance_errors.append(f'{claim.evidence_id}: evidence offsets do not match Markdown guide')
        if not claim.quote or claim.quote != claim.text or claim.quote not in evidence.text:
            provenance_errors.append(f'{claim.evidence_id}: claim/quotation not anchored verbatim in evidence')
        for name, section_text in sections.items():
            if claim.quote and claim.quote in section_text:
                covered.add(name)
    missing_groups = [group for group in case['required_text_groups'] if not any(value.casefold() in text for value in group)]
    forbidden = [value for value in case['forbidden_text'] if value.casefold() in text]
    missing_sections = sorted(set(case['expected_source_sections']) - covered)
    unexpected_sections = sorted(covered - set(case['expected_source_sections']))
    claim_ids = {claim.evidence_id for claim in answer.claims}
    if claim_ids != set(answer.evidence_ids):
        provenance_errors.append('Claim evidence IDs differ from answer evidence IDs')
    def normalize(value):
        return ' '.join(value.split())
    body = normalize(' '.join(claim.text for claim in answer.claims))
    if answer.status == 'supported':
        response_consistent = bool(answer.claims) and normalize(answer.text) == body
    elif answer.status == 'conflict':
        prefix = 'Sources conflict; a reviewed priority decision is required.'
        response_consistent = bool(answer.claims) and normalize(answer.text) == normalize(prefix + ' ' + body)
    else:
        refusals = {
            'No applicable rule found in the permitted snapshot.',
            'Only observations or examples found; these do not establish an authoritative rule.',
            'This read-only answer cannot authorize or execute an action; use the reviewed workflow.',
        }
        response_consistent = not answer.claims and not answer.evidence_ids and answer.text.strip() in refusals
    checks = {
        'retrieval_executed': answer.retrieval is not None and answer.retrieval.status == 'ready',
        'rendered_text_matches_validated_claims_or_refusal': response_consistent,
        'status_matches': answer.status in STATUS_MAP[case['expected_status']],
        'all_required_facts_present': not missing_groups,
        'required_source_sections_covered': not missing_sections,
        'forbidden_text_absent': not forbidden,
        'claims_have_valid_source_provenance': not provenance_errors,
        'no_provider_calls': answer.usage.calls == 0,
        'no_relay_side_effects': not atlas.store.list('relay_effects'),
    }
    passed = all(checks.values()) if case['certainty'] == 'high' else None
    return {
        'id': case['id'], 'category': case['category'], 'certainty': case['certainty'],
        'query': case['query'], 'scope': scope.model_dump(), 'mode': mode, 'method': method,
        'expected_status_semantic': case['expected_status'],
        'acceptable_api_statuses': sorted(STATUS_MAP[case['expected_status']]),
        'source_level_facts': case['source_level_facts'],
        'rationale': case['rationale'], 'passed': passed, 'checks': checks,
        'missing_text_groups': missing_groups, 'forbidden_text_observed': forbidden,
        'missing_source_sections': missing_sections, 'extra_source_sections_observed': unexpected_sections,
        'provenance_errors': provenance_errors,
        'actual': {'status': answer.status, 'text': answer.text, 'evidence_ids': answer.evidence_ids,
                   'claims': [claim.model_dump() for claim in answer.claims],
                   'generation_kind': answer.generation_kind, 'latency_ms': answer.latency_ms,
                   'usage': answer.usage.model_dump(), 'run_id': answer.run_id,
                   'retrieval_status': answer.retrieval.status if answer.retrieval else None,
                   'retrieval_hit_ids': [hit.evidence.id for hit in answer.retrieval.hits] if answer.retrieval else []},
    }


def test_independent_case_freeze_and_source_integrity():
    assert _sha(CASE_PATH) == FROZEN_CASE_SHA256, 'Frozen holdout changed; create a new version rather than silently editing it'
    for relative_path, expected_hash in CASE_SET['sources_sha256'].items():
        # Narrative documentation can change after review; only the four factual guides
        # define this fixed expectation set and must keep their original hashes.
        if relative_path.startswith('datasets/public-demo/') and relative_path != 'datasets/public-demo/README.md':
            assert _sha(REVIEW_ROOT / relative_path) == expected_hash
    assert len(CASES) >= 16
    assert len({case['id'] for case in CASES}) == len(CASES)


@pytest.mark.parametrize('case', [case for case in CASES if case['certainty'] == 'high'], ids=lambda case: case['id'])
def test_independent_source_question(case, tmp_path):
    result = assess(Atlas(Store(tmp_path / 'independent.sqlite')), case)
    assert result['passed'], json.dumps(result, ensure_ascii=False, indent=2)


@pytest.mark.parametrize('case_id', ['IQ05', 'IQ14'])
def test_independent_harness_rejects_unattributed_response_text(case_id, tmp_path, monkeypatch):
    atlas = Atlas(Store(tmp_path / 'independent.sqlite'))
    original = atlas.answer
    def corrupted(*args, **kwargs):
        answer = original(*args, **kwargs)
        answer.text += '\nThe return period is 42 days.'
        return answer
    monkeypatch.setattr(atlas, 'answer', corrupted)
    case = next(case for case in CASES if case['id'] == case_id)
    result = assess(atlas, case)
    assert not result['checks']['rendered_text_matches_validated_claims_or_refusal']
    assert result['passed'] is False


def test_independent_harness_rejects_mismatched_claim_quote(tmp_path, monkeypatch):
    atlas = Atlas(Store(tmp_path / 'independent.sqlite'))
    original = atlas.answer
    def corrupted(*args, **kwargs):
        answer = original(*args, **kwargs)
        answer.claims[0].quote = 'Never stretch or rotate'
        return answer
    monkeypatch.setattr(atlas, 'answer', corrupted)
    result = assess(atlas, next(case for case in CASES if case['id'] == 'IQ05'))
    assert not result['checks']['claims_have_valid_source_provenance']
    assert result['passed'] is False


def test_independent_harness_does_not_score_blocked_retrieval_as_abstention(tmp_path, monkeypatch):
    atlas = Atlas(Store(tmp_path / 'independent.sqlite'))
    original = atlas.answer
    def corrupted(*args, **kwargs):
        answer = original(*args, **kwargs)
        answer.retrieval.status = 'MODEL_NOT_PREPARED'
        return answer
    monkeypatch.setattr(atlas, 'answer', corrupted)
    result = assess(atlas, next(case for case in CASES if case['id'] == 'IQ14'))
    assert not result['checks']['retrieval_executed']
    assert result['passed'] is False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--label', required=True)
    parser.add_argument('--mode', choices=['fixture', 'local'], default='fixture')
    parser.add_argument('--methods', nargs='+', choices=['lexical', 'full_pack', 'dense', 'hybrid'], default=['lexical', 'full_pack'])
    parser.add_argument('--model-dir', type=Path)
    parser.add_argument('--cases', type=Path, default=CASE_PATH)
    parser.add_argument('--expected-cases-sha256', default=FROZEN_CASE_SHA256)
    args = parser.parse_args()
    test_independent_case_freeze_and_source_integrity()
    if _sha(args.cases) != args.expected_cases_sha256:
        raise ValueError('Challenge file does not match supplied frozen hash')
    active_case_set = json.loads(args.cases.read_text())
    active_cases = active_case_set['cases']
    started = datetime.now(timezone.utc).isoformat()
    implementation_hash_start = source_fingerprint()
    with tempfile.TemporaryDirectory(prefix='tracecraft-independent-run-') as temporary:
        encoder = Encoder(directory=args.model_dir) if args.model_dir else Encoder()
        atlas = Atlas(Store(Path(temporary) / 'independent.sqlite'), encoder=encoder)
        with network_disabled():
            encoder_status = encoder.status()
        rows = [assess(atlas, case, args.mode, method) for method in args.methods for case in active_cases]
    summary = {}
    for method in args.methods:
        subset = [row for row in rows if row['method'] == method]
        summary[method] = {
            'passed': sum(row['passed'] is True for row in subset),
            'failed': sum(row['passed'] is False for row in subset),
            'uncertain_not_scored': sum(row['passed'] is None for row in subset),
            'failed_case_ids': [row['id'] for row in subset if row['passed'] is False],
            'provenance_failures': sum(bool(row['provenance_errors']) for row in subset),
            'cases_with_extra_source_sections': sum(bool(row['extra_source_sections_observed']) for row in subset),
        }
    implementation_hash_end = source_fingerprint()
    report = {
        'schema_version': 1, 'label': args.label, 'started_at_utc': started,
        'finished_at_utc': datetime.now(timezone.utc).isoformat(),
        'mode': args.mode, 'methods': args.methods,
        'case_file': str(args.cases.resolve().relative_to(REVIEW_ROOT)), 'case_file_sha256': _sha(args.cases),
        'harness_sha256': _sha(__file__), 'implementation_source_hash': implementation_hash_end,
        'implementation_source_hash_at_start': implementation_hash_start,
        'implementation_changed_during_run': implementation_hash_start != implementation_hash_end,
        'encoder_inference_batches': encoder.calls,
        'implementation_source_tree': 'working-tree' if IMPLEMENTATION_ROOT == REVIEW_ROOT else 'isolated-checkout',
        'encoder_status': encoder_status,
        'network': 'socket connects disabled; no downloads or provider calls permitted',
        'independence_boundary': active_case_set['independence_boundary'],
        'scoring_policy': active_case_set['evaluation_policy'],
        'additional_scoring_notes': [
            'Semantic insufficient accepts insufficient_evidence and needs_review because both abstain.',
            'All expected source sections must be cited; extra sections are recorded but do not by themselves fail a case.',
            'Confident cases require requested source facts, truthful status, no forbidden text, provenance, zero provider calls, and no Relay side effects.',
            'Retrieval must execute successfully; returned answer text must exactly consist of validated claims and known status boilerplate, or a recognized empty-claim refusal.',
            'This small public synthetic set is not statistically representative and does not measure generative model quality.',
        ],
        'summary': summary, 'results': rows,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'report': str(args.report), 'summary': summary}, indent=2))


if __name__ == '__main__':
    main()
