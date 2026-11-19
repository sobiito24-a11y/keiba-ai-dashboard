"""Frozen-current-evaluation versus unified-SABCD D-to-C *shadow* review.

Hypothesis selected after inspecting 2026-11-11/15/18 results; therefore it
must NOT change the visible grade until validated on NEW racing dates.

No results, final odds, purchases or retrospective outcomes are inputs.
Evidence is taken from the matching race's originally frozen horse materials,
NOT the re-rendered table's newer/materially different commentary.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

from .research_index_rescue import _number, _past3

VERSION = "current-eval-c-shadow-20261119-v1"
GRADES = ("S", "A", "B", "C", "D")


def _rank(value):
    n = _number(value)
    return int(n) if n is not None and n.is_integer() and n >= 1 else None


def _verified_check(mark):
    # '✓' is the NAR rescue check; formal Top5's '✔︎' must not be substituted.
    return str(mark or "").replace("\ufe0e", "").replace("\ufe0f", "").strip() == "✓"


def _exact_course_podium(horse):
    context = horse.get("race_context") or {}
    venue = str(context.get("venue") or context.get("racecourse") or "").strip()
    surface = str(context.get("surface") or context.get("芝ダート") or "").replace("ダート", "ダ").strip()
    distance = _number(context.get("distance"))
    if not venue or not surface or distance is None:
        return 0
    return sum(
        bool(run.get("finish") is not None and run["finish"] <= 3
             and str(run.get("venue") or "").strip() == venue
             and str(run.get("surface") or "").replace("ダート", "ダ").strip() == surface
             and run.get("distance") == distance)
        for run in _past3(horse)
    )


def assess(horse, frozen_horse):
    """Evaluate a single contender without touching unified_sabcd or marks."""
    result = dict(
        version=VERSION, research_only=True, candidate_grade=None,
        candidate=False, status="insufficient_source",
        current_rank=None, checked=False, suitability=False,
        recent_rising=False, same_course_podium=False,
        independent_family_count=0, past_podium_count=0,
        form_conflict=False, reason="発走前の保存済み材料を照合できません。",
    )
    if not isinstance(horse, Mapping) or not isinstance(frozen_horse, Mapping):
        return result
    if str(horse.get("no") or "") != str(frozen_horse.get("horse_no") or ""):
        return result
    unified = horse.get("unified_sabcd") or {}
    if not isinstance(unified, Mapping) or unified.get("grade") not in GRADES:
        result.update(status="ungraded", reason="統合研究ランク未取得")
        return result
    if unified.get("grade") != "D":
        result.update(status="not_d", reason="統合SABCDがDではないため対象外")
        return result
    rank = _rank(horse.get("current_evaluation_rank"))
    # Compare independently frozen horse rank; conflicting rank means abstain.
    frozen_rank = _rank(frozen_horse.get("current_evaluation_rank"))
    if rank is not None and frozen_rank is not None and rank != frozen_rank:
        result.update(status="conflicting_rank", reason="今回評価順位が表示データと保存データで不一致")
        return result
    rank = frozen_rank if frozen_rank is not None else rank
    checked = _verified_check(frozen_horse.get("mark")) or _verified_check(horse.get("mark"))
    screened = (rank is not None and rank <= 5) or checked
    plus = frozen_horse.get("plus_materials")
    if not isinstance(plus, list) or not all(isinstance(v, str) for v in plus):
        result.update(status="missing_materials", reason="保存済みプラス材料の検証に必要な情報が未取得")
        return result
    suitability = "距離実績◎" in plus or "コース実績◎" in plus
    recent_rising = "近走上昇" in plus
    past_podium_count = _exact_course_podium(horse)
    same_course_podium = past_podium_count >= 1
    count = int(suitability) + int(recent_rising) + int(same_course_podium)
    state = str(frozen_horse.get("state") or "")
    conflict = recent_rising and any(t in state for t in ("下降", "弱含み", "不振", "低下"))
    candidate = bool(screened and count >= 2)
    reasons = [
        f"今回評価{rank}位" if rank is not None and rank <= 5 else "参考チェック✓" if checked else "今回評価5位外",
        "コース・距離実績◎" if suitability else "",
        "保存済み近走上昇" if recent_rising else "",
        f"同場同距離の過去3走3着以内{past_podium_count}回" if same_course_podium else "",
    ]
    reasons = [r for r in reasons if r]
    explanation = (" / ".join(reasons)
        + "。研究DのC補正候補として記録するのみ。"
        "実際のSABCD・モデル値・順位・正式印・買い目は不変。"
        "適性指数と同場同距離実績は相関し得るため独立確率として加算しない。")
    if conflict:
        explanation += f"注意：保存済み近走上昇と状態「{state}」が矛盾。"
    result.update(candidate=candidate, candidate_grade="C" if candidate else None,
        status="candidate" if candidate else "screened_insufficient" if screened else "not_screened",
        current_rank=rank, checked=checked, suitability=suitability,
        recent_rising=recent_rising, same_course_podium=same_course_podium,
        independent_family_count=count, past_podium_count=past_podium_count,
        form_conflict=conflict, reason=explanation)
    return result


def annotate_view(view, race_snapshot=None):
    """Attach preview evidence only; immutable event and visible grade remain unchanged.

    A race_id/date mismatch abstains, and only the original frozen horse list
    is used. race_results_v1 is deliberately never read.
    """
    race = race_snapshot if isinstance(race_snapshot, Mapping) else {}
    original_horses = race.get("horses")
    frozen = {str(h.get("horse_no")): h for h in original_horses
              if isinstance(h, Mapping) and h.get("horse_no") is not None
              } if isinstance(original_horses, list) else {}
    for h in view or ():
        if not isinstance(h, dict):
            continue
        context = h.get("race_context") or {}
        hdate = str(context.get("race_date") or context.get("date") or "")[:10]
        rdate = str(race.get("date") or "")[:10]
        rid = str(context.get("race_id") or "")
        same_date = bool(hdate and rdate and hdate == rdate)
        same_id = not rid or rid == str(race.get("race_id") or "")
        same_mode = h.get("mode") == race.get("race_mode")
        saved = frozen.get(str(h.get("no") or "")) if same_date and same_id and same_mode else None
        h["research_current_eval_c_floor"] = assess(h, saved)
    return view
