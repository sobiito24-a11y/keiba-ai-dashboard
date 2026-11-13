"""Offline regression tests for the one-button Yuma -> Keibalab failover.

Mocks represent normal and blocked public endpoints, never bypass a 403 or
depend on whether a third-party page happens to be live during CI.
"""
from copy import deepcopy
from datetime import datetime

import pytest

from core import race_odds
from core.jra_historical_odds import parse_keibalab_html, fetch_once as lab_fetch
from core.jra_historical_odds_failover import fetch_once
from core.jra_yuma_odds import parse_yuma_pages
from tests.test_jra_historical_odds import ID, INFO, CLOCK, page


def yuma_page(kind):
    name = "単勝オッズ" if kind == "tan" else "複勝オッズ"
    rows = [
        ("1", "シュライアハフト", "11.9" if kind == "tan" else "2.6-4.2"),
        ("2", "テリオスベラ", "2.7" if kind == "tan" else "1.2-1.5"),
    ]
    body = "".join(
        f"<tr><td>{no}</td><td>○</td><td>{horse}</td><td>{price}</td></tr>"
        for no, horse, price in rows
    )
    return (
        '<html><head><title>単勝・複勝オッズ【2026年11月8日京都1R】'
        '</title></head><body><table><tr>'
        f'<th>馬番</th><th>印</th><th>馬名</th><th>{name}</th>'
        f'</tr>{body}</table></body></html>'
    ).encode()


def primary(full=True):
    return parse_yuma_pages(
        {"tan": yuma_page("tan"), **({"fuk": yuma_page("fuk")} if full else {})},
        ID, INFO, now=CLOCK,
    )


def alternative():
    return parse_keibalab_html(page(), ID, INFO, now=CLOCK)


def test_primary_full_success_never_calls_fallback():
    count = []
    def lab(*_args, **_kwargs):
        count.append(1)
        raise AssertionError("fallback must not run")
    q = fetch_once(ID, INFO, now=CLOCK,
                   yuma_fetch=lambda *_a, **_kw: primary(),
                   keibalab_fetch=lab)
    assert not count
    assert q["source"].startswith("優馬JAPAN")
    assert q["fallback_used"] is False
    assert q["coverage"]["win"]["count"] == 2
    assert q["coverage"]["place"]["count"] == 2


def test_primary_403_fallback_to_valid_keibalab_and_model_unchanged():
    calls = []
    def denied(*_args, **_kwargs):
        calls.append("yuma")
        raise ValueError("優馬JAPANの単勝ページがHTTP 403を返しました")
    def lab(*_args, **_kwargs):
        calls.append("lab")
        return alternative()
    q = fetch_once(ID, INFO, now=CLOCK, yuma_fetch=denied, keibalab_fetch=lab)
    assert calls == ["yuma", "lab"]
    assert q["source"].startswith("競馬ラボ")
    assert q["fallback_used"] is True
    assert "自動切替" in " ".join(q["warnings"])
    assert q["coverage"]["win"]["count"] == 2
    assert q["coverage"]["place"]["count"] == 2
    original = [dict(no="1", rank="C", score=36, mark="△", odds="88"),
                dict(no="2", rank="S", score=80, mark="◎", odds="88")]
    frozen = deepcopy(original)
    shown = race_odds.overlay(original, q, "自動切替の過去オッズ")
    assert shown[0]["odds"] == "11.9"
    assert shown[1]["place_odds"] == "1.2〜1.5"
    assert [h["rank"] for h in shown] == ["C", "S"]
    assert [h["score"] for h in shown] == [36, 80]
    assert [h["mark"] for h in shown] == ["△", "◎"]
    assert original == frozen


def test_partial_primary_triggers_fallback_to_full_single_provider_snapshot():
    partial = primary(full=False)
    full = alternative()
    assert partial["coverage"]["win"]["count"] == 2
    assert partial["coverage"]["place"]["count"] == 0
    q = fetch_once(ID, INFO, now=CLOCK,
                   yuma_fetch=lambda *_a, **_kw: partial,
                   keibalab_fetch=lambda *_a, **_kw: full)
    assert q["source"].startswith("競馬ラボ")
    assert q["fallback_used"] is True
    assert q["coverage"]["place"]["count"] == 2
    assert q["observed_at"] == full["observed_at"]
    assert q["prices"] == full["prices"]  # never splice between providers


def test_partial_primary_survives_alternative_failure_without_fake_place():
    partial = primary(full=False)
    q = fetch_once(ID, INFO, now=CLOCK,
                   yuma_fetch=lambda *_a, **_kw: partial,
                   keibalab_fetch=lambda *_a, **_kw: (_ for _ in ()).throw(
                       ValueError("HTTP 403")))
    assert q["source"].startswith("優馬JAPAN")
    assert q["coverage"]["win"]["count"] == 2
    assert q["coverage"]["place"]["count"] == 0
    assert "place" in q["missing_kinds"]
    assert "取得できた券種のみ" in " ".join(q["warnings"])
    assert q["fallback_used"] is False


def test_partial_provider_is_kept_on_equal_coverage_without_mixing():
    partial = primary(full=False)
    lab_partial = deepcopy(alternative())
    lab_partial["prices"] = [p for p in lab_partial["prices"] if p["kind"] == "place"]
    q = fetch_once(ID, INFO, now=CLOCK,
                   yuma_fetch=lambda *_a, **_kw: partial,
                   keibalab_fetch=lambda *_a, **_kw: lab_partial)
    assert q["source"].startswith("優馬JAPAN")
    assert q["coverage"]["place"]["count"] == 0
    assert len(q["prices"]) == 2


def test_mismatch_from_first_provider_is_rejected_and_never_overlaid():
    false_quote = deepcopy(primary())
    false_quote["race_id"] = "202608050211"
    q = fetch_once(ID, INFO, now=CLOCK,
                   yuma_fetch=lambda *_a, **_kw: false_quote,
                   keibalab_fetch=lambda *_a, **_kw: alternative())
    assert q["source"].startswith("競馬ラボ")
    assert q["race_id"] == ID["race_id"]


def test_both_providers_fail_with_both_reasons_and_no_quote():
    count = []
    def bad_yuma(*_a, **_kw):
        count.append("yuma")
        raise ValueError("HTTP 403")
    def bad_lab(*_a, **_kw):
        count.append("lab")
        raise ValueError("HTTP 429")
    with pytest.raises(ValueError, match="両サイトで過去の単勝・複勝を取得できませんでした") as e:
        fetch_once(ID, INFO, now=CLOCK,
                   yuma_fetch=bad_yuma, keibalab_fetch=bad_lab)
    assert count == ["yuma", "lab"]
    assert "優馬JAPAN：HTTP 403" in str(e.value)
    assert "競馬ラボ：HTTP 429" in str(e.value)


def test_fallback_rejects_wrong_race_html_without_reusing_saved_odds():
    def wrong_lab(*_a, **_kw):
        return parse_keibalab_html(
            page(title="単勝・複勝オッズ〖2026年11月8日東京1R〗"),
            ID, INFO, now=CLOCK,
        )
    with pytest.raises(ValueError, match="両サイト"):
        fetch_once(ID, INFO, now=CLOCK,
                   yuma_fetch=lambda *_a, **_kw: (_ for _ in ()).throw(
                       ValueError("HTTP 403")),
                   keibalab_fetch=wrong_lab)


def test_keibalab_same_race_canonical_redirect_only():
    url = "https://keibalab.jp/db/race/202611080801/odds.html"
    class Response:
        def __init__(self, status_code, content=b"", headers=None):
            self.status_code, self.content, self.headers = status_code, content, headers or {}
    requested = []
    def getter(uri, **kwargs):
        requested.append((uri, kwargs))
        if len(requested) == 1:
            return Response(301, headers={"Location": url})
        return Response(200, content=page())
    q = lab_fetch(ID, INFO, now=CLOCK, get=getter)
    assert q["coverage"]["win"]["count"] == 2
    assert len(requested) == 2
    assert requested[1][0] == url
    assert all(req[1]["allow_redirects"] is False for req in requested)


def test_keibalab_refuses_redirect_to_login_or_another_race():
    class Redirect:
        status_code = 302
        content = b""
        headers = {"Location": "https://keibalab.jp/login"}
    count = []
    def getter(*_args, **_kwargs):
        count.append(1)
        return Redirect()
    with pytest.raises(ValueError, match="移動先"):
        lab_fetch(ID, INFO, now=CLOCK, get=getter)
    assert len(count) == 1
