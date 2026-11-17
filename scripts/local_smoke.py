"""Explicit real-model test, excluded from fixture CI. No download/network path."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from tracecraft.atlas import Atlas  # noqa: E402
from tracecraft.core.models import Scope  # noqa: E402
from tracecraft.core.store import Store, source_fingerprint, utcnow  # noqa: E402

def worker(database):
    atlas=Atlas(Store(database))
    answer=atlas.search('Как далеко нужно отодвинуть знак от соседних элементов?',Scope(),method='dense',mode='local')
    if answer.status!='ready':
        raise RuntimeError(answer.reason)
    return {'ids':[h.evidence.id for h in answer.hits], 'scores':[h.score for h in answer.hits],
            'embedding_calls':atlas.encoder.calls,'stored_vectors':len(atlas.store.list('embeddings')),
            'dimensions':len(atlas.store.list('embeddings')[0]['vector']), 'model':atlas.encoder.model_id}

def main():
    started=time.perf_counter()
    (ROOT/'runtime').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT/'runtime',prefix='local-smoke-') as folder:
        command=[sys.executable,str(Path(__file__).resolve()),'--worker',str(Path(folder)/'vectors.sqlite')]
        env={**os.environ,'HF_HUB_OFFLINE':'1','TOKENIZERS_PARALLELISM':'false'}
        first=json.loads(subprocess.check_output(command,text=True,env=env))
        second=json.loads(subprocess.check_output(command,text=True,env=env))
    checks={'real_384_dimensions':first['dimensions']==384,
            'new_process_reuses_passage_vectors':first['embedding_calls']>1 and second['embedding_calls']==1,
            'same_ranking_after_restart':first['ids']==second['ids'],
            'same_scores_after_restart':first['scores']==second['scores'],
            'paraphrase_top_source':first['ids'][0]=='luma-v2-clearspace'}
    report={'status':'PASS' if all(checks.values()) else 'FAIL','mode':'local','data_origin':'synthetic',
            'measurement_status':'measured','checked_at':utcnow(),'code_source_hash':source_fingerprint(),
            'checks':checks,'first_process':first,'restarted_process':second,'elapsed_ms':(time.perf_counter()-started)*1000}
    (ROOT/'reports/public/local-smoke.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='PASS' else 1

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--worker':
        print(json.dumps(worker(sys.argv[2])))
    else:
        sys.exit(main())
