import pytest
from core.sabcd_probability_research import predict_shadow


def model():
    return dict(train_through='2026-11-17', rates={'A':.6},features=['intercept','distance','distance__missing'],
                median=[2.],mean=[2.],scale=[1.],coefficients=[0.,10.,-1.],cap=.08)


def test_future_only_unknown_grade_and_missing_are_explicit():
    m=model()
    assert predict_shadow(m,'A',{'distance':3},race_date='2026-11-17')['probability'] is None
    assert predict_shadow(m,'未判定',{'distance':3},race_date='2026-11-18')['status']=='missing_grade'
    assert predict_shadow(m,'A',{},race_date='2026-11-18')['status']=='missing_inputs'


def test_bounded_correction_never_changes_grade_or_uses_outcomes():
    m=model();a=predict_shadow(m,'A',{'distance':3},race_date='2026-11-18')
    assert a['probability']==pytest.approx(.68)
    assert not a['grade_change_enabled'] and not a['production_enabled']
    assert predict_shadow(m,'A',{'distance':3,'finish':1,'actual_corner':1},race_date='2026-11-18')==a
    assert predict_shadow(m,'A',{'distance':-9},race_date='2026-11-18')['probability']==pytest.approx(.52)
