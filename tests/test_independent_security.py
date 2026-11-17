"""Independent adversarial checks, using temporary synthetic state only.

These regressions exercise externally observable boundaries and deterministic
concurrency interleavings; no external provider or private source is accessed.
"""

import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient

from tracecraft.api.app import create_app
from tracecraft.atlas import Atlas
from tracecraft.core import reports
from tracecraft.core.models import Scope
from tracecraft.core.store import ROOT, Store
from tracecraft.echo import Echo
from tracecraft.relay import Relay, RelayError


@pytest.fixture
def independent_system(tmp_path):
    store = Store(tmp_path / 'independent.sqlite')
    atlas = Atlas(store)
    return store, atlas, Relay(store, atlas), Echo(store, atlas)


def complete_brief(copy='Explore more'):
    return {'brand': 'luma', 'objective': 'logo banner', 'width': 1200,
            'height': 628, 'copy': copy}


def test_cache_revalidates_access_to_returned_uncited_context(independent_system):
    """Revoking a contextual source must remove it from the complete response."""
    _, atlas, _, echo = independent_system
    first = echo.request('What is the primary color?', policy='exact')
    assert first['admitted']
    answer = first['answer']
    contextual = next(c for c in answer['retrieval']['context']
                      if c['id'] not in answer['evidence_ids'])
    atlas.chunks = [c.model_copy(update={'permissions': ['partner']})
                    if c.id == contextual['id'] else c for c in atlas.chunks]
    assert atlas.evidence(Scope(), contextual['id']) is None

    second = echo.request('What is the primary color?', policy='exact')
    assert contextual['text'] not in json.dumps(second, ensure_ascii=False), (
        'The cache returned a now-restricted source in its uncited retrieval payload.'
    )


def test_cache_rejects_claim_outside_declared_dependencies(independent_system):
    """Every emitted claim must belong to the dependency and citation closure."""
    store, atlas, _, echo = independent_system
    assert echo.request('What is the primary color?', policy='exact')['admitted']
    entry = store.list('cache')[0]
    source = atlas.evidence(Scope(), 'luma-v2-clearspace')
    assert source.id not in entry['dependencies']
    entry['answer']['claims'].append({'text': source.text, 'quote': source.text,
                                      'evidence_id': source.id})
    entry['answer']['text'] = '\n\n'.join(c['text'] for c in entry['answer']['claims'])
    store.put('cache', entry['id'], entry)

    result = echo.request('What is the primary color?', policy='exact')
    assert not result['hit'], 'A source-backed claim without a declared dependency was accepted.'
    assert source.text not in result['answer']['text']


def test_cache_invalidation_preserves_other_authorized_namespaces(independent_system):
    """Invalidating one scope must not evict fresh entries for another scope."""
    store, _, _, echo = independent_system
    assert echo.request('What is the primary color?', Scope(brand='luma'), policy='exact')['admitted']
    assert echo.request('What is the primary color?', Scope(brand='veyra'), policy='exact')['admitted']
    before = {e['id'] for e in store.list('cache')}
    assert len(before) == 2

    echo.invalidate(Scope(brand='luma'))
    assert {e['id'] for e in store.list('cache')} == before, (
        'Valid entries in another brand namespace were removed by scope-local invalidation.'
    )


def test_conflicting_resume_during_active_work_is_not_silently_discarded(independent_system, monkeypatch):
    """An accepted edit must persist, or the caller must receive an explicit conflict."""
    _, atlas, relay, _ = independent_system
    run = relay.create({'brand': 'luma', 'objective': 'logo banner'})
    entered, release = Event(), Event()
    search = atlas.search

    def blocked_search(*args, **kwargs):
        entered.set()
        assert release.wait(5), 'test worker was not released'
        return search(*args, **kwargs)

    monkeypatch.setattr(atlas, 'search', blocked_search)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(relay.resume, run['id'], {'width': 1200, 'height': 628, 'copy': 'First text'})
        assert entered.wait(5), 'first resume never reached its read-only work'
        conflict = None
        try:
            relay.resume(run['id'], {'copy': 'Second text'})
        except RelayError as error:
            conflict = error
        finally:
            release.set()
        first.result(timeout=5)

    assert conflict is not None or relay.get(run['id'])['brief']['copy'] == 'Second text', (
        'Concurrent resume returned successfully while silently dropping its changed copy.'
    )


def test_live_provider_failure_preserves_concurrent_cancellation(independent_system):
    """A delayed provider failure cannot replace a committed terminal cancellation."""
    store, _, relay, _ = independent_system
    entered, release = Event(), Event()

    class DelayedFailingProvider:
        usage = {'calls': 1, 'input_tokens': None, 'output_tokens': None, 'cost_usd': None}

        def propose_tools(self, brief, observations, schemas):
            entered.set()
            assert release.wait(5), 'test provider was not released'
            raise TimeoutError('synthetic delayed provider failure')

    with ThreadPoolExecutor(max_workers=1) as pool:
        execution = pool.submit(relay.run_live, DelayedFailingProvider(), complete_brief())
        assert entered.wait(5), 'provider did not start'
        state = store.list('relay')[0]
        try:
            cancelled = relay.cancel(state['id'])
            assert cancelled['state'] == 'cancelled'
        finally:
            release.set()
        result = execution.result(timeout=5)

    assert result['state'] == 'cancelled', 'Provider failure resurrected a cancelled run as failed.'
    assert relay.get(state['id'])['state'] == 'cancelled'
    assert store.get('runs', state['id'])['status'] == 'cancelled'


def test_live_usage_persistence_cannot_restore_cancelled_checkpoint(independent_system, monkeypatch):
    """Usage bookkeeping must preserve a cancellation committed after tool return."""
    store, _, relay, _ = independent_system
    persist_usage = relay._live_usage

    class DraftProvider:
        usage = {'calls': 1, 'input_tokens': None, 'output_tokens': None, 'cost_usd': None}

        def propose_tools(self, brief, observations, schemas):
            return [{'name': 'draft_handoff', 'arguments': {}, 'idempotency_key': 'independent-draft'}]

    def cancel_before_usage(state, provider, steps):
        assert state['state'] == 'awaiting_approval'
        relay.cancel(state['id'])
        return persist_usage(state, provider, steps)

    monkeypatch.setattr(relay, '_live_usage', cancel_before_usage)
    result = relay.run_live(DraftProvider(), complete_brief())
    assert result['state'] == 'cancelled', 'Usage persistence restored a stale awaiting-approval checkpoint.'
    assert relay.get(result['id'])['state'] == 'cancelled'
    assert store.get('runs', result['id'])['status'] == 'cancelled'


def test_cancellation_during_fixture_search_prevents_artifact_commit(independent_system, monkeypatch):
    """Positive control: the fixture workflow must fence a stale worker's effects."""
    store, atlas, relay, _ = independent_system
    run = relay.create({'brand': 'luma', 'objective': 'logo banner'})
    search = atlas.search

    def cancel_then_search(*args, **kwargs):
        relay.cancel(run['id'])
        return search(*args, **kwargs)

    monkeypatch.setattr(atlas, 'search', cancel_then_search)
    result = relay.resume(run['id'], {'width': 1200, 'height': 628, 'copy': 'Explore more'})
    assert result['state'] == 'cancelled'
    assert not relay.artifacts(run['id'])
    assert not store.list('relay_effects')


def test_api_denies_all_relay_operations_for_other_principal(independent_system):
    """Positive control: knowing a run ID does not authorize state or artifacts."""
    store, _, relay, _ = independent_system
    state = relay.create(complete_brief(), scope=Scope(principal='other-reader'))
    with TestClient(create_app(store)) as client:
        responses = [client.get(f'/api/relay/{state["id"]}'),
                     client.get(f'/api/relay/{state["id"]}/artifacts'),
                     client.post(f'/api/relay/{state["id"]}/resume', json={'answers': {}}),
                     client.post(f'/api/relay/{state["id"]}/cancel', json={}),
                     client.post(f'/api/relay/{state["id"]}/approve',
                                 json={'artifact_hash': state['artifact_hash'],
                                       'input_hash': state['input_hash']})]
    assert all(response.status_code in {400, 403, 404} for response in responses)
    assert relay.get(state['id'], Scope(principal='other-reader'))['state'] == 'awaiting_approval'


@pytest.mark.parametrize('kind', ['file', 'directory', 'root_file'])
def test_public_export_does_not_follow_links_into_excluded_trees(tmp_path, monkeypatch, kind):
    """The allowlist must apply to resolved sources, not just lexical path names."""
    project = tmp_path / 'synthetic-project'
    project.mkdir()
    (project / 'private').mkdir()
    (project / 'src').mkdir()
    marker = 'synthetic excluded source: orchard sample 8921'
    (project / 'private' / 'source.txt').write_text(marker)
    if kind == 'file':
        (project / 'src' / 'linked.txt').symlink_to(project / 'private' / 'source.txt')
    elif kind == 'directory':
        (project / 'src' / 'linked-dir').symlink_to(project / 'private', target_is_directory=True)
    else:
        (project / 'README.md').symlink_to(project / 'private' / 'source.txt')
    spec = importlib.util.spec_from_file_location('independent_export_public', ROOT / 'scripts/export_public.py')
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    monkeypatch.setattr(exporter, 'ROOT', project)
    monkeypatch.setattr(reports, 'ROOT', project)
    destination = tmp_path / 'review-copy'

    try:
        exporter.export(destination)
    except ValueError:
        pass
    copied = [p for p in destination.rglob('*') if p.is_file()]
    assert not any(marker in p.read_text(errors='replace') for p in copied), (
        'The public review copy contains a file whose resolved source is under excluded private/.'
    )


def test_public_export_rejects_link_in_allowlisted_parent(tmp_path, monkeypatch):
    """A selected nested path must not hide a symlink in an ancestor component."""
    project = tmp_path / 'synthetic-project'
    project.mkdir()
    excluded = project / 'private' / 'public-demo'
    excluded.mkdir(parents=True)
    marker = 'synthetic excluded source: orchard sample 8921'
    (excluded / 'sample.txt').write_text(marker)
    (project / 'datasets').symlink_to(project / 'private', target_is_directory=True)
    # The selected source itself is not a symlink; only its parent is.
    assert not (project / 'datasets' / 'public-demo').is_symlink()
    spec = importlib.util.spec_from_file_location('independent_export_parent', ROOT / 'scripts/export_public.py')
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    monkeypatch.setattr(exporter, 'ROOT', project)
    monkeypatch.setattr(reports, 'ROOT', project)
    destination = tmp_path / 'review-copy'

    assert reports.privacy_check()['status'] == 'FAIL'
    with pytest.raises(ValueError):
        exporter.export(destination)
    assert not destination.exists(), 'Rejected source paths must not create a review copy.'
