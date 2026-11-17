"""Export only explicit synthetic experiment results; runtime is never copied wholesale."""
import importlib
import json
import re
from pathlib import Path

from .store import ROOT, canonical, digest, utcnow

MODULES = ('atlas','relay','sentinel','lens','echo','canon')
PRIVATE_MARKERS = ('PRIVATE_CANARY', 'TRACECRAFT_PRIVATE', '/Users/', 'BEGIN PRIVATE KEY', 'AKIA')

def audit_public(value):
    encoded = canonical(value)
    if any(marker in encoded for marker in PRIVATE_MARKERS) or re.search(r'\bsk-[A-Za-z0-9_-]{16,}', encoded):
        raise ValueError('Public export rejected: private/secret canary or local source path')
    def walk(item):
        if isinstance(item, dict):
            if item.get('data_origin') in ('private','user','external'):
                raise ValueError('Public export rejected: unapproved data origin')
            if 'permissions' in item and item['permissions'] != ['public']:
                # Access-revocation experiment can describe its empty scope, never restricted evidence.
                if item['permissions'] or 'text' in item:
                    raise ValueError('Public export rejected: restricted source')
            for key, child in item.items():
                if key.casefold() in ('api_key','authorization','password','cookies','source_root'):
                    raise ValueError('Public export rejected: sensitive field')
                walk(child)
        elif isinstance(item,list):
            for child in item:
                walk(child)
    walk(value)
    return {'status':'PASS','bytes':len(encoded.encode()),'sha256':digest(value),
            'limitations':'Allowlisted synthetic experiments and heuristic secret scan; not a universal private-data classifier.'}

def run_experiment(module, store, atlas, mode='fixture', export=True):
    if module not in MODULES:
        raise ValueError('Unknown module')
    if mode not in ('fixture','local'):
        return {'module':module,'mode':mode,'status':'NOT_RUN','measurement_status':'not_run',
                'reason':'Live requires explicit CLI budget; replay reads saved reports.'}
    implementation = importlib.import_module('tracecraft.'+module)
    manifest = store.new_run(module+'-experiment',mode,{'corpus_hash':atlas.corpus_hash,'protocol':'public-demo/1'})
    report = implementation.experiment(store,atlas,mode=mode)
    report['experiment_manifest'] = store.finish_run(manifest['id'],'completed')
    report['provenance'] = {'data_origin':'synthetic','corpus_hash':atlas.corpus_hash,'created_at':utcnow(),
                            'source':'independently_authored_public_demo','code':'tracecraft-labs/0.1.0'}
    audit = audit_public(report)
    if export:
        directory = ROOT/'reports/public'
        directory.mkdir(parents=True,exist_ok=True)
        if module=='relay' and report.get('status')=='PASS':
            from tracecraft.relay import Relay
            artifact_dir=directory/f'relay-{mode}-artifacts'
            Relay(store,atlas).export_artifacts(report['run_id'],artifact_dir)
            report['exported_artifacts']=[str(p.relative_to(ROOT)) for p in artifact_dir.iterdir() if p.is_file()]
        if module=='lens' and report.get('status')=='PASS':
            from tracecraft.lens import Lens
            (directory/f'lens-{mode}.html').write_text(Lens(store,atlas).report_html(report['run_id']))
        audit = audit_public(report)
        (directory/f'{module}-{mode}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        (directory/f'{module}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        update_manifest(module,mode,audit)
    return report

def update_manifest(module,mode,audit):
    path = ROOT/'RUNS_MANIFEST.json'
    data = json.loads(path.read_text()) if path.exists() else {'schema_version':'tracecraft.delivery/1','runs':{}}
    data['runs'][f'{module}-{mode}'] = {'report':f'reports/public/{module}-{mode}.json','mode':mode,
                                     'data_origin':'synthetic','measurement_status':'measured','audit':audit}
    data['updated_at'] = utcnow()
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False))

def privacy_check():
    roots = ['src','web','docs','datasets/public-demo','reports/public','tests','examples','configs','scripts','.github']
    findings = []
    scanned = 0
    for name in roots:
        parts=Path(name).parts
        if any(ROOT.joinpath(*parts[:i]).is_symlink() for i in range(1,len(parts)+1)):
            findings.append(name+': symlink is not publishable')
            continue
        for file in (ROOT/name).rglob('*'):
            if file.is_symlink():
                findings.append(str(file.relative_to(ROOT))+': symlink is not publishable')
                continue
            if not file.is_file() or '__pycache__' in file.parts or file.suffix in ('.png','.jpg'):
                continue
            scanned += 1
            text = file.read_text(errors='replace')
            # Tests deliberately contain rejection canaries. Inspect publishable source for real patterns only.
            if re.search(r'\bsk-[A-Za-z0-9_-]{20,}',text) or re.search(r'AKIA[A-Z0-9]{16}',text):
                findings.append(str(file.relative_to(ROOT)))
            if file.is_relative_to(ROOT/'reports/public'):
                try:
                    if file.suffix == '.json':
                        audit_public(json.loads(text))
                except ValueError as error:
                    findings.append(f'{file.relative_to(ROOT)}: {error}')
    for file in ROOT.iterdir():
        if file.is_symlink() and file.suffix in ('.md','.json','.toml','.txt','.lock'):
            findings.append(file.name+': symlink is not publishable')
    return {'status':'PASS' if not findings else 'FAIL','scanned_files':scanned,'findings':findings,
            'private_corpus':'MISSING_PRIVATE_SOURCE','limitations':'Heuristic scan plus synthetic-only report boundary; no comprehensive historical secret audit.'}
