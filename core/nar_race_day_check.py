"""NAR research-only, class-aware race-day review.

Observed NAR 179R / 11-07..11-11: ability ranks 4..8 and projected
4C 1..3 placed 74/183; projected 4C 4+ placed 117/693.
Jockey course rate 35%+ with >=20 samples: 37/68 vs 37/115 in
the 4C-front subset. These are exploratory, NOT per-horse probabilities.

No results, live odds, popularity or race-day outcome is used here.
This never changes saved predictions, ranks, marks or bets.
"""
from __future__ import annotations

from collections.abc import Mapping
from html import escape
import math
import re
import unicodedata

VERSION = "nar_race_day_research_20261115"


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        x = float(str(value).strip().replace("位", "").replace("%", ""))
        return x if math.isfinite(x) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _rank(value):
    n = _number(value)
    return int(n) if n is not None and n >= 1 and n.is_integer() else None


def _text(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def race_group(info):
    """Do not pool venue-specific C1 and JRA 1勝 as the same class."""
    if not isinstance(info, Mapping):
        return "区分不明"
    name = _text(info.get("race_name"))
    raw = _text(info.get("race_data2") or info.get("raw_class_text") or "")
    label = _text(info.get("class_label_v2") or info.get("class_label") or "")
    s = " ".join((name, raw, label))
    if re.search(r"重賞|Jpn[123]|(?<![A-Z])G[123](?!\d)", s, re.I):
        return "重賞・交流"
    if "新馬" in s:
        return "新馬"
    if re.search(r"2歳|2才", s):
        return "2歳戦"
    if re.search(r"3歳|3才", s) and not re.search(r"3歳以上|3才以上", s):
        return "3歳限定"
    # Prefer explicit current class, never guess from a past-race name.
    match = re.search(r"(?<![A-Za-z])([ABC])([123])(?=級|組|[一二三四五六七八九十]|\b)", s)
    if match:
        return match.group(1) + match.group(2) + "級"
    match = re.search(r"(?<![A-Za-z])([ABC])級", s)
    if match:
        return match.group(1) + "級"
    return "区分不明"


def annotate(view, race_info=None):
    if not view or view[0].get("mode") != "nar":
        return view
    info = race_info or view[0].get("race_context") or {}
    venue = _text(info.get("racecourse") or info.get("venue"))
    # Ban'ei is a separate sport: 4th-corner thoroughbred projections do not apply.
    if "帯広" in venue or "ばんえい" in venue or "ばんえい" in _text(info.get("race_name")):
        for h in view:
            h["nar_race_day_check"] = {
                "version": VERSION, "group": "ばんえい・対象外",
                "role": "", "reasons": [], "rank_changed": False,
                "probability_calibrated": False,
            }
        return view
    group = race_group(info)
    for h in view:
        ability = _rank(h.get("ability_rank"))
        corner = _rank(h.get("corner"))
        formal = _rank(h.get("rank"))
        formal_member = h.get("formal_member")
        outside = (formal_member is False) or (formal is not None and formal > 5)
        inputs = h.get("research_inputs") or {}
        starts = _number(inputs.get("jockey_n"))
        rate = _number(inputs.get("jockey_rate"))
        strong_jockey = (starts is not None and starts >= 20 and
                         rate is not None and 35 <= rate <= 100)
        front_middle = ability is not None and 4 <= ability <= 8 and corner is not None and corner <= 3
        role, reasons = "", []
        if front_middle:
            role = "中位×4角前"
            reasons.append(f"純能力{ability}位・予測4角{corner}番手")
            if strong_jockey:
                reasons.append(f"騎手コース複勝率{rate:g}%・{starts:g}走")
            if outside:
                role = "Top5外再確認"
                reasons.append("正式Top5外。予測位置だけで買い推奨にはしない")
        if ability is not None and ability <= 3 and corner is not None and corner >= 7:
            role = "位置予測注意"
            reasons.append(f"純能力{ability}位だが予測4角{corner}番手")
            reasons.append("後方予測のみで除外しない")
        h["nar_race_day_check"] = {
            "version": VERSION, "group": group, "role": role,
            "reasons": reasons, "ability_rank": ability, "corner4_rank": corner,
            "jockey_supported": strong_jockey, "rank_changed": False,
            "probability_calibrated": False,
        }
    return view


def render(view):
    if not view or view[0].get("mode") != "nar":
        return ""
    first = view[0].get("nar_race_day_check")
    if not isinstance(first, Mapping):
        return ""
    group = first["group"]
    notices = []
    for role in ("Top5外再確認", "中位×4角前", "位置予測注意"):
        items = [h for h in view if (h.get("nar_race_day_check") or {}).get("role") == role]
        if items:
            notices.append(role + " " + "・".join(
                f"{h.get('no')}番{h.get('name')}" for h in items[:3]))
    if not notices:
        notices.append("今回の固定条件では再確認候補なし")
    text = (
        f"NAR研究照合（{group}）｜" + "｜".join(notices)
        + "｜過去179Rの能力4〜8位：4角前予測74/183頭（40.4%）、"
        + "4角4番手以下117/693頭（16.9%）。"
        + "騎手35%以上・20走以上は補助根拠。"
        + "場・クラス別の確率ではなく、正式印・順位は変更しません。"
    )
    return '<p class="nar-race-day-check" role="note">' + escape(text) + '</p>'
