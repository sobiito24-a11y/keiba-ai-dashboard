"""JRA official bodyweight: race identity, 1-2 finishes and read-only UI."""
from copy import deepcopy

import pytest

from core import jra_body_weight as bw
from core.race_explorer_ui import _cell
from core.race_explorer_columns import columns, records


RID = "202608050511"
INFO = {"race_date": "2026-11-21", "racecourse": "京都"}
URL = "https://www.jra.go.jp/JRADB/accessD.html?CNAME=pw01dde0108202605051120261121/25"


def identity():
    return {"race_id": RID, "mode": "jra", "horses": [
        {"horse_no": 1, "name": "保存馬A"},
        {"horse_no": 2, "name": "保存馬B"},
        {"horse_no": 3, "name": "保存馬C"},
        {"horse_no": 4, "name": "除外馬D"},
    ]}


def _runner(no, name, today, past):
    td = "".join("<td>" + text + "</td>" for text in past)
    return f"<tr><td>枠</td><td>{no}</td><td>{name}<p>{today}</p><p>馬主</p></td>" \
           f"<td>牡3</td>{td}</tr>"


def page(*, wrong_name=False, wrong_header=False):
    heads = ("枠", "馬番", "馬名 / 単勝オッズ(人気) 馬体重",
             "性齢 / 毛色", "前走", "前々走", "3走前", "4走前")
    title = "出馬表2026年11月21日（土曜）5回京都5日 11レース"
    if wrong_header:
        title = title.replace("11レース", "12レース")
    a = _runner(1, "保存馬A", "501kg(+4)", [
        "<p>1着</p><p>498kg</p>", "<p>3着</p><p>490kg</p>",
        "<p>2着</p><p>496kg</p>", "<p>12着</p><p>502kg</p>"])
    b = _runner(2, "別馬B" if wrong_name else "保存馬B", "468kg(-2)", [
        "<p>3着</p><p>460kg</p>", "<p>8着</p><p>455kg</p>", "", ""])
    c = _runner(3, "保存馬C", "488kg(初出走)", ["", "", "", ""])
    excluded = _runner("除外", "除外馬D", "計不", ["", "", "", ""])
    return ("<html><h1>" + title + "</h1><table><thead><tr>"
            + "".join("<th>" + head + "</th>" for head in heads)
            + "</tr></thead><tbody>" + a+b+c+excluded + "</tbody></table></html>")


def test_official_card_url_computed_against_published_jra_pages():
    assert bw.official_card_url(identity(), INFO) == URL
    examples = [
        ("202605050511", "2026-11-22", "東京", "04"),
        ("202605060511", "2026-11-23", "東京", "34"),
    ]
    for rid, date, venue, checksum in examples:
        ident = {"race_id": rid, "mode": "jra", "horses": [{"horse_no": 1, "name": "保存馬A"}]}
        url = bw.official_card_url(ident, {"race_date": date, "racecourse": venue})
        assert url.endswith(f"/{checksum}")


def test_parser_current_change_kept_with_no_paired_finish():
    rows = bw.parse_card(page(), URL, identity(), INFO)
    assert len(rows) == 4
    assert rows[0]["current_kg"] == 501
    assert rows[0]["change_kg"] == 4
    assert (rows[0]["paired_min_kg"], rows[0]["paired_max_kg"]) == (496, 498)
    assert rows[1]["current_kg"] == 468 and rows[1]["change_kg"] == -2
    assert rows[1]["paired_min_kg"] is None and rows[1]["paired_max_kg"] is None
    assert rows[2]["current_kg"] == 488 and rows[2]["change_label"] == "初出走"
    assert rows[2]["paired_min_kg"] is None
    assert rows[3]["current_kg"] is None  # official card says excluded without a number


@pytest.mark.parametrize("bad_html,bad_url", [
    (page(wrong_name=True), URL),
    (page(wrong_header=True), URL),
    (page(), URL.replace("1120261121", "1220261121")),
])
def test_fail_closed_on_wrong_name_race_or_header(bad_html, bad_url):
    with pytest.raises(ValueError):
        bw.parse_card(bad_html, bad_url, identity(), INFO)


def test_overlay_is_read_only_and_never_changes_ranks_or_marks():
    view = [
        {"no": str(i), "name": name, "mode": "jra", "rank": i,
         "mark": "◎" if i == 1 else "—", "unified_sabcd": {"grade": "A"}}
        for i, name in enumerate(("保存馬A", "保存馬B", "保存馬C", "除外馬D"), 1)
    ]
    snapshot = deepcopy(view)
    observation = dict(race_id=RID, retrieved_at="2026-11-21T14:00:00+09:00",
                       source_url=URL, prestart_observed=True,
                       rows=bw.parse_card(page(), URL, identity(), INFO))
    out = bw.overlay(view, observation)
    assert out is not view and view == snapshot
    assert out[1]["rank"] == 2 and out[1]["unified_sabcd"] == {"grade": "A"}
    assert out[1]["jra_body_weight_research"]["current_kg"] == 468


@pytest.mark.parametrize("key", ["nar_body_weight", "jra_body_weight"])
def test_without_paired_history_shows_current_and_dash(key):
    data = {key: 468, key+"_change": -2,
            key+"_min": None, key+"_max": None}
    html = _cell({"no": "2"}, data, key)
    assert "468" in html and "(-2)" in html
    assert 'nar-bodyweight-paired">-</small>' in html
    missing = dict(data, **{key: None})
    html = _cell({"no": "2"}, missing, key)
    assert "未取得" in html and 'nar-bodyweight-paired">-</small>' in html


def test_table_has_jra_weight_immediately_after_popularity():
    view = [{"mode": "jra"}]
    visible = [spec["key"] for spec in columns(view) if not spec.get("table_hidden")]
    assert visible.index("jra_body_weight") == visible.index("popularity") + 1
    assert "nar_body_weight" not in visible
