"""Reproducible benchmark runner. No gold is passed to retrieval or generation."""
import hashlib
import json
import math
import statistics
import time
from collections import defaultdict
from typing import Callable

from tracecraft.atlas import Atlas
from tracecraft.core.models import EvalCase, EvidenceChunk, Scope
from tracecraft.core.store import ROOT, Store, digest
from .evaluator import EVALUATOR_VERSION, RUBRIC, evaluate, retrieval_metrics

DATASET = ROOT / 'datasets' / 'public-demo'

def load_cases(split: str | None = None) -> list[EvalCase]:
    cases = [EvalCase.model_validate(c) for c in json.loads((DATASET/'cases.json').read_text())]
    if split and split not in {'development','validation','test'}:
        raise ValueError('invalid_split')
    return [case for case in cases if not split or case.split == split]

def validate_dataset() -> dict:
    """Fail on incorrect gold spans, source offsets, hashes or leaked families."""
    corpus = [EvidenceChunk.model_validate(c) for c in json.loads((DATASET/'corpus.json').read_text())]
    by_id = {c.id:c for c in corpus}
    cases = load_cases()
    errors = []
    if len(by_id) != len(corpus):
        errors.append('duplicate_evidence_ids')
    if len({c.id for c in cases}) != len(cases):
        errors.append('duplicate_case_ids')
    for chunk in corpus:
        source = (DATASET/f'{chunk.document_id}.md').read_bytes()
        if hashlib.sha256(source).hexdigest() != chunk.source_hash:
            errors.append(f'source_hash:{chunk.id}')
        if source.decode()[chunk.start:chunk.end] != chunk.text:
            errors.append(f'source_span:{chunk.id}')
        if not set(chunk.links) <= by_id.keys():
            errors.append(f'broken_links:{chunk.id}')
    families: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        families[case.family].add(case.split)
        if not set(case.evidence_ids) <= by_id.keys():
            errors.append(f'unknown_gold:{case.id}')
        for span in case.gold_spans:
            gold_chunk = by_id.get(span['evidence_id'])
            if not gold_chunk or gold_chunk.text[span['start']:span['end']] != span['quote']:
                errors.append(f'gold_span:{case.id}')
            elif gold_chunk.brand != case.brand or gold_chunk.snapshot != case.snapshot:
                errors.append(f'gold_scope:{case.id}')
        if {s['evidence_id'] for s in case.gold_spans} != set(case.evidence_ids):
            errors.append(f'incomplete_gold_spans:{case.id}')
    for family, splits in families.items():
        if len(splits) != 1:
            errors.append(f'family_split_leak:{family}')
    return {'status':'PASS' if not errors else 'FAIL', 'errors':errors, 'cases':len(cases),
            'records':len(corpus), 'families':len(families), 'review_status':'machine_authored_source_checked',
            'dataset_hash':digest([c.model_dump() for c in cases]), 'corpus_hash':digest([c.model_dump() for c in corpus])}

def configuration(method: str, mode: str, cases: list[EvalCase], repeats=1, adapter='baseline') -> dict:
    return {'schema_version':'tracecraft.eval-config/1', 'dataset_hash':digest([c.model_dump() for c in cases]),
            'corpus_hash':digest(json.loads((DATASET/'corpus.json').read_text())),
            'split':sorted({c.split for c in cases}), 'dataset_visibility':'public_exploratory',
            'evaluator':EVALUATOR_VERSION,'rubric_hash':digest(RUBRIC),'method':method,'mode':mode,
            'adapter':adapter, 'repeats':repeats, 'model':'none-extractive','prompt':Atlas.answer_policy,
            'generation':{'max_output_tokens':0,'temperature':None},
            'budget':{'max_cases':64,'max_repeats':3,'paid_calls':0,'full_pack_max_chars':24000},
            'review_status':'machine_authored_source_checked'}

def _wilson(successes: int, n: int):
    if not n:
        return None
    z = 1.96
    rate = successes/n
    center = (rate+z*z/(2*n))/(1+z*z/n)
    margin = z*math.sqrt(rate*(1-rate)/n+z*z/(4*n*n))/(1+z*z/n)
    return [max(0,center-margin),min(1,center+margin)]

def summarize(rows: list[dict]) -> dict:
    counts = {key:sum(row['passed'] is value for row in rows) for key,value in [('passed',True),('failed',False),('skipped',None)]}
    by_case: dict[str,list] = defaultdict(list)
    groups: dict[str,dict] = {}
    for row in rows:
        by_case[row['case_id']].append(row)
        group = groups.setdefault(row['category'], {'passed':0,'failed':0,'skipped':0,'attempts':0})
        group['attempts'] += 1
        group['passed' if row['passed'] is True else ('failed' if row['passed'] is False else 'skipped')] += 1
    fully_checked = [attempts for attempts in by_case.values() if all(a['passed'] is not None for a in attempts)]
    passing_cases = sum(all(a['passed'] for a in attempts) for attempts in fully_checked)
    latency = [row['elapsed_ms'] for row in rows]
    retrieval = [row['retrieval_metrics']['recall_at_k'] for row in rows if row['retrieval_metrics']['recall_at_k'] is not None]
    rr = [row['retrieval_metrics']['reciprocal_rank'] for row in rows if row['retrieval_metrics']['reciprocal_rank'] is not None]
    expected_unknown = [row for row in rows if row['expected_status'] == 'insufficient_evidence']
    expected_supported = [row for row in rows if row['expected_status'] == 'supported']
    usage = [row['answer'].get('usage',{}) for row in rows]
    return {'counts':{'total':len(rows),**counts},'distinct_cases':len(by_case),'groups':groups,
            'fully_checked_cases':len(fully_checked),'passing_cases':passing_cases,
            'case_pass_rate':passing_cases/len(fully_checked) if fully_checked else None,
            'uncertainty':{'kind':'descriptive_wilson_95_by_case','interval':_wilson(passing_cases,len(fully_checked)),
                           'note':'Exploratory authored corpus, not an IID production sample. Repeats are not independent cases.'},
            'retrieval':{'mean_recall_at_k':statistics.mean(retrieval) if retrieval else None,
                         'mean_reciprocal_rank':statistics.mean(rr) if rr else None},
            'answers':{'correct_abstentions':sum(row['answer'].get('status')=='insufficient_evidence' for row in expected_unknown),
                       'unknown_cases':len(expected_unknown),
                       'false_abstentions':sum(row['answer'].get('status')=='insufficient_evidence' for row in expected_supported),
                       'supported_cases':len(expected_supported)},
            'latency_ms':{'mean':statistics.mean(latency) if latency else None,
                          'p95':sorted(latency)[max(0,math.ceil(len(latency)*.95)-1)] if latency else None,
                          'total':sum(latency)},
            'usage':{'calls':sum(u.get('calls',0) for u in usage),
                     'input_tokens':sum(u['input_tokens'] for u in usage) if usage and all(u.get('input_tokens') is not None for u in usage) else None,
                     'output_tokens':sum(u['output_tokens'] for u in usage) if usage and all(u.get('output_tokens') is not None for u in usage) else None,
                     'cost_usd':sum(u['cost_usd'] for u in usage) if usage and all(u.get('cost_usd') is not None for u in usage) else None},
            'human_rework':{'measurement_status':'NOT_RUN','minutes':None},'model_judge':'NOT_RUN'}

def run_benchmark(store: Store, atlas, mode='fixture', method='lexical', split=None, repeats=1,
                  adapter: Callable | None=None, adapter_name='baseline', module='canon') -> dict:
    if mode not in {'fixture','local'}:
        return {'module':module,'status':'NOT_RUN','mode':mode,'measurement_status':'not_run',
                'reason':'Live requires the separately bounded opt-in runner; replay is not a new benchmark.'}
    if method not in {'lexical','dense','hybrid','full_pack','no_context'}:
        raise ValueError('invalid_method')
    if method == 'no_context':
        return {'module':module,'status':'NOT_RUN','mode':mode,'measurement_status':'not_run',
                'reason':'No-context baseline requires an explicitly authorized generative model.'}
    if not isinstance(repeats,int) or not 1 <= repeats <= 3:
        raise ValueError('invalid_repeats')
    validation = validate_dataset()
    if validation['status'] != 'PASS':
        raise ValueError('invalid_gold:'+','.join(validation['errors']))
    cases = load_cases(split)
    config = configuration(method,mode,cases,repeats,adapter_name)
    config['corpus_hash'] = getattr(atlas,'corpus_hash',config['corpus_hash'])
    config['embedding_model'] = getattr(getattr(atlas,'encoder',None),'model_id',None) if method in {'dense','hybrid'} else None
    manifest = store.new_run(module, mode, config)
    rows = []
    for case in cases:
        scope = Scope(brand=case.brand,snapshot=case.snapshot,locale=case.locale)
        for repeat in range(repeats):
            started = time.perf_counter()
            try:
                answer = atlas.answer(case.query, scope, method=method, mode=mode)
                if adapter:
                    answer = adapter(answer,case)
                result = evaluate(case,answer,atlas,scope)
                row = result.model_dump()
                row['retrieval_metrics'] = retrieval_metrics(case,answer)
            except (ValueError,RuntimeError,OSError) as error:
                row = {'case_id':case.id,'passed':None,'checks':{'execution':'NOT_RUN'},'answer':{},
                       'latency_ms':0,'error':f'{type(error).__name__}: {error}',
                       'retrieval_metrics':{'recall_at_k':None,'reciprocal_rank':None,'k':0,'context_recall':None}}
            row.update(repeat=repeat,category=case.category,family=case.family,split=case.split,
                       severity=case.severity,expected_status=case.expected_status,
                       elapsed_ms=(time.perf_counter()-started)*1000)
            rows.append(row)
            store.trace(manifest['id'],'evaluation',{'case_id':case.id,'repeat':repeat,'config_hash':manifest['config_hash']},
                        {'passed':row['passed'],'checks':row['checks'],'answer_run_id':row['answer'].get('run_id')},
                        status='skipped' if row['passed'] is None else ('ok' if row['passed'] else 'error'),error=row['error'])
    summary = summarize(rows)
    status = 'NOT_RUN' if not rows or summary['counts']['skipped']==len(rows) else ('INCONCLUSIVE' if summary['counts']['skipped'] else 'COMPLETED')
    report = {'schema_version':'tracecraft.benchmark/1','module':module,'id':manifest['id'],'run_id':manifest['id'],
              'mode':mode,'data_origin':'synthetic','measurement_status':'measured','review_status':'machine_authored_source_checked',
              'status':status,'config':config,'dataset_validation':validation,'summary':summary,'rows':rows,
              'limitations':['Exploratory public synthetic corpus, no hidden holdout.',
                             'Fixture mode executes deterministic extraction, not a generative model.',
                             'Gold checked mechanically against original fictional documents; no expert review.',
                             'Free-form semantic support is not inferred from cosine or text similarity.',
                             'No claim of quality on private STC data, production reliability or ROI.']}
    final_manifest = store.finish_run(manifest['id'],status,usage=summary['usage'])
    report['manifest'] = final_manifest
    store.put('eval_runs',manifest['id'],report)
    store.put('reports',module,report)
    return report

def experiment(store: Store, atlas, mode='fixture') -> dict:
    reports = {method:run_benchmark(store,atlas,mode=mode,method=method) for method in ['lexical','full_pack','dense','hybrid']}
    no_context = {'status':'NOT_RUN','reason':'Generative no-context baseline not authorized; not a production fallback.'}
    executed = any(report.get('status') != 'NOT_RUN' for report in reports.values())
    report = {'schema_version':'tracecraft.canon-experiment/1','module':'canon','mode':mode,'data_origin':'synthetic',
              'measurement_status':'measured' if executed else 'not_run','review_status':'machine_authored_source_checked',
              'status':'COMPLETED' if executed else 'NOT_RUN','comparisons':reports,'no_context':no_context,
              'limitations':['Methods may tie or lose. No winner is prescribed.','Public test families are exploratory, not a secret holdout.']}
    store.put('reports','canon',report)
    return report
