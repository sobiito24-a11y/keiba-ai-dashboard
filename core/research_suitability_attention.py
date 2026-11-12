"""NAR-only *evidence* attention for C/D with repeated past good runs.

This is NOT a rank promotion, recommendation or betting ticket. In the
2026-11-09..12 observational audit, C and D behaved differently:
C candidates 7/40 placed vs other C 70/317, whereas D 7/31 vs 70/782.
The day-to-day effect was inconsistent. The label therefore describes
verified, dated evidence only; it does NOT assert higher win probability.
"""
from __future__ import annotations

from . import research_six_dimensions as six

VERSION = "six-factors-cd-evidence-20261112"


def assess(horse):
    result = dict(label=None, reason=None, research_only=True, version=VERSION)
    if not isinstance(horse, dict) or horse.get("mode") != "nar":
        return result
    grade = (horse.get("research_sabcd_weight_class") or {}).get("grade")
    if grade not in ("C", "D"):
        return result
    evidence = six.evaluate(horse)
    factors = evidence["factors"]
    distance_grade = factors["distance"]["grade"]
    recent_grade = factors["recent"]["grade"]
    if distance_grade not in ("S", "A") or recent_grade not in ("S", "A"):
        return result

    context = horse.get("race_context") or {}
    current_distance = six._distance(context.get("distance"))
    current_surface = six._surface(context.get("surface") or context.get("芝ダート"))
    if current_distance is None or current_surface is None:
        return result

    # Use the *same filtered/deduplicated* known past starts as the six-factor
    # cards. No unknown-date, current-race, future-result or JRA conversion.
    history = six._run_history(horse)
    recent_local = [
        x for x in history[:5]
        if x["mode"] == "nar" and x["finish"] is not None
    ][:3]
    dated_podiums = {x["day"] for x in recent_local if 1 <= x["finish"] <= 3}
    if len(dated_podiums) < 2:
        return result
    near_dated_podiums = {
        x["day"] for x in history
        if x["mode"] == "nar"
        and x["surface"] == current_surface
        and x["distance"] is not None
        and abs(x["distance"] - current_distance) <= 200
        and x["finish"] is not None and 1 <= x["finish"] <= 3
    }
    if not near_dated_podiums:
        return result
    reason = (
        f"総合{grade}／距離{distance_grade}・近走{recent_grade}。"
        f"同主催で異なる過去{len(dated_podiums)}走が3着以内、"
        f"うち同馬場の距離±200mでの3着内実績を確認。"
        "距離と近走の評価には同じレースが重複します。"
        "4日間の検証ではCで好走率の上昇が確認できず、Dでも標本不足・日付差があります。"
        "『適性注目』は好走実績の見落とし防止だけで、"
        "総合ランクの昇格・軸指定・買い目への追加は行いません。"
    )
    return dict(result, label="適性注目", reason=reason,
                distance_grade=distance_grade, recent_grade=recent_grade,
                distinct_podium_starts=len(dated_podiums),
                near_distance_podium_starts=len(near_dated_podiums))


def assign_to_view(view):
    for horse in view:
        horse["research_suitability_attention"] = assess(horse)
    return view
