from fastapi.testclient import TestClient

from tracecraft.api.app import create_app
from tracecraft.core.store import Store

def client(tmp_path):
    return TestClient(create_app(Store(tmp_path/'api.sqlite')))

def test_origin_host_size_and_server_principal(tmp_path):
    api=client(tmp_path)
    assert api.get('/api/status',headers={'host':'evil.example'}).status_code==403
    assert api.post('/api/atlas',json={'query':'color'},headers={'origin':'https://evil.example'}).status_code==403
    assert api.post('/api/atlas',json={'query':'color','tenant':'other'}).status_code==422
    assert api.post('/api/atlas',content='x'*66000,headers={'content-type':'application/json'}).status_code==413
    assert api.post('/api/atlas',content='query=color').status_code==415

def test_ui_and_actual_atlas_api(tmp_path):
    api=client(tmp_path)
    assert api.get('/').status_code==200
    assert 'TRACECRAFT' in api.get('/').text
    assert api.get('/app.js').status_code==200
    assert api.get('/api/status').json()['private_source']=='MISSING_PRIVATE_SOURCE'
    data=api.post('/api/atlas',json={'query':'LF-MOSS-42'}).json()
    assert data['answer']['status']=='supported'
    assert data['dense']['status']=='MODEL_NOT_PREPARED'

def test_sources_reports_traces_are_scoped(tmp_path):
    api=client(tmp_path)
    assert api.get('/api/evidence/luma-v2-palette?brand=veyra').status_code==404
    assert api.get('/api/evidence/luma-v2-partner?brand=luma').status_code==404
    store=api.app.state.store
    run=store.new_run('atlas','fixture',{'scope':{'tenant':'other','principal':'other','permissions':['private']}})
    assert api.get('/api/runs/'+run['id']).status_code==404
    assert all(r['id']!=run['id'] for r in api.get('/api/runs').json()['runs'])
    assert api.get('/api/reports/unknown').status_code==404

def test_http_restart_resume_and_bound_approval(tmp_path):
    path=tmp_path/'api.sqlite'
    api=TestClient(create_app(Store(path)))
    run=api.post('/api/relay',json={'brief':{'brand':'luma','objective':'digital logo banner'}}).json()
    assert run['state']=='awaiting_input'
    second=TestClient(create_app(Store(path)))
    run=second.post(f'/api/relay/{run["id"]}/resume',json={'answers':{'width':1200,'height':628,'copy':'Explore the collection'}}).json()
    assert run['state']=='awaiting_approval'
    assert second.post(f'/api/relay/{run["id"]}/approve',json={'artifact_hash':'stale','input_hash':run['input_hash']}).status_code==400
    accepted=second.post(f'/api/relay/{run["id"]}/approve',json={'artifact_hash':run['artifact_hash'],'input_hash':run['input_hash']}).json()
    assert accepted['state']=='succeeded'
    assert len(second.get(f'/api/relay/{run["id"]}/artifacts').json()['artifacts'])==3

def test_browser_live_never_triggers_provider(tmp_path):
    api=client(tmp_path)
    assert api.post('/api/atlas',json={'query':'color','mode':'live'}).status_code==400
    assert api.post('/api/experiments/atlas',json={'mode':'live'}).json()['status']=='NOT_RUN'
