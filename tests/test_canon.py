import json

import pytest

from tracecraft.atlas import Atlas
from tracecraft.canon.evaluator import evaluate
from tracecraft.canon.service import DATASET, load_cases, run_benchmark, summarize, validate_dataset
from tracecraft.core.models import Answer, Claim, Scope
from tracecraft.core.store import Store


@pytest.fixture
def context(tmp_path):
    store=Store(tmp_path/'test.sqlite')
    return store,Atlas(store)


def test_gold_matches_original_documents_and_has_disjoint_families():
    audit=validate_dataset()
    assert audit['status']=='PASS',audit['errors']
    assert 24<=audit['cases']<=40
    assert {c.locale for c in load_cases()}=={'en','ru'}
    assert {c.category for c in load_cases()} >= {
        'direct','paraphrase','exact_code','combined','prohibition','exception','old_version',
        'conflict','unknown','denied_source','example_against_rule'
    }
    corpus=json.loads((DATASET/'corpus.json').read_text())
    assert all('expected_status' not in chunk and 'gold_spans' not in chunk for chunk in corpus)


def test_actual_lexical_answer_is_checked_against_gold(context):
    _,atlas=context
    case=next(c for c in load_cases() if c.id=='lf-palette-ru')
    scope=Scope(brand=case.brand)
    answer=atlas.answer(case.query,scope)
    result=evaluate(case,answer,atlas,scope)
    assert result.passed is True,result.checks
    assert result.checks['quote_location'] is True
    assert result.checks['expected_evidence'] is True


def test_existing_citation_does_not_prove_false_claim(context):
    _,atlas=context
    case=next(c for c in load_cases() if c.id=='lf-palette-ru')
    scope=Scope()
    evidence=atlas.evidence(scope,'luma-v2-palette')
    fabricated='The primary color is #000000.'
    answer=Answer(status='supported',text=fabricated,evidence_ids=[evidence.id],
                  claims=[Claim(text=fabricated,evidence_id=evidence.id,quote=evidence.text)])
    result=evaluate(case,answer,atlas,scope)
    assert result.checks['evidence_access'] is True
    assert result.checks['quote_location'] is True
    assert result.checks['claim_support'] is False
    assert result.passed is False


def test_denied_source_and_wrong_snapshot_cannot_pass(context):
    _,atlas=context
    case=next(c for c in load_cases() if c.id=='lf-denied')
    answer=Answer(status='supported',text='DEMO-EMBER-73',evidence_ids=['luma-v2-restricted'],
                  claims=[Claim(text='DEMO-EMBER-73',evidence_id='luma-v2-restricted',quote='DEMO-EMBER-73')])
    result=evaluate(case,answer,atlas,Scope())
    assert result.passed is False
    assert result.checks['evidence_access'] is False
    version_case=next(c for c in load_cases() if c.id=='lf-version-old')
    current=atlas.answer('primary color',Scope())
    stale=evaluate(version_case,current,atlas,Scope(snapshot='v1'))
    assert stale.passed is False
    assert stale.checks['version'] is False


def test_free_form_answer_requires_semantic_review(context):
    _,atlas=context
    case=next(c for c in load_cases() if c.id=='lf-palette-ru')
    answer=atlas.answer(case.query,Scope()).model_copy(update={'generation_kind':'live'})
    result=evaluate(case,answer,atlas,Scope())
    assert result.passed is None
    assert result.checks['human_rubric_review']=='NOT_RUN'


def test_uncited_extra_assertion_and_secret_in_refusal_fail(context):
    _,atlas=context
    case=next(c for c in load_cases() if c.id=='lf-palette-ru')
    answer=atlas.answer(case.query,Scope())
    answer.text+=' The products are waterproof.'
    result=evaluate(case,answer,atlas,Scope())
    assert result.passed is False
    assert result.checks['all_assertions_attributed'] is False
    denied=next(c for c in load_cases() if c.id=='lf-denied')
    refusal=Answer(status='insufficient_evidence',text='I cannot disclose DEMO-EMBER-73.')
    assert evaluate(denied,refusal,atlas,Scope()).passed is False


def test_fixture_dense_is_skipped_not_passed(context):
    store,atlas=context
    report=run_benchmark(store,atlas,method='dense',split='development')
    assert report['status']=='NOT_RUN'
    assert report['summary']['counts']=={'total':8,'passed':0,'failed':0,'skipped':8}
    assert report['summary']['case_pass_rate'] is None


def test_report_repeats_do_not_inflate_distinct_cases(context):
    store,atlas=context
    report=run_benchmark(store,atlas,split='development',repeats=2)
    assert report['summary']['counts']['total']==16
    assert report['summary']['distinct_cases']==8
    assert report['summary']['uncertainty']['kind']=='descriptive_wilson_95_by_case'
    assert report['summary']['usage']['calls']==0
    assert report['summary']['usage']['cost_usd'] is None
    assert store.get('eval_runs',report['id'])['rows']==report['rows']


def test_no_context_and_live_are_honestly_not_run(context):
    store,atlas=context
    assert run_benchmark(store,atlas,method='no_context')['status']=='NOT_RUN'
    assert run_benchmark(store,atlas,mode='live')['status']=='NOT_RUN'
    with pytest.raises(ValueError,match='invalid_repeats'):
        run_benchmark(store,atlas,repeats=4)


def test_missing_results_do_not_count_as_success():
    result=summarize([])
    assert result['case_pass_rate'] is None
    assert result['counts']['passed']==0
