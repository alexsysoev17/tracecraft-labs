from copy import deepcopy

from tracecraft.atlas import Atlas
from tracecraft.canon.service import configuration,load_cases
from tracecraft.core.store import Store
from tracecraft.sentinel.service import compare,compare_manifests,quality_gate


def manifest(method='lexical'):
    return {'config':configuration(method,'fixture',load_cases()),'code_revision':'test-revision',
            'code_source_hash':'source-hash',
            'dirty_tree':False,'mode':'fixture','data_origin':'synthetic'}


def test_manifests_reject_undeclared_changes():
    baseline=manifest()
    candidate=manifest('full_pack')
    assert compare_manifests(baseline,candidate,'method')['comparable'] is True
    candidate['config']['corpus_hash']='other'
    comparison=compare_manifests(baseline,candidate,'method')
    assert comparison['comparable'] is False
    assert 'config.corpus_hash' in comparison['changed_fields']
    assert quality_gate({}, {}, comparison)['decision']=='NOT_COMPARABLE'


def test_missing_manifest_conditions_rejected():
    baseline=manifest()
    candidate=deepcopy(baseline)
    del candidate['config']['rubric_hash']
    assert compare_manifests(baseline,candidate,'method')['comparable'] is False


def test_source_change_invalidates_comparison_without_a_git_commit():
    baseline=manifest()
    candidate=manifest('full_pack')
    candidate['code_source_hash']='new-source-hash'
    result=compare_manifests(baseline,candidate,'method')
    assert result['comparable'] is False
    assert 'code_source_hash' in result['changed_fields']


def test_real_broken_adapter_rejected_and_outputs_preserved(tmp_path):
    store=Store(tmp_path/'test.sqlite')
    report=compare(store,Atlas(store),candidate='broken',split='development')
    assert report['gate']=='REGRESSION'
    assert report['comparability']['comparable'] is True
    assert report['regressions']
    regression=report['regressions'][0]
    assert regression['baseline_answer'] != regression['candidate_answer']
    assert 'The primary color is #000000.' in regression['candidate_answer']['text']
    assert 'claim_support' in regression['failed_checks']
    assert report['candidate']['summary']['counts']['failed']>0
    assert store.get('comparisons',report['id'])['gate']=='REGRESSION'


def test_normal_configurations_are_executed_without_predetermined_winner(tmp_path):
    store=Store(tmp_path/'test.sqlite')
    report=compare(store,Atlas(store),candidate='normal',split='development')
    assert report['baseline']['rows'] and report['candidate']['rows']
    assert report['comparability']['changed_fields']==['config.method']
    assert report['gate'] in {'PASS','REGRESSION','INCONCLUSIVE'}
    assert report['candidate']['config']['method']=='full_pack'


def row(id_,passed,severity='normal',checks=None):
    return {'case_id':id_,'repeat':0,'category':'test','severity':severity,'passed':passed,
            'checks':checks or {'status':passed},'answer':{}}


def test_critical_failure_not_compensated_by_average():
    baseline={'rows':[row('ok',True),row('leak',True)]}
    candidate={'rows':[row('ok',True),row('leak',False,'critical',{'evidence_access':False})]}
    gate=quality_gate(baseline,candidate,{'comparable':True})
    assert gate['decision']=='REGRESSION'
    assert gate['critical_failures'][0]['case_id']=='leak'


def test_missing_and_skipped_checks_are_not_a_pass():
    baseline={'rows':[row('one',True),row('two',True)]}
    assert quality_gate(baseline,{'rows':[row('one',True)]},{'comparable':True})['decision']=='INCONCLUSIVE'
    assert quality_gate(baseline,{'rows':[row('one',True),row('two',None)]},{'comparable':True})['decision']=='INCONCLUSIVE'
    assert quality_gate(baseline,{'rows':[row('one',None)]},{'comparable':True})['decision']=='NOT_RUN'
