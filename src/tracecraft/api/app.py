import json
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from tracecraft.atlas import Atlas
from tracecraft.canon import load_cases, run_benchmark
from tracecraft.core.models import Scope
from tracecraft.core.reports import MODULES, run_experiment
from tracecraft.core.store import ROOT, Store
from tracecraft.echo import Echo
from tracecraft.lens import Lens
from tracecraft.relay import Relay
from tracecraft.sentinel import compare

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Query(Input):
    query: str = Field(min_length=1,max_length=2000)
    brand: Literal['luma','veyra'] = 'luma'
    snapshot: Literal['v1','v2'] = 'v2'
    mode: Literal['fixture','local','live','replay'] = 'fixture'
    policy: Literal['off','exact','semantic'] = 'semantic'

class Options(Input):
    mode: Literal['fixture','local','live','replay'] = 'fixture'
    method: Literal['lexical','dense','hybrid','full_pack'] = 'lexical'
    candidate: Literal['broken','normal'] = 'broken'

class BriefInput(Input):
    brief: dict
    mode: Literal['fixture','local'] = 'fixture'

class ResumeInput(Input):
    answers: dict = Field(default_factory=dict)

class ApprovalInput(Input):
    artifact_hash: str
    input_hash: str

class LensInput(Input):
    run_id: str | None = None
    fault: Literal['invalid_args','timeout','omit_evidence','wrong_snapshot','repeat_event'] | None = None
    mode: Literal['fixture','local'] = 'fixture'

def scope_for(brand='luma',snapshot='v2'):
    return Scope(brand=brand,snapshot=snapshot)

def create_app(store=None):
    app = FastAPI(title='TRACECRAFT LABS',version='0.1.0',docs_url=None,redoc_url=None)
    store = store or Store()
    atlas = Atlas(store)
    relay, lens, echo = Relay(store,atlas), Lens(store,atlas), Echo(store,atlas)
    app.state.store, app.state.atlas = store,atlas

    @app.middleware('http')
    async def local_boundary(request: Request, call_next):
        host = request.headers.get('host','').split(':')[0]
        if host not in ('127.0.0.1','localhost','testserver'):
            return JSONResponse({'error':'Loopback host required'},status_code=403)
        origin = request.headers.get('origin')
        if origin and origin not in (f'http://{request.headers.get("host")}',f'https://{request.headers.get("host")}'):
            return JSONResponse({'error':'Origin rejected'},status_code=403)
        if request.method in ('POST','PUT','PATCH'):
            if request.headers.get('content-type','').split(';')[0] != 'application/json':
                return JSONResponse({'error':'JSON required'},status_code=415)
            try:
                size = int(request.headers.get('content-length','0'))
            except ValueError:
                return JSONResponse({'error':'Invalid content length'},status_code=400)
            if size > 65536:
                return JSONResponse({'error':'Request too large'},status_code=413)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>65536:
                    return JSONResponse({'error':'Request too large'},status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.exception_handler(ValueError)
    async def value_error(request,error):
        return JSONResponse({'error':str(error),'code':getattr(error,'code','invalid_request')},status_code=400)

    @app.exception_handler(KeyError)
    async def key_error(request,error):
        return JSONResponse({'error':'Record not found'},status_code=404)

    def check_mode(mode):
        if mode in ('live','replay'):
            raise ValueError('Live requires opt-in CLI; replay uses a saved run/report without new computation.')

    def visible_run(id):
        run=store.get('runs',id)
        if not run:
            raise KeyError(id)
        saved = run.get('config',{}).get('scope')
        if saved and (saved.get('tenant')!='demo' or saved.get('principal')!='demo-reader' or saved.get('permissions')!=['public']):
            raise HTTPException(404,'Run not accessible')
        if run.get('data_origin') != 'synthetic':
            raise HTTPException(404,'Run not accessible')
        return run

    @app.get('/api/status')
    def status():
        return {'status':'ready','version':'0.1.0','modules':list(MODULES),'embedding':atlas.encoder.status(),
                'private_source':'MISSING_PRIVATE_SOURCE','data_origin':'synthetic','authentication':'local demo principal; not SaaS authentication',
                'modes':{'fixture':'Deterministic extractive workflow; real BM25, no LLM',
                         'local':'Real CPU embeddings and extractive evidence','live':'Explicit CLI only; not run automatically',
                         'replay':'Recorded outputs, no new model computation'},
                'brands':[{'id':'luma','name':'Luma Field'},{'id':'veyra','name':'Veyra Works'}]}

    @app.get('/api/corpus')
    def corpus(brand: Literal['luma','veyra']='luma',snapshot: Literal['v1','v2']='v2'):
        return {'chunks':[c.model_dump() for c in atlas.eligible(scope_for(brand,snapshot))], 'corpus_hash':atlas.corpus_hash}

    @app.get('/api/evidence/{id}')
    def evidence(id: str,brand: Literal['luma','veyra']='luma',snapshot: Literal['v1','v2']='v2'):
        item=atlas.evidence(scope_for(brand,snapshot),id)
        if not item:
            raise HTTPException(404,'Evidence not accessible')
        return item.model_dump()

    @app.get('/api/runs')
    def runs():
        result=[]
        for run in store.list('runs')[-250:]:
            try:
                result.append(visible_run(run['id']))
            except HTTPException:
                pass
        return {'runs':list(reversed(result))}

    @app.get('/api/runs/{id}')
    def run(id:str):
        manifest=visible_run(id)
        return {'manifest':manifest,'spans':store.spans(id),'answer':store.get('answers',id),'mode':'replay'}

    @app.get('/api/reports/{module}')
    def report(module:str,mode:str|None=None):
        if module not in MODULES or mode not in (None,'fixture','local'):
            raise HTTPException(404,'Unknown report')
        path=ROOT/'reports/public'/f'{module}{"-"+mode if mode else ""}.json'
        return json.loads(path.read_text()) if path.exists() else {'module':module,'status':'NOT_RUN','measurement_status':'not_run'}

    @app.get('/api/cases')
    def cases():
        return {'cases':[c.model_dump() for c in load_cases()],'data_origin':'synthetic','review_status':'machine_authored_source_checked'}

    @app.post('/api/atlas')
    def search(body: Query):
        check_mode(body.mode)
        scope=scope_for(body.brand,body.snapshot)
        results={m:atlas.search(body.query,scope,method=m,mode=body.mode).model_dump() for m in ('lexical','dense','hybrid')}
        answer=atlas.answer(body.query,scope,method='hybrid' if body.mode=='local' and results['hybrid']['status']=='ready' else 'lexical',mode=body.mode)
        return {**results,'answer':answer.model_dump(),'data_origin':'synthetic','mode':body.mode}

    @app.post('/api/relay')
    def start_relay(body:BriefInput):
        return relay.create(body.brief,mode=body.mode)

    @app.get('/api/relay/{id}')
    def get_relay(id:str):
        return relay.get(id)

    @app.post('/api/relay/{id}/resume')
    def resume(id:str,body:ResumeInput):
        return relay.resume(id,answers=body.answers)

    @app.post('/api/relay/{id}/approve')
    def approve(id:str,body:ApprovalInput):
        return relay.approve(id,body.artifact_hash,body.input_hash)

    @app.post('/api/relay/{id}/cancel')
    def cancel(id:str,body:Input):
        return relay.cancel(id)

    @app.get('/api/relay/{id}/artifacts')
    def artifacts(id:str):
        return {'artifacts':relay.artifacts(id)}

    @app.post('/api/sentinel')
    def sentinel(body:Options):
        check_mode(body.mode)
        return compare(store,atlas,candidate=body.candidate,mode=body.mode)

    @app.post('/api/lens')
    def diagnose(body:LensInput):
        if body.run_id:
            visible_run(body.run_id)
            return lens.diagnose(body.run_id)
        return lens.inject(body.fault or 'invalid_args',mode=body.mode)

    @app.post('/api/lens/{id}/draft')
    def draft(id:str,body:Input):
        visible_run(id)
        return lens.draft(id)

    @app.post('/api/echo')
    def cache(body:Query):
        check_mode(body.mode)
        if body.mode=='local' and body.policy=='semantic' and atlas.encoder.status()['status']=='ready' and not store.get('cache_config',echo.calibration_key()):
            echo.calibrate()
        return echo.request(body.query,scope_for(body.brand,body.snapshot),policy=body.policy,mode=body.mode)

    @app.post('/api/echo/experiment')
    def cache_experiment(body:Options):
        return run_experiment('echo',store,atlas,body.mode)

    @app.post('/api/canon')
    def canon(body:Options):
        check_mode(body.mode)
        return run_benchmark(store,atlas,mode=body.mode,method=body.method)

    @app.post('/api/experiments/{module}')
    def experiment(module:str,body:Options):
        return run_experiment(module,store,atlas,body.mode)

    @app.post('/api/demo')
    def demo(body:Input):
        return {module:run_experiment(module,store,atlas) for module in MODULES}

    @app.get('/')
    def index():
        return FileResponse(ROOT/'web/index.html')

    app.mount('/',StaticFiles(directory=ROOT/'web'),name='web')
    return app
