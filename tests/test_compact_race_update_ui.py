"""The normal Dashboard asks for only two odds actions and one weight action.

Research parsers and provenance checks remain intact; this tests only the
compact controls and that the exact fetched observation reaches the lineup.
"""
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
import sys

import pytest

from core import race_odds, race_odds_ui_live, nar_body_weight, nar_body_weight_ui


class OnlyButtons:
    """Every non-button widget is forbidden in the compact mode."""
    def __init__(self, active=None):
        self.session_state = {}
        self.secrets = {}
        self.pressed = active
        self.buttons = []
        self.notices = []

    def columns(self, count):
        assert count == 2
        return (self, self)

    def button(self, label, **kwargs):
        self.buttons.append((label, kwargs))
        return label == self.pressed and not kwargs.get("disabled", False)

    def spinner(self, *args, **kwargs):
        return nullcontext()

    def success(self, msg):
        self.notices.append(("success", msg))

    def warning(self, msg):
        self.notices.append(("warning", msg))

    def error(self, msg):
        self.notices.append(("error", msg))

    def __getattr__(self, name):
        raise AssertionError("Unexpected extra widget in compact view: " + name)


@pytest.mark.parametrize("clicked", [None, "当日リアルオッズ取得"])
def test_nar_compact_odds_has_exactly_two_buttons_and_no_other_widgets(monkeypatch, clicked):
    from core import independent_ai_odds, nar_official_odds

    st = OnlyButtons(active=clicked)
    monkeypatch.setitem(sys.modules, "streamlit", st)
    monkeypatch.setattr(independent_ai_odds, "provider",
                        lambda *a, **k: SimpleNamespace(available=False))
    identity = dict(race_id="202646112510", mode="nar",
                    horses=[dict(horse_no=1, name="保存馬")])
    monkeypatch.setattr(race_odds, "identity_from_result", lambda result: deepcopy(identity))
    monkeypatch.setattr(race_odds, "state_for", lambda result:
                        dict(schema_version=1, saved=[], history=[]))
    monkeypatch.setattr(race_odds, "merge", lambda hist, newer, identity: list(hist)+list(newer))
    seen = []
    monkeypatch.setattr(race_odds, "overlay", lambda view, quote, label:
                        seen.append((deepcopy(quote), label)) or deepcopy(view))
    monkeypatch.setattr(nar_official_odds, "locator", lambda *a, **kw:
                        ("金沢", "20261125", 10))
    quote = dict(
        observation_id="fresh-odds-nar-001", horse_count=1,
        expected_horses=1, source="NAR公式テスト",
        coverage={"win": {"count": 1}, "place": {"count": 1}},
        prices=[], received_at="2026-11-25T12:00:00+09:00")
    monkeypatch.setattr(nar_official_odds, "fetch_daily",
                        lambda: ("official_daily.zip", b"zip"))
    monkeypatch.setattr(nar_official_odds, "parse_daily_zip",
                        lambda *args, **kwargs: deepcopy(quote))
    class Fixed:
        @staticmethod
        def now(tz):
            return datetime(2026, 11, 25, 12, 0, tzinfo=tz)
    monkeypatch.setattr(race_odds_ui_live, "datetime", Fixed)
    result = SimpleNamespace(race_info={"race_date": "2026-11-25"})
    view = [dict(no="1", name="保存馬", score=123, mark="◎", rank=1)]
    before = deepcopy(view)

    shown = race_odds_ui_live.render(result, view, compact=True)
    assert [label for label, _ in st.buttons] == ["過去オッズ取得", "当日リアルオッズ取得"]
    assert st.buttons[0][1]["disabled"]
    assert not st.buttons[1][1]["disabled"]
    assert shown == view == before
    if clicked:
        assert seen[-1][0]["observation_id"] == quote["observation_id"]
        assert st.notices and "オッズ更新結果" in st.notices[-1][1]
        st.pressed = None
        st.buttons.clear()
        race_odds_ui_live.render(result, view, compact=True)
        assert seen[-1][0]["observation_id"] == quote["observation_id"]
        assert len(st.buttons) == 2
    else:
        assert seen[-1][0] is None


def test_nar_compact_weight_has_one_button_and_overlays_exact_horse(monkeypatch):
    st = OnlyButtons(active="当日馬体重を更新（楽天競馬）")
    monkeypatch.setitem(sys.modules, "streamlit", st)
    day = datetime.now(race_odds.JST).strftime("%Y%m%d")
    rid = day[:4] + "46" + day[4:] + "10"
    identity = dict(race_id=rid, mode="nar",
                    horses=[dict(horse_no=1, name="保存馬")])
    monkeypatch.setattr(race_odds, "identity_from_result", lambda r: identity)
    monkeypatch.setattr(nar_body_weight, "racecard_url", lambda *a:
                        "https://keiba.rakuten.co.jp/race_card/list/RACEID/202611252200000010")
    monkeypatch.setattr(nar_body_weight, "result_url", lambda *a:
                        "https://keiba.rakuten.co.jp/race_performance/list/RACEID/202611252200000010")
    monkeypatch.setattr(nar_body_weight, "_prestart", lambda *a: (None, False))
    monkeypatch.setattr(nar_body_weight, "fetch_page", lambda url: "<html>public</html>")
    row = dict(horse_no=1, name="保存馬", current_kg=423, change_kg=-4,
               paired_min_kg=420, paired_max_kg=430, band="範囲内")
    quote = dict(retrieved_at=datetime.now(race_odds.JST).isoformat(),
                 prestart_observed=False, rows=[row], source_url="https://keiba.rakuten.co.jp")
    monkeypatch.setattr(nar_body_weight, "make_observation", lambda *args, **kw: deepcopy(quote))
    monkeypatch.setattr(nar_body_weight, "add_observation", lambda book, q: {
        "races": {rid: {"observations": [q]}}})
    result = SimpleNamespace(race_mode="nar", race_info={})
    view = [dict(no="1", name="保存馬", mode="nar", mark="◎",
                 rank=1, score=100, independent_ai_sabcd={"grade": "A"})]
    before = deepcopy(view)

    shown = nar_body_weight_ui.render(result, view, compact=True)
    assert [label for label, _ in st.buttons] == ["当日馬体重を更新（楽天競馬）"]
    assert st.buttons[0][1]["disabled"] is False
    assert shown[0]["nar_body_weight_research"]["current_kg"] == 423
    assert shown[0]["nar_body_weight_research"]["paired_min_kg"] == 420
    assert (shown[0]["mark"], shown[0]["rank"], shown[0]["score"]) == (
        before[0]["mark"], before[0]["rank"], before[0]["score"])
    assert view == before
    assert st.notices and st.notices[-1][0] == "success"
