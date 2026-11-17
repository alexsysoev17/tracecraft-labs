import httpx
import pytest

from tracecraft.core.providers import LiveProvider
from tracecraft.core.reports import audit_public

def test_live_is_opt_in_and_never_reads_other_credentials(monkeypatch):
    with pytest.raises(PermissionError):
        LiveProvider()
    monkeypatch.delenv('TRACECRAFT_LIVE_API_KEY',raising=False)
    with pytest.raises(ValueError):
        LiveProvider(allow=True,model='explicit-model')

def test_live_budget_and_unknown_usage(monkeypatch):
    monkeypatch.setenv('TRACECRAFT_LIVE_API_KEY','test-only')
    transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]}))
    provider=LiveProvider(allow=True,model='test-model',max_calls=1,transport=transport)
    provider._request([{'role':'user','content':'test'}])
    assert provider.usage=={'calls':1,'input_tokens':None,'output_tokens':None,'cost_usd':None}
    with pytest.raises(TimeoutError):
        provider._request([])

def test_failed_attempt_is_counted_without_fake_cost(monkeypatch):
    monkeypatch.setenv('TRACECRAFT_LIVE_API_KEY','test-only')
    provider=LiveProvider(allow=True,model='test-model',transport=httpx.MockTransport(lambda request:httpx.Response(429,text='secret body')))
    with pytest.raises(RuntimeError,match='withheld'):
        provider._request([])
    assert provider.usage['calls']==1 and provider.usage['cost_usd'] is None

@pytest.mark.parametrize('payload',[{'text':'PRIVATE_CANARY client rule'}, {'data_origin':'private'}, {'authorization':'value'}, {'text':'/Users/example/private.txt'}])
def test_public_export_rejects_private_material(payload):
    with pytest.raises(ValueError):
        audit_public(payload)
