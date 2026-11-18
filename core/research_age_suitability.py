"""Conservative same-age suitability C floor for three-and-older mixed races.

Research/display projection only. Eligible D becomes C (not an extra Top5
horse); unchanged: frozen model score, unified rank, formal marks, saved
snapshots and buying advice. All past finishes are checked before race date.

Frozen research rule (2026-11-19):
- explicit three-and-older race with actual 3yo and older runners;
- at least THREE horses of the same age, all with BOTH numeric indices;
- course AND distance ranks <=2 against that same-age cohort;
- at least two DISTINCT dated prior starts in the latest three, each at the
  exact venue + surface + distance and placed 1st-3rd.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

from .research_index_rescue import _number, _past3

VERSION = "age-cohort-suitability-c-floor-20261119-v1"


def _age(horse):
    raw = unicodedata.normalize("NFKC", str(horse.get("age") or ""))
    match = re.search(r"(\d+)\s*$", raw)
    return int(match.group(1)) if match else None


def _metric_value(horse, key):
    raw = horse.get(key)
    return _number(raw.get("value")) if isinstance(raw, Mapping) else None


def _age_open_race(view):
    if not view or not all(isinstance(h, Mapping) for h in view):
        return False
    modes = {h.get("mode") for h in view}
    if len(modes) != 1 or next(iter(modes)) not in ("nar", "jra"):
        return False
    contexts = [h.get("race_context") or {} for h in view]
    dates = {str(ctx.get("race_date") or ctx.get("date") or "") for ctx in contexts}
    if len(dates) != 1 or not next(iter(dates)):
        return False
    raw = " ".join(str(contexts[0].get(key) or "") for key in
                   ("race_data2", "raw_class_text", "race_data"))
    raw = unicodedata.normalize("NFKC", raw)
    ages = {_age(h) for h in view}
    # 3歳限定戦や4歳以上のみでは若齢馬との比較ではない。
    return (bool(re.search(r"3歳(?:以上|上)", raw)) and
            3 in ages and any(a is not None and a >= 4 for a in ages))


def _podiums_exact(horse):
    context = horse.get("race_context") or {}
    venue = str(context.get("venue") or context.get("racecourse") or "").strip()
    surface = str(context.get("surface") or context.get("芝ダート") or "").replace("ダート", "ダ")
    distance = _number(context.get("distance"))
    if not venue or not surface or distance is None:
        return [], []
    exact = [r for r in _past3(horse)
             if r["venue"] == venue and r["surface"] == surface
             and r["distance"] == distance]
    placed = [r for r in exact if r["finish"] is not None and 1 <= r["finish"] <= 3]
    return exact, placed


def evaluate_race(view):
    """Return immutable-evidence summaries keyed by horse number (no grade edits)."""
    horses = [h for h in view or () if isinstance(h, Mapping)]
    output = {}
    for h in horses:
        no = str(h.get("no") or "")
        if no:
            output[no] = dict(qualified=False, label=None, reason=None,
                              age=_age(h), course_age_rank=None,
                              distance_age_rank=None, cohort_n=0,
                              exact_starts=0, exact_podiums=0,
                              version=VERSION, research_only=True)
    if not _age_open_race(horses):
        return output
    by_age = {}
    for horse in horses:
        age = _age(horse)
        if age is not None:
            by_age.setdefault(age, []).append(horse)

    for age, group in by_age.items():
        if len(group) < 3:
            continue
        # Reject partial same-age coverage; otherwise "top 2" is artificially
        # easy when competitors have missing measurements.
        course = [_metric_value(h, "course") for h in group]
        distance = [_metric_value(h, "distance") for h in group]
        if any(x is None for x in course + distance):
            continue
        for horse, c, d in zip(group, course, distance):
            no = str(horse.get("no") or "")
            if no not in output:
                continue
            cr = 1 + sum(x > c for x in course)
            dr = 1 + sum(x > d for x in distance)
            exact, placed = _podiums_exact(horse)
            valid = cr <= 2 and dr <= 2 and len(placed) >= 2
            details = dict(age=age, course_age_rank=cr, distance_age_rank=dr,
                           cohort_n=len(group), exact_starts=len(exact),
                           exact_podiums=len(placed), qualified=valid)
            if valid:
                # Only verified pre-race starts. Previous wins are NOT counted
                # multiple times for course and distance.
                details.update(
                    label="同年齢適性",
                    reason=(f"{age}歳内 コース指数{cr}位・距離指数{dr}位"
                            f"（同年齢{len(group)}頭）。同場同距離の過去3走"
                            f"{len(exact)}戦{len(placed)}回3着以内。"
                            "同じ過去走は1回だけ数え、近走不振・昇級の"
                            "警戒情報は維持。適性根拠による表示C下限"
                            "（順位・モデル値・正式印は不変）。"))
            output[no].update(details)
    return output


def assign_to_view(view):
    evidence = evaluate_race(view)
    for horse in view or ():
        if not isinstance(horse, dict):
            continue
        no = str(horse.get("no") or "")
        review = evidence.get(no, {})
        horse["research_age_suitability"] = review
        current = horse.get("unified_sabcd") or {}
        if not review.get("qualified") or not isinstance(current, Mapping):
            continue
        if current.get("grade") != "D":
            continue
        adjusted = dict(current)
        adjusted["grade"] = "C"
        adjusted["grade_before_suitability"] = "D"
        adjusted["age_cohort_c_floor"] = True
        adjusted["suitability_c_floor"] = True
        adjusted["status_before_suitability"] = current.get("status")
        adjusted["status"] = "age_cohort_suitability_c_floor"
        adjusted["reason"] = (str(current.get("reason") or "") +
            "【同年齢適性補正】" + str(review.get("reason") or "") +
            "発走前の研究Dを表示Cに補正。統合順位・研究スコアは変更しません。")
        horse["unified_sabcd"] = adjusted
    return view
