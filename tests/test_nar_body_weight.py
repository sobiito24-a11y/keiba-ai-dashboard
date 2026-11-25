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



def test_urawa_race_3_same_frame_rows_are_not_dropped_and_missing_paired_keeps_weight():
    """Regression: 2026-11-25 Urawa 3R horses 6/8/10/12 omit frame TD."""
    horse_data = [
        (1, 1, "ニエリカ", 463, 2, 461, 461),
        (2, 2, "フルールバトル", 419, 2, None, None),
        (3, 3, "ウィズボンド", 456, -8, 464, 464),
        (4, 4, "オンブラドーロ", 490, 0, 490, 490),
        (5, 5, "ツガノヤマト", 499, 14, None, None),
        (5, 6, "スモモサンジョ", 421, -6, None, None),
        (6, 7, "ユウユウヒレシュ", 412, -1, None, None),
        (6, 8, "ノーブルフリージア", 493, -4, 491, 491),
        (7, 9, "ジーティーマルーン", 405, 15, 390, 390),
        (7, 10, "トーケンジンバック", 479, 21, 458, 458),
        (8, 11, "シナノダムール", 448, -4, 452, 452),
        (8, 12, "タカイチイーロン", 470, 0, None, None),
    ]
    identity = dict(mode="nar", race_id="202642112503", horses=[
        dict(horse_no=no, name=name) for _, no, name, *_ in horse_data
    ])
    info = dict(race_date="2026-11-25", racecourse="浦和")
    source_url = bw.racecard_url(identity, info)
    title = "浦和競馬場 出馬表 | 2026/11/25 3R ：楽天競馬"
    head = "".join(f"<th>{col}</th>" for col in (
        "枠番", "馬番", "あなたの予想", "父馬 馬名 母馬", "性齢",
        "連対時馬体重", "馬体重増減", "前5走", "成績"
    ))
    html_rows = []
    last_frame = None
    for frame, no, name, kg, delta, low, high in horse_data:
        frame_td = f"<td>{frame}</td>" if frame != last_frame else ""
        last_frame = frame
        band = f"{low}<p>|</p><p>{high}</p>" if low is not None else "-"
        change = "±0" if delta == 0 else f"{delta:+d}"
        html_rows.append(
            f"<tr>{frame_td}<td>{no}</td><td>-</td>"
            f"<td>父馬<p>{name}</p>母馬</td><td>牝2</td>"
            f"<td>{band}</td><td>{kg}{change}</td><td>前走</td><td>成績</td></tr>"
        )
    html = (f"<html><title>{title}</title><table><thead><tr>{head}</tr></thead>"
            f"<tbody>{''.join(html_rows)}</tbody></table></html>")
    rows = bw.parse_card(html, source_url, identity, info)
    assert len(rows) == 12
    assert [r["current_kg"] for r in rows] == [x[3] for x in horse_data]
    by_no = {r["horse_no"]: r for r in rows}
    for no, kg, delta in ((6, 421, -6), (8, 493, -4),
                          (10, 479, 21), (12, 470, 0)):
        assert by_no[no]["current_kg"] == kg
        assert by_no[no]["change_kg"] == delta
    for no in (6, 12):
        assert by_no[no]["paired_min_kg"] is None
        assert by_no[no]["paired_max_kg"] is None
    for no, low in ((8, 491), (10, 458)):
        assert by_no[no]["paired_min_kg"] == low


def test_rowspan_does_not_allow_a_wrong_saved_horse_name():
    """Wrong horse must stay unmatched rather than borrowing the prior frame."""
    from core.race_odds import identity_from_result
    identity = identity_from_result(prediction())
    html = card_html().replace("<tr><td>2</td><td>2</td>", "<tr><td>2</td>")
    html = html.replace("シャンパンスター", "異なる馬")
    rows = bw.parse_card(html, URL, identity, prediction().race_info)
    assert rows[1]["current_kg"] is None
    assert rows[0]["current_kg"] == 482


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


def test_one_click_research_ui_fetch_and_later_settlement_leave_prediction_unchanged(monkeypatch):
    from contextlib import nullcontext
    import sys
    from core import nar_body_weight_ui as ui

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {}
            self.pressed = set()
            self.notes = []
            self.displayed = []
        def markdown(self, *args, **kwargs): pass
        def caption(self, *args, **kwargs): pass
        def info(self, *args, **kwargs): self.notes.append(("info", args))
        def warning(self, *args, **kwargs): self.notes.append(("warning", args))
        def error(self, *args, **kwargs): self.notes.append(("error", args))
        def success(self, *args, **kwargs): self.notes.append(("success", args))
        def expander(self, *args, **kwargs): return nullcontext()
        def spinner(self, *args, **kwargs): return nullcontext()
        def file_uploader(self, *args, **kwargs): return None
        def download_button(self, *args, **kwargs): return False
        def dataframe(self, data, **kwargs): self.displayed.append(data)
        def button(self, label, **kwargs):
            return label in self.pressed and not kwargs.get("disabled")

    class Clock:
        today = TIME
        @classmethod
        def now(cls, zone):
            return cls.today

    streamlit = FakeStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    monkeypatch.setattr(ui, "datetime", Clock)
    calls = []
    def fetch(url):
        calls.append(url)
        return result_html() if "/race_performance/" in url else card_html()
    monkeypatch.setattr(ui.bw, "fetch_page", fetch)

    result = prediction()
    original = view()
    frozen = deepcopy(original)
    streamlit.pressed = {"当日馬体重を更新"}
    shown = ui.render(result, original)
    assert calls == [URL]
    assert original == frozen and result.overall_table.shape[0] == 5
    assert shown[0]["nar_body_weight_research"]["current_kg"] == 482
    assert shown[0]["rank"] == original[0]["rank"]
    book = streamlit.session_state["nar_body_weight_book_v1"]
    assert len(book["races"][RID]["observations"]) == 1
    assert book["races"][RID]["result"] is None

    Clock.today = TIME + timedelta(hours=2)
    streamlit.pressed = {"楽天競馬の確定着順を取得"}
    ui.render(result, original)
    assert calls == [URL, RESULT_URL]
    book = streamlit.session_state["nar_body_weight_book_v1"]
    assert book["races"][RID]["result"]["finishes"]["1"] == 1
    assert len(bw.cohort_rows(book)) == 3
    assert original == frozen


def test_selected_horse_detail_escapes_research_only_data():
    from core.nar_body_weight_ui import horse_detail_html
    h = {"mode": "nar", "nar_body_weight_research": {
        "current_kg": 450, "change_kg": -4, "paired_min_kg": 440,
        "paired_max_kg": 452, "band": "<script>alert(1)</script>",
        "prestart_observed": False,
    }}
    html = horse_detail_html(h)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "発走前と未確認" in html
