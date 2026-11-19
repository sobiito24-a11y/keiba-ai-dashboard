"""JRA race-day V3 checking lens, not a silently fitted ranking model.

Only frozen/available pre-race ranking inputs can enter the comparison.
Class groups are from the explicitly saved JRA race conditions, NOT from
legacy A級/B級 values that once confused turf rail A/B with race class.

The 93-race audit is descriptive. No observed win rate is used to assign
horse-specific probabilities, rank points, bets, or revised SABCD grades.
"""
from __future__ import annotations

from html import escape
from collections.abc import Mapping
import math
import re
import unicodedata


VERSION = "jra_race_day_check_v3_20261115"
# Observed only on 2026-11-07, 08, 14; NOT a fitted prediction table.
AUDIT = {
    "2歳未勝利": (30, 21, 22),
    "1勝": (28, 12, 14),
    "2勝": (15, 10, 12),
    "3勝": (8, 5, 6),
    "OP・重賞": (8, 4, 4),
    "障害": (4, 2, 3),
}


def _rank(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        num = float(str(value).strip().removesuffix("位"))
    except (TypeError, ValueError, OverflowError):
        return None
    return int(num) if math.isfinite(num) and num >= 1 and num.is_integer() else None


def class_group(info):
    """Use source-visible *current* race conditions, never former local grades."""
    if not isinstance(info, Mapping):
        return ""
    condition = unicodedata.normalize(
        "NFKC", str(info.get("race_data2") or info.get("raw_class_text") or "")
    )
    name = unicodedata.normalize("NFKC", str(info.get("race_name") or ""))
    surface = str(info.get("surface") or "")
    label = unicodedata.normalize("NFKC", str(info.get("class_label_v2") or info.get("class_label") or ""))
    raw = condition + " " + name
    if ("障" in surface or re.search(r"障害|ジャンプ", raw)):
        return "障害"
    # Explicit G1–G3 and Jpn grades override generic OPEN.
    if (re.search(r"(?<![A-Za-z0-9])(?:Jpn|G)[123](?!\d)", label, flags=re.I)
            or label in ("G1", "G2", "G3", "L", "OP")
            or re.search(r"(?<![A-Za-z0-9])(?:Jpn|G)[123](?!\d)|重賞|オープン|リステッド", raw, flags=re.I)):
        return "OP・重賞"
    for klass in ("3勝", "2勝", "1勝"):
        if klass in condition or label == klass:
            return klass
    if "未勝利" in condition or label == "未勝利":
        return "2歳未勝利" if "2歳" in condition else "未勝利（その他）"
    if "新馬" in condition or "メイクデビュー" in raw:
        return "新馬"
    return ""


def _model_b_map(view, report):
    """Fail closed if B is missing, not JRA, not safely aligned, or re-run postrace."""
    if not isinstance(report, Mapping) or report.get("status") != "ready":
        return {}
    if report.get("mode", "jra").lower() != "jra":
        return {}
    if report.get("historical_recalculation") or report.get("prediction_origin") == "retrospective_recalculation":
        return {}
    if not isinstance(view, list) or not view:
        return {}
    expected = [str(h.get("no")) for h in view]
    if len(expected) != len(set(expected)):
        return {}
    items = report.get("horses")
    if not isinstance(items, list) or len(items) != len(expected):
        return {}
    mapped = {}
    for item in items:
        if not isinstance(item, Mapping):
            return {}
        no = str(item.get("no"))
        rank = _rank(item.get("rank"))
        if no in mapped or rank is None or rank > len(view):
            return {}
        mapped[no] = rank
    if set(mapped) != set(expected) or sorted(mapped.values()) != list(range(1, len(view) + 1)):
        return {}
    return mapped


def annotate(view, report=None, race_info=None):
    """Attach non-scoring audit badges to the *display view* only."""
    if not view or view[0].get("mode") != "jra":
        return view
    group = class_group(race_info or view[0].get("race_context"))
    model = _model_b_map(view, report)
    for horse in view:
        formal = _rank(horse.get("rank"))
        current = _rank(horse.get("current_evaluation_rank"))
        pure = _rank(horse.get("ability_rank"))
        b_rank = model.get(str(horse.get("no")))
        agreements = sum(x is not None and x <= 5 for x in (formal, current, b_rank))
        notes = []
        category = ""
        if formal == 1 and b_rank is not None and b_rank >= 6:
            category = "軸注意"
            notes.append("正式1位だが研究BではTop5外")
        elif formal is not None and formal > 5 and b_rank is not None and b_rank <= 5:
            category = "取りこぼし再確認"
            notes.append(f"研究B {b_rank}位・正式{formal}位")
            if current is not None and current <= 5:
                notes.append(f"今回評価{current}位も支持")
        elif formal is not None and formal <= 5 and b_rank is not None and b_rank <= 5 and current is not None and current <= 5:
            category = "3評価一致"
            notes.append("正式・研究B・今回評価のTop5が一致")
        elif formal is not None and formal > 5 and current is not None and current <= 5:
            category = "取りこぼし再確認"
            notes.append(f"今回評価{current}位・正式{formal}位")
        if formal == 1 and group == "1勝":
            notes.append("1勝クラス：正式1位の信頼度は要検証")
        if group == "2歳未勝利" and formal is not None and formal >= 6 and pure is not None and pure <= 5:
            notes.append("2歳未勝利：純能力Top5を無印だけで消さない")
            if not category:
                category = "取りこぼし再確認"
        horse["jra_race_day_check"] = {
            "version": VERSION, "class_group": group, "role": category,
            "formal_rank": formal, "current_rank": current,
            "ability_rank": pure, "model_b_rank": b_rank,
            "top5_agreement": agreements, "model_b_ready": bool(model),
            "reasons": notes, "rank_changed": False, "probability_calibrated": False,
        }
    return view


def render(view):
    """One compact header for quick race-day decisions; no betting directions."""
    if not view or view[0].get("mode") != "jra":
        return ""
    states = [h.get("jra_race_day_check") for h in view]
    if not states or not isinstance(states[0], Mapping):
        return ""
    group = states[0].get("class_group", "")
    stats = AUDIT.get(group)
    segments = []
    if stats:
        n, formal, b = stats
        segments.append(f"保存済み{n}Rで正式Top5の勝ち馬捕捉{formal}/{n}" +
                        (f"、研究B {b}/{n}" if states[0].get("model_b_ready") else ""))
    elif group:
        segments.append("保存93Rではこの区分の十分な比較なし")
    if group == "1勝":
        segments.append("取りこぼし最多のため、上位順位のみで軸を決めない")
    elif group == "2歳未勝利":
        segments.append("出走経験や比較材料が少ないため、評価の根拠と欠損を確認")
    elif group == "OP・重賞":
        segments.append("比較標本が少ないため、ランクだけで取捨を決めない")
    elif group == "障害":
        segments.append("材料不足が多いため、評価の根拠と欠損を確認")

    rechecks = []
    warnings = []
    agreed = []
    for horse in view:
        d = horse.get("jra_race_day_check") or {}
        no, name = str(horse.get("no") or ""), str(horse.get("name") or "")
        if not no or not name:
            continue
        label = f"{no}番{name}"
        if d.get("role") == "軸注意":
            warnings.append(label)
        elif d.get("role") == "取りこぼし再確認":
            rechecks.append((d.get("model_b_rank") or d.get("current_rank") or 999, label))
        elif d.get("role") == "3評価一致":
            agreed.append((d.get("model_b_rank") or 999, label))
    if warnings:
        segments.append("軸注意 " + "・".join(warnings[:2]))
    if agreed:
        segments.append("3評価一致 " + "・".join(label for _, label in sorted(agreed)[:3]))
    if rechecks:
        segments.append("正式Top5外の再確認 " + "・".join(label for _, label in sorted(rechecks)[:3]))
    if not states[0].get("model_b_ready"):
        segments.append("研究B未照合（保存順位や入力が揃わない場合は代用しない）")
    segments.append("正式ランク・印は維持。93Rの観測値は予測確率ではない")
    return ('<p class="jra-race-day-v3" role="note"><strong>'
            + "JRA V3・当日照合（クラス " + escape(group or "判定不可") + "）"
            + '</strong> ' + "｜".join(escape(x) for x in segments) + "。</p>")
