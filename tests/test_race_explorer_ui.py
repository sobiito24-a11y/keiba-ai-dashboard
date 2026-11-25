from copy import deepcopy
import json

from bs4 import BeautifulSoup
import pytest

from core.final_candidate_selection import formal_score
from core.game_race_ui import build_view, document, frame_number
from core.prediction_table_ui import prediction_table_records
from core.race_explorer_common import index_html, number_badge, value
from core.race_explorer_columns import columns
from core.race_explorer_ui import lineup_html


def field(mode='jra', count=9):
    info = dict(race_id='202610220101', race_date='2026-10-22',
                venue='東京', surface='ダート', distance=1600)
    rows = [dict(馬番=i, 馬名=f'保存馬{i}', 枠番=(i % 8) + 1,
                 jra_top5_score=100 - i + .25, jra_top5_rank=i,
                 nar_top5_order_score=100 - i + .25,
                 nar_final_rank=i if i <= 5 else None,
                 pure_ability_top5_group=i <= 5,
                 ver3_ability_core=85 - i, market_ability_rank=i,
                 netkeiba_corner4_rank=i, netkeiba_running_style='先',
                 netkeiba_pace='M', 距離指数=80 - i, コース指数=70 - i,
                 平均指数=60 - i, 最高指数=75 - i,
                 _past_runs=[dict(label=label, race_date=day, racecourse='東京',
                                  surface='ダート', distance=1600, position=finish,
                                  value=score, turn='左')
                             for label, day, finish, score in [
                                 ('前走', '2026-10-01', 2, 60 - i),
                                 ('2走前', '2026-09-01', 3, 65 - i),
                                 ('3走前', '2026-08-01', 4, 70 - i)]])
            for i in range(1, count + 1)]
    records = prediction_table_records(rows, rows, info, mode)
    return rows, records, info, build_view(rows, records, rows, mode, info)


@pytest.mark.parametrize('mode,count', [(mode, count) for mode in ('jra','nar') for count in (12,16,18)])
def test_normal_layout_full_field_manual_checks_and_source_nonmutation(mode, count):
    rows, records, info, view = field(mode, count)
    saved = deepcopy((rows, records, info, view))
    # Deliberately scramble input order; the main table starts in horse order.
    shown = list(reversed(view))
    doc = BeautifulSoup(document(shown, info['race_id']), 'html.parser')
    assert (rows, records, info, view) == saved
    section_order = [heading.text for heading in doc.select(
        '.overview-accordion > summary .overview-title, #lineup-workspace h2')]
    assert section_order == ['レースピックアップ', 'レース展開予想', '純能力の見える化', '全頭予想・比較一覧']
    overviews=doc.select('details.overview-accordion')
    assert [panel['id'] for panel in overviews]==['race-pickup','race-development','race-ability']
    for panel in overviews:
        assert not panel.has_attr('open') and not panel.has_attr('name')
        assert panel.has_attr('data-persist-panel')
        summary=panel.select_one('summary')
        assert summary.select_one('.overview-description').text.strip()
        assert not summary.select('[data-horse-open], .number-badge, .metric-number')
        assert all(horse['name'] not in summary.text for horse in view)
    lineup = doc.select_one('#lineup-workspace')
    runners = lineup.select('tbody tr[data-horse]')
    assert [row['data-horse'] for row in runners] == [str(i) for i in range(1, count + 1)]
    checks = lineup.select('input[type="checkbox"][data-user-check]')
    assert len(checks) == count
    assert all(not check.has_attr('checked') and check.has_attr('aria-label') for check in checks)
    assert [option['value'] for option in lineup.select('#lineup-filter option')] == ['all', 'selected']
    assert lineup.select_one('#clear-user-selection').text == '選択クリア'
    assert not lineup.select_one('#lineup-sort option').has_attr('disabled')
    assert lineup.select_one('#lineup-sort option')['value'] == 'no'
    assert lineup.select_one('.explorer-table-scroll')['tabindex'] == '0'
    for row in runners:
        assert len(row.select('.col-user,.col-number,.col-name')) == 3
        assert row.select_one('.col-name button[data-horse-open]')['data-horse-open'] == row['data-horse']
    headers = [header.select_one('.column-label').text for header in lineup.select('th')]
    assert headers[headers.index('3走前'):headers.index('3走前')+5] == ['3走前', '2走前', '前走', '3走平均', '★最高指数']
    assert ('調教' in headers) == (mode == 'jra')
    if mode == 'jra':
        assert headers.index('調教') == headers.index('脚質・位置') + 1
    assert '同場同距離指数' not in headers
    assert 'オッズ単複' in headers and '脚質・位置' in headers
    assert headers[-1] == 'AI評価メモ'
    assert '4角想定' not in headers and '序盤傾向' not in headers
    specs=columns(view)
    keys=[spec['key'] for spec in specs]
    table_keys=[spec['key'] for spec in specs if not spec.get('table_hidden')]
    assert [header['data-column'] for header in lineup.select('th')]==table_keys
    assert [button['data-column-sort'] for button in lineup.select('[data-column-sort]')]==table_keys
    assert [button['data-column-filter'] for button in lineup.select('[data-column-filter]')]==table_keys
    assert [option['value'] for option in lineup.select('#filter-column option')]==keys
    assert {option['value'] for option in lineup.select('#lineup-sort option')}==set(keys)
    assert 'rank' not in table_keys
    assert 'rank' in keys
    assert not {'ability_rank','distance_rank','course_rank'}.intersection(table_keys)
    assert headers.index('純能力指数') == headers.index('統合SABCD') + 1
    assert not lineup.select('.col-rank')
    assert 'rank' in keys
    assert 'age' not in table_keys and 'age' in keys
    assert {'ability_rank','distance_rank','course_rank'}.issubset(keys)
    assert not {'score','reference_score'}.intersection(keys)
    assert all(len(row.select('td'))==len(headers) for row in runners)
    assert lineup.select_one('#filter-min')['type']=='number'
    assert lineup.select_one('#filter-max')['type']=='number'
    assert lineup.select_one('#filter-text')['type']=='search'
    assert lineup.select_one('#clear-column-filters') and lineup.select_one('#active-column-filters')
    assert not lineup.select_one('#lineup-filters').has_attr('open')


@pytest.mark.parametrize('mode', ['jra', 'nar'])
def test_normal_workspace_hides_final_scores_and_shows_ten_independent_analyses(mode):
    _, _, info, view = field(mode)
    # Retaining saved B data must never make it the normal displayed model.
    for horse in view:
        horse['active_model'] = 'A'
        horse['model_b'] = {'score': 9999, 'rank': 1, 'version': 'saved-research'}
        horse['mark'] = '◎'
        horse['explorer_facts'].update(plus=['○ 保存済みの距離実績'], caution=['△ 保存済みの状態材料'])
    before = deepcopy(view)
    doc = BeautifulSoup(document(view, info['race_id']), 'html.parser')
    payload = json.loads(doc.select_one('#race-data').string)
    assert payload['active_model'] == 'A'
    assert payload['experience'] == 'race-comparison'
    assert [horse['sort']['score'] for horse in payload['horses']] == [formal_score(horse) for horse in view]
    assert payload['columns']==columns(view)
    assert all(horse['values']['user'] is False for horse in payload['horses'])
    assert [horse['values']['score'] for horse in payload['horses']]==[formal_score(horse) for horse in view]
    table_rows = doc.select('#lineup-workspace tr[data-horse]')
    assert not doc.select('.col-score,.col-reference_score')
    assert not doc.select('#lineup-workspace .col-rank')
    assert '旧正式順位（比較用）' in doc.get_text()
    assert not doc.select('#lineup-sort option[value="score"],#filter-column option[value="reference_score"]')
    assert all('最終評価' not in row.get_text() for row in table_rows)
    analyses = doc.select_one('details#detail-analysis')
    assert not analyses.has_attr('open')
    assert len(analyses.select('[role="tab"]')) == 10
    assert [tab['data-tab'] for tab in analyses.select('[role="tab"]')] == [
        'corner', 'ability', 'course', 'distance', 'training',
        'star', 'away', 'average', 'materials', 'changes']
    assert len(payload['tabs']) == 10
    assert '最終候補' not in analyses.get_text() and '新AI総合' not in analyses.get_text()
    assert all(detail.find_parent(id='detail-analysis') is not None for detail in doc.select('.metric-comparison'))
    for section in (doc.select_one('#lineup-workspace'), doc.select_one('#race-pickup')):
        assert not section.select('.mark,.focus-badge,.medal-card,.candidate-group')
        for rank in section.select('.metric-rank'):
            rank.extract()  # Index ranks are distinct from hidden formal marks.
        assert not any(mark in section.text for mark in ('◎', '○', '▲', '✔', '△'))
    # Material stays out of the main table and is available in the selected detail.
    assert '保存済みの距離実績' not in doc.select_one('#lineup-workspace').text
    assert any('保存済みの距離実績' in card for card in payload['cards'])
    assert not doc.select('input[name="research-model"], [data-model-switch]')
    assert view == before


def test_names_in_html_and_embedded_detail_json_remain_escaped():
    _, _, _, view = field(count=1)
    name = '</script><img src=x onerror="bad()">'
    view[0]['name'] = name
    view[0]['explorer_facts']['stable_comment_raw'] = '<script>bad()</script>\nコメント全文'
    doc = BeautifulSoup(document(view, 'race</script>key'), 'html.parser')
    assert not doc.select('img,[onerror],[onclick]')
    assert len(doc.select('script')) == 2
    payload = json.loads(doc.select_one('#race-data').string)
    assert payload['names'] == ['1 ' + name]
    detail = BeautifulSoup(payload['cards'][0], 'html.parser')
    assert not detail.select('script,img')
    assert name in detail.text
    assert detail.select_one('.detail-comment-original').text == '<script>bad()</script>\nコメント全文'
    assert 'horse-detail-1' == doc.select_one('#lineup-workspace [data-horse-open]')['aria-controls']


@pytest.mark.parametrize('raw', [float('inf'), -float('inf'), 'INF', '-Infinity', 'NaN'])
def test_common_values_never_display_nonfinite_indices(raw):
    assert value(raw) == '未取得'
    assert '未取得' in index_html({'value': raw, 'rank': 1})
    assert '位' not in index_html({'value': 50, 'rank': 1.5})
    assert '未取得' in index_html('invalid saved metric')


@pytest.mark.parametrize('aliases,expected', [
    ({'枠番': 3}, 3), ({'枠番': 3, 'frame_no': 3}, 3),
    ({'枠番': 3, 'frame_no': 4}, None),
    ({'枠番': 3, 'frame_no': 9}, None),
    ({'枠番': 3, 'frame_no': True}, None),
    ({'frame_no': 0}, None), ({'frame_no': 2.5}, None),
    ({'馬番': 8}, None), ({'枠番': None}, None),
])
def test_frame_aliases_are_explicit_consistent_and_in_range(aliases, expected):
    assert frame_number(aliases) == expected
    badge = BeautifulSoup(number_badge({'no': '18', 'frame': frame_number(aliases)}), 'html.parser').span
    assert badge.has_attr('style') == (expected is not None)


def test_verified_uploaded_frame_only_fills_missing_metadata_and_never_conflict():
    row = dict(馬番=1, 馬名='保存馬1')
    records = prediction_table_records([row], [row], {}, 'jra')
    frames = {'1': dict(frame=8, name='保存馬1')}
    assert build_view([row], records, [row], 'jra', frames=frames)[0]['frame'] == 8
    assert build_view([row], records, [row], 'jra', frames={'1': dict(frame=8, name='別馬')})[0]['frame'] is None
    for aliases in ({'枠番': 3, 'frame_no': 4}, {'枠番': 3, 'frame_no': 9}):
        conflicting = dict(row, **aliases)
        before = deepcopy((conflicting, frames))
        shown = build_view([conflicting], records, [conflicting], 'jra', frames=frames)
        assert shown[0]['frame'] is None
        assert (conflicting, frames) == before
    original, displayed = dict(row, 枠番=3), dict(row, 枠番=4)
    assert build_view([displayed], records, [original], 'jra', frames=frames)[0]['frame'] is None


def test_empty_main_table_has_controls_and_safe_header():
    doc = BeautifulSoup(lineup_html([]), 'html.parser')
    assert not doc.select('tr[data-horse], input[data-user-check]')
    assert doc.select_one('#lineup-filter')
    assert '全0頭' in doc.text


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_research_sabcd_does_not_change_real_view_formal_marks_and_scores(mode):
    from core.race_explorer_columns import records as projected_records
    rows, original, info, view = field(mode, 12)
    assert len(view)==12
    assigned=[h.get("research_sabcd",{}) for h in view]
    assert all("version" in tier for tier in assigned)
    assert all(t.get("grade")==t.get("raw_grade") and not t.get("demoted")
               for t in assigned if t.get("grade") is not None)
    assert all(t.get("score") is None or 0 <= t["score"] <= 1
               for t in assigned)
    assert all(t.get("retro") for t in assigned)  # 2026-10-22 was in fit period
    cells=projected_records(view)
    headers=[s["key"] for s in columns(view) if not s.get("table_hidden")]
    assert headers[headers.index("research_sabcd")+1] == "ability"
    assert headers[headers.index("ability")+1] == "style"
    assert ("training" in headers) == (mode == "jra")
    if mode == "jra":
        assert headers.index("training") == headers.index("style") + 1
    assert headers[-2:] == ["class_attention", "ai_memo"]
    assert "research_sabcd_weight_class" not in headers
    assert "research_sabcd_old" not in headers
    assert "research_sabcd_sort" not in headers
    assert "research_sabcd_reason" not in headers
    for horse in view:
        item=cells[str(horse["no"])]
        assert item["research_sabcd"] in ("S", "A", "B", "C", "D", None)
        assert item["research_sabcd_weight_class"] in ("S", "A", "B", "C", "D", None)
        assert item["research_sabcd"] == horse["unified_sabcd"].get("grade")
        assert item["unified_sabcd_rank"] == horse["unified_sabcd"].get("rank")
        assert item["research_sabcd_old"] == horse["research_sabcd"].get("grade")
        if item["research_sabcd"]:
            assert "購入推奨" in item["research_sabcd_reason"]
    snapshot=deepcopy((rows,original))
    html=BeautifulSoup(document(view, info["race_id"]), "html.parser")
    # The research letter is display-only and not part of the official
    # prediction table or stored records.
    assert html.select_one("th.col-research_sabcd .column-label").text=="統合SABCD"
    assert html.select("#lineup-workspace td.col-research_sabcd")
    assert not html.select("#lineup-workspace td.col-research_sabcd_weight_class")
    assert html.select_one(".detail-basic") or html.select_one("#detail-analysis")
    assert (rows,original)==snapshot


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_research_grade_tints_only_its_cell_in_normal_and_postrace_tables(mode):
    from core.postrace_review_ui import review_html
    rows, saved, info, view = field(mode, 12)
    original = deepcopy((rows, saved))
    tiers = ("S", "A", "B", "C", "D", None)
    for horse, tier in zip(view, tiers):
        # Test the *visual layer*, not the model allocation or official marks.
        horse["unified_sabcd"] = {
            "grade": tier, "reason": "統合研究表示のみ", "retro": False,
            "strength": .45,
        }
    normal = BeautifulSoup(lineup_html(view), "html.parser")
    review = BeautifulSoup(
        review_html(view, {"race_id": info["race_id"], "runners": [],
                           "payouts": [], "source": "検証用"}), "html.parser"
    )
    for document, parent in ((normal, "#lineup-workspace"),
                             (review, "#postrace-review")):
        trs = document.select(parent + " .explorer-table tbody tr")
        trs = [tr for tr in trs if tr.select_one("td.col-research_sabcd")]
        for index, tier in enumerate(tiers):
            cell = trs[index].select_one("td.col-research_sabcd")
            assert cell is not None
            assert not any("research-tier-" in cls for cls in trs[index].get("class", []))
            if tier:
                assert "research-tier-" + tier in cell.get("class", [])
                assert cell.select_one(".research-sabcd-" + tier).text == tier
                assert cell.select_one(".research-sabcd-label") is None
                # Do not mistake a single positive factor for a grade-level
                # explanation: D can have jockey fitness but remains D.
                assert "騎手適性" not in cell.text and "中位×4角前" not in cell.text
            else:
                assert not any("research-tier-" in cls for cls in cell.get("class", []))
                assert "判定不可" in cell.text
            assert all(
                not any(cls.startswith("research-tier-") for cls in other.get("class", []))
                for other in trs[index].select("td:not(.col-research_sabcd)")
            )
    assert (rows, saved) == original


def test_research_grade_palette_covers_both_tables_without_changing_marks():
    from core.game_race_ui import ASSETS
    css = (ASSETS / "race_comparison.css").read_text(encoding="utf-8")
    for tier in "SABCD":
        normal = ".race-explorer .explorer-table tbody tr td.col-research_sabcd.research-tier-" + tier
        review = "#postrace-review .postrace-review-scroll .explorer-table tbody tr td.col-research_sabcd.research-tier-" + tier
        assert normal in css
        assert review in css
        assert ".research-sabcd-" + tier in css
    assert "background:#e6f4ec!important" in css  # S: subtle green
    assert "background:#e8f2fc!important" in css  # A: subtle blue
    assert "background:#fff3dd!important" in css  # B: subtle amber
    assert "background:#f0f3f6!important" in css  # C: grey
    assert "background:#f9eaea!important" in css  # D: light coral


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_retrospective_grade_label_is_explicit_and_explained(mode):
    rows, saved, info, view = field(mode, 9)
    for horse in view:
        horse["research_sabcd_weight_class"] = {
            "grade": "A", "reason": "斤量・クラスで評価。過去開催で再計算",
            "score": .55, "retro": True,
        }
        horse["unified_sabcd"] = {
            "grade": "A", "reason": "統合研究。過去開催で再計算",
            "strength": .55, "retro": True,
        }
    html = BeautifulSoup(lineup_html(view), "html.parser")
    # Provenance belongs in a single lineup note and in the grade tooltip,
    # never as repeated bait-like text beneath every S/A/B/C/D badge.
    assert html.select_one("#lineup-workspace td.col-research_sabcd .research-sabcd-retro") is None
    cell = html.select_one("#lineup-workspace td.col-research_sabcd")
    grade = cell.select_one(".research-sabcd")
    assert grade.text == "A"
    assert "後日算出" in grade.get("title")
    assert "発走前の当時予想ではありません" in grade.get("title")
    assert "後付け" not in cell.text
    assert "後日算出が含まれます" in html.get_text()


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_paper_running_style_four_boxes_and_saved_positions(mode):
    _, _, info, view = field(mode, count=3)
    for horse, style, start, corner in zip(
            view, ("逃げ", "差し", "—"), (2, 8, None), (4, 10, None)):
        horse["style"] = style
        horse["start_rank"] = start
        horse["corner"] = corner
        if isinstance(horse.get("final_metrics"), dict):
            horse["final_metrics"]["style"] = style
            horse["final_metrics"]["corner"] = corner
        facts = horse.get("explorer_facts") or {}
        if isinstance(facts.get("metrics"), dict):
            facts["metrics"]["style"] = style
            facts["metrics"]["corner"] = corner
    before = deepcopy(view)
    doc = BeautifulSoup(document(view, info["race_id"]), "html.parser")
    heads = [cell.get("data-column") for cell in doc.select("#lineup-workspace th")]
    assert heads.index("research_sabcd") < heads.index("ability") < heads.index("style")
    assert "star" not in heads and "away" not in heads
    assert "place_odds" not in heads and "corner" not in heads
    for no, idx, position in ((1, 0, "序盤2 / 4角4"),
                              (2, 2, "序盤8 / 4角10"),
                              (3, None, "序盤— / 4角—")):
        row = doc.select_one(f'#lineup-workspace tr[data-horse="{no}"]')
        assert row is not None
        squares = row.select(".col-style .running-style-square")
        assert len(squares) == 4
        active = [i for i, span in enumerate(squares)
                  if "running-style-square-active" in span.get("class", [])]
        assert active == ([] if idx is None else [idx])
        assert position in row.select_one(".col-style .running-style-position").text
    assert view == before


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_one_compact_odds_column_retains_exact_win_and_place_values(mode):
    _, _, info, view = field(mode, count=2)
    for horse in view:
        horse["sort_values"]["place_odds_low"] = 1.2
        horse["sort_values"]["place_odds_high"] = 2.3
    before=deepcopy(view)
    doc=BeautifulSoup(document(view,info["race_id"]),"html.parser")
    headers=doc.select("#lineup-workspace th[data-column]")
    assert len([x for x in headers if x["data-column"]=="odds"])==1
    assert not doc.select("#lineup-workspace th.col-place_odds")
    first=doc.select_one('#lineup-workspace tr[data-horse="1"] .col-odds')
    assert first.select_one(".odds-both-cell .metric-number")
    assert "複 1.2〜2.3倍" in first.get_text(" ",strip=True)
    assert view==before


def test_formal_rank_never_inferred_from_sabcd_or_ability():
    from core.race_explorer_ui import _cell
    h = {"no": 8, "name": "保存馬8", "mode": "nar"}
    assert "判定不可" in _cell(h, {"rank": None, "research_sabcd": "S", "ability_rank": 1}, "rank")
    assert "formal-top5-rank" not in _cell(h, {"rank": None, "research_sabcd": "S", "ability_rank": 1}, "rank")
    assert "formal-top5-rank" in _cell(h, {"rank": 5, "research_sabcd": "D", "ability_rank": 12}, "rank")
    assert "formal-top5-rank" not in _cell(h, {"rank": 6, "research_sabcd": "S", "ability_rank": 1}, "rank")


def test_nar_bodyweight_is_two_lines_right_next_to_popularity_after_update():
    _, _, info, view = field("nar", 3)
    source = deepcopy(view)
    update = view[0]["nar_body_weight_research"] = {
        "horse_no": 1, "name": "保存馬1", "current_kg": 423,
        "change_kg": -4, "paired_min_kg": 420, "paired_max_kg": 430,
        "band": "範囲内", "prestart_observed": True,
        "retrieved_at": "2026-11-25T11:05:00+09:00",
    }
    view[1]["nar_body_weight_research"] = {
        "horse_no": 2, "name": "保存馬2", "current_kg": 454,
        "change_kg": +10, "paired_min_kg": 447, "paired_max_kg": 449,
        "band": "範囲外", "prestart_observed": False,
        "retrieved_at": "2026-11-25T11:05:00+09:00",
    }
    frozen = deepcopy(view)
    html = lineup_html(view)
    parsed = BeautifulSoup(html, "html.parser")
    names = [x.text for x in parsed.select('th .column-label')]
    assert names[names.index('人気') + 1] == '馬体重'
    weights = parsed.select('td.col-nar_body_weight')
    assert len(weights) == 3
    assert weights[0].select_one("strong").text == "423(-4)"
    assert weights[0].select_one("small").text == "420〜430"
    assert weights[1].select_one("strong").text == "454(+10)"
    assert weights[1].select_one("small").text == "447〜449"
    assert "発走前未確認" in weights[1]["title"]
    assert weights[2].text == "未取得"
    assert weights[2].select_one("strong") is None
    specs = columns(view)
    column = next(x for x in specs if x['key'] == 'nar_body_weight')
    assert column['type'] == 'number'
    assert not column.get('table_hidden')
    assert frozen == view
    assert source[0].get("nar_body_weight_research") is None
    # The new weight column must not alter the original prediction.
    for a, b in zip(source, view):
        assert (a["mark"], a["rank"], a["score"], a["ability"]) == (
            b["mark"], b["rank"], b["score"], b["ability"])


def test_jra_does_not_gain_nar_bodyweight_column():
    _, _, info, view = field("jra", 3)
    for horse in view:
        horse["nar_body_weight_research"] = {
            "current_kg": 423, "change_kg": -4, "paired_min_kg": 420,
            "paired_max_kg": 430,
        }
    assert all(s['key'] != 'nar_body_weight' for s in columns(view))
    html = BeautifulSoup(lineup_html(view), "html.parser")
    assert not html.select('td.col-nar_body_weight')
    assert "馬体重" not in [x.text for x in html.select('th .column-label')]



@pytest.mark.parametrize("mode, raw_class, expected_class", [
    ("jra", "2勝クラス", "2勝"),
    ("nar", "C2二", "C2"),
])
def test_three_historical_cells_show_finish_and_class_next_to_index(mode, raw_class, expected_class):
    _, _, _, view = field(mode, count=2)
    for horse in view:
        for run in horse["explorer_facts"]["runs"]:
            run.update(finish="3着", class_raw=raw_class,
                       venue="京都" if mode == "jra" else "浦和",
                       surface="芝" if mode == "jra" else "ダ")
    before = deepcopy(view)
    doc = BeautifulSoup(lineup_html(view), "html.parser")
    for row in doc.select("tbody tr[data-horse]"):
        for key in ("run_old", "run_middle", "run_latest"):
            td = row.select_one(".col-" + key)
            assert td is not None
            line = td.select_one(".run-finish-class")
            assert line is not None
            assert "着順 3着" in line.text
            assert "クラス " + expected_class in line.text
            assert td.select_one(".metric-number") is not None
            assert td.select_one(".run-condition") is not None
    assert view == before


def test_missing_finish_or_class_is_visible_without_invention():
    _, _, _, view = field("jra", count=1)
    for run in view[0]["explorer_facts"]["runs"]:
        run.update(finish="未取得", class_raw="レースの固有名", venue="東京", surface="芝")
    html = BeautifulSoup(lineup_html(view), "html.parser")
    for td in html.select(".col-run_old,.col-run_middle,.col-run_latest"):
        line = td.select_one(".run-finish-class")
        assert line is not None
        assert "着順 未取得" in line.text
        assert "クラス 未取得" in line.text
