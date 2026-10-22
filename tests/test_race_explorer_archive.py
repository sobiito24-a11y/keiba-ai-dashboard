"""Ordinary comparison views preserve native saved A/B predictions and archives."""
from contextlib import nullcontext
from copy import deepcopy
import json

from bs4 import BeautifulSoup
import pandas as pd
import pytest

from core.final_candidate_selection import formal_score, select_indices
from core.game_race_ui import document
from core.model_b import KEY as B_KEY, resolve
from core.model_b_ui import project as project_research_b
from core.prediction_snapshot import keiba_bytes, load_keiba, restore_prediction_result
from core.race_explorer_cards import detail_html
from core.race_odds import KEY as ODDS_KEY
from tests.test_final_candidate_archive import _saved_event, _snapshot_payload, _view


def _document_data(view):
    dom = BeautifulSoup(document(view, "archive-comparison"), "html.parser")
    data = json.loads(dom.select_one("script#race-data").string)
    assert data["experience"] == "race-comparison"
    assert data["active_model"] == "A"
    return dom, data


def _assert_comparison(view):
    before = deepcopy(view)
    dom, data = _document_data(view)
    rows = dom.select("tr[data-horse]")
    assert [row["data-horse"] for row in rows] == sorted(
        (horse["no"] for horse in view), key=int)
    checks = dom.select("input[data-user-check]")
    assert len(checks) == len(view) == 8
    assert not any(check.has_attr("checked") for check in checks)
    assert len({check["data-user-check"] for check in checks}) == len(view)
    table = rows[0].find_parent("table")
    headers = [cell.get_text(" ", strip=True) for cell in table.select("thead th")]
    assert [headers.index(label) for label in ("3走前", "2走前", "前走", "3走平均", "★最高指数")] == sorted(
        headers.index(label) for label in ("3走前", "2走前", "前走", "3走平均", "★最高指数"))
    for row in rows:
        assert row.select_one("[data-horse-open]")["data-horse-open"] == row["data-horse"]
        assert not row.select(".mark,.focus-badge,.candidate-category")
        assert not any(mark in row.get_text() for mark in "◎○▲✔△")

    selected = [view[index]["no"] for index in select_indices(view, "no")]
    pickup = dom.select(".pickup-card[data-horse-open]")
    assert [card["data-horse-open"] for card in pickup] == selected
    assert 5 <= len(selected) <= 6 and len(selected) == len(set(selected))
    assert sum(view[index]["formal_member"] for index in select_indices(view)) == 5
    assert sum(not view[index]["formal_member"] for index in select_indices(view)) <= 1
    assert all(not any(mark in card.text for mark in "◎○▲✔✓△") for card in pickup)

    assert data["cards"] == [detail_html(horse) for horse in view]
    cards_by_no = dict(zip((horse["no"] for horse in view), data["cards"]))
    assert {horse["no"] for horse in data["horses"]} == set(cards_by_no)
    for horse in view:
        saved = next(item for item in data["horses"] if item["no"] == horse["no"])
        assert saved["sort"]["final_score"] == formal_score(horse)
        detail = BeautifulSoup(cards_by_no[horse["no"]], "html.parser")
        assert detail.select_one(".detail-header h3").text == horse["name"]
        assert [run.h5.text for run in detail.select(".detail-run")] == ["3走前", "2走前", "前走"]
    for card in pickup:
        assert card["data-horse-open"] in cards_by_no
        assert card["aria-controls"] == "horse-detail-" + card["data-horse-open"]

    # Display orders are serialized from new containers and retain original facts.
    # The client may sort the records and open any shared card in either order.
    for ordered in (list(reversed(view)),
                    sorted(view, key=lambda h: (formal_score(h) is None,
                                               -(formal_score(h) or 0)))):
        ordered_before = deepcopy(ordered)
        _, reordered = _document_data(ordered)
        assert dict(zip((h["no"] for h in ordered), reordered["cards"])) == cards_by_no
        assert {h["no"]: h["sort"]["final_score"] for h in reordered["horses"]} == {
            h["no"]: formal_score(h) for h in view}
        assert ordered == ordered_before
    assert view == before


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_native_archive_normal_a_comparison_and_saved_b_remain_unchanged(mode, monkeypatch):
    event = _saved_event(mode)
    original = deepcopy(event)
    payload_before = _snapshot_payload(keiba_bytes(event))
    result = restore_prediction_result(event["races"][0])
    report = resolve(result)
    assert report["status"] == "ready" and len(report["horses"]) == 8
    frozen_before = deepcopy(result.debug_info[B_KEY])
    tables = [table.copy(deep=True) for table in (result.overall_table, result.horse_evaluation)]
    view = _view(result)
    view_before = deepcopy(view)

    import core.model_b as model_b
    monkeypatch.setattr(model_b, "predict", lambda *a, **k: pytest.fail("比較操作による研究Bの再計算"))
    _assert_comparison(view)

    # Research B remains an explicit projection of the exact frozen report.
    research = project_research_b(view, report)
    assert all(horse["active_model"] == "B" for horse in research)
    assert {h["no"] for h in research if h["formal_member"]} == set(report["top5"])
    for horse in research:
        saved = next(item for item in report["horses"] if item["no"] == horse["no"])
        assert formal_score(horse) == saved["score"]
    assert view == view_before
    for actual, expected in zip((result.overall_table, result.horse_evaluation), tables):
        pd.testing.assert_frame_equal(actual, expected)
    assert result.debug_info[B_KEY] == frozen_before
    assert resolve(result) == report
    assert event == original
    after = keiba_bytes(event)
    assert _snapshot_payload(after) == payload_before
    reloaded = load_keiba(after)
    assert reloaded == original
    assert reloaded["races"][0][ODDS_KEY] == original["races"][0][ODDS_KEY]
    assert resolve(restore_prediction_result(reloaded["races"][0])) == report


@pytest.mark.parametrize("mode", ["jra", "nar"])
@pytest.mark.parametrize("failure", [None, "missing_input", "integrity", "changed_input"])
def test_ordinary_app_route_never_requests_or_projects_research_b(mode, failure, monkeypatch):
    import app
    import core.game_race_ui as race_ui
    import core.game_ui_uploads as uploads
    import core.model_b as model_b
    import core.model_b_ui as model_b_ui
    import core.paper_betting_ui as paper
    import core.race_odds_ui as odds

    event = _saved_event(mode, failure)
    before = deepcopy(event)
    result = restore_prediction_result(event["races"][0])
    tables = [table.copy(deep=True) for table in (result.overall_table, result.horse_evaluation)]
    frozen = deepcopy(result.debug_info[B_KEY])
    expected = _view(result)
    rendered = []
    checkboxes = []

    def disabled_research(label, *args, **kwargs):
        assert kwargs.get("value", False) is False
        checkboxes.append(label)
        return False

    def forbidden(*args, **kwargs):
        pytest.fail("通常のA表示から研究Bを呼び出した")

    monkeypatch.setattr(app.st, "session_state", {})
    monkeypatch.setattr(app.st, "expander", lambda *a, **k: nullcontext())
    monkeypatch.setattr(app.st, "checkbox", disabled_research)
    monkeypatch.setattr(app.st, "caption", lambda *a, **k: None)
    monkeypatch.setattr(uploads, "uploaded_frames", lambda *a, **k: ({}, []))
    monkeypatch.setattr(odds, "render", lambda result, view: view)
    monkeypatch.setattr(paper, "current_decision", lambda *a, **k: None)
    monkeypatch.setattr(paper, "render", lambda *a, **k: None)
    monkeypatch.setattr(race_ui, "render_component", lambda view, *a, **k: rendered.append(deepcopy(view)))
    monkeypatch.setattr(model_b, "resolve", forbidden)
    monkeypatch.setattr(model_b, "predict", forbidden)
    monkeypatch.setattr(model_b_ui, "render", forbidden)
    monkeypatch.setattr(model_b_ui, "resolve", forbidden)

    app.render_game_prediction(result)

    assert len(rendered) == 1
    assert checkboxes
    assert all(h.get("active_model", "A") == "A" for h in rendered[0])
    assert [(h["no"], h["rank"], h["mark"], formal_score(h)) for h in rendered[0]] == [
        (h["no"], h["rank"], h["mark"], formal_score(h)) for h in expected]
    for actual, saved in zip((result.overall_table, result.horse_evaluation), tables):
        pd.testing.assert_frame_equal(actual, saved)
    assert result.debug_info[B_KEY] == frozen
    assert event == before
