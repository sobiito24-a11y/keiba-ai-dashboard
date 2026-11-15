"""JRA ranks: pre-race disagreement audit, never post-race reranking.

On a 93-race archive, formal Top5 found 54 winners; union with the saved
current-evaluation Top5 found 64, but increased candidates from 5.0 to 6.1
per race. Therefore we flag differences as CHECKS, not additional bets or
a replacement for the saved official prediction.
"""
from html import escape
import math
import re


def _rank(value):
    if isinstance(value, bool) or value is None:
        return None
    text = str(value).strip().removesuffix("位")
    try:
        value = float(text)
    except (ValueError, TypeError):
        return None
    return int(value) if math.isfinite(value) and value >= 1 and value.is_integer() else None


def _rest_at_least_70_days(value):
    text = str(value or "")
    # A "中10週" display is 70+ days; absence stays unknown, not rested.
    match = re.search(r"中\s*(\d+)\s*週", text)
    if match:
        return int(match[1]) >= 10
    match = re.search(r"(\d+)\s*日", text)
    return bool(match and int(match[1]) >= 70)


def annotate(view):
    """Add read-only flags to transient JRA display rows."""
    if not view or view[0].get("mode") != "jra":
        return view
    for h in view:
        formal = _rank(h.get("rank"))
        current = _rank(h.get("current_evaluation_rank"))
        ability = _rank(h.get("ability_rank"))
        reasons = []
        role = None
        if formal is not None and formal > 5 and current is not None and current <= 5:
            role = "再確認"
            reasons.append(f"今回評価{current}位／正式{formal}位")
            if ability is not None and ability <= 5:
                reasons.append(f"純能力{ability}位")
        if formal == 1:
            if current is not None and current >= 5:
                role = "軸注意"
                reasons.append(f"正式1位でも今回評価{current}位")
            if ability is not None and ability >= 6:
                role = "軸注意"
                reasons.append(f"純能力{ability}位")
        # A clearly documented pre-race layoff plus poor workout is a
        # verification warning, never a hidden numeric model penalty.
        training = str(h.get("training") or "").strip()
        if formal is not None and formal <= 3 and _rest_at_least_70_days(h.get("rest")) and (
                training.startswith("C") or training.startswith("D")):
            role = "軸注意"
            reasons.append("70日以上休養＋調教C/D")
        h["jra_rank_second_look"] = {
            "role": role, "reasons": reasons, "formal_rank": formal,
            "current_rank": current, "ability_rank": ability,
            "research_only": True,
        }
    return view


def render(view):
    """Show a compact check-list of rank conflicts, not a bet recommendation."""
    if not view or view[0].get("mode") != "jra":
        return ""
    caution = []
    recheck = []
    for horse in view:
        flag = horse.get("jra_rank_second_look") or {}
        reasons = flag.get("reasons") or []
        if not reasons:
            continue
        no = str(horse.get("no") or "").strip()
        name = str(horse.get("name") or "").strip()
        if not no or not name:
            continue
        line = escape(no+"番 "+name+"： "+"／".join(reasons))
        if flag.get("role") == "軸注意":
            caution.append(line)
        elif flag.get("role") == "再確認":
            recheck.append((flag.get("current_rank") or 999, line))
    if not caution and not recheck:
        return ""
    recheck.sort(key=lambda item: item[0])
    segments=[]
    if caution:
        segments.append("軸注意 "+ "・".join(caution[:2]))
    if recheck:
        segments.append("Top5外の再確認 "+ "・".join(line for _,line in recheck[:3]))
    return ('<p class="jra-rank-disagreement" role="note"><strong>'
            'JRAランク照合（購入推奨ではありません）</strong> '
            + "｜".join(segments) +
            '。正式順位は変更せず、発走前の異なる評価が食い違う馬を確認する研究表示。</p>')
