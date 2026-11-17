"""Reproducible entry points. Live is opt-in and absent from default demo/CI."""
import argparse
import json
import os
import sys

from tracecraft.atlas import Atlas
from tracecraft.core.models import Scope
from tracecraft.core.reports import MODULES, privacy_check, run_experiment
from tracecraft.core.store import ROOT, Store

def emit(value):
    print(json.dumps(value,ensure_ascii=False,indent=2))

def main():
    parser=argparse.ArgumentParser(prog='tracecraft')
    parser.add_argument('--db',default=str(ROOT/'runtime/tracecraft.sqlite'))
    sub=parser.add_subparsers(dest='command',required=True)
    serve=sub.add_parser('serve')
    serve.add_argument('--port',type=int,default=8317)
    experiment=sub.add_parser('experiment')
    experiment.add_argument('module',choices=MODULES+('all',))
    experiment.add_argument('--mode',choices=('fixture','local'),default='fixture')
    sub.add_parser('demo')
    sub.add_parser('models')
    sub.add_parser('privacy-check')
    search=sub.add_parser('atlas')
    search.add_argument('query')
    search.add_argument('--brand',choices=('luma','veyra'),default='luma')
    search.add_argument('--method',choices=('lexical','dense','hybrid','full_pack'),default='lexical')
    search.add_argument('--mode',choices=('fixture','local'),default='fixture')
    replay=sub.add_parser('replay')
    replay.add_argument('run_id')
    ingest=sub.add_parser('import-akella')
    ingest.add_argument('--root',default=os.getenv('AKELLA_ROOT'))
    ingest.add_argument('--brand',default='stc')
    document=sub.add_parser('import-document')
    document.add_argument('--root',required=True)
    document.add_argument('relative_path')
    live=sub.add_parser('live')
    live.add_argument('--allow-live',action='store_true')
    live.add_argument('--model')
    live.add_argument('--max-calls',type=int,default=4)
    live.add_argument('--max-seconds',type=int,default=60)
    live.add_argument('--max-output-tokens',type=int,default=600)
    live.add_argument('--query',default='What is the primary color?')
    live.add_argument('--relay',action='store_true')
    args=parser.parse_args()
    if args.command=='privacy-check':
        result=privacy_check()
        emit(result)
        return 0 if result['status']=='PASS' else 1
    if args.command=='models':
        from tracecraft.core.embeddings import prepare_model
        emit(prepare_model())
        return 0
    if args.command=='import-akella':
        from tracecraft.core.ingest import import_akella
        if not args.root:
            emit({'status':'MISSING_PRIVATE_SOURCE','reason':'Pass --root or AKELLA_ROOT explicitly'})
            return 0
        report=import_akella(args.root,args.brand)
        # Keep private source paths out of terminal/public delivery summaries.
        emit({k:v for k,v in report.items() if k not in ('source_root','destination','source_hashes_before','source_hashes_after')})
        return 0
    if args.command=='import-document':
        from tracecraft.core.ingest import import_document
        emit(import_document(args.root,args.relative_path))
        return 0
    store=Store(args.db)
    atlas=Atlas(store)
    if args.command=='serve':
        import fcntl
        import uvicorn
        from tracecraft.api.app import create_app
        # Exactly one server owner per DB. CLI experiments should use a separate --db while server runs.
        lock=store.path.with_suffix('.server.lock').open('w')
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('A server already owns this runtime database')
        print(f'TRACECRAFT LABS: http://127.0.0.1:{args.port}',flush=True)
        uvicorn.run(create_app(store),host='127.0.0.1',port=args.port,log_level='warning')
        return 0
    if args.command in ('experiment','demo'):
        modules=MODULES if args.command=='demo' or args.module=='all' else (args.module,)
        mode=getattr(args,'mode','fixture')
        results={}
        for module in modules:
            result=run_experiment(module,store,atlas,mode)
            results[module]={'report':f'reports/public/{module}-{mode}.json','status':result.get('status','measured'),
                             'mode':mode,'data_origin':'synthetic'}
        emit(results)
        return 0
    if args.command=='atlas':
        emit(atlas.answer(args.query,Scope(brand=args.brand),method=args.method,mode=args.mode).model_dump())
    elif args.command=='replay':
        from tracecraft.lens import Lens
        emit(Lens(store,atlas).replay(args.run_id))
    elif args.command=='live':
        from tracecraft.core.providers import LiveProvider
        provider=LiveProvider(allow=args.allow_live,model=args.model,max_calls=args.max_calls,
                              max_seconds=args.max_seconds,max_output_tokens=args.max_output_tokens)
        if args.relay:
            from tracecraft.relay import Relay
            result=Relay(store,atlas).run_live(provider,{'brand':'luma','objective':'A digital brand banner',
                       'width':1200,'height':628,'copy':'Explore the collection'})
        else:
            result=provider.answer(atlas,args.query,Scope()).model_dump()
        # Live output is private unless separately reviewed; never goes to reports/public.
        target=ROOT/'private/live'
        target.mkdir(parents=True,exist_ok=True)
        (target/'last-run.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        emit({'status':result.get('state','completed'),'mode':'live','usage':provider.usage,'report':'private/live/last-run.json'})
        if result.get('state')=='failed':
            return 2
    return 0

if __name__=='__main__':
    try:
        sys.exit(main())
    except (ValueError,PermissionError,TimeoutError) as error:
        emit({'status':'BLOCKED','error':str(error)})
        sys.exit(2)
