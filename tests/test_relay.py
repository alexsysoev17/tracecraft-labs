import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from tracecraft.atlas import Atlas
from tracecraft.core.models import Scope
from tracecraft.core.store import Store, digest
from tracecraft.relay import Relay, RelayError, experiment


@pytest.fixture
def system(tmp_path):
    store = Store(tmp_path / 'relay.sqlite')
    atlas = Atlas(store)
    return store, atlas, Relay(store, atlas)


def brief(**updates):
    return {'brand': 'luma', 'objective': 'logo banner', 'width': 1200, 'height': 628,
            'copy': 'Explore more', **updates}


def test_incomplete_brief_resume_and_artifact_postconditions(system, tmp_path):
    store, atlas, relay = system
    initial = relay.create({'brand': 'luma', 'objective': 'logo banner'})
    assert initial['state'] == 'awaiting_input'
    assert {q['field'] for q in initial['questions']} == {'width', 'height', 'copy'}
    restarted = Relay(Store(store.path), Atlas(Store(store.path)))
    prepared = restarted.resume(initial['id'], {'width': 800, 'height': 600, 'copy': 'Find your path'})
    assert prepared['state'] == 'awaiting_approval'
    artifacts = restarted.artifacts(initial['id'])
    assert {a['name'] for a in artifacts} == {'requirements.json', 'questions.md', 'handoff.md'}
    requirements = json.loads(next(a['content'] for a in artifacts if a['name'] == 'requirements.json'))
    assert requirements['brief']['width'] == 800
    assert requirements['rules'] and requirements['input_hash'] == prepared['input_hash']
    paths = restarted.export_artifacts(initial['id'], tmp_path / 'export')
    assert len(paths) == 3
    for artifact in artifacts:
        assert digest((tmp_path / 'export' / artifact['name']).read_bytes()) == artifact['sha256']
    approved = restarted.approve(initial['id'], prepared['artifact_hash'], prepared['input_hash'])
    assert approved['state'] == 'succeeded'
    assert restarted.approve(initial['id'], prepared['artifact_hash'], prepared['input_hash']) == approved


def test_stale_approval_rejected_after_input_edit(system):
    store, _, relay = system
    prepared = relay.create(brief())
    revised = relay.resume(prepared['id'], {'copy': 'A revised approved phrase'})
    assert revised['artifact_hash'] != prepared['artifact_hash']
    with pytest.raises(RelayError, match='Approval rejected'):
        relay.approve(prepared['id'], prepared['artifact_hash'], prepared['input_hash'])
    assert relay.get(prepared['id'])['state'] == 'awaiting_approval'
    assert any(s['error'] == 'stale_approval' for s in store.spans(prepared['id']))


def test_corrupt_artifact_cannot_be_approved(system):
    store, _, relay = system
    prepared = relay.create(brief())
    artifact = relay.artifacts(prepared['id'])[0]
    artifact['content'] += 'tampered'
    store.put('artifacts', artifact['id'], artifact)
    with pytest.raises(RelayError, match='corrupted'):
        relay.approve(prepared['id'], prepared['artifact_hash'], prepared['input_hash'])


def test_source_change_invalidates_approval(system, monkeypatch):
    _, atlas, relay = system
    prepared = relay.create(brief())
    original = atlas.evidence
    monkeypatch.setattr(atlas, 'evidence', lambda scope, eid: original(scope, eid).model_copy(update={'source_hash': 'changed'}))
    with pytest.raises(RelayError, match='Approval rejected'):
        relay.approve(prepared['id'], prepared['artifact_hash'], prepared['input_hash'])


def test_cancel_cannot_resume_as_succeeded(system):
    _, _, relay = system
    run = relay.create({'brand': 'luma'})
    assert relay.cancel(run['id'])['state'] == 'cancelled'
    assert relay.resume(run['id'])['state'] == 'cancelled'
    with pytest.raises(RelayError):
        relay.resume(run['id'], {'copy': 'new'})


def test_duplicate_and_concurrent_resume_no_duplicate_effect(system):
    store, atlas, relay = system
    run = relay.create({'brand': 'luma', 'objective': 'logo banner'})
    answers = {'width': 1200, 'height': 628, 'copy': 'Explore more'}
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: Relay(Store(store.path), atlas).resume(run['id'], answers), range(4)))
    state = relay.get(run['id'])
    assert state['state'] == 'awaiting_approval'
    relay.resume(run['id'])
    effects = [e for e in store.list('relay_effects') if e['run_id'] == run['id']]
    assert len(effects) == 1
    assert len(relay.artifacts(run['id'])) == 3


@pytest.mark.parametrize('payload', [
    'not json', {'name': 'delete_everything', 'arguments': {}, 'idempotency_key': 'x'},
    {'name': 'read_evidence', 'arguments': {'evidence_id': 17}, 'idempotency_key': 'x'},
    {'name': 'read_evidence', 'arguments': {'evidence_id': 'x', 'path': '/etc/passwd'}, 'idempotency_key': 'x'},
])
def test_invalid_tool_proposals_never_execute(system, payload):
    store, _, relay = system
    run = relay.create({'brand': 'luma'})
    before = len(store.list('relay_effects'))
    with pytest.raises(RelayError):
        relay.execute_tool(run['id'], payload)
    assert len(store.list('relay_effects')) == before
    assert any(s['stage'] == 'tool.validation' and not s['outputs']['executed'] for s in store.spans(run['id']))


def test_scope_denied_for_state_artifacts_and_evidence(system):
    _, _, relay = system
    run = relay.create(brief())
    other = Scope(brand='veyra')
    with pytest.raises(RelayError):
        relay.get(run['id'], other)
    with pytest.raises(RelayError):
        relay.artifacts(run['id'], other)
    with pytest.raises(RelayError):
        relay.execute_tool(run['id'], {'name': 'read_evidence', 'arguments': {'evidence_id': 'veyra-v2-palette'}, 'idempotency_key': 'x'})


def test_schema_and_values_are_separate(system):
    _, _, relay = system
    with pytest.raises(ValidationError):
        relay.create(brief(width=-10))
    with pytest.raises(ValidationError):
        relay.create(brief(width='1200'))
    run = relay.create({'brand': 'luma'})
    with pytest.raises(RelayError):
        relay.resume(run['id'], {'brand': 'veyra'})


def test_deadline_and_retry_boundaries(system, monkeypatch):
    store, atlas, relay = system
    run = relay.create({'brand': 'luma'})
    run['deadline_at'] = time.time() - 1
    store.put('relay', run['id'], run)
    assert relay.resume(run['id'])['error']['code'] == 'timeout'
    calls = []
    def unavailable(*args, **kwargs):
        calls.append(1)
        raise TimeoutError('temporary service outage')
    monkeypatch.setattr(atlas, 'search', unavailable)
    failed = relay.create(brief())
    assert failed['state'] == 'failed'
    assert len(calls) == 2
    assert not failed['artifact_ids']


def test_missing_source_does_not_create_artifact(system):
    _, _, relay = system
    run = relay.create(brief(), scope=Scope(snapshot='unknown'))
    assert run['state'] == 'failed'
    assert run['error']['code'] == 'missing_source'
    assert not run['artifact_ids']


def test_live_adapter_uses_typed_proposals_without_paid_calls(system):
    _, _, relay = system
    class FakeProvider:
        usage = {'calls': 1, 'input_tokens': None, 'output_tokens': None, 'cost_usd': None}
        def propose_tools(self, supplied_brief, observations, schemas):
            assert 'draft_handoff' in schemas
            return [{'name': 'draft_handoff', 'arguments': {}, 'idempotency_key': 'fixture-live-adapter-test'}]
    run = relay.run_live(FakeProvider(), brief())
    assert run['state'] == 'awaiting_approval'
    assert run['mode'] == 'live'  # Adapter contract test, not a real provider benchmark.
    assert run['workflow_kind'] == 'model_tool_proposals_with_deterministic_handoff'
    assert run['tool_steps'] == 1


def test_relay_experiment_measured_checks(system):
    store, atlas, _ = system
    report = experiment(store, atlas)
    assert report['status'] == 'PASS'
    assert report['failed'] == 0
    assert report['review_status'] == 'automated_demo_approval'
