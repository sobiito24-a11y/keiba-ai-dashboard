"""Offline candidate inference only. Never called by the live grade pipeline."""
import math


def predict_shadow(model, grade, features, *, race_date):
    if not race_date or race_date <= model['train_through']:
        return dict(status='not_future_of_training', probability=None, production_enabled=False)
    if grade not in model['rates']:
        return dict(status='missing_grade', probability=None, production_enabled=False)
    count = len(model['median'])
    names = model['features'][1:1 + count]
    values, missing = [], []
    for i, name in enumerate(names):
        raw = features.get(name)
        try:
            value = float(raw)
            known = math.isfinite(value)
        except (ValueError, TypeError):
            known = False
        missing.append(0. if known else 1.)
        value = value if known else model['median'][i]
        values.append(max(-5., min(5., (value-model['mean'][i])/model['scale'][i])))
    if all(missing):
        return dict(status='missing_inputs', probability=None, production_enabled=False)
    vector = [1.] + values + missing
    if len(vector) != len(model['coefficients']):
        raise ValueError('Feature/model dimensions differ')
    baseline = model['rates'][grade]
    offset = math.log(baseline/(1-baseline))
    score = offset + sum(a*b for a,b in zip(vector, model['coefficients']))
    p = 1/(1+math.exp(-max(-30.,min(30.,score))))
    p = max(.001,min(.999,max(baseline-model['cap'],min(baseline+model['cap'],p))))
    return dict(status='research_only', probability=p, baseline_probability=baseline,
                original_grade=grade, grade_change_enabled=False, production_enabled=False,
                training_grade_origin=model.get('source_grade'))
