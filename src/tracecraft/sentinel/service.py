"""A comparison runner does not let configurations award themselves a score."""
from copy import deepcopy
from typing import Any

from tracecraft.canon.service import run_benchmark
from tracecraft.core.models import Answer, Claim
from tracecraft.core.store import Store, digest

GATE_VERSION = 'sentinel-critical-no-regression/1'

def differences(before: Any, after: Any, prefix='') -> list[str]:
    if isinstance(before,dict) and isinstance(after,dict):
        changed=[]
        for key in sorted(set(before)|set(after)):
            path=f'{prefix}.{key}' if prefix else key
            if key not in before or key not in after:
                changed.append(path)
            else:
                changed.extend(differences(before[key],after[key],path))
        return changed
    return [] if before==after else [prefix]

def compare_manifests(baseline: dict,candidate: dict, declared_factor: str) -> dict:
    """Ignore run IDs/timestamps; every experimental condition is compared."""
    left={'config':baseline.get('config',{}),'code_revision':baseline.get('code_revision'),
          'code_source_hash':baseline.get('code_source_hash'),
          'dirty_tree':baseline.get('dirty_tree'),'mode':baseline.get('mode'),
          'data_origin':baseline.get('data_origin')}
    right={'config':candidate.get('config',{}),'code_revision':candidate.get('code_revision'),
           'code_source_hash':candidate.get('code_source_hash'),
           'dirty_tree':candidate.get('dirty_tree'),'mode':candidate.get('mode'),
           'data_origin':candidate.get('data_origin')}
    changed=differences(left,right)
    allowed=f'config.{declared_factor}'
    unexpected=[key for key in changed if key != allowed]
    reasons=[f'undeclared_condition_changed:{field}' for field in unexpected]
    required={'dataset_hash','corpus_hash','evaluator','rubric_hash','budget','mode','method','repeats','adapter'}
    for label,manifest in [('baseline',left),('candidate',right)]:
        missing=required-set(manifest['config'])
        reasons.extend(f'{label}_missing_condition:{key}' for key in sorted(missing))
    if declared_factor not in {'method','adapter','model','prompt'}:
        reasons.append('unsupported_declared_factor')
    return {'comparable':not reasons,'declared_factor':declared_factor,'changed_fields':changed,
            'reasons':reasons,'code_revision_known':bool(left['code_revision'] and right['code_revision'])}

def broken_adapter(answer: Answer, _case) -> Answer:
    """Inject a real bad output, not a preassigned failing score."""
    mutated=answer.model_copy(deep=True)
    if mutated.status=='supported' and mutated.claims:
        original=mutated.claims[0]
        fabricated='The primary color is #000000.'
        mutated.claims[0]=Claim(text=fabricated,evidence_id=original.evidence_id,quote=original.quote)
        mutated.text=fabricated+'\n'+mutated.text
        mutated.evidence_ids=[e for e in mutated.evidence_ids if e != original.evidence_id]
    return mutated

def quality_gate(baseline: dict,candidate: dict,comparability: dict) -> dict:
    if not comparability['comparable']:
        return {'decision':'NOT_COMPARABLE','regressions':[],'critical_failures':[],
                'reason':'At least one undeclared experimental condition differs.'}
    old={(r['case_id'],r['repeat']):r for r in baseline.get('rows',[])}
    new={(r['case_id'],r['repeat']):r for r in candidate.get('rows',[])}
    if not old or not new or all(r['passed'] is None for r in new.values()):
        return {'decision':'NOT_RUN','regressions':[],'critical_failures':[],
                'reason':'No completed comparable candidate evaluation.'}
    regressions=[]
    critical=[]
    for key,row in new.items():
        previous=old.get(key)
        failed=[name for name,value in row['checks'].items() if value is False]
        item={'case_id':row['case_id'],'repeat':row['repeat'],'category':row['category'],
              'severity':row['severity'],'baseline_passed':previous['passed'] if previous else None,
              'candidate_passed':row['passed'],'failed_checks':failed,
              'baseline_answer':previous['answer'] if previous else None,'candidate_answer':row['answer']}
        if row['passed'] is False and previous and previous['passed'] is True:
            regressions.append(item)
        if row['passed'] is False and (row['severity']=='critical' or any(
                row['checks'].get(check) is False for check in ['evidence_access','version','claim_support'])):
            critical.append(item)
    if regressions or critical:
        decision='REGRESSION'
        reason='Observed regressions or critical candidate violations; averages cannot override them.'
    elif set(old)!=set(new) or any(r['passed'] is None for r in list(old.values())+list(new.values())):
        decision='INCONCLUSIVE'
        reason='Missing or skipped checks prevent a passing gate.'
    elif any(r['passed'] is False for r in new.values()):
        decision='INCONCLUSIVE'
        reason='No newly detected regression, but unresolved candidate failures remain.'
    else:
        decision='PASS'
        reason='All candidate checks passed with no observed regression. This is not statistical improvement.'
    return {'decision':decision,'regressions':regressions,'critical_failures':critical,'reason':reason}

def compare(store: Store,atlas,candidate='broken',mode='fixture',split=None,repeats=1) -> dict:
    if candidate not in {'broken','normal'}:
        raise ValueError('invalid_candidate')
    baseline=run_benchmark(store,atlas,mode=mode,method='lexical',split=split,repeats=repeats,
                           adapter_name='baseline',module='sentinel-baseline')
    is_broken=candidate=='broken'
    challenger=run_benchmark(store,atlas,mode=mode,method='lexical' if is_broken else 'full_pack',
                             split=split,repeats=repeats,adapter=broken_adapter if is_broken else None,
                             adapter_name='broken-citations-v1' if is_broken else 'baseline',module='sentinel-candidate')
    declared_factor='adapter' if is_broken else 'method'
    comparability=compare_manifests(baseline.get('manifest',{}),challenger.get('manifest',{}),declared_factor)
    gate=quality_gate(baseline,challenger,comparability)
    if baseline.get('status')=='NOT_RUN' and 'rows' not in baseline:
        gate={'decision':'NOT_RUN','regressions':[],'critical_failures':[],'reason':baseline.get('reason')}
    report={'schema_version':'tracecraft.comparison/1','module':'sentinel','mode':mode,'data_origin':'synthetic',
            'measurement_status':'measured' if 'rows' in baseline else 'not_run','review_status':'machine_authored_source_checked',
            'status':gate['decision'],'gate':gate['decision'],'decision':gate['decision'],
            'gate_version':GATE_VERSION,'gate_reason':gate['reason'],'candidate_name':candidate,
            'comparability':comparability,'baseline':baseline,'candidate':challenger,
            'regressions':gate['regressions'],'critical_failures':gate['critical_failures'],
            'summary':{'regressions':len(gate['regressions']),'critical_failures':len(gate['critical_failures']),
                       'baseline_counts':baseline.get('summary',{}).get('counts'),
                       'candidate_counts':challenger.get('summary',{}).get('counts')},
            'limitations':['Public exploratory cases, no hidden holdout and no production promotion.',
                           'Broken candidate intentionally changes actual answer claims and citation IDs.',
                           'Normal comparison changes only retrieval method; no improvement is presumed.',
                           'Passing is a quality gate on covered checks, not a statistical reliability claim.']}
    run=store.new_run('sentinel',mode,{'candidate':candidate,'declared_factor':declared_factor,'gate_version':GATE_VERSION,
                                      'baseline_config_hash':digest(baseline.get('config',{})),
                                      'candidate_config_hash':digest(challenger.get('config',{}))})
    report['id']=report['run_id']=run['id']
    store.trace(run['id'],'quality_gate',{'baseline_run':baseline.get('run_id'),'candidate_run':challenger.get('run_id')},
                {'decision':gate['decision'],'regression_case_ids':[r['case_id'] for r in gate['regressions']]},
                status='error' if gate['decision']=='REGRESSION' else 'ok')
    report['manifest']=store.finish_run(run['id'],gate['decision'])
    store.put('comparisons',run['id'],report)
    store.put('reports','sentinel',report)
    return report

def experiment(store: Store,atlas,mode='fixture') -> dict:
    broken=compare(store,atlas,candidate='broken',mode=mode)
    normal=compare(store,atlas,candidate='normal',mode=mode)
    # Exercise the manifest guard without relabeling it a generation experiment.
    changed=deepcopy(normal['candidate'].get('manifest',{}))
    if changed:
        changed['config']['corpus_hash']='deliberately-different-corpus'
    mismatch=compare_manifests(normal['baseline'].get('manifest',{}),changed,'method')
    mismatch_gate=quality_gate(normal['baseline'],normal['candidate'],mismatch)
    executed = broken['gate'] != 'NOT_RUN' or normal['gate'] != 'NOT_RUN'
    report={'schema_version':'tracecraft.sentinel-experiment/1','module':'sentinel','mode':mode,
            'data_origin':'synthetic','measurement_status':'measured' if executed else 'not_run',
            'status':'COMPLETED' if executed else 'NOT_RUN',
            'broken':broken,'normal':normal,'manifest_negative':{'comparability':mismatch,**mismatch_gate},
            'limitations':['Fixture results verify runner/evaluator behavior, not live model reliability.']}
    store.put('reports','sentinel',report)
    return report
