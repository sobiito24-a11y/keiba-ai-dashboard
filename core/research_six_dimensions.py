"""Six-factor, read-only *evidence* labels for the horse detail.

Do not interpret them as trained probabilities or combine the six letters to
replace the frozen SABCD model.  Only pre-race, dated runs from the existing
saved profile are examined.  JRA/NAR indices are never directly compared.
"""
from __future__ import annotations

from datetime import date
from html import escape
import math
import re
from collections.abc import Mapping

VERSION = "six-factors-evidence-20261112-audit1"
FACTORS = (("distance", "距離"), ("course", "コース"), ("recent", "近走"),
           ("jockey", "騎手"), ("development", "展開"), ("conditions", "相手・条件"))
JRA_VENUES = frozenset(("札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"))
NAR_VENUES = frozenset(("帯広", "門別", "盛岡", "水沢", "浦和", "船橋", "大井", "川崎",
                        "金沢", "笠松", "名古屋", "園田", "姫路", "高知", "佐賀"))


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        val = float(str(value).replace("kg", "").replace("％", "").replace("%", "").strip())
    except (ValueError, TypeError, OverflowError):
        return None
    return val if math.isfinite(val) else None


def _date(value):
    try:
        return date.fromisoformat(str(value or "")[:10].replace("/", "-"))
    except (TypeError, ValueError):
        return None


def _venue(value):
    return re.sub(r"(競馬場|\s)+", "", str(value or "")).strip()


def _jurisdiction(venue):
    key = _venue(venue)
    if key in JRA_VENUES:
        return "jra"
    if key in NAR_VENUES:
        return "nar"
    return None


def _surface(value):
    val = str(value or "").strip()
    return "ダ" if val in ("ダ", "ダート") else "芝" if val == "芝" else None


def _distance(value):
    raw = str(value or "").strip().replace("ｍ", "m")
    match = re.fullmatch(r"(?:芝|ダート|ダ)?\s*(\d{3,4})(?:\s*m)?", raw)
    return int(match[1]) if match else None


def _finish(value):
    match = re.fullmatch(r"\s*(\d+)(?:着)?\s*", str(value or ""))
    return int(match[1]) if match and int(match[1]) > 0 else None


def _run_history(horse):
    profile = horse.get("profile") or {}
    context = horse.get("race_context") or {}
    current = _date(context.get("race_date") or context.get("date"))
    history = []
    for run in [*(profile.get("runs", ()) or ()), *(profile.get("extended_history", ()) or ())]:
        if not isinstance(run, Mapping):
            continue
        day = _date(run.get("date"))
        # Never infer that an undated/current/future result was available.
        if not current or not day or day >= current:
            continue
        venue = _venue(run.get("venue"))
        history.append(dict(
            day=day, venue=venue, mode=_jurisdiction(venue),
            surface=_surface(run.get("surface")),
            distance=_distance(run.get("distance")),
            finish=_finish(run.get("finish")),
            index=_num(run.get("time_index")),
            class_raw=str(run.get("class_raw") or "").strip(),
        ))
    # The normalized recent-three and the saved original archive often
    # overlap.  Keep one record per real past start, preferring whichever
    # copy has verified index/finish values.
    merged = {}
    for run in history:
        key = (run["day"], run["venue"], run["surface"], run["distance"])
        old = merged.get(key)
        if old is None:
            merged[key] = run
        else:
            for field in ("finish", "index", "class_raw"):
                if (old.get(field) is None or old.get(field) == "") and run.get(field) is not None:
                    old[field] = run[field]
    unique = sorted(merged.values(), key=lambda x: x["day"], reverse=True)
    return unique[:12]


def _label(grade, reason, hint=""):
    return dict(grade=grade if grade in ("S", "A", "B", "C", "D") else "—",
                reason=str(reason), hint=str(hint or ""))


def _record_hint(label, matches):
    """Visible sample evidence even when fewer than two runs allow no grade."""
    finished = [r for r in matches if r.get("finish") is not None]
    if not finished:
        return ""
    wins = sum(r["finish"] == 1 for r in finished)
    placed = sum(r["finish"] <= 3 for r in finished)
    suffix = "・参考1走" if len(finished) == 1 else ""
    return f"{label}{len(finished)}戦{wins}勝・3着内{placed}回{suffix}"


def _sample_grade(matches):
    """Tentative descriptions of repeated performances; NOT probabilities."""
    finished = [r for r in matches if r["finish"] is not None]
    n = len(finished)
    top = sum(r["finish"] <= 3 for r in finished)
    if n < 2:
        return "—", top, n
    # Three thirds against unknown opposition do not prove an S-level edge.
    if n >= 3 and top == n and any(r["finish"] == 1 for r in finished):
        return "S", top, n
    if top >= 2:
        return "A", top, n
    if top == 1:
        return "B", top, n
    # No automatic D from defeats against unknown opposition.
    return "C", top, n


def evaluate(horse):
    """Return independent 6-factor provisional evidence for one horse."""
    profile = horse.get("profile") or {}
    mode = horse.get("mode")
    context = horse.get("race_context") or {}
    runs = _run_history(horse)
    known = [r for r in runs if r["mode"] is not None]
    local = [r for r in known if r["mode"] == mode]
    visiting = [r for r in known if r["mode"] != mode]
    surface = _surface(context.get("surface") or context.get("芝ダート"))
    distance = _distance(context.get("distance"))
    venue = _venue(context.get("venue") or context.get("racecourse"))
    transfer = mode == "nar" and any(r["mode"] == "jra" for r in visiting)
    # Keep each jurisdiction's index values separate. Their scales and class
    # contexts are not safely comparable without validated conversion.
    indices = {m: [r["index"] for r in known
                   if r["mode"] == m and r["index"] is not None]
               for m in ("jra", "nar")}
    other_index_note = ""
    if visiting:
        names = {"jra": "中央", "nar": "地方"}
        snippets = [f'{names[m]}指数 '+"/".join(f'{v:g}' for v in indices[m])
                    for m in ("jra", "nar") if m != mode and indices[m]]
        other_index_note = (
            f'過去{len(runs)}走に別主催の出走{len(visiting)}走。'
            + ("、".join(snippets) + "。" if snippets else "")
            + "中央・地方の指数は直接合算・比較しません。"
        )

    # Distance: past finishes and distance conditions, not merely rank/index.
    dist_runs = [r for r in local if r["surface"] == surface and
                 r["distance"] is not None and distance is not None and
                 abs(r["distance"] - distance) <= 200]
    d_grade, d_top, d_n = _sample_grade(dist_runs)
    exact_dist = [r for r in dist_runs if r["distance"] == distance]
    distance_item = _label(
        d_grade,
        f"同主催・同馬場・近似距離（±200m）で{d_n}走中3着以内{d_top}回。"
        + ("材料不足のため未判定。" if d_grade == "—" else "複数の着順で仮判定。")
        + "距離900mと1100mなども近似扱い。完全一致の実績を別に表示。"
        + other_index_note,
        _record_hint("同距離", exact_dist) or _record_hint("近似距離", dist_runs),
    )

    # Course: same venue AND surface, independent of identical-distance check.
    course_runs = [r for r in local if venue and r["venue"] == venue and
                   surface is not None and r["surface"] == surface]
    c_grade, c_top, c_n = _sample_grade(course_runs)
    course_item = _label(c_grade,
         f"同主催・同競馬場・同馬場{c_n}走中3着以内{c_top}回。"
         + ("着順の母数不足（不得意の証拠ではありません）。" if c_grade == "—"
            else "コース実績の仮判定。")
         + "距離・近走の同じレースを含む場合があります。",
         _record_hint("同競馬場", course_runs))

    # Recent form: compare only recent finishes WITHIN the current circuit.
    # A former JRA horse with no local runs is not automatically graded D.
    local_finished = [r for r in runs[:5] if r["mode"] == mode and r["finish"] is not None][:3]
    r_grade, r_top, r_n = _sample_grade(local_finished)
    if r_n >= 2:
        if r_top >= 2 and local_finished[0]["finish"] == 1:
            r_grade = "S" if r_n >= 3 and r_top == r_n else "A"
        elif r_top == 0:
            r_grade = "C"
        else:
            r_grade = "A" if r_top >= 2 else "B"
    recent_item = _label(
        r_grade,
        f"同主催の確認済み近走{r_n}走中3着以内{r_top}回。"
        + ("中央から地方での実績換算は行わず、地方での比較材料が揃うまで未判定。"
           if transfer and r_n < 2 else
           "過去の別主催の着順を現在の着順順位に直接換算しません。" if visiting else "")
        + (other_index_note if visiting else "")
        + "近走の勢いは同主催直近最大3走で評価。古い保存履歴は別枠で参照。",
        _record_hint("同主催近走", local_finished),
    )

    # Jockey place rate: require sample size rather than trust a percentage.
    inputs = horse.get("research_inputs") or {}
    n = _num(inputs.get("jockey_n"))
    rate = _num(inputs.get("jockey_rate"))
    if n is None or n < 20 or rate is None or not (0 <= rate <= 100):
        j_grade = "—"
        j_reason = "同条件の騎手複勝率と20走以上の母数が揃わず未判定。"
    else:
        higher = 35 if mode == "nar" else 30
        if n >= 50 and rate >= higher + 12:
            j_grade = "S"
        elif rate >= higher:
            j_grade = "A"
        elif rate >= higher - 10:
            j_grade = "B"
        elif rate >= 12:
            j_grade = "C"
        else:
            j_grade = "D" if n >= 50 else "C"
        j_reason = f"保存された騎手複勝率{rate:g}%／{int(n)}走。コース等の集計条件に限定した参考判定。"
    jockey_item = _label(
        j_grade, j_reason,
        f"複勝率{rate:g}%・{int(n)}走" if rate is not None and n is not None and n >= 0
        else "母数不足・未取得",
    )

    # Development: require both predicted start and corner4, never historical
    # finished positions disguised as future predictions.
    start, corner = _num(horse.get("start_rank")), _num(horse.get("corner"))
    style = str(horse.get("style") or "")
    pace = str(context.get("netkeiba_pace") or context.get("pace_prediction") or "")
    if start is None or corner is None or start < 1 or corner < 1:
        dev_grade = "—"
        dev_reason = "発走前の序盤／4角位置予測が不足しており未判定。"
    else:
        mismatch = any(x in style for x in ("逃", "先")) and start >= 8
        if mismatch:
            dev_grade = "—"
            dev_reason = "逃げ・先行脚質と序盤後方予測が矛盾。位置?として再確認（自動減点しない）。"
        elif start <= 3 and corner <= 3 and pace in ("S", "M"):
            dev_grade = "A"
            dev_reason = "序盤・4角とも1〜3番手想定。ペースの前方有利は未検証。"
        elif corner <= 3:
            dev_grade = "B"
            dev_reason = "4角前方想定。序盤・ペースとの整合は要確認。"
        elif start >= 7 and corner >= 7:
            dev_grade = "C"
            dev_reason = "序盤・4角とも後方想定。消し判定ではありません。"
        else:
            dev_grade = "B"
            dev_reason = "位置予測が中位、または位置変化あり。"
    position_hint = (
        f"序盤{int(start)}→4角{int(corner)}番手"
        if start is not None and corner is not None and start >= 1 and corner >= 1
        else "位置予測が不足"
    )
    if "位置?" in dev_reason:
        position_hint = "位置?・要確認"
    development_item = _label(dev_grade, dev_reason, position_hint)

    # Opposition/conditions: only comparable class systems; no automatic
    # penalty/bonus for NAR vs JRA because their class numbers differ.
    shift = str(profile.get("class_shift") or "")
    materials = (horse.get("research_sabcd_weight_class") or {}).get("materials") or {}
    delta = _num(materials.get("weight_delta"))
    relative = _num(materials.get("weight_vs_field"))
    if shift not in ("同級", "昇級", "降級", "クラス昇級", "クラス降級"):
        co_grade = "—"
        co_reason = "クラス体系・対戦相手の比較不能（転入・年齢条件等の可能性）。"
    else:
        up = "昇級" in shift
        down = "降級" in shift
        co_grade = ("C" if up and delta is not None and delta >= 2 else
                    "B" if up else
                    "A" if down and delta is not None and delta <= 0 else
                    "B")
        co_reason = f"比較可能な前走クラス：{shift}。"
    co_reason += (
        f" 前走斤量差{delta:+g}kg。" if delta is not None else " 前走斤量差未取得。"
    ) + (
        f"今回の出走馬平均から{relative:+.1f}kg（性齢による設定差に注意）。"
        if relative is not None else "今回の相対斤量未取得。"
    ) + " 強い相手との実績は開催体系の照合なしに換算しません。"
    shift_hint = shift if co_grade != "—" else "クラス比較不能"
    if delta is not None:
        shift_hint += f"・斤量{delta:+g}kg"
    conditions_item = _label(co_grade, co_reason, shift_hint)

    factors = dict(distance=distance_item, course=course_item,
                   recent=recent_item, jockey=jockey_item,
                   development=development_item, conditions=conditions_item)
    return dict(factors=factors, version=VERSION, transfer_evidence=transfer,
                recent_source_count=len(runs), local_count=len(local),
                other_circuit_count=len(visiting),
                note="6項目は保存情報からの暫定的な根拠評価。距離・コース・近走は同じ過去走を重複して参照することがあります。履歴は保存で確認できた最大12走のみ。総合研究SABCDの計算には使用しません。")


def detail_html(horse):
    """Small six-factor block in the expanded horse detail; no table columns."""
    result = evaluate(horse)
    cells = []
    for key, title in FACTORS:
        item = result["factors"][key]
        rank = item["grade"]
        cells.append(
            '<div class="six-factor-item"><span class="six-factor-title">'
            + escape(title) + '</span><strong class="six-factor-rank six-factor-'
            + (rank if rank != "—" else "unknown") + '">'
            + escape(rank) + '</strong>'
            + ('<span class="six-factor-hint">' + escape(item["hint"]) + '</span>'
               if item.get("hint") else '')
            + '<details class="six-factor-more"><summary>根拠</summary>'
            + '<small>' + escape(item["reason"]) + '</small></details></div>'
        )
    transfer = ('<p class="six-factor-transfer">別主催の過去走あり：'
                '中央・地方の指数やクラスは未換算で別々に参照します。</p>'
                if result["other_circuit_count"] else '')
    return ('<section class="detail-six-factors" aria-label="6項目の研究評価">'
            '<h4>6項目の研究評価（暫定）</h4>'
            '<div class="six-factor-grid">' + ''.join(cells) + '</div>'
            + transfer + '<p class="detail-note">'
            + escape(result["note"] + "『—』は材料不足・比較不能でありDではありません。")
            + '</p></section>')
