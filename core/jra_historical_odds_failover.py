"""One-click JRA historical win/place odds with two independent public providers.

Prefer validated, race-specific 優馬JAPAN observations, then try 競馬ラボ
when the first site is unreachable, rejects access, has changed layout, or
only supplies part of the single/place table. Do not combine two providers'
prices: their published snapshots can represent different times.

Explicit user action only. No polling, login, proxy, CAPTCHA workarounds or
retry loops. On two failures, return no observation rather than saved odds.
"""
from datetime import datetime

from . import race_odds as odds


def _quality(quote):
    """Number of individually observed single/place prices, not horse count."""
    coverage = quote.get("coverage") or {}
    return (coverage.get("win") or {}).get("count", 0) + (
        coverage.get("place") or {}).get("count", 0)


def _complete(quote):
    coverage = quote.get("coverage") or {}
    return all((coverage.get(kind) or {}).get("count", 0) == (
        coverage.get(kind) or {}).get("expected", -1)
        for kind in ("win", "place")) and quote.get("expected_horses", 0) > 0


def _explain(exc):
    # Keep status concise and do not echo uncontrolled remote HTML/URLs.
    if isinstance(exc, ValueError):
        msg = str(exc).replace("\n", " ").strip()
        return msg[:135] if msg else "取得したページを照合できません"
    return type(exc).__name__


def fetch_once(identity, race_info, *, now=None, yuma_fetch=None,
               keibalab_fetch=None):
    """Try Yuma once, then Keibalab once if needed; return one valid snapshot.

    Supports dependency injection for offline tests. Both sources independently
    validate date, venue, race, all saved numbers and names before acceptance.
    A partial verified Yuma observation remains usable if Keibalab also fails;
    a successful, more complete Keibalab snapshot wins over a Yuma partial.
    """
    from .jra_yuma_odds import fetch_once as fetch_yuma
    from .jra_historical_odds import fetch_once as fetch_keibalab

    now = now or datetime.now(odds.JST)
    yuma_fetch = yuma_fetch or fetch_yuma
    keibalab_fetch = keibalab_fetch or fetch_keibalab

    results = []
    failures = []

    def attempt(label, fetch):
        try:
            quote = odds.validate(fetch(identity, race_info, now=now), identity)
            if _quality(quote) <= 0:
                raise ValueError("有効な単勝・複勝の掲載値がありません")
            results.append((label, quote))
            return quote
        except Exception as exc:
            failures.append((label, _explain(exc)))
            return None

    primary = attempt("優馬JAPAN", yuma_fetch)
    if primary is not None and _complete(primary):
        return primary

    alternative = attempt("競馬ラボ", keibalab_fetch)
    if not results:
        errors = " ／ ".join(f"{label}：{error}" for label, error in failures)
        raise ValueError(
            "両サイトで過去の単勝・複勝を取得できませんでした。"
            + errors + "。保存済み価格は代用していません"
        )

    label, chosen = max(results, key=lambda item: _quality(item[1]))
    # Copy only display metadata; do not rewrite the provenance or odds.
    chosen = dict(chosen)
    chosen["warnings"] = list(chosen.get("warnings") or [])
    if label == "競馬ラボ":
        chosen["warnings"].append(
            "優馬JAPANが未取得または単複不完全のため競馬ラボに自動切替しました"
        )
        chosen["fallback_used"] = True
    elif not _complete(chosen):
        chosen["warnings"].append(
            "取得できた券種のみ表示しています。別サイトのオッズとは混合しません"
        )
        chosen["fallback_used"] = False
    else:
        chosen["fallback_used"] = False
    if failures:
        chosen["warnings"].append(
            "取得できなかったサイト：" + "／".join(
                f"{site}（{reason}）" for site, reason in failures
            )
        )
    return chosen
