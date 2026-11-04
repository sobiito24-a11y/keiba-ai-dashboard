"""NAR all-runner recent-form *research reference*. No marks or formal Top5 edits.

All features use only pre-race data. In netkeiba's _past_runs,
'position' means FINISH, not fourth-corner order.
"""
from __future__ import annotations

import math
import re
from typing import Any, Mapping

VERSION = "nar_recent_form_reference_v1_20261104"
RESEARCH_COLUMNS = (
    "nar_form_ref_score", "nar_form_ref_rank", "nar_form_ref_reason",
    "nar_form_ref_flag", "nar_form_ref_status", "nar_form_ref_pace",
    "nar_form_ref_prior_corner", "nar_form_ref_version",
)


def _num(value: Any) -> float | None:
    try:
        if isinstance(value, bool) or value is None or str(value).strip() in ("", "None", "nan", "—", "-"):
            return None
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    x = _num(value)
    return int(x) if x is not None and x >= 1 and x.is_integer() else None


def _no(row: Mapping[str, Any]) -> str:
    for key in ("馬番", "horse_no", "number", "馬"):
        n = _int(row.get(key))
        if n is not None:
            return str(n)
    return ""


def _past(row: Mapping[str, Any], label: str, race_date: str) -> Mapping[str, Any]:
    values = row.get("_past_runs")
    if not isinstance(values, list):
        return {}
    for value in values:
        if not isinstance(value, Mapping) or value.get("key", value.get("run_key")) != label:
            continue
        previous_date = str(value.get("race_date") or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", previous_date):
            return {}
        if race_date and previous_date >= race_date:
            return {}
        return value
    return {}


def _previous_four_corner(run: Mapping[str, Any]) -> int | None:
    # Never use run['position'] (the finishing position).
    for key in ("corner4_rank", "last_4c", "fourth_corner_rank"):
        rank = _int(run.get(key))
        if rank is not None:
            return rank
    passing = run.get("passing_order")
    if isinstance(passing, str) and re.fullmatch(r"\s*\d+(?:\s*[-,]\s*\d+)+\s*", passing):
        return _int(re.findall(r"\d+", passing)[-1])
    return None


def _trusted_pace(row: Mapping[str, Any]) -> str:
    status = str(row.get("_lap_prediction_status") or row.get("lap_prediction_status_market") or "").lower()
    if any(flag in status for flag in ("実値なし", "未取得", "存在しない", "missing", "unavailable", "not found")):
        return "未取得"
    if not status:
        return "未確認"  # A bare H in an old snapshot is not evidence.
    pace = str(row.get("_netkeiba_pace") or row.get("provider_pace_market") or "").upper()
    return pace if pace in ("S", "M", "H") else "未取得"


def evaluate_nar_rows(
    rows: list[Mapping[str, Any]],
    race_info: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """All-runner reference scores; never modifies input rows or formal scores."""
    info = race_info or {}
    day = str(info.get("date") or info.get("race_date") or "")[:10]
    venue = str(info.get("venue") or info.get("racecourse") or "").strip()
    distance = _int(info.get("distance"))
    n = len(rows)
    out = [dict(row) for row in rows]
    if not out:
        return []

    ability = [
        next((x for key in ("market_ability_score", "ver3_ability_core", "ability_value", "能力評価値")
              if (x := _num(row.get(key))) is not None), None)
        for row in out
    ]
    existing_ranks = [
        next((v for key in ("market_ability_rank", "ability_rank")
              if (v := _int(row.get(key))) is not None), None)
        for row in out
    ]
    if all(value is not None for value in ability):
        order = sorted(range(n), key=lambda i: (-ability[i], int(_no(out[i]) or 999)))
        ranks = [None] * n
        for rank, i in enumerate(order, 1):
            ranks[i] = rank
    else:
        ranks = existing_ranks

    for i, row in enumerate(out):
        rank = ranks[i]
        last = _past(row, "race1", day)
        second = _past(row, "race2", day)
        third = _past(row, "race3", day)
        finish = _int(last.get("position"))  # FINISH, not 4th-corner.
        finish2 = _int(second.get("position"))
        corner = _int(row.get("netkeiba_corner4_rank") or row.get("_netkeiba_corner4_rank"))
        past_corner = _previous_four_corner(last)
        bonus = 0.0
        reasons: list[str] = []
        flags: list[str] = []

        if corner is not None and corner <= 3:
            bonus += 1.3
            reasons.append("今回4角想定3位内")
        elif corner is not None and corner <= 5:
            bonus += 0.4
        if finish is not None and finish <= 2:
            bonus += 1.0
            reasons.append("前走2着以内")
        elif finish == 3:
            bonus += 0.5
        if finish is not None and finish2 is not None and finish2 - finish >= 3:
            bonus += 0.8
            reasons.append("前走着順改善")
        if past_corner is not None and past_corner <= 3:
            bonus += 2.0
            reasons.append("前走4角3位内（実データ）")
        if (venue and distance and finish is not None and finish <= 3
                and str(last.get("venue") or last.get("racecourse") or "") == venue
                and _int(last.get("distance")) == distance):
            bonus += 0.8
            reasons.append("同会場同距離で前走3着内")
        if re.search(r"直近.*先着", str(row.get("対戦") or "")):
            bonus += 0.8
            reasons.append("直近直接対戦で先着")
        last_index = _num(last.get("value"))
        older = [_num(run.get("value")) for run in (second, third)]
        older = [value for value in older if value is not None]
        if last_index is not None and older and last_index >= max(older) + 12:
            bonus += 0.8
            reasons.append("前走指数上昇")
        elif last_index is not None and older and max(older) - last_index >= 25:
            flags.append("前走指数急落（原因未確認）")
        if rank is not None and rank > 5 and corner is not None and corner <= 3:
            if past_corner is not None and past_corner <= 3:
                flags.append("前走4角＋今回想定：再確認")
            elif "直近直接対戦で先着" in reasons:
                flags.append("対戦＋今回先行想定：再確認")
            else:
                flags.append("能力順位と4角想定が乖離")
        pace = _trusted_pace(row)
        if pace not in ("S", "M", "H"):
            flags.append("ペース未確認：加減点なし")
        score = round(3.0 * (n - rank) + min(bonus, 6.0), 2) if rank is not None else None
        row.update(
            nar_form_ref_score=score, nar_form_ref_rank=None,
            nar_form_ref_reason=" / ".join(reasons) or "明確な見直し材料なし",
            nar_form_ref_flag=" / ".join(flags) or "—",
            nar_form_ref_status="一部材料あり" if last else "過去走情報不足",
            nar_form_ref_pace=pace, nar_form_ref_prior_corner=past_corner,
            nar_form_ref_version=VERSION,
        )

    order = sorted(
        (i for i, row in enumerate(out) if row["nar_form_ref_score"] is not None),
        key=lambda i: (-out[i]["nar_form_ref_score"], ranks[i], int(_no(out[i]) or 999)),
    )
    for rank, i in enumerate(order, 1):
        out[i]["nar_form_ref_rank"] = rank
    return out


def neutralize_unverified_nar_pace(result: Any) -> Any:
    """Only clear fake provider H when source explicitly says lap data absent."""
    if str(getattr(result, "race_mode", "")).lower() != "nar":
        return result
    import pandas as pd
    for attr in ("overall_table", "horse_evaluation"):
        table = getattr(result, attr, None)
        if not isinstance(table, pd.DataFrame) or table.empty or "_lap_prediction_status" not in table.columns:
            continue
        frame = table.copy()
        for idx, row in frame.iterrows():
            status = str(row.get("_lap_prediction_status") or "").lower()
            if not any(flag in status for flag in ("実値なし", "未取得", "存在しない", "missing", "unavailable")):
                continue
            for col in ("_netkeiba_pace", "netkeiba_pace"):
                if col in frame.columns:
                    frame.at[idx, col] = ""
        setattr(result, attr, frame)
    return result


def attach_nar_form_reference(result: Any) -> Any:
    """Persist the research-only reference columns on fresh NAR snapshots."""
    if str(getattr(result, "race_mode", "")).lower() != "nar":
        return result
    import pandas as pd
    for attr in ("overall_table", "horse_evaluation"):
        table = getattr(result, attr, None)
        if isinstance(table, pd.DataFrame) and not table.empty:
            reviewed = evaluate_nar_rows(table.to_dict("records"), result.race_info)
            setattr(result, attr, pd.DataFrame(reviewed, index=table.index))
    debug = dict(getattr(result, "debug_info", None) or {})
    debug["nar_form_reference"] = {
        "version": VERSION, "research_only": True, "source": "pre_race_existing_rows",
    }
    result.debug_info = debug
    return result
