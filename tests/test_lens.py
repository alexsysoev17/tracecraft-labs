import pytest

from tracecraft.atlas import Atlas
from tracecraft.core.models import Scope, TraceSpan
from tracecraft.core.store import Store, utcnow
from tracecraft.lens import Lens, LensError, experiment
from tracecraft.relay import Relay


@pytest.fixture
def system(tmp_path):
    store = Store(tmp_path / 'lens.sqlite')
    atlas = Atlas(store)
    return store, atlas, Lens(store, atlas)


def test_reproduced_fault_has_real_span_evidence_and_reviewed_draft_boundary(system):
    store, _, lens = system
    report = lens.inject('invalid_args')
    finding = next(f for f in report['findings'] if f['classification'] == 'invalid_args')
    assert finding['certainty'] == 'reproduced'
    assert report['injection']['checks']['bounded_fix_verified']
    assert set(finding['evidence_span_ids']) <= {s['id'] for s in report['timeline']}
    assert finding['reproduction_run_id'] != report['run_id']
    draft = lens.draft(report['run_id'])
    assert draft['expected_behavior'] is None and draft['gold'] is None
    assert draft['review_status'] == 'needs_expected_behavior_review'
    confirmed = lens.confirm_draft(draft['id'], 'Reject invalid arguments before any tool execution.', 'local-reviewer')
    assert confirmed['review_status'] == 'expected_behavior_reviewed'
    assert confirmed['gold'] is None  # A reviewed statement alone is not an executable evaluator.
    assert store.get('eval_case_drafts', draft['id'])['reviewer'] == 'local-reviewer'


@pytest.mark.parametrize('fault', ['timeout', 'omit_evidence'])
def test_fault_guard_reproduction_and_bounded_fix(system, fault):
    _, _, lens = system
    report = lens.inject(fault)
    assert report['injection']['checks']['failure_observed']
    assert report['injection']['checks']['failure_reproduced']
    assert report['injection']['checks']['bounded_fix_verified']


def test_recorded_replay_does_not_execute_effects(system):
    store, _, lens = system
    report = lens.inject('invalid_args')
    before = (store.list('relay_effects'), len(store.list('spans')))
    replay = lens.replay(report['run_id'])
    after = (store.list('relay_effects'), len(store.list('spans')))
    assert before == after
    assert replay['mode'] == 'replay' and replay['new_model_calls'] == 0 and replay['executed_tools'] == 0


def test_missing_source_is_hypothesis_not_proven_cause(system):
    _, atlas, lens = system
    answer = atlas.answer('unicorn spacecraft liability', Scope())
    report = lens.diagnose(answer.run_id)
    assert report['findings'][0]['certainty'] == 'hypothesis'
    assert report['findings'][0]['classification'] == 'missing_source'


def test_cross_scope_trace_denied(system):
    store, atlas, lens = system
    relay = Relay(store, atlas)
    run = relay.create({'brand': 'luma'})
    with pytest.raises(LensError, match='scope'):
        lens.diagnose(run['id'], Scope(brand='veyra'))
    with pytest.raises(LensError):
        lens.replay(run['id'], Scope(tenant='other'))


def imported_span(**updates):
    return TraceSpan(id='external-one', run_id='old-run', timestamp=utcnow(), stage='tool',
                     inputs={}, outputs={'api_key': 'secret'}, status='error', error='invalid_args').model_copy(update=updates).model_dump()


def test_external_import_version_validation_redaction_and_export_boundary(system):
    _, _, lens = system
    with pytest.raises(LensError):
        lens.import_trace({'schema_version': 'unknown', 'spans': []})
    with pytest.raises(LensError):
        lens.import_trace({'schema_version': 'tracecraft.trace/1', 'spans': [imported_span(), imported_span()]})
    report = lens.import_trace({'schema_version': 'tracecraft.trace/1', 'spans': [imported_span()]})
    assert report['data_origin'] == 'external'
    assert report['timeline'][0]['outputs']['api_key'] == '[REDACTED]'
    assert report['timeline'][0]['id'] != 'external-one'
    with pytest.raises(LensError, match='synthetic'):
        lens.report_html(report['run_id'])


def test_external_import_parent_cycles_rejected(system):
    _, _, lens = system
    with pytest.raises(LensError, match='cycle'):
        lens.import_trace({'schema_version': 'tracecraft.trace/1', 'spans': [imported_span(parent_id='external-one')]})


def test_html_report_escapes_recorded_text(system):
    store, _, lens = system
    report = lens.inject('invalid_args')
    store.trace(report['run_id'], 'untrusted_source', {}, {'text': '<script>alert(1)</script>'})
    output = lens.report_html(report['run_id'])
    assert '<script>alert' not in output
    assert '&lt;script&gt;' in output


def test_no_failure_no_draft_and_repeat_event_observed(system):
    store, atlas, lens = system
    run = Relay(store, atlas).create({'brand': 'luma'})
    with pytest.raises(LensError, match='No observed incident'):
        lens.draft(run['id'])
    duplicate = lens.inject('repeat_event')
    assert duplicate['status'] == 'NO_OBSERVED_FAILURE'
    assert duplicate['injection']['checks']['bounded_fix_verified']


def test_lens_experiment(system):
    store, atlas, _ = system
    report = experiment(store, atlas)
    assert report['status'] == 'PASS'
    assert report['failed'] == 0
