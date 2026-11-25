"""NAR Rakuten body-weight research: identity, no leaks, study denominators."""
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from core import nar_body_weight as bw
from core.nar_body_weight_ui import _overlay, _bodyweight_table, horse_detail_html
from core.independent_ai_sabcd import MODEL_ID


RID = "202646112309"
URL = "https://keiba.rakuten.co.jp/race_card/list/RACEID/202611232200000009"
RESULT_URL = URL.replace("/race_card/", "/race_performance/")
NAMES = ("ニャンタロウ", "シャンパンスター", "ミライミライ", "トーキョースター", "ハナノキ")
TIME = datetime.fromisoformat("2026-11-23T17:30:00+09:00")


def prediction():
    return SimpleNamespace(
        race_mode="nar", race_name="ＭＲＯ金賞",
        race_info={"race_id": RID, "racecourse": "金沢", "race_date": "2026-11-23",
                   "start_at": "2026-11-23T18:15:00+09:00"},
        overall_table=pd.DataFrame(
            [{"馬番": i+1, "馬名": name} for i, name in enumerate(NAMES)]),
        horse_evaluation=pd.DataFrame([]), source_files={}, debug_info={},
    )


def view():
    values = []
    for i, name in enumerate(NAMES, 1):
        g = ("A", "B", "C", "D", "S")[i-1]
        values.append({"no": str(i), "name": name, "mode": "nar",
                       "rank": i, "score": 100-i, "mark": "◎" if i == 1 else "—",
                       "independent_ai_sabcd": {"grade": g, "source_model_id": MODEL_ID},
                       "unified_sabcd": {"grade": g}})
    return values


def card_html(*, wrong_name=False, wrong_date=False):
    title = "金沢競馬場 出馬表 | 2026/11/23 9R ：楽天競馬"
    if wrong_date:
        title = title.replace("11/23", "11/24")
    heads = "".join("<th>"+x+"</th>" for x in
        ("枠番","馬番","あなたの予想","父馬 馬名 母馬","性齢","連対時馬体重",
         "馬体重増減","前5走","成績"))
    weights = ((482, 3, 466, 479), (431, -3, 430, 436),
               (498, 0, 490, 501), (None, None, 470, 490), (470, 2, None, None))
    lines = []
    for i, name in enumerate(NAMES, 1):
        current, delta, lo, hi = weights[i-1]
        text = (str(current)+ ("±0" if delta == 0 else
                f"{delta:+d}") if current is not None else "計不")
        range_text = (f"{lo}<p>|</p><p>{hi}</p>" if lo is not None
                      else "—")
        horse = "異なる馬" if wrong_name and i == 2 else name
        lines.append(
            f"<tr><td>{i}</td><td>{i}</td><td>-</td>"
            f"<td>父馬<p>{horse}</p>母馬</td><td>牡3</td>"
            f"<td>{range_text}</td><td>{text}</td><td>前走</td><td>実績</td></tr>"
        )
    return f"<html><head><title>{title}</title></head><body><table><thead><tr>{heads}</tr></thead><tbody>{''.join(lines)}</tbody></table></body></html>"


def result_html():
    heads = "<th>着順</th><th>枠</th><th>馬番</th><th>馬名</th>"
    rows = [f"<tr><td>{place}</td><th>{no}</th><td>{no}</td><td>{NAMES[no-1]}</td></tr>"
            for place, no in enumerate((1, 3, 2, 5, 4), 1)]
    return ("<html><head><title>金沢競馬場 競走成績 | 2026/11/23 9R ：楽天競馬"
            "</title></head><body><h3>■全着順</h3><table><thead><tr>"
            + heads + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></body></html>")


def test_exact_rakuten_url_and_horse_names():
    from core.race_odds import identity_from_result
    identity = identity_from_result(prediction())
    assert bw.racecard_url(identity, prediction().race_info) == URL
    rows = bw.parse_card(card_html(), URL, identity, prediction().race_info)
    assert len(rows) == 5
    assert rows[0]["name"] == "ニャンタロウ"
    assert rows[0]["current_kg"] == 482
    assert rows[0]["change_kg"] == 3
    assert rows[0]["paired_min_kg"] == 466
    assert rows[0]["paired_max_kg"] == 479
    assert rows[0]["band"] == "範囲外"
    assert rows[0]["distance_from_range_kg"] == 3
    assert rows[1]["band"] == "範囲内"
    assert rows[2]["change_kg"] == 0
    assert rows[3]["band"] == "判定不能"
    assert rows[4]["band"] == "判定不能"


def test_wrong_race_and_foreign_origin_fail_closed():
    from core.race_odds import identity_from_result
    ident = identity_from_result(prediction())
    for html, url in ((card_html(wrong_date=True), URL),
                      (card_html(), URL.replace("20261123","20261124")),
                      (card_html(), URL.replace("keiba.rakuten.co.jp", "unsafe.example"))):
        with pytest.raises(ValueError):
            bw.parse_card(html, url, ident, prediction().race_info)
    with pytest.raises(ValueError, match="照合が不足"):
        bw.parse_card(card_html(wrong_name=True).replace("ニャンタロウ","偽馬").replace(
            "ミライミライ","違う馬").replace("ハナノキ", "異名"), URL, ident, prediction().race_info)


def test_prestart_vs_poststart_observations_and_no_rank_mutations():
    result = prediction()
    original = view()
    untouched = deepcopy(original)
    early = bw.make_observation(result, original, URL, card_html(), now=TIME)
    late = bw.make_observation(result, original, URL, card_html(),
                               now=TIME + timedelta(hours=2))
    assert early["prestart_observed"] is True
    assert [r["sabcd"] for r in early["rows"]] == ["A","B","C","D","S"]
    assert late["prestart_observed"] is False
    assert all(r["sabcd"] is None for r in late["rows"])
    assert original == untouched
    book = bw.add_observation(bw.empty_book(), early)
    assert bw.add_observation(book, early) == book
    assert book != bw.add_observation(book, late)
    shown = _overlay(original, early)
    assert original == untouched
    assert shown[0]["nar_body_weight_research"]["band"] == "範囲外"
    assert "馬体重コンディション" in horse_detail_html(shown[0])
    assert "SABCD" in horse_detail_html(shown[0])
    assert _bodyweight_table(early)[0]["新SABCD"] == "A"
    assert shown[0]["mark"] == original[0]["mark"]
    assert shown[0]["rank"] == original[0]["rank"]


def test_result_is_separate_from_prestart_prediction_and_exact_race():
    from core.race_odds import identity_from_result
    ident = identity_from_result(prediction())
    finishes = bw.parse_result(result_html(), RESULT_URL, ident, prediction().race_info)
    assert finishes["1"] == 1 and finishes["3"] == 2 and finishes["2"] == 3
    early = bw.make_observation(prediction(), view(), URL, card_html(), now=TIME)
    late = bw.make_observation(prediction(), view(), URL, card_html(),
                               now=TIME + timedelta(hours=2))
    book = bw.add_observation(bw.add_observation(bw.empty_book(), early), late)
    before = deepcopy(book["races"][RID]["observations"])
    book = bw.attach_result(book, RID, finishes, source_url=RESULT_URL,
                            now=TIME + timedelta(hours=2))
    assert book["races"][RID]["observations"] == before
    rows = bw.cohort_rows(book)
    assert len(rows) == 3  # only horses with a saved grade AND usable range
    assert {x["horse_no"] for x in rows} == {1,2,3}
    assert {x["finish"] for x in rows} == {1,2,3}
    summary = bw.grade_summary(rows)
    a_out = next(x for x in summary if x["sabcd"] == "A" and x["band"] == "範囲外")
    assert a_out["count"] == 1 and a_out["win"] == 1
    b_in = next(x for x in summary if x["sabcd"] == "B" and x["band"] == "範囲内")
    assert b_in["top3"] == 1 and b_in["win"] == 0
    assert "未使用期間" in bw.heldout_value(rows)["message"]


def test_saved_study_book_import_merges_without_overwrite():
    quote = bw.make_observation(prediction(), view(), URL, card_html(), now=TIME)
    book = bw.add_observation(bw.empty_book(), quote)
    merged = bw.merge_book(bw.empty_book(), book)
    assert merged == book
    assert bw.merge_book(merged, book) == book
    with pytest.raises(ValueError):
        bw.merge_book(bw.empty_book(), {"schema": "other", "races": {}})
    modified = deepcopy(quote)
    modified["rows"][0]["current_kg"] = 399
    with pytest.raises(ValueError, match="ハッシュ"):
        bw.add_observation(bw.empty_book(), modified)


def test_no_live_request_to_arbitrary_domain_and_bounded_content():
    with pytest.raises(ValueError):
        bw.fetch_page("http://keiba.rakuten.co.jp/race_card/list/RACEID/a")
    with pytest.raises(ValueError):
        bw.fetch_page("https://evil.invalid/race_card/list/RACEID/a")


def test_heldout_brier_evaluation_is_only_a_report_not_grade_update():
    synthetic = []
    for day in range(20):
        for r in range(2):
            for no in range(5):
                band = "範囲内" if no < 3 else "範囲外"
                synthetic.append(dict(race_id=f"202611{day+1:02d}{r:02d}",
                                      race_date=f"202611{day+1:02d}", sabcd="A",
                                      band=band, finish=1 if no == 0 else 2 if no == 1 else 5))
    before = deepcopy(synthetic)
    out = bw.heldout_value(synthetic)
    assert out["status"] == "evaluated"
    assert out["train_days"] == 14 and out["test_days"] == 6
    assert out["weight_brier"] < out["base_brier"]
    assert synthetic == before
