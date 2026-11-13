"""One-click JRA historical win/place odds with three public providers.

Prefer validated, race-specific 優馬JAPAN observations, then try 競馬ラボ,
and finally スポーツナビ when prior sources fail or supply incomplete prices.
Do not combine providers'
prices: their published snapshots can represent different times.

Explicit user action only. No polling, login, proxy, CAPTCHA workarounds or
retry loops. On three failures, return no observation rather than saved odds.
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
               keibalab_fetch=None, sportsnavi_fetch=None,
               prefer_sportsnavi=False):
    """Try each source at most once. A valid FULL quote wins at first success.

    The normal UI prioritizes the verified fast Sports Navi route to avoid
    spending tens of seconds on two regularly timing-out servers. The legacy
    order remains available for regression comparison and older callers.
    Each provider independently checks race identity before supplying a quote.
    """
    from .jra_yuma_odds import fetch_once as fetch_yuma
    from .jra_historical_odds import fetch_once as fetch_keibalab
    from .jra_sportsnavi_odds import fetch_once as fetch_sportsnavi

    now = now or datetime.now(odds.JST)
    yuma_fetch = yuma_fetch or fetch_yuma
    keibalab_fetch = keibalab_fetch or fetch_keibalab
    sportsnavi_fetch = sportsnavi_fetch or fetch_sportsnavi
    providers = (
        [("スポーツナビ", sportsnavi_fetch),
         ("優馬JAPAN", yuma_fetch),
         ("競馬ラボ", keibalab_fetch)]
        if prefer_sportsnavi else
        [("優馬JAPAN", yuma_fetch),
         ("競馬ラボ", keibalab_fetch),
         ("スポーツナビ", sportsnavi_fetch)]
    )
    best = None
    first_label = providers[0][0]
    failures = []
    for label, fetch in providers:
        try:
            quote = odds.validate(fetch(identity, race_info, now=now), identity)
            if _quality(quote) <= 0:
                raise ValueError("有効な単勝・複勝の掲載値がありません")
        except Exception as exc:
            failures.append((label, _explain(exc)))
            continue
        if best is None or _quality(quote) > _quality(best[1]):
            best = (label, quote)
        if _complete(quote):
            best = (label, quote)
            break

    if best is None:
        errors = " ／ ".join(f"{label}：{error}" for label, error in failures)
        raise ValueError(
            "3サイトとも過去の単勝・複勝を取得できませんでした。"
            + errors + "。保存済み価格は代用していません"
        )
    label, selected = best
    chosen = dict(selected)
    chosen["warnings"] = list(chosen.get("warnings") or [])
    chosen["fallback_used"] = label != first_label
    if chosen["fallback_used"]:
        chosen["warnings"].append(
            first_label + "の単複が未取得・不完全のため" + label +
            "の照合済み掲載値に自動切替しました"
        )
    if not _complete(chosen):
        chosen["warnings"].append(
            "取得できた券種のみ表示しています。別サイトのオッズとは混合しません"
        )
    if failures:
        chosen["warnings"].append(
            "取得できなかったサイト：" + "／".join(
                f"{site}（{reason}）" for site, reason in failures
            )
        )
    return chosen
