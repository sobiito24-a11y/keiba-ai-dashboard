"""One research grade for the normal lineup: shadow SABCD + verified formal Top5.

This is a READ-ONLY display ranking, not a new calibrated podium probability.
Research 2026-11-11/14 holdout 2026-11-15: frozen pre-race evidence only;
the thin 10% formal boost is deliberately conservative. No additional Top5
horses, odds or final race results enter this function. Historical .keiba
snapshots and official ranks/marks are NEVER modified.
"""
from __future__ import annotations

from collections.abc import Mapping
import math
import re

from .research_sabcd import grade_from_probability

VERSION = "unified-shadow-formal-top5-20261116"
SHADOW_WEIGHT = 0.90
FORMAL_WEIGHT = 0.10
GRADES = ("S", "A", "B", "C", "D")


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def _formal_top5_rank(horse):
    """Only an explicitly saved formal Top5 can boost; never a reference rank."""
    raw = horse.get("rank")
    if isinstance(raw, str):
        raw = re.sub(r"位\s*$", "", raw.strip())
    value = _number(raw)
    if value is None or not value.is_integer() or not 1 <= value <= 5:
        return None
    # NAR can have an out-of-Top5 reference order without a formal score;
    # do not silently turn that reference into a formal rank.
    if horse.get("mode") == "nar" and "candidate_formal_score" in horse:
        if _number(horse.get("candidate_formal_score")) is None:
            return None
    return int(value)


def _number_key(horse):
    raw = str(horse.get("no") or "")
    return (0, int(raw)) if raw.isdigit() else (1, raw)


def evaluate_race(view):
    """Return a fused grade+one rank, preserving the race's source grade counts.

    Research score rank percentile is 90%; verified formal Top5 evidence is
    a bounded 10%. Fused ranks reorder the existing sorted research grades:
    the number of S/A/B/C/D grades within a race never increases or decreases,
    so we do not force an S or pretend to calibrate probabilities.
    If formal evidence is unavailable, retain the original grade/order.
    """
    horses = [horse for horse in view or () if isinstance(horse, Mapping)]
    if not horses:
        return {}
    valid = []
    for horse in horses:
        old = horse.get("research_sabcd_weight_class") or {}
        score = _number(old.get("score")) if isinstance(old, Mapping) else None
        no = str(horse.get("no") or "")
        if no and score is not None and 0 <= score <= 1:
            valid.append((no, horse, score, old))
    if not valid:
        return {
            str(h.get("no")): dict(grade=None, rank=None, strength=None,
                raw_score=None, original_grade=None, formal_top5_rank=None,
                status="missing_research_score",
                reason="元の研究スコアが未取得。正式順位だけでは統合評価を作りません。",
                version=VERSION, retro=False)
            for h in horses if h.get("no") is not None
        }
    scores = [item[2] for item in valid]
    formal_available = any(_formal_top5_rank(h) is not None for _, h, _, _ in valid)
    # Equally valued model scores share a percentile; horse-number sorting is
    # a deterministic tiebreaker, not evidence of different ability.
    def percentile(score):
        less = sum(x < score for x in scores)
        equal = sum(x == score for x in scores)
        return (less + (equal + 1) / 2) / len(scores)

    fused = []
    for no, horse, score, old in valid:
        formal_rank = _formal_top5_rank(horse)
        boost = (6 - formal_rank) / 5 if formal_rank is not None else 0.
        pct = percentile(score)
        strength = (SHADOW_WEIGHT * pct + FORMAL_WEIGHT * boost
                    if formal_available else pct)
        fused.append((no, horse, score, old, formal_rank, strength))
    fused.sort(key=lambda item: (-item[5], -item[2], _number_key(item[1])))
    # Use the *source grade* rather than reconstructing from rounded source
    # scores: a rounded 0.5000 may have been below the A cutoff originally.
    grade_order = sorted(valid, key=lambda item: (-item[2], _number_key(item[1])))
    source_grades = [item[3].get("grade") for item in grade_order]
    output = {}
    for order, (no, horse, score, old, formal_rank, strength) in enumerate(fused, 1):
        source_grade = source_grades[order - 1]
        tier = source_grade if source_grade in GRADES else grade_from_probability(
            grade_order[order - 1][2])
        origin = old.get("grade")
        status = "integrated" if formal_available else "shadow_only"
        reason = (
            f"統合研究順位{order}位。旧研究SABCDは{origin or '判定不可'}。"
            + (f"正式Top5 {formal_rank}位を補助評価。"
               if formal_rank is not None else "正式Top5の加点なし。")
            + ("研究順位90%・正式Top5 10%で順位比較し、既存のランク人数を保持。"
               if formal_available else "正式Top5が未取得のため元研究評価を維持。")
            + "相対順位強度は確率ではなく、購入推奨・正式印・正式順位は変更しません。"
        )
        output[no] = dict(grade=tier, rank=order,
            strength=round(strength, 6), raw_score=score,
            original_grade=origin, formal_top5_rank=formal_rank,
            status=status, reason=reason, version=VERSION,
            retro=old.get("retro") is True)
    for horse in horses:
        no = str(horse.get("no") or "")
        if not no or no in output:
            continue
        old = horse.get("research_sabcd_weight_class") or {}
        output[no] = dict(grade=None, rank=None, strength=None,
            raw_score=None, original_grade=None,
            formal_top5_rank=_formal_top5_rank(horse),
            status="missing_research_score",
            reason="元の研究スコアが未取得。正式順位だけでは統合評価を作りません。",
            version=VERSION, retro=old.get("retro") is True)
    return output


def assign_to_view(view):
    """Attach research-only fields to the temporary UI projection."""
    result = evaluate_race(view)
    for horse in view:
        horse["unified_sabcd"] = result.get(str(horse.get("no")), {})
    return view
