"""Display-only race tendency inferred from the frozen pre-race research model.

Experimental thresholds, NOT calibrated probabilities, payoffs, or betting
advice.  Never read odds, results, official marks, or race outcomes.
Missing scores always lead to an explicit hold rather than a false "混戦".
"""
from __future__ import annotations

import math
from collections.abc import Mapping

VERSION = "race-tendency-study-20261112"


def _valid_score(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if math.isfinite(n) and 0. <= n <= 1. else None


def assess(view):
    """Return a small, honest label and facts; never mutate the view.

    All horses must have valid pre-race shadow scores before calling a race
    "axis-favored" or "mixed".  A model score is NOT a calibrated podium rate.
    """
    horses = [h for h in view or () if isinstance(h, Mapping)]
    n = len(horses)
    unique = {str(h.get("no", "")) for h in horses}
    rows = [h.get("research_sabcd_weight_class") or {} for h in horses]
    vals = [_valid_score(r.get("score")) if isinstance(r, Mapping) else None for r in rows]
    known = sum(v is not None for v in vals)
    retrospective = any(isinstance(r, Mapping) and r.get("retro") is True for r in rows)

    def result(label, tone, detail):
        return dict(label=label, tone=tone, detail=detail,
                    known=known, total=n, retrospective=retrospective,
                    version=VERSION)

    if n < 5 or len(unique) != n or "" in unique or known != n:
        return result("判定保留", "neutral",
                      f"研究スコア取得 {known}/{n}頭。全頭の比較材料が揃うまでレース傾向は判定しません。")
    scores = sorted(vals, reverse=True)
    first, second, third = scores[:3]
    gap = first - second
    span = first - third
    if first >= .65 and gap >= .15 and span >= .22:
        label, tone = "軸候補が浮上", "axis"
    elif first < .52 and gap <= .09 and span <= .16:
        label, tone = "混戦傾向", "mixed"
    elif first < .52:
        label, tone = "軸候補不在", "neutral"
    elif gap <= .09:
        label, tone = "上位拮抗", "mixed"
    else:
        label, tone = "軸は要比較", "neutral"
    detail = (f"全{n}頭｜研究モデル値 上位 {first:.3f} / {second:.3f} / {third:.3f}"
              f"（1・2位差 {gap:.3f}）。")
    return result(label, tone, detail)


def as_html(view):
    """Escaped, modest one-line widget for the Streamlit race header."""
    from html import escape
    data = assess(view)
    warning = (" 過去開催への後日算出です。" if data["retrospective"] else "")
    return (
        '<div class="game-race-tendency" role="note"'
        ' aria-label="研究用レース傾向">'
        '<span class="game-race-tendency-key">レース傾向（研究）</span>'
        '<strong class="game-race-tendency-label game-race-tendency-'
        + escape(data["tone"], quote=True) + '">' + escape(data["label"]) + '</strong>'
        '<span class="game-race-tendency-detail">' + escape(data["detail"]) + '</span>'
        '<small class="game-race-tendency-caveat">'
        + escape("判定は未校正モデルの暫定基準。的中率・荒れやすさ・購入価値を保証しません。" + warning)
        + '</small></div>'
    )
