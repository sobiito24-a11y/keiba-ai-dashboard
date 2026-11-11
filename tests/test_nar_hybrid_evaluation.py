"""NAR hybrid preview is a read-only research projection of saved pre-race facts."""
from copy import deepcopy

from core.nar_hybrid_evaluation import VERSION, with_nar_hybrid_evaluation
from core.race_explorer_columns import columns, records
from core.race_explorer_ui import lineup_html


def fixture():
    return {
        "race_mode": "nar", "race_id": "202611040001", "date": "2026-11-04",
        "venue": "園田", "surface": "ダ", "distance": 1400,
        "horses": [
            {"horse_no": "1", "horse_name": "馬A", "ability_value": 55, "ability_rank": 1,
             "jockey_course_stats": "10% / 15% / 40%"},
            {"horse_no": "2", "horse_name": "馬B", "ability_value": 50, "ability_rank": 2,
             "jockey_course_stats": ""},
        ],
        "mobile_snapshot": {
            "horses": [
                {"horse_no": "1", "horse_name": "馬A", "recent_races": [
                    {"label": "前走", "date": "2026-10-21", "venue": "園田",
                     "surface": "ダ", "distance": "1400m", "finish": "1着", "race_name": "C2"}]},
                {"horse_no": "2", "horse_name": "馬B", "recent_races": [
                    {"label": "前走", "date": "2026-10-21", "venue": "園田",
                     "surface": "ダ", "distance": "1400m", "finish": "6着", "race_name": "C2"}]},
            ],
            "nar_newspaper_v2_shadow": {"horses": []},
        },
        "model_b_prediction": {"evidence": {}},
    }


def test_hybrid_matches_fixed_research_formula_and_is_display_only():
    snapshot = fixture()
    before = deepcopy(snapshot)
    view = [dict(mode="nar", no="1", name="馬A"), dict(mode="nar", no="2", name="馬B")]
    projected = with_nar_hybrid_evaluation(view, snapshot, [snapshot])
    assert snapshot == before and projected is not view
    a, b = projected
    # C1/N1 condition: .44 for one same-track similar-distance podium.
    # Jockey .75*(40-25)/100=.1125; coefficient six.
    assert abs(a["nar_hybrid_score"] - (55 + 6 * (.44 + .1125))) < 1e-8
    assert a["nar_hybrid_rank"] == 1
    assert b["nar_hybrid_rank"] == 2
    assert "同会場近距離" in a["nar_hybrid_reason"]
    assert a["nar_hybrid_version"] == VERSION
    assert "今回評価" in [x["label"] for x in columns(projected)]
    assert not any(x["label"] in ("NAR前走参考順位", "NAR見直し") for x in columns(projected))
    assert (records(projected)["1"]["nar_hybrid_score"],
            records(projected)["1"]["nar_hybrid_rank"]) == (a["nar_hybrid_score"], 1)
    html = lineup_html(projected)
    # Its research value remains available, but no longer consumes width
    # in the normal all-runner table.
    assert "col-nar_hybrid_score" not in html and "col-ability" in html
    assert 'data-column="class_attention"' in html


def test_result_fields_do_not_enter_prediction():
    s = fixture()
    view = [dict(mode="nar", no="1"), dict(mode="nar", no="2")]
    expected = with_nar_hybrid_evaluation(view, s, [s])
    s["result_file"] = {"results": [{"horse_no": "1", "finish": 12}]}
    s["mobile_snapshot"]["result_file"] = {"results": [{"horse_no": "2", "finish": 1}]}
    s["horses"][0]["finish"] = 12
    assert with_nar_hybrid_evaluation(view, s, [s]) == expected


def test_exact_historical_race_id_joins_are_optional_not_guessed():
    s = fixture()
    s["model_b_prediction"]["evidence"] = {
        "1": {"past_runs": [{"race_id": "202610210009", "date": "2026-10-21",
                             "venue": "園田", "distance": 1400, "finish": 1}]},
        "2": {"past_runs": [{"race_id": "202610210009", "date": "2026-10-21",
                             "venue": "園田", "distance": 1400, "finish": 6}]},
    }
    v = [dict(mode="nar", no="1"), dict(mode="nar", no="2")]
    with_id = with_nar_hybrid_evaluation(v, s, [s])
    s["model_b_prediction"]["evidence"] = {}
    without_id = with_nar_hybrid_evaluation(v, s, [s])
    assert with_id[0]["nar_hybrid_score"] > without_id[0]["nar_hybrid_score"]
    assert with_id[1]["nar_hybrid_score"] < without_id[1]["nar_hybrid_score"]
    assert "直接対戦" in with_id[0]["nar_hybrid_reason"]


def test_missing_ability_or_mismatched_identity_does_not_invent_values():
    s = fixture()
    view = [dict(mode="nar", no="1"), dict(mode="nar", no="2")]
    s["horses"][1]["ability_value"] = None
    projected = with_nar_hybrid_evaluation(view, s, [s])
    assert all("nar_hybrid_score" not in x for x in projected)
    s = fixture()
    s["mobile_snapshot"]["horses"][0]["horse_name"] = "別馬"
    projected = with_nar_hybrid_evaluation(view, s, [s])
    assert all("nar_hybrid_score" not in x for x in projected)


def test_jra_unchanged():
    source = [dict(mode="jra", no="1", ability=90, ability_rank=1)]
    assert with_nar_hybrid_evaluation(source, fixture()) == source
    assert "nar_hybrid_score" not in [x["key"] for x in columns(source)]
