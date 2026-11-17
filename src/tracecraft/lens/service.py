"""Diagnoses reference observable spans, never hidden model reasoning."""
from __future__ import annotations

import html
import json
import re
import time
import uuid
from typing import Any

from tracecraft.core.models import Scope, TraceSpan
from tracecraft.core.store import Store, canonical, digest, utcnow
from tracecraft.relay import Relay, RelayError

TAXONOMY = ['ingestion', 'missing_source', 'retrieval_miss', 'stale_source', 'unsupported_claim',
            'invalid_args', 'tool_execution', 'permission', 'unsafe_cache_hit', 'timeout_budget',
            'stale_approval', 'evaluator_gap', 'unknown']
FIXES = {
    'ingestion': 'Validate source parsing and hash provenance before indexing.',
    'missing_source': 'Supply a permitted source, or abstain without inventing a rule.',
    'retrieval_miss': 'Inspect eligible evidence, query and exact context assembly; evaluate a bounded retrieval change.',
    'stale_source': 'Refresh the pinned snapshot and invalidate dependent artifacts or cache entries.',
    'unsupported_claim': 'Remove unsupported assertions or obtain evidence that entails the claim.',
    'invalid_args': 'Correct the typed tool proposal and validate its values before execution.',
    'tool_execution': 'Inspect the failed tool result and apply bounded recovery without duplicate effects.',
    'permission': 'Keep the scope boundary; do not bypass it to make the task pass.',
    'unsafe_cache_hit': 'Invalidate the entry and require compatible scope and source dependencies.',
    'timeout_budget': 'Stop the attempt and revise the budget explicitly before a new run.',
    'stale_approval': 'Prepare the current artifact package and request a new bound review.',
    'evaluator_gap': 'Add a separately reviewed test for the missed property.',
    'unknown': 'Gather missing observations; do not assert an unverified cause.',
}
PROPOSED_EXPECTATIONS = {
    'invalid_args': 'Reject malformed or out-of-range tool arguments before any effect.',
    'timeout_budget': 'Mark an expired run failed; do not write an artifact or claim success.',
    'retrieval_miss': 'Preserve the retrieved applicable evidence in the answer context.',
    'stale_approval': 'Reject approval for changed input, artifacts, source dependencies or deadline.',
    'missing_source': 'Return insufficient evidence without inventing a rule.',
    'unknown': 'Review the incident and state a testable expected behavior independently.',
}


class LensError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _scrub(value: Any):
    """Defense in depth for local rendered diagnostics; not a general secret proof."""
    if isinstance(value, dict):
        return {key: '[REDACTED]' if re.search(r'(api.?key|password|secret|authorization|cookie|token)$', key, re.I)
                else _scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, str):
        return re.sub(r'\b(?:sk-[A-Za-z0-9_-]{16,}|Bearer\s+[A-Za-z0-9_.-]{10,})', '[REDACTED]', value)
    return value


class Lens:
    def __init__(self, store: Store, atlas):
        self.store = store
        self.atlas = atlas

    def _run(self, run_id: str, scope: Scope | None):
        manifest = self.store.get('runs', run_id)
        if manifest is None:
            raise KeyError(run_id)
        saved_scope = manifest.get('config', {}).get('scope')
        if not saved_scope and manifest.get('data_origin') != 'synthetic':
            raise LensError('permission', 'Nonpublic traces require an explicit bound scope.')
        if saved_scope:
            saved = Scope.model_validate(saved_scope)
            active = scope or Scope(brand=saved.brand, snapshot=saved.snapshot)
            if saved.model_dump() != active.model_dump():
                raise LensError('permission', 'Trace is outside the current demo scope.')
        elif scope and (scope.tenant != 'demo' or scope.principal != 'demo-reader' or scope.permissions != ['public']):
            raise LensError('permission', 'Only public demo traces are available in this profile.')
        return manifest

    @staticmethod
    def _classification(span: dict) -> str | None:
        error = (span.get('error') or '').lower()
        stage = span['stage'].lower()
        if span['status'] != 'error' and not error:
            return None
        if 'omit' in error or span.get('inputs', {}).get('injected_fault') == 'omit_evidence':
            return 'retrieval_miss'
        if 'stale_approval' in error or stage == 'approval.validation':
            return 'stale_approval'
        if any(word in error for word in ('timeout', 'budget', 'deadline')) or stage == 'deadline':
            return 'timeout_budget'
        for category in TAXONOMY:
            if category in error:
                return category
        return 'unknown'

    def diagnose(self, run_id: str, scope: Scope | None = None) -> dict:
        manifest = self._run(run_id, scope)
        spans = self.store.spans(run_id)
        findings = []
        for span in spans:
            category = self._classification(span)
            if category is None:
                continue
            findings.append({'classification': category, 'symptom': f"{span['stage']}: {span.get('error') or span['status']}",
                             'hypothesis': FIXES[category], 'certainty': 'observed',
                             'evidence_span_ids': [span['id']], 'fix': FIXES[category]})
        # A no-evidence answer alone cannot establish a retrieval bug.
        for span in spans:
            if span['stage'] == 'answer_validation' and span['outputs'].get('status') == 'insufficient_evidence' and not findings:
                findings.append({'classification': 'missing_source', 'symptom': 'Answer abstained because no applicable evidence reached it.',
                                 'hypothesis': 'The source may be absent, outside scope, or missed by retrieval; these are not equivalent.',
                                 'certainty': 'hypothesis', 'evidence_span_ids': [span['id']],
                                 'fix': 'Inspect the eligible corpus and retrieved/context IDs before choosing a change.'})
        reproduction = self.store.get('lens_reproductions', run_id)
        if reproduction and reproduction.get('checks', {}).get('failure_reproduced'):
            for finding in findings:
                if finding['classification'] == reproduction.get('classification'):
                    finding['certainty'] = 'reproduced'
                    finding['reproduction_run_id'] = reproduction['reproduction_run_id']
                    finding['reproduction_evidence_span_ids'] = reproduction['reproduction_evidence_span_ids']
        report = {'schema_version': 'tracecraft.diagnosis/1', 'run_id': run_id,
                  'manifest': manifest, 'timeline': spans, 'findings': findings,
                  'status': 'INCIDENT' if findings else 'NO_OBSERVED_FAILURE', 'mode': manifest['mode'],
                  'data_origin': manifest.get('data_origin', 'unknown'), 'measurement_status': 'observed_trace',
                  'review_status': 'not_human_reviewed', 'replay_kind': 'recorded_observation',
                  'taxonomy': TAXONOMY, 'injection': reproduction,
                  'limitations': ['A trace records observations, not hidden model reasoning.',
                                  'A missing span does not prove a step succeeded. Hypotheses require reproduction.']}
        return _scrub(report)

    def replay(self, run_id: str, scope: Scope | None = None) -> dict:
        report = self.diagnose(run_id, scope)
        report.update(mode='replay', original_mode=report['manifest']['mode'], replay_kind='recorded',
                      executed_tools=0, new_model_calls=0, measurement_status='recorded_not_new_benchmark')
        return report

    def draft(self, run_id: str, scope: Scope | None = None) -> dict:
        report = self.diagnose(run_id, scope)
        if not report['findings']:
            raise LensError('no_observed_failure', 'No observed incident is available for a regression draft.')
        finding = report['findings'][0]
        draft = {'schema_version': 'tracecraft.eval-case-draft/1', 'id': uuid.uuid4().hex,
                 'source_run_id': run_id, 'created_at': utcnow(), 'scope': report['manifest'].get('config', {}).get('scope', Scope().model_dump()),
                 'data_origin': report['data_origin'], 'review_status': 'needs_expected_behavior_review',
                 'classification': finding['classification'], 'observed_failure': finding['symptom'],
                 'evidence_span_ids': finding['evidence_span_ids'], 'expected_behavior': None,
                 'proposed_expected_behavior': PROPOSED_EXPECTATIONS.get(finding['classification'], PROPOSED_EXPECTATIONS['unknown']),
                 'gold': None, 'warning': 'Observed failing output is not gold. A human must confirm an independent expected behavior.'}
        self.store.put('eval_case_drafts', draft['id'], draft)
        return draft

    def confirm_draft(self, draft_id: str, expected_behavior: str, reviewer: str, scope: Scope | None = None) -> dict:
        draft = self.store.get('eval_case_drafts', draft_id)
        if not draft:
            raise KeyError(draft_id)
        self._run(draft['source_run_id'], scope)
        if not 12 <= len(expected_behavior.strip()) <= 4000 or not reviewer.strip():
            raise LensError('invalid_args', 'Supply a concrete expected behavior and reviewer identity.')
        draft.update(expected_behavior=expected_behavior.strip(), review_status='expected_behavior_reviewed',
                     reviewer=reviewer.strip(), reviewed_at=utcnow())
        self.store.put('eval_case_drafts', draft_id, draft)
        return draft

    def import_trace(self, payload: dict, scope: Scope | None = None) -> dict:
        """External traces stay external, regardless of a supplied synthetic label."""
        scope = scope or Scope()
        if len(canonical(payload).encode()) > 1_000_000:
            raise LensError('too_large', 'Trace import exceeds 1 MB.')
        if set(payload) - {'schema_version', 'spans', 'label'} or payload.get('schema_version') != 'tracecraft.trace/1':
            raise LensError('invalid_schema', 'Expected tracecraft.trace/1 with spans and optional label.')
        raw_spans = payload.get('spans')
        if not isinstance(raw_spans, list) or not 1 <= len(raw_spans) <= 500:
            raise LensError('invalid_schema', 'Import between 1 and 500 typed spans.')
        spans = [TraceSpan.model_validate(value) for value in raw_spans]
        if any(span.schema_version != 'tracecraft.span/1' for span in spans):
            raise LensError('invalid_schema', 'Unsupported span schema version.')
        ids = [span.id for span in spans]
        if len(set(ids)) != len(ids):
            raise LensError('invalid_schema', 'Duplicate span IDs are not allowed.')
        if len({span.run_id for span in spans}) != 1:
            raise LensError('invalid_schema', 'One import must describe one run.')
        if any(span.parent_id and span.parent_id not in ids for span in spans):
            raise LensError('invalid_schema', 'Parent spans must be included in this trace.')
        # Reject cycles before remapping IDs into a new isolated namespace.
        parents = {span.id: span.parent_id for span in spans}
        for sid in ids:
            seen = set()
            current: str | None = sid
            while current:
                if current in seen:
                    raise LensError('invalid_schema', 'Span parent cycle detected.')
                seen.add(current)
                current = parents.get(current)
        run = self.store.new_run('lens-import', 'replay', {'scope': scope.model_dump(), 'source_schema': payload['schema_version'],
                                                        'label': str(payload.get('label', 'Imported trace'))[:200]})
        remapped = {sid: uuid.uuid4().hex for sid in ids}
        for span in spans:
            item = span.model_dump()
            item.update(id=remapped[span.id], run_id=run['id'],
                        parent_id=remapped.get(span.parent_id) if span.parent_id else None, data_origin='external')
            self.store.put('spans', item['id'], _scrub(item))
        self.store.finish_run(run['id'], 'recorded', data_origin='external')
        return self.diagnose(run['id'], scope)

    def _failure_once(self, fault: str, mode: str, scope: Scope):
        relay = Relay(self.store, self.atlas)
        if fault == 'invalid_args':
            state = relay.create({'brand': scope.brand, 'objective': 'logo banner'}, mode, scope)
            rejected = False
            try:
                relay.execute_tool(state['id'], {'name': 'read_evidence', 'arguments': {'evidence_id': 41},
                                                'idempotency_key': 'isolated-invalid-args'}, scope)
            except RelayError as exc:
                rejected = exc.code == 'invalid_args'
            fixed = relay.execute_tool(state['id'], {'name': 'validate_requirements', 'arguments': {},
                                                    'idempotency_key': 'isolated-corrected-args'}, scope)
            return state['id'], rejected, bool(fixed['schema_valid']), 'invalid_args'
        if fault == 'timeout':
            state = relay.create({'brand': scope.brand}, mode, scope)
            # Explicit local fault: expire the persisted deadline. Detection uses the real guard.
            state['deadline_at'] = time.time() - 1
            self.store.put('relay', state['id'], state)
            self.store.trace(state['id'], 'fault_injection', {'fault': 'timeout'}, {'deadline_expired': True})
            expired = relay.resume(state['id'], scope=scope)
            repaired = relay.create({'brand': scope.brand}, mode, scope)
            return state['id'], expired['state'] == 'failed' and expired['error']['code'] == 'timeout', repaired['state'] == 'awaiting_input', 'timeout_budget'
        if fault in {'omit_evidence', 'wrong_snapshot'}:
            query = 'logo'
            faulty_scope = scope.model_copy(update={'snapshot': 'isolated-missing-snapshot'}) if fault == 'wrong_snapshot' else scope
            answer = self.atlas.answer(query, faulty_scope, mode=mode, fault='omit_evidence' if fault == 'omit_evidence' else None)
            if fault == 'wrong_snapshot':
                self.store.trace(answer.run_id, 'fault_injection', {'fault': fault, 'snapshot': faulty_scope.snapshot},
                                 {'actual_evidence_count': len(answer.evidence_ids), 'answer_status': answer.status},
                                 'error' if not answer.evidence_ids else 'ok', 'missing_source' if not answer.evidence_ids else None)
            fixed_answer = self.atlas.answer(query, scope, mode=mode)
            return answer.run_id, answer.status == 'insufficient_evidence', bool(fixed_answer.evidence_ids), 'retrieval_miss' if fault == 'omit_evidence' else 'missing_source'
        if fault == 'repeat_event':
            state = relay.create({'brand': scope.brand, 'objective': 'logo banner', 'width': 1200, 'height': 628,
                                  'copy': 'Explore more'}, mode, scope)
            before = len([e for e in self.store.list('relay_effects') if e['run_id'] == state['id']])
            relay.resume(state['id'], scope=scope)
            after = len([e for e in self.store.list('relay_effects') if e['run_id'] == state['id']])
            self.store.trace(state['id'], 'fault_injection', {'fault': 'repeat_event'},
                             {'effect_count_before': before, 'effect_count_after': after, 'duplicate_prevented': before == after})
            return state['id'], False, before == after == 1, 'tool_execution'
        raise LensError('invalid_args', 'Unknown isolated fault.')

    def inject(self, fault: str, mode: str = 'fixture', scope: Scope | None = None) -> dict:
        if mode not in {'fixture', 'local'}:
            raise LensError('MODE_NOT_AVAILABLE', 'Fault injection uses isolated fixture/local demo computation only.')
        scope = scope or Scope()
        if scope.tenant != 'demo' or scope.permissions != ['public'] or scope.brand not in {'luma', 'veyra'}:
            raise LensError('permission', 'Fault injection is restricted to public synthetic demo scope.')
        first, failed, fixed, category = self._failure_once(fault, mode, scope)
        second, repeated, fixed_again, _ = self._failure_once(fault, mode, scope)
        first_spans = self.store.spans(first)
        second_spans = self.store.spans(second)
        # Reproduction is established by running the guarded operation again, not by copying a label.
        evidence = [s['id'] for s in second_spans if self._classification(s) == category]
        reproduction = {'fault': fault, 'classification': category, 'reproduction_run_id': second,
                        'reproduction_evidence_span_ids': evidence,
                        'checks': {'failure_observed': failed, 'failure_reproduced': bool(failed and repeated and evidence),
                                   'bounded_fix_verified': bool(fixed and fixed_again)},
                        'source_trace_hash': digest(first_spans), 'reproduction_trace_hash': digest(second_spans)}
        self.store.put('lens_reproductions', first, reproduction)
        # wrong_snapshot diagnosis is viewed in the same explicit missing snapshot scope.
        report_scope = scope.model_copy(update={'snapshot': 'isolated-missing-snapshot'}) if fault == 'wrong_snapshot' else scope
        return self.diagnose(first, report_scope)

    def report_html(self, run_id: str, scope: Scope | None = None) -> str:
        report = self.diagnose(run_id, scope)
        if report['data_origin'] != 'synthetic' or any(s.get('data_origin') != 'synthetic' for s in report['timeline']):
            raise LensError('private_export', 'Only allowlisted synthetic demo traces can be exported publicly.')
        # Source IDs in arbitrary external traces cannot be laundered via the synthetic label.
        body = html.escape(json.dumps(report, ensure_ascii=False, indent=2))
        return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                '<title>LENS observed trace report</title><style>body{max-width:1100px;margin:40px auto;padding:24px;'
                'font:16px system-ui;background:#f3f4ef;color:#152421}pre{white-space:pre-wrap;overflow-wrap:anywhere;'
                'padding:24px;background:white;border:1px solid #ccc;font:12px ui-monospace}</style>'
                '<h1>LENS — observed trace</h1><p>Recorded evidence. No external actions re-executed. '
                'Synthetic corpus; no production reliability claim.</p><pre>' + body + '</pre></html>')


def experiment(store: Store, atlas, mode: str = 'fixture') -> dict:
    start = time.perf_counter()
    lens = Lens(store, atlas)
    diagnosis = lens.inject('invalid_args', mode)
    draft = lens.draft(diagnosis['run_id'])
    replay = lens.replay(diagnosis['run_id'])
    effects_before = len(store.list('relay_effects'))
    lens.replay(diagnosis['run_id'])
    effects_after = len(store.list('relay_effects'))
    checks = {**diagnosis['injection']['checks'], 'draft_is_not_gold': draft['gold'] is None and draft['expected_behavior'] is None,
              'replay_has_no_effects': effects_before == effects_after and replay['executed_tools'] == 0,
              'span_references_exist': all(set(f['evidence_span_ids']) <= {s['id'] for s in diagnosis['timeline']} for f in diagnosis['findings'])}
    report = {'module': 'lens', 'mode': mode, 'data_origin': 'synthetic', 'measurement_status': 'measured',
              'status': 'PASS' if all(checks.values()) else 'FAIL', 'run_id': diagnosis['run_id'],
              'draft_id': draft['id'], 'diagnosis': diagnosis, 'checks': checks,
              'passed': sum(checks.values()), 'failed': sum(not v for v in checks.values()), 'skipped': 0,
              'elapsed_ms': (time.perf_counter() - start) * 1000, 'usage': {'calls': 0, 'cost_usd': None},
              'limitations': ['Only the isolated demonstrated fault is reproduced; general root-cause accuracy is not measured.',
                              'The corrected operation is validated, not an autonomous system update.',
                              'Draft expected behavior still requires separate human review.']}
    store.put('reports', 'lens', report)
    return report
