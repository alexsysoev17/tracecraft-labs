"""Independent negative review: cache identity, complete provenance and API scope."""
from fastapi.testclient import TestClient

from tracecraft.api.app import create_app
from tracecraft.atlas import Atlas
from tracecraft.core.models import Scope
from tracecraft.core.store import Store
from tracecraft.echo import Echo


def cache_context(tmp_path):
    store=Store(tmp_path/'review.sqlite')
    atlas=Atlas(store)
    return store,atlas,Echo(store,atlas)


def test_exact_cache_does_not_erase_numeric_meaning(tmp_path):
    _,_,echo=cache_context(tmp_path)
    first=echo.request('What is the primary color for 1.5 banners?',policy='exact')
    assert first['admitted'] is True
    changed=echo.request('What is the primary color for 1 5 banners?',policy='exact')
    assert changed['hit'] is False,'Exact matching must not conflate a decimal with two integers.'


def test_explicit_mutation_request_is_never_cached(tmp_path):
    _,_,echo=cache_context(tmp_path)
    query='Delete the primary color rule.'
    first=echo.request(query,policy='exact')
    second=echo.request(query,policy='exact')
    assert first['admitted'] is False
    assert second['hit'] is False
    assert first['reason']=='read_only_policy_rejected'


def test_cached_answer_rejects_extra_uncited_assertions(tmp_path):
    store,_,echo=cache_context(tmp_path)
    echo.request('What is the primary color?',policy='exact')
    entry=store.list('cache')[0]
    entry['answer']['text']+=' The product cures disease.'
    store.put('cache',entry['id'],entry)
    result=echo.request('What is the primary color?',policy='exact')
    assert result['hit'] is False,'Valid quotes do not authorize extra unsupported rendered text.'
    assert 'The product cures disease.' not in result['answer']['text']


def test_cached_supported_answer_without_claims_is_not_reused(tmp_path):
    store,_,echo=cache_context(tmp_path)
    echo.request('What is the primary color?',policy='exact')
    entry=store.list('cache')[0]
    entry['answer']['claims']=[]
    entry['answer']['text']='Everything is approved.'
    store.put('cache',entry['id'],entry)
    assert echo.request('What is the primary color?',policy='exact')['hit'] is False


def test_cache_rechecks_source_hash_at_hit(tmp_path):
    _,atlas,echo=cache_context(tmp_path)
    first=echo.request('What is the primary color?',policy='exact')
    assert first['admitted']
    evidence_id=first['answer']['evidence_ids'][0]
    atlas.chunks=[chunk.model_copy(update={'source_hash':'changed'}) if chunk.id==evidence_id else chunk
                  for chunk in atlas.chunks]
    assert echo.request('What is the primary color?',policy='exact')['hit'] is False


def test_cache_access_revocation_and_tenant_isolation(tmp_path):
    _,atlas,echo=cache_context(tmp_path)
    assert echo.request('What is the primary color?',policy='exact')['admitted']
    revoked=Scope(permissions=[],acl_version='2')
    result=echo.request('What is the primary color?',scope=revoked,policy='exact')
    assert result['hit'] is False
    assert result['answer']['evidence_ids']==[]
    other=Scope(tenant='another-tenant')
    assert atlas.search('DEMO-EMBER-73',other).hits==[]
    assert echo.request('What is the primary color?',scope=other,policy='exact')['hit'] is False


def test_api_rejects_unknown_scope_fields_and_denies_preview(tmp_path):
    app=create_app(Store(tmp_path/'api.sqlite'))
    with TestClient(app) as client:
        for field,value in [('tenant','another'),('principal','administrator'),('permissions',['partner'])]:
            response=client.post('/api/echo',json={'query':'What is the primary color?',field:value})
            assert response.status_code==422
        response=client.get('/api/evidence/luma-v2-restricted')
        assert response.status_code==404
        assert 'DEMO-EMBER-73' not in response.text
        assert client.post('/api/atlas',json={'query':'palette'},headers={'Origin':'https://attacker.invalid'}).status_code==403
