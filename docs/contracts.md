# Frozen module contracts v1

All Pydantic types live in `tracecraft.core.models`; no module changes them without the integrator. Store is `Store(path)` with `get(namespace,key,default=None)`, `put(namespace,key,value)`, `list(namespace)`, `delete(namespace,key)`, and `transaction()` yielding sqlite connection (records table: namespace, key, value JSON, updated REAL). Values stored must be JSON compatible. `Store.trace(run_id,stage,inputs,outputs,status='ok',error=None,parent_id=None)` persists a TraceSpan and returns its dict. `Store.spans(run_id)` returns ordered spans. `Store.new_run(module,mode,config)` returns/persists a manifest dict. `Store.finish_run(run_id,status,**fields)` updates it. `Store.path` is a Path.

`Atlas(store).search(query: str, scope: Scope, method='lexical', mode='fixture', k=5) -> RetrievalResult`; `.answer(query,scope,method='lexical',mode='fixture',fault=None) -> Answer`; `.evidence(scope,id)->EvidenceChunk|None`; `.eligible(scope)->list[EvidenceChunk]`. It reads only `datasets/public-demo/corpus.json` by default. Evidence file is a list of EvidenceChunk JSON. Method full_pack is also supported. Fault `omit_evidence` is isolated diagnostic demo only. Fixture dense is explicitly unavailable; never present lexical as dense. Controlled encoder test doubles are not reported as real semantic measurements.

`Scope`: tenant='demo', project='public-lab', brand='luma', snapshot='v2', principal='demo-reader', permissions=['public'], locale='ru', context='', acl_version='1'. Browser cannot choose tenant/principal/permissions: API constructs scope. All local demo brands: **luma** (Luma Field) and **veyra** (Veyra Works). Both are original fictional brands.

`EvidenceChunk`: id, document_id, brand, snapshot, title, text, section, source_hash, data_origin='synthetic', tenant='demo', permissions=['public'], status='reviewed', authority='explicit', polarity='neutral', kind='rule', mandatory=False, topic='', rule_key='', value='', links=[], tags=[], start=0,end=0. Chunks with the same rule_key and distinct values are a conflict; unreviewed/observed material is never authoritative. Gold stays in `datasets/public-demo/cases.json`, never in corpus/index.

`Answer`: status, text, evidence_ids, claims[{text,evidence_id,quote}], retrieval, mode, data_origin, measurement_status, review_status, generation_kind, latency_ms, usage{calls,input_tokens,output_tokens,cost_usd}, run_id. `.model_dump()` at external boundaries. Extractive responses label themselves accordingly.

Module services should export their scenario runner `experiment(store, atlas, mode='fixture') -> dict` (CANON/SENTINEL may have additional functions). Integrator owns CLI/HTTP routes and report writing. Suggested owners: RELAY + LENS; CANON dataset + SENTINEL/evaluator; web UI. Root handles ATLAS + ECHO + importer + integration.

## HTTP interface (all JSON)

GET /api/status, /api/corpus?brand=luma, /api/evidence/{id}?brand=luma, /api/runs, /api/runs/{id}, /api/reports/{module}, /api/cases.
POST /api/atlas {query,brand,snapshot,mode}; returns {lexical,dense,hybrid,answer,...}.
POST /api/relay {brief:{brand,objective,width,height,copy},mode}; GET /api/relay/{id}; POST /api/relay/{id}/resume {answers}; POST /api/relay/{id}/approve {artifact_hash,input_hash}; POST /api/relay/{id}/cancel {}; GET /api/relay/{id}/artifacts.
POST /api/sentinel {candidate:'broken'|'normal',mode}; POST /api/lens {run_id} (or {fault:'invalid_args'|'timeout'|'omit_evidence'}); POST /api/lens/{run_id}/draft {}.
POST /api/echo {query,brand,snapshot,policy:'off'|'exact'|'semantic',mode}; POST /api/echo/experiment {mode}.
POST /api/canon {mode,method:'lexical'|'full_pack'|'dense'|'hybrid'}.
POST /api/experiments/{module} {mode}; POST /api/demo {}. API reports blocked modes instead of fabricating results. Live network is never triggered from browser.
