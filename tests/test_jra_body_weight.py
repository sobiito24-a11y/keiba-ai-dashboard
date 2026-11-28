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


# Regression for 2026-11-28: 8R has public weights while 10-12R
# may legitimately have a valid racecard but no published weights yet.
def _nov28():
    rid = "202608050708"  # Kyoto fifth meeting, seventh day, 8R
    info = {"race_date": "2026-11-28", "racecourse": "京都"}
    ident = identity()
    ident["race_id"] = rid
    html = page().replace(
        "2026年11月21日（土曜）5回京都5日 11レース",
        "2026年11月28日（土曜）5回京都7日 8レース")
    return ident, info, html


def test_nov28_live_official_url_checksums():
    ident, info, _html = _nov28()
    assert bw.official_card_url(ident, info).endswith(
        "pw01dde0108202605070820261128/D7")
    for rid, code in [("202608050710", "81"), ("202608050712", "EB"),
                      ("202605050701", "06")]:
        sample = dict(ident, race_id=rid)
        local = dict(info, racecourse="東京" if rid.startswith("202605") else "京都")
        assert bw.official_card_url(sample, local).endswith("/" + code)


def test_prepublication_still_parses_exact_horses_and_paired_history():
    ident, info, html = _nov28()
    url = bw.official_card_url(ident, info)
    html = html.replace("501kg(+4)", "").replace("468kg(-2)", "").replace("488kg(初出走)", "")
    rows = bw.parse_card(html, url, ident, info)
    assert bw._retrieval_status(rows) == "unpublished"
    assert all(h["current_kg"] is None for h in rows)
    assert rows[0]["paired_min_kg"] == 496
    assert rows[0]["paired_max_kg"] == 498
    assert rows[1]["paired_min_kg"] is None


def test_automatic_fallback_to_second_official_jra_host_without_guessed_data():
    import asyncio
    from datetime import datetime

    ident, info, html = _nov28()
    calls = []

    class Response:
        def __init__(self, status, content):
            self.status_code = status
            self.content = content

    def get(url, **kwargs):
        calls.append(url)
        assert kwargs["allow_redirects"] is False
        if url.startswith("https://www.jra.go.jp/"):
            return Response(403, b"blocked")
        return Response(200, html.encode("utf-8"))

    observed = asyncio.run(bw.fetch_once(
        ident, info, now=datetime(2026, 11, 28, 13, 45, tzinfo=bw.JST),
        request_get=get, browser_fallback=False))
    assert len(calls) == 2
    assert observed["source_url"].startswith("https://jra.jp/")
    assert observed["publication_status"] == "published"
    assert observed["current_count"] == 3
    assert observed["rows"][0]["current_kg"] == 501
    assert observed["rows"][1]["current_kg"] == 468


def test_valid_racecard_without_current_weights_reports_unpublished():
    import asyncio
    from datetime import datetime

    ident, info, html = _nov28()
    html = html.replace("501kg(+4)", "").replace("468kg(-2)", "").replace("488kg(初出走)", "")

    class Response:
        status_code = 200
        content = html.encode("utf-8")

    observation = asyncio.run(bw.fetch_once(
        ident, info, now=datetime(2026, 11, 28, 13, 5, tzinfo=bw.JST),
        request_get=lambda *_args, **_kwargs: Response(),
        browser_fallback=False))
    assert observation["publication_status"] == "unpublished"
    assert observation["current_count"] == 0
    assert len(observation["rows"]) == 4
    # Past winning weights may be shown even when today's weight is absent.
    assert observation["rows"][0]["paired_min_kg"] == 496


def test_official_http_failure_reports_source_instead_of_false_success():
    import asyncio
    from datetime import datetime

    ident, info, _html = _nov28()

    class Denied:
        status_code = 403
        content = b"blocked"

    with pytest.raises(ValueError, match="HTTP 403"):
        asyncio.run(bw.fetch_once(
            ident, info, now=datetime(2026, 11, 28, 13, 5, tzinfo=bw.JST),
            request_get=lambda *_args, **_kwargs: Denied(),
            browser_fallback=False))


def test_kyoto7_nov28_cached_zero_then_live_18_retries_other_official_host():
    """Regression for screenshot: Kyoto 7R 13:19 showed 0/18 with published data."""
    import asyncio
    from datetime import datetime

    names_weights = [
        ("カラペルソナ", "446kg(+6)"),
        ("コスモフィレンツェ", "496kg(+14)"),
        ("スマートティアナ", "410kg(-6)"),
        ("スノースケープ", "474kg(+6)"),
        ("ラッキーストーン", "502kg(+2)"),
        ("ニシノマルガリート", "436kg(-6)"),
        ("フィングステン", "480kg(+6)"),
        ("アイスヴィレッジ", "506kg(-6)"),
        ("ペイシャシス", "400kg(+4)"),
        ("ブランドブラン", "502kg(+2)"),
        ("トップオンザヒル", "470kg(-4)"),
        ("ジャストビート", "436kg(+6)"),
        ("ブルーミングローズ", "480kg(+8)"),
        ("アドマイヤシュラ", "440kg(-10)"),
        ("アージュドール", "436kg(+6)"),
        ("ゴーゴータカシ", "486kg(0)"),
        ("マイネルビスマルク", "504kg(+6)"),
        ("アレンテージョ", "498kg(+18)"),
    ]
    ident = {"race_id": "202608050707", "mode": "jra", "horses": [
        {"horse_no": n, "name": name} for n, (name, _kg) in enumerate(names_weights, 1)
    ]}
    info = {"race_date": "2026-11-28", "racecourse": "京都", "start_time": "13:25"}
    url = bw.official_card_url(ident, info)
    assert url.endswith("pw01dde0108202605070720261128/22")
    headers = ["枠", "馬番", "馬名 / 馬体重", "性齢", "前走", "前々走", "3走前", "4走前"]
    head = "".join(f"<th>{h}</th>" for h in headers)
    heading = "<h1>出馬表2026年11月28日（土曜）5回京都7日 7レース</h1>"

    def card(with_current):
        trs = []
        for number, (name, kg) in enumerate(names_weights, 1):
            weight = kg if with_current else ""
            trs.append(_runner(number, name, weight, ["", "", "", ""]))
        return (f"<html>{heading}<table><thead><tr>{head}</tr></thead>"
                f"<tbody>{''.join(trs)}</tbody></table></html>").encode("utf-8")

    class Response:
        def __init__(self, content):
            self.status_code = 200
            self.content = content

    calls = []

    def get(url, **kwargs):
        calls.append(url)
        assert kwargs["headers"]["Cache-Control"].startswith("no-cache")
        if url.startswith("https://www.jra.go.jp/"):
            # Old cached response was still a valid 18-horse page.
            return Response(card(False))
        return Response(card(True))

    result = asyncio.run(bw.fetch_once(
        ident, info, now=datetime(2026, 11, 28, 13, 19, tzinfo=bw.JST),
        request_get=get, browser_fallback=False))
    assert len(calls) == 2
    assert result["current_count"] == 18
    assert result["publication_status"] == "published"
    assert result["rows"][0]["current_kg"] == 446
    assert result["rows"][1]["current_kg"] == 496
    assert result["rows"][17]["change_kg"] == 18
    assert result["prestart_observed"] is True


def test_kyoto7_zero_on_both_hosts_is_uncertain_not_proof_of_nonpublication():
    import asyncio
    from datetime import datetime

    ident, info, html = _nov28()
    html = html.replace("501kg(+4)", "").replace("468kg(-2)", "").replace("488kg(初出走)", "")

    class Response:
        status_code = 200
        content = html.encode("utf-8")

    calls = []
    def get(url, **kwargs):
        calls.append(url)
        return Response()

    result = asyncio.run(bw.fetch_once(
        ident, info, now=datetime(2026, 11, 28, 13, 19, tzinfo=bw.JST),
        request_get=get, browser_fallback=False))
    assert len(calls) == 2
    assert result["publication_uncertain"] is True
    assert result["current_count"] == 0
