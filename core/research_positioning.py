"""Read-only research positioning for A and overlooked C/D or missing grades.

This module uses only pre-race facts already in the saved display projection.
It does NOT change model probabilities, ranks, formal marks, or bets.
Thresholds are hypotheses discovered in 2026-11-11 analysis and require
prospective evaluation; they are NOT verified win probabilities.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from .research_sabcd import _finish

VERSION = "positioning-study-20261112"


def _number(raw):
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        number = float(str(raw).strip())
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _positive_rank(raw):
    n = _number(raw)
    return int(n) if n is not None and n >= 1 and n.is_integer() else None


def _last_podium(horse):
    profile = horse.get("profile") or {}
    runs = [run for run in profile.get("runs", ()) or ()
            if isinstance(run, Mapping)]
    return any((_finish(r.get("finish")) or 999) <= 3 for r in runs)


def _missing_core(horse):
    missing = []
    if _positive_rank(horse.get("ability_rank")) is None:
        missing.append("純能力順位")
    corner = _positive_rank(horse.get("corner"))
    if corner is None:
        corner = _positive_rank((horse.get("final_metrics") or {}).get("corner"))
    if corner is None:
        missing.append("予測4角順位")
    return missing


def assess(horse):
    """Classify research position without looking at results or odds."""
    if not isinstance(horse, Mapping):
        return dict(label=None, kind=None, reason="判定材料なし", version=VERSION)
    grade_data = horse.get("research_sabcd_weight_class") or {}
    grade = grade_data.get("grade")
    score = _number(grade_data.get("score"))
    mode = horse.get("mode")
    mode_threshold = 35 if mode == "nar" else 30
    jockey = horse.get("research_inputs") or {}
    rate, starts = _number(jockey.get("jockey_rate")), _number(jockey.get("jockey_n"))
    qualified = starts is not None and starts >= 20 and rate is not None and 0 <= rate <= 100
    strong_jockey = qualified and rate >= mode_threshold
    corner = _positive_rank(horse.get("corner"))
    if corner is None:
        corner = _positive_rank((horse.get("final_metrics") or {}).get("corner"))
    start = _positive_rank(horse.get("start_rank"))
    prior_podium = _last_podium(horse)
    reason = ""
    label = None
    kind = None
    if grade == "A":
        if score is not None and score >= .60 and strong_jockey:
            label, kind = "軸候補", "axis"
            reason = (f"研究モデル値{score:.3f}、同条件騎手複勝率{rate:g}%／"
                      f"{int(starts)}走。11/11の探索条件であり、開催場別の"
                      "未使用レースでは有効性未確認。")
        elif score is not None and score < .60 and not strong_jockey:
            label, kind = "軸慎重", "caution"
            reason = (f"研究モデル値{score:.3f}、騎手条件は"
                      + (f"複勝率{rate:g}%／{int(starts)}走。" if qualified
                         else "母数不足・未取得。")
                      + "A評価でも軸として過信しないための参考表示。")
        else:
            label, kind = "相手本線", "neutral"
            reason = ("研究Aの相手候補。推定値と騎手実績の両方による"
                      "軸候補判定には達しない、または片方の材料が不足。")
    elif grade in ("C", "D") and corner is not None and corner <= 3 and prior_podium:
        label, kind = "押さえ候補", "cover"
        reason = (f"研究{grade}だが予測4角{corner}番手、近3走に3着以内実績あり。"
                  "過去日の探索で見つかった条件なので、買い目への自動追加はしません。")
    elif grade not in ("S", "A", "B", "C", "D"):
        missing = _missing_core(horse)
        if missing:
            reason = "総合SABCD判定に必要な" + "・".join(missing) + "が未取得。"
            if start is not None:
                reason += f"序盤{start}番手予測は取得済み。"
            if corner is not None:
                reason += f"4角{corner}番手予測は取得済み。"
            if qualified:
                reason += f"騎手複勝率{rate:g}%／{int(starts)}走を確認。"
            if not missing or not (start and corner):
                reason += "不足順位を脚質や別の能力指数から推測して補いません。"
            if strong_jockey and start is not None and start <= 3 and corner is not None and corner <= 3:
                label, kind = "押さえ参考", "missing"
                reason += "好位予測と騎手実績に注目。ただし総合ランクは判定不可のまま。"
            else:
                label, kind = "材料不足", "missing"
        else:
            label, kind = "判定保留", "missing"
            reason = "研究SABCDの数値算出に必要なその他の材料を確認。"
    return dict(label=label, kind=kind, reason=reason, version=VERSION,
                research_only=True, missing_core=tuple(_missing_core(horse)))


def assign_to_view(view):
    for horse in view:
        horse["research_positioning"] = assess(horse)
    return view
