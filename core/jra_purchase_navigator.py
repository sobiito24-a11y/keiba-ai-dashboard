"""Read-only navigation derived from the existing JRA comparison rows.

No prediction, odds, market, results, tickets, or Snapshot writes belong here.
"""
from __future__ import annotations

import math
import unicodedata
from decimal import Decimal
from datetime import date
from typing import Any, Mapping, Sequence
from .jra_display_mark import jra_display_mark_from_row


DESCRIPTIONS = {
    "強軸": "純能力と今回評価が一致し、上位との差もあるレース",
    "評価分裂": "純能力と今回評価のズレが大きいレース",
    "上位混戦": "上位候補は残るが、1頭固定には慎重なレース",
}
GUIDES = {
    "強軸": (
        "Top5 1位を軸候補として扱えるレース",
        "ワイド軸流し向き",
        "相手はCORE・SETUP・ABILITYから確認",
        "馬連は相手を絞れる場合のみ",
    ),
    "上位混戦": (
        "Top5 1位の単独固定は慎重",
        "CORE中心。ABILITYは機械的に消さない",
        "SETUPは今回条件の上昇馬として相手候補",
        "BOXまたは複数軸を検討",
    ),
    "評価分裂": (
        "印順購入は非推奨",
        "見送り優先",
        "買う場合は少額で候補を広めに確認",
    ),
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _rank(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number >= 1 and number.is_integer() else None


def classify_jra_horse_role(ability_rank: Any, top5_rank: Any) -> str | None:
    ability, current = _rank(ability_rank), _rank(top5_rank)
    if ability is None or current is None:
        return None
    if ability <= 5:
        return "CORE" if current <= 5 else "ABILITY"
    return "SETUP" if current <= 5 else "OTHER"


def calculate_top5_swap_count(pure_top5: set[str], jra_top5: set[str]) -> int:
    return len(pure_top5 - jra_top5)


def build_jra_buy_candidates(rows: Sequence[Mapping[str, Any]], status: str = "強軸") -> dict[str, Any]:
    """Select by the table's final display mark; ranks only sort within roles."""
    candidates, attention, seen = [], [], set()
    def order(row):
        score = _number(row.get("jra_top5_score"))
        return (_rank(row.get("jra_top5_rank")) or math.inf,
                -score if score is not None else math.inf)
    roles = {"◎": "中心", "○": "本線", "▲": "本線", "✔": "狙い", "△": "押さえ参考"}
    # Python's stable sort preserves the detail table order for exact ties.
    for row in sorted(rows, key=order):
        number = _rank(row.get("number"))
        if number is None or number in seen:
            continue
        seen.add(number)
        mark = jra_display_mark_from_row(row).replace("\ufe0e", "").replace("\ufe0f", "")
        horse = {"number": str(number), "name": str(row.get("name") or "")}
        role = roles.get(mark)
        if role:
            candidates.append(dict(horse, role=role))
        elif mark == "✓":
            attention.append(horse)
    return {"buy_candidates": [] if status == "評価分裂" else [h for h in candidates if h["role"] != "押さえ参考"],
            "reference_candidates": candidates if status == "評価分裂" else [h for h in candidates if h["role"] == "押さえ参考"], "buy_groups": {
        role: [h for h in candidates if h["role"] == role] for role in ("中心", "本線", "押さえ参考", "狙い")
    }, "hole_attention": attention}


def _saved_interval_days(row: Mapping[str, Any], race_info: Mapping[str, Any]) -> int | None:
    for key in ("_days_since_last", "レース間隔日数", "days_since_last", "_新聞前走間隔日数"):
        value = _number(row.get(key))
        if value is not None and value >= 0 and value.is_integer():
            return int(value)
    # Only an explicitly labelled previous run; never infer from older runs or today's date.
    runs = row.get("_past_runs")
    if not isinstance(runs, list):
        return None
    previous = [r for r in runs if isinstance(r, Mapping) and r.get("label") == "前走"]
    if len(previous) != 1:
        return None
    try:
        current = date.fromisoformat(str(race_info.get("race_date")))
        last = date.fromisoformat(str(previous[0].get("race_date")))
    except ValueError:
        return None
    days = (current - last).days
    return days if days >= 0 else None


def build_jra_layoff_warnings(rows: Sequence[Mapping[str, Any]], race_info: Mapping[str, Any],
                             saved_rows: Sequence[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """Join only saved interval/date material; scores and marks never cross this boundary."""
    saved: dict[int, list[Mapping[str, Any]]] = {}
    for row in saved_rows:
        number = _rank(row.get("number", row.get("馬番")))
        if number is not None:
            saved.setdefault(number, []).append(row)
    warnings, seen = [], set()
    for row in sorted(rows, key=lambda r: _rank(r.get("jra_top5_rank")) or math.inf):
        number = _rank(row.get("number"))
        if number is None or number in seen:
            continue
        seen.add(number)
        days = _saved_interval_days(row, race_info)
        matches = saved.get(number, [])
        if days is None and len(matches) == 1:
            days = _saved_interval_days(matches[0], race_info)
        if days is not None and days >= 90:
            warnings.append({"number": str(number), "name": str(row.get("name") or ""),
                             "days": days, "is_top1": _rank(row.get("jra_top5_rank")) == 1})
    return warnings


def classify_jra_race_structure(
    *, leaders_match: bool | None, top5_score_gap: Any,
    ability_gap: Any, swap_count: Any,
) -> str:
    score_gap, pure_gap, swaps = map(_number, (top5_score_gap, ability_gap, swap_count))
    if (not isinstance(leaders_match, bool) or score_gap is None or pure_gap is None
            or swaps is None or min(score_gap, pure_gap, swaps) < 0 or not swaps.is_integer()):
        return "判定材料不足"
    if leaders_match and score_gap >= 6.0 and pure_gap >= 3.0 and swaps <= 1:
        return "強軸"
    if not leaders_match or swaps >= 2:
        return "評価分裂"
    return "上位混戦"


def _race_kind(info: Mapping[str, Any]) -> str:
    values = [str(info.get(k) or "") for k in
              ("surface", "course_type", "race_name", "race_data", "distance_label", "label")]
    text = unicodedata.normalize("NFKC", " ".join(values)).lower()
    if "障" in text or any(x in text for x in ("jump", "steeplechase", "hurdle")):
        return "jump"
    surface = unicodedata.normalize("NFKC", str(info.get("surface") or info.get("course_type") or "")).lower()
    if surface in {"芝", "ダ", "ダート", "turf", "dirt"} or "芝" in text or "ダート" in text:
        return "flat"
    return "unknown"


def build_jra_purchase_navigation(
    rows: Sequence[Mapping[str, Any]], *, race_mode: str, race_info: Mapping[str, Any],
    saved_rows: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Consume canonical comparison fields only; never mutate or re-rank input.

    Reject incomplete/ambiguous ranks, rather than filling missing data with zero
    or borrowing ranks from legacy marks, Candidate B, or another display path.
    """
    if race_mode != "jra":
        return {"show": False}
    result: dict[str, Any] = {
        "show": True, "status": "判定材料不足", "description": "必要な順位・値を確認できません。",
        "guides": [], "horses": [], "groups": {k: [] for k in ("CORE", "ABILITY", "SETUP", "OTHER")},
        "axis": None, "partners": [], "leaders_match": None,
        "top5_score_gap": None, "ability_gap": None, "swap_count": None,
    }
    kind = _race_kind(race_info)
    if kind == "jump":
        result.update(status="対象外", description="障害レース：買い方ナビ対象外")
        return result
    if kind != "flat" or len(rows) < 2:
        return result
    horses = []
    for row in rows:
        # Explicit projection is also the odds/results exclusion boundary.
        horse = {
            "number": _rank(row.get("number")), "name": str(row.get("name") or ""),
            "ability_rank": _rank(row.get("_v1_ability_rank")),
            "ability_value": _number(row.get("jra_pure_ability_score")),
            "top5_rank": _rank(row.get("jra_top5_rank")),
            "top5_score": _number(row.get("jra_top5_score")),
        }
        if any(horse[k] is None for k in ("number", "ability_rank", "ability_value", "top5_rank", "top5_score")):
            return result
        horse["number"] = str(horse["number"])
        horse["role"] = classify_jra_horse_role(horse["ability_rank"], horse["top5_rank"])
        horses.append(horse)
    n = len(horses)
    if len({h["number"] for h in horses}) != n or {h["top5_rank"] for h in horses} != set(range(1, n+1)):
        return result
    if any(h["ability_rank"] > n for h in horses):
        return result
    pure_first = [h for h in horses if h["ability_rank"] == 1]
    pure_second = [h for h in horses if h["ability_rank"] == 2]
    if len(pure_first) != 1 or len(pure_second) != 1:
        return result
    ordered = sorted(horses, key=lambda h: h["top5_rank"])
    # Values inconsistent with their own ranks do not justify a strong-axis label.
    by_ability = sorted(horses, key=lambda h: h["ability_rank"])
    if any(a["ability_value"] < b["ability_value"] for a, b in zip(by_ability, by_ability[1:])):
        return result
    if any(a["top5_score"] < b["top5_score"] for a, b in zip(ordered, ordered[1:])):
        return result
    pure_top5 = {h["number"] for h in horses if h["ability_rank"] <= 5}
    current_top5 = {h["number"] for h in horses if h["top5_rank"] <= 5}
    match = pure_first[0]["number"] == ordered[0]["number"]
    # Do not round before threshold comparisons.
    score_gap = float(Decimal(str(ordered[0]["top5_score"])) - Decimal(str(ordered[1]["top5_score"])))
    ability_gap = float(Decimal(str(pure_first[0]["ability_value"])) - Decimal(str(pure_second[0]["ability_value"])))
    swaps = calculate_top5_swap_count(pure_top5, current_top5)
    status = classify_jra_race_structure(leaders_match=match, top5_score_gap=score_gap,
                                         ability_gap=ability_gap, swap_count=swaps)
    if status == "判定材料不足":
        return result
    groups = {k: [h for h in ordered if h["role"] == k] for k in result["groups"]}
    axis = ordered[0] if status == "強軸" else None
    partners = [h for h in ordered if 2 <= h["top5_rank"] <= 5 or h["role"] == "ABILITY"] if axis else []
    result.update(status=status, description=DESCRIPTIONS[status], guides=list(GUIDES[status]),
                  horses=ordered, groups=groups, axis=axis, partners=partners,
                  leaders_match=match, top5_score_gap=score_gap, ability_gap=ability_gap, swap_count=swaps)
    result.update(build_jra_buy_candidates(rows, status))
    result["layoff_warnings"] = build_jra_layoff_warnings(rows, race_info, saved_rows)
    return result
