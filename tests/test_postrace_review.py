from copy import deepcopy

import pytest
from bs4 import BeautifulSoup

from core.prediction_snapshot import KEIBA_FORMAT, keiba_bytes, load_keiba
from core.race_result_review import (
    KEY, validate, export_copy, parse_results_csv, parse_payouts_csv,
    template_results, template_payouts,
)
from core.postrace_review_ui import review_html
from core.race_explorer_columns import columns, records
from core.race_explorer_ui import lineup_html


def race(mode="jra"):
    return dict(
        race_id="202611070811", race_mode=mode, date="2026-11-07",
        horses=[dict(horse_no="1", horse_name="サンプルA"),
                dict(horse_no="2", horse_name="サンプルB")],
        prediction_result=dict(race_mode=mode, created_at="2026-11-06T12:00:00",
                               overall_table=dict(columns=["馬番", "馬名", "純能力指数"],
                                                  records=[{"馬番": 1, "馬名": "サンプルA", "純能力指数": 68.4},
                                                           {"馬番": 2, "馬名": "サンプルB", "純能力指数": 57.2}])),
    )


def event(mode="jra"):
    return dict(format=KEIBA_FORMAT, schema_version=1, races=[race(mode)])


def overlay(mode="jra"):
    return dict(schema_version=1, race_id="202611070811", mode=mode,
                source="結果公表サイト（検証用）",
                runners=[dict(horse_no="1", horse_name="サンプルA",
                              finish="1", final_win_odds="8.6",
                              final_popularity="3", corner4="2"),
                         dict(horse_no="2", horse_name="サンプルB",
                              finish="4着", final_win_odds="2.8",
                              final_popularity="1", corner4="5")],
                payouts=[
                    dict(bet_type="単勝", selection="1", payout_yen="860", stake_yen=100),
                    dict(bet_type="馬連", selection="1-2", payout_yen="1630", stake_yen=100),
                    dict(bet_type="ワイド", selection="2-1", payout_yen="580", stake_yen=100),
                    dict(bet_type="3連複", selection="1-2-1", payout_yen="1230", stake_yen=100),
                ])


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_result_overlay_round_trip_preserves_all_prediction_fields(mode):
    original = event(mode)
    before = deepcopy(original)
    source = keiba_bytes(original)
    data = overlay(mode)
    data["payouts"].pop()  # A trio with the same horse twice is invalid.
    output = export_copy(source, original["races"][0]["race_id"], data)
    assert original == before
    old = load_keiba(source)
    loaded = load_keiba(output)
    assert set(loaded["races"][0]) == set(old["races"][0]) | {KEY}
    for key in old["races"][0]:
        assert loaded["races"][0][key] == old["races"][0][key]
    assert loaded["races"][0][KEY]["runners"][0]["finish"] == 1
    assert loaded["races"][0][KEY]["payouts"][2]["selection"] == "1-2"
    # Duplicate import is idempotent.
    assert load_keiba(export_copy(output, original["races"][0]["race_id"], data)) == loaded


def test_reject_unmatched_horse_id_and_never_invent_missed_earnings():
    good = overlay()
    good["payouts"].pop()
    bad = deepcopy(good)
    bad["runners"][0]["horse_name"] = "別の馬"
    with pytest.raises(ValueError, match="馬名"):
        validate(race(), bad)
    bad = deepcopy(good)
    bad["race_id"] = "202611070812"
    with pytest.raises(ValueError, match="レースID"):
        validate(race(), bad)
    bad = deepcopy(good)
    bad["payouts"].append(dict(bet_type="3連単", selection="1-1-2", payout_yen=8000))
    with pytest.raises(ValueError, match="重複"):
        validate(race(), bad)


def test_bet_type_payout_unit_and_order_are_not_guessed():
    q = overlay()
    q["payouts"] = [
        dict(bet_type="馬単", selection="2-1", payout_yen=7850, stake_yen=100),
        dict(bet_type="3連単", selection="2-1-2", payout_yen=40000, stake_yen=100),
    ]
    with pytest.raises(ValueError, match="重複"):
        validate(race(), q)
    q["payouts"][1]["selection"] = "1-2-1"
    with pytest.raises(ValueError, match="重複"):
        validate(race(), q)
    q["payouts"][1]["selection"] = "2-1-3"
    with pytest.raises(ValueError, match="存在"):
        validate(race(), q)
    q["payouts"] = [dict(bet_type="馬単", selection="2-1", payout_yen=7850, stake_yen=100)]
    clean = validate(race(), q)
    assert clean["payouts"][0]["selection"] == "2-1"
    assert clean["payouts"][0]["payout_yen"] == 7850


def test_csv_templates_and_partial_results_still_valid():
    r = race()
    populated = template_results(r).decode("utf-8-sig")
    assert populated.splitlines()[0].startswith("馬番,馬名,着順")
    assert len(parse_results_csv(template_results(r))) == 2
    assert template_payouts().decode("utf-8-sig").startswith("式別,組合せ,払戻金")
    csv_data = ("馬番,馬名,着順,最終単勝,最終人気,実4角\n"
                "1,サンプルA,1,8.6,3,2\n").encode("utf-8-sig")
    selected = parse_results_csv(csv_data)
    assert validate(r, dict(schema_version=1, race_id=r["race_id"], mode="jra",
                            source="公表結果", runners=selected, payouts=[]))["runners"][0]["finish"] == 1
    payout_data = ("式別,組合せ,払戻金,基準額\n"
                   "複勝,1,260,100\nワイド,2-1,580,100\n").encode("utf-8-sig")
    assert len(parse_payouts_csv(payout_data)) == 2


def two_runner_view(mode="jra"):
    return [
        dict(no="1", name="サンプルA", age="牡4", mode=mode,
             frame=1, ability=69.4, ability_rank=3,
             profile={"class_attention":{"display":"同級好走 · 前走 C2一 3着",
                                         "reason":"前走 C2一 3着｜保存根拠"}}),
        dict(no="2", name="サンプルB", age="牝4", mode=mode,
             frame=2, ability=57.2, ability_rank=8,
             profile={"class_attention":{"display":"昇級 · 前走 1勝 1着",
                                         "reason":"前走 1勝 1着｜保存根拠"}}),
    ]


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_folded_review_mirrors_exact_visible_columns_then_appends_results(mode):
    view = two_runner_view(mode)
    result = overlay(mode)
    result["payouts"].pop()
    clean = validate(race(mode), result)
    before = deepcopy(view)
    content = review_html(view, clean)
    soup = BeautifulSoup(content, "html.parser")
    main = BeautifulSoup(lineup_html(view), "html.parser")
    original_headers = [h.text.strip() for h in main.select("th")]
    mirrored = [h.text.strip() for h in soup.select("th")][:len(original_headers)]
    assert mirrored == original_headers
    assert [h.text.strip() for h in soup.select("th")][len(original_headers):len(original_headers)+4] == [
        "実着順", "最終単勝", "最終人気", "実4角"
    ]
    assert not soup.select_one("details#postrace-review").has_attr("open")
    assert not soup.select("tr[data-horse],th[data-column],input[data-user-check],[data-horse-open]")
    assert len(soup.select(".postrace-review-scroll tbody tr")) == 2
    assert "68" not in content  # actual ability is 69.4
    assert "69.4" in content and "57.2" in content
    assert "C2一 3着" in content
    assert "8.6倍" in content and "1着" in content and "4着" in content
    assert "860円" in content and "1,630円" in content
    assert "購入履歴や回収率ではありません" in content
    assert view == before


def test_review_not_rendered_if_missing_and_missing_actuals_are_marked():
    view = two_runner_view()
    assert review_html(view, None) == ""
    result = validate(race(), dict(schema_version=1, race_id=race()["race_id"],
                                   mode="jra", source="公表",
                                   runners=[dict(horse_no="1", horse_name="サンプルA", finish=1)],
                                   payouts=[]))
    doc = BeautifulSoup(review_html(view, result), "html.parser")
    assert "未取得" in doc.select(".postrace-review-scroll tbody tr")[1].text
    assert "払戻金未取得" in doc.text
