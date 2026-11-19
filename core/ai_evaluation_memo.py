"""Short pre-race, evidence-only AI evaluation memo for the rightmost horse column.

The memo is NOT a betting recommendation, grade, or new model input.
Never use current-race outcomes, final odds, undocumented guesses, or an LLM.
"""
from __future__ import annotations

from collections.abc import Mapping
import re
import unicodedata
from .research_index_rescue import _past3, _number, _day


def _rank(cell):
    if not isinstance(cell, Mapping) or _number(cell.get("value")) is None:
        return None
    rank = _number(cell.get("rank"))
    return int(rank) if rank is not None and rank.is_integer() and rank >= 1 else None


def _positive_rank(value):
    val = _number(value)
    return int(val) if val is not None and val >= 1 and val.is_integer() else None


def _same_venue_near_podium(horse, runs):
    ctx = horse.get("race_context") or {}
    venue = str(ctx.get("venue") or ctx.get("racecourse") or "").strip()
    surface = str(ctx.get("surface") or ctx.get("芝ダート") or "").strip().replace("ダート", "ダ")
    distance = _number(ctx.get("distance"))
    if not venue or not surface or distance is None:
        return []
    return [run for run in runs
            if run["venue"] == venue
            and run["surface"] == surface
            and run["distance"] is not None
            and abs(run["distance"] - distance) <= 200
            and run["finish"] is not None and 1 <= run["finish"] <= 3]


def _nar_class(texts):
    """Read a single explicit NAR A/B/C level; reject mixed/unmapped labels."""
    names = set()
    for value in texts:
        norm = unicodedata.normalize("NFKC", str(value or "")).upper()
        names.update(re.findall(r"(?<![A-Z0-9])([ABC])\s*([1-9])(?!\d)", norm))
    return next(iter(names)) if len(names) == 1 else None


def _explicit_drop(horse, runs):
    """Show NAR C2→C3 only when current and last classes are stated in source.

    Do not infer classes from today's result, age, an unnamed race, or an
    uncomparable historical venue/surface. Fallback to upstream verified
    class_shift only when it explicitly says 降級.
    """
    if horse.get("mode") != "nar":
        return ""
    profile = horse.get("profile") or {}
    context = horse.get("race_context") or {}
    venue = str(context.get("venue") or context.get("racecourse") or "").strip()
    surface = str(context.get("surface") or context.get("芝ダート") or "").replace("ダート", "ダ")
    current = _nar_class(context.get(key) for key in
                         ("raw_class_text", "race_data2", "race_name"))
    previous = None
    if runs and venue and surface and runs[0]["venue"] == venue and runs[0]["surface"] == surface:
        latest = runs[0]["day"]
        sources = [
            run for run in profile.get("runs", ()) or ()
            if isinstance(run, Mapping)
            and _day(run.get("date")) == latest
            and str(run.get("venue") or "").strip() == venue
            and str(run.get("surface") or "").replace("ダート", "ダ") == surface
        ]
        previous = _nar_class(
            value for run in sources for value in
            (run.get("class_raw"), run.get("race_name")))
    if (current and previous and current[0] == previous[0]
            and int(current[1]) > int(previous[1])):
        return f"{previous[0]}{previous[1]}→{current[0]}{current[1]}降級"
    # No class numbers have been reconstructed: retain only an upstream
    # explicit, verified class-shift statement.
    if str(profile.get("class_shift") or "") in ("降級", "クラス降級"):
        return "クラス降級"
    return ""


def _recent_poor_finishes(runs):
    if len(runs) < 2:
        return ""
    first, second = runs[0]["finish"], runs[1]["finish"]
    if first is not None and second is not None and first >= 6 and second >= 6:
        return f"近2走{first}着・{second}着"
    return ""


def evaluation_memo(horse):
    """Return no more than two short factual lines, without mutating the horse.

    Priority: suitability ranks first, then pure ability, workout, expected
    corner. All historical finishes come exclusively from dated pre-start runs.
    Absence of evidence is not negative evidence.
    """
    if not isinstance(horse, Mapping):
        return "特記材料なし"
    course, distance = _rank(horse.get("course")), _rank(horse.get("distance"))
    indices = [
        f"コース指数{course}位" if course is not None and course <= 3 else "",
        f"距離指数{distance}位" if distance is not None and distance <= 3 else "",
    ]
    indices = [item for item in indices if item]
    ability = _positive_rank(horse.get("ability_rank"))
    corner = _positive_rank(horse.get("corner"))
    primary = "・".join(indices)
    if not primary and ability is not None and ability <= 3:
        primary = f"純能力{ability}位"
    if not primary and horse.get("mode") == "jra" and horse.get("training") == "A":
        primary = "調教A"
    if not primary and corner is not None and corner <= 3:
        primary = f"4角{corner}番手想定"

    runs = _past3(horse)
    near = _same_venue_near_podium(horse, runs)
    near_wins = sum(run["finish"] == 1 for run in near)
    wins = sum(run["finish"] == 1 for run in runs)
    supportive = ""
    if near_wins:
        supportive = f"同場近似距離{near_wins}勝"
    elif near:
        supportive = f"同場近似距離3着内{len(near)}回"
    elif wins:
        supportive = f"近3走{wins}勝"
    elif horse.get("mode") == "jra" and horse.get("training") == "A" and primary != "調教A":
        supportive = "調教A"
    elif corner is not None and corner <= 3 and not primary.startswith("4角"):
        supportive = f"4角{corner}番手想定"

    inputs = horse.get("research_inputs") or {}
    n, pct = _number(inputs.get("jockey_n")), _number(inputs.get("jockey_rate"))
    if not supportive and n is not None and n >= 20 and pct is not None:
        threshold = 35 if horse.get("mode") == "nar" else 30
        if pct >= threshold:
            supportive = f"騎手複勝率{pct:g}%（{int(n)}走）"

    profile = horse.get("profile") or {}
    state = str(profile.get("state") or "")
    caution = str(horse.get("caution") or "")
    declined = state in ("注意", "下降") or "近走下降" in caution or "指数下降" in caution
    age_review = horse.get("research_age_suitability") or {}
    if isinstance(age_review, Mapping) and age_review.get("qualified") is True:
        a = age_review["age"]
        c, d = age_review["course_age_rank"], age_review["distance_age_rank"]
        starts, placed = age_review["exact_starts"], age_review["exact_podiums"]
        primary = f"{a}歳内 コース{c}位・距離{d}位"
        detail = f"同場同距離{starts}戦{placed}回3着内"
        if declined:
            detail += "／近走下降注意"
        elif "昇級" in str(profile.get("class_shift") or ""):
            detail += "／昇級注意"
        return primary + "\n" + detail
    # A strong same-age comparison is worth showing even if the research
    # C-floor is NOT qualified (e.g. no recent exact-condition podiums).
    # This changes the memo ONLY, never the unified grade or selection.
    if isinstance(age_review, Mapping) and (age_review.get("cohort_n") or 0) >= 3:
        c = _positive_rank(age_review.get("course_age_rank"))
        d = _positive_rank(age_review.get("distance_age_rank"))
        a = _positive_rank(age_review.get("age"))
        if a is not None and c is not None and d is not None and c <= 2 and d <= 2:
            drop = _explicit_drop(horse, runs)
            poor = _recent_poor_finishes(runs)
            if drop or poor:
                primary = f"{a}歳内 コース{c}位・距離{d}位"
                detail = "／".join(x for x in (drop, poor) if x)
                if not poor and declined:
                    detail += "／近走下降注意"
                return primary + "\n" + detail
    secondary = "／".join(x for x in (supportive, "近走下降注意" if declined else "") if x)
    if not primary:
        primary, secondary = secondary, ""
    if not primary:
        return "特記材料なし"
    return primary + ("\n" + secondary if secondary else "")
