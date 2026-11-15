"""Read-only experimental fusion of saved formal order and research SABCD.

Frozen research rule: 25% of saved formal order + 75% of the pre-race
weight/class SABCD model order. A lower relative ordinal is better.

The two inputs share some ability/evidence and MUST NOT be presented as
independent probabilities. This output is an uncalibrated rank comparison,
NOT a S/A/B/C/D grade, podium probability, official selection or betting
advice. It never changes formal rank/score, SABCD, marks, odds or archive data.
Retrospective / missing core input stays explicitly labelled.

2026-11-11, 14, 15 research: common-five captures on 11/15:
JRA formal 19 winners/47 podium vs fusion 20/52 in 28 races,
NAR formal 34/95 vs fusion 35/100 in 41 races.
The 11/15 test is now consumed and must not be used for further tuning.
"""
from __future__ import annotations

from collections.abc import Mapping
from math import isfinite

from .final_candidate_selection import formal_score
from .prediction_table_ui import number

VERSION = "formal-sabcd-ordinal-shadow-20261116"
FORMAL_WEIGHT = 0.25
SABCD_WEIGHT = 0.75


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        n = number(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return float(n) if n is not None and isfinite(float(n)) else None


def _positive_rank(value):
    n = _number(value)
    return int(n) if n is not None and n >= 1 and n.is_integer() else None


def _prob(value):
    n = _number(value)
    return n if n is not None and 0 <= n <= 1 else None


def _no(horse):
    n = _positive_rank(horse.get("no"))
    return n if n is not None else 10**8


def evaluate_race(view):
    """Never use outcomes, final odds, postrace material, or a forced S quota."""
    horses = [h for h in (view or ()) if isinstance(h, Mapping)]
    if not horses:
        return {}
    if len({_no(h) for h in horses}) != len(horses):
        raise ValueError("研究統合には重複のない馬番が必要です")
    mode = horses[0].get("mode")
    if mode not in ("jra", "nar") or any(h.get("mode") != mode for h in horses):
        return {}
    formal = sorted([h for h in horses if _positive_rank(h.get("rank")) is not None],
                    key=lambda h: (_positive_rank(h.get("rank")), _no(h)))
    sabcd = sorted([h for h in horses if _prob(
        (h.get("research_sabcd_weight_class") or {}).get("score")) is not None],
        key=lambda h: (-_prob((h.get("research_sabcd_weight_class") or {}).get("score")), _no(h)))
    f = {str(h["no"]): (i + 1) / len(formal) for i, h in enumerate(formal)}
    s = {str(h["no"]): (i + 1) / len(sabcd) for i, h in enumerate(sabcd)}
    outcomes = {}
    sortable = []
    for h in horses:
        no = str(h.get("no") or "")
        shadow = h.get("research_sabcd_weight_class") or {}
        retro = bool(shadow.get("retro"))
        source = ("保存正式Top5の順位" if formal_score(h) is not None
                  else "Top5外の参考順位（正式スコア未確認）")
        if no not in f or no not in s:
            outcomes[no] = dict(version=VERSION, rank=None, top5=False,
                ordinal_score=None, score=None, retro=retro, source=source,
                reason="保存正式順位またはSABCDモデル値が未取得。推測して埋めません。")
            continue
        val = FORMAL_WEIGHT * f[no] + SABCD_WEIGHT * s[no]
        sortable.append((val, _no(h), no))
        outcomes[no] = dict(
            version=VERSION, rank=None, top5=False,
            ordinal_score=round(val, 6), score=None, retro=retro,
            source=source,
            reason="正式順位25%＋研究SABCD順75%の順位比較。"
                   "確率・正式ランク・SABCDグレードへの変換は未実施。"
                   + ("過去開催を後日算出（当時の予想ではありません）。" if retro else "")
                   + ("地方のTop5外は正式スコアのない参考順位を利用。"
                      if mode == "nar" and formal_score(h) is None else ""),
        )
    complete = len(sortable) >= 5
    for i, (_score, _horse, no) in enumerate(sorted(sortable)):
        item = outcomes[no]
        item["rank"] = i + 1
        item["top5"] = bool(complete and i < 5)
        item["eligible_count"] = len(sortable)
        item["total_count"] = len(horses)
    for item in outcomes.values():
        item.setdefault("eligible_count", len(sortable))
        item.setdefault("total_count", len(horses))
    return outcomes


def assign_to_view(view):
    """Annotate transient UI data only. Returns the same list."""
    results = evaluate_race(view)
    for h in view or ():
        h["research_formal_sabcd_fusion"] = results.get(str(h.get("no")), {})
    return view
