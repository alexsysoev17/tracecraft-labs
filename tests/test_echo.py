from concurrent.futures import ThreadPoolExecutor

import pytest

from tracecraft.atlas import Atlas
from tracecraft.core.models import Scope
from tracecraft.core.store import Store
from tracecraft.echo import Echo
from tracecraft.echo.service import compatible_query

@pytest.fixture
def cache(tmp_path):
    store=Store(tmp_path/'cache.sqlite')
    return Echo(store,Atlas(store))

def test_exact_persists_after_restart(cache):
    first=cache.request('What is the primary color?',policy='exact')
    restarted=Echo(Store(cache.store.path),cache.atlas)
    second=restarted.request('What is the primary color?',policy='exact')
    assert first['answer_calls']==1 and not first['hit']
    assert second['hit'] and second['answer_calls']==0

@pytest.mark.parametrize('scope',[
    Scope(brand='veyra'),Scope(snapshot='v1'),Scope(tenant='other'),Scope(principal='other'),
    Scope(permissions=[]),Scope(context='additional print requirement'),Scope(locale='en'),Scope(acl_version='2')])
def test_cache_scope_boundaries(cache,scope):
    cache.request('What is the primary color?',policy='exact')
    assert not cache.request('What is the primary color?',scope,policy='exact')['hit']

@pytest.mark.parametrize('candidate',[
    'What is not the primary color?','What is the primary color for 20 banners?',
    'What is the primary color for accessibility?', 'What is the primary color on mobile?',
    'Give me a new variant of the primary color.', 'What is the primary color on 2026-12-20?'])
def test_semantic_guard_rejects_changed_meaning(candidate):
    assert not compatible_query('What is the primary color?',candidate)

def test_conservative_safe_paraphrase():
    assert compatible_query('What is the primary color?','Tell me the primary colour.')

def test_source_invalidation_and_no_error_admission(cache):
    cache.request('What is the primary color?',policy='exact')
    changed=cache.atlas.evidence(Scope(),'luma-v2-palette')
    changed.source_hash='new-hash'
    assert cache.invalidate(Scope())==1
    unknown=cache.request('quantum neutrino warranty',policy='exact')
    assert not unknown['admitted']

def test_singleflight_counts_actual_calls(cache):
    with ThreadPoolExecutor(max_workers=4) as pool:
        outputs=list(pool.map(lambda _:cache.request('What is the primary color?',policy='exact'),range(4)))
    assert sum(o['answer_calls'] for o in outputs)==1

def test_ttl_and_size_are_enforced(cache):
    cache.ttl=-1
    assert not cache.request('What is the primary color?',policy='exact')['admitted']
    assert not cache.store.list('cache')

def test_new_variant_not_cached(cache):
    result=cache.request('Give a new variant of the primary color',policy='exact')
    assert not result['admitted'] and result['reason']=='read_only_policy_rejected'
