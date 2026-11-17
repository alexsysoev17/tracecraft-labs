"""Independent reviewer reproductions: source references are not answer content."""
import pytest

from tracecraft.atlas import Atlas
from tracecraft.canon.evaluator import evaluate
from tracecraft.canon.service import load_cases
from tracecraft.core.models import Answer, Claim, Scope
from tracecraft.core.store import Store


@pytest.mark.parametrize('case_id,answer,check', [
    ('lf-palette-ru', Answer(status='supported',text='The',evidence_ids=['luma-v2-palette'],
        claims=[Claim(text='The',quote='The',evidence_id='luma-v2-palette')]), 'required_content'),
    ('lf-conflict-ru', Answer(status='conflict',text='Sources conflict; a reviewed priority decision is required.',
        evidence_ids=['luma-v2-packing-a','luma-v2-packing-b']), 'supported_has_claims'),
    ('lf-unknown', Answer(status='insufficient_evidence',
        text='This product is certified fireproof and safe for every use.'), 'refusal_content'),
])
def test_shallow_answer_cannot_pass_by_correct_status_and_reference(tmp_path,case_id,answer,check):
    atlas=Atlas(Store(tmp_path/'eval.sqlite'))
    case=next(c for c in load_cases() if c.id==case_id)
    result=evaluate(case,answer,atlas,Scope())
    assert result.passed is False
    assert result.checks[check] is False
