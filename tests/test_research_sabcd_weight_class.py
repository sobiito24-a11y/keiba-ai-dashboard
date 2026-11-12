from copy import deepcopy

import pytest

from core.research_sabcd_weight_class import (
    VERSION, FEATURES, PARAMS, _normalise_to_podium_slots,
    _weight_kg, assign_to_view, evaluate_race, feature_values, predict,
)
def horse(rank, *, mode="nar", date="2026-11-14"):
    return dict(
        no=str(rank), name="検証馬"+str(rank), mode=mode, mark="◎" if rank == 1 else "—",
        score=900-rank, ability_rank=rank, corner=rank, start_rank=rank,
        research_inputs=dict(jockey_n=320, jockey_rate=40),
        race_context=dict(race_date=date, venue="高知", surface="ダ", distance=1400),
        profile=dict(runs=[
            dict(label="前走", date="2026-10-30", venue="高知", surface="ダ", distance=1400, finish="2着"),
            dict(label="2走前", date="2026-10-10", venue="高知", surface="ダ", distance=1400, finish="4着"),
        ]),
    )



def _field():
    view = [horse(n, mode="nar", date="2026-11-14") for n in range(1, 6)]
    for i, h in enumerate(view):
        h["weight"] = f"{52+i}kg"
        h["weight_delta"] = float(i-2)
        h["age"] = "牝3" if i % 2 == 0 else "牡4"
        h["profile"]["class_shift"] = "昇級" if i == 0 else "同級"
    return view


def test_frozen_feature_order_and_models_remain_different():
    assert len(FEATURES) == 15
    for mode, params in PARAMS.items():
        assert len(params["coef"]) == len(params["mean"]) == len(params["scale"]) == 15
    v = (0.2, 12, 0.2, 0.3, 0.4, 0.1, 1, 1, -1, -2, 1, 3, 0, 0, 0)
    assert 0 < predict("jra", v) < 1
    assert 0 < predict("nar", v) < 1
    assert predict("jra", v) != predict("nar", v)


def test_weight_class_inputs_are_independent_and_explainable():
    view = _field()
    vals, detail = feature_values(view[0], len(view), 54.)
    assert len(vals) == 15
    assert detail["weight_kg"] == 52
    assert detail["weight_delta"] == -2
    assert detail["weight_vs_field"] == -2
    assert detail["class_shift"] == "クラス昇級"
    assert vals[12:15] == (1., 0., 0.)
    assert vals[10:12] == (1., 3.)
    assert _weight_kg({"weight": "不明"}) is None


def test_all_horses_have_independent_trial_grades_and_projections_are_readonly():
    view = _field()
    saved = deepcopy(view)
    result = evaluate_race(view)
    assert set(result) == {str(i) for i in range(1, 6)}
    assert all(result[str(i)]["grade"] in "SABCD" for i in range(1, 6))
    assert all(result[str(i)]["version"] == VERSION for i in range(1, 6))
    assert view == saved
    assign_to_view(view)
    for i, h in enumerate(view):
        assert h["mark"] == saved[i]["mark"]
        assert h["score"] == saved[i]["score"]
        assert h["research_sabcd_weight_class"] == result[str(i)]
    # Calibrating the total by construction is not the same as validation.
    assert sum(h["research_sabcd_weight_class"]["normalized_score"] for h in view) == pytest.approx(3, abs=0.0005)


def test_missing_core_inputs_are_not_assigned_d():
    view = _field()
    view[0]["corner"] = None
    r = evaluate_race(view)
    assert r["1"]["grade"] is None
    assert r["1"]["normalized_score"] is None


def test_normalising_sum_preserves_order_but_not_model_score():
    source = [.8, .45, .3, .2, .1]
    adjusted = _normalise_to_podium_slots(source)
    assert sum(adjusted) == pytest.approx(3., abs=1e-7)
    assert sorted(range(5), key=lambda i: -source[i]) == sorted(range(5), key=lambda i: -adjusted[i])
