"""Read-only class/pace/field race gate and research candidate presentation.

NEVER overwrites prediction, formal membership, marks, score, corner or odds.
This is a prospective, unvalidated display/selection hypothesis.  All signals
derive from facts available before the target race, not its eventual result.
"""
from collections.abc import Mapping
from html import escape
import re
import unicodedata

from .final_candidate_selection import formal_score, select_indices
from .race_explorer_common import plain, value
from .race_explorer_visuals import _pace


def _map(item):
    return item if isinstance(item, Mapping) else {}


def _int(item, lo=0):
    if isinstance(item, bool):
        return None
    try:
        n = float(item)
        return int(n) if n.is_integer() and lo <= n < 100000 else None
    except (ValueError, TypeError, OverflowError):
        return None


def _float(item):
    if isinstance(item, bool):
        return None
    try:
        n = float(item)
        return n if n == n and abs(n) < 100000 else None
    except (ValueError, TypeError, OverflowError):
        return None


def _norm(raw):
    return unicodedata.normalize("NFKC", str(raw or "")).strip()


def _recent_runs(horse):
    facts = _map(horse.get("explorer_facts"))
    result = []
    for run in facts.get("runs") or ():
        if not isinstance(run, Mapping) or run.get("label") not in ("3走前", "2走前", "前走"):
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(run.get("date") or "")):
            continue
        finish = re.fullmatch(r"(\d+)(?:着)?", _norm(run.get("finish")))
        if not finish:
            continue
        result.append((run.get("label"), int(finish.group(1)), _norm(run.get("class_raw"))))
    return result


def _condition_top3(horse):
    facts = _map(horse.get("explorer_facts"))
    for record in facts.get("condition_records") or ():
        if not isinstance(record, Mapping) or record.get("key") not in ("venue_distance", "surface_distance"):
            continue
        count = _int(record.get("starts"), 0)
        top3 = _int(record.get("top3"), 0)
        if count and top3 and top3 <= count and record.get("scope"):
            return record.get("key"), count, top3
    return None


def race_profile(view):
    if not view:
        return dict(mode="jra", class_label="未確認", age_label="未確認",
                    surface="未確認", pace="", front_count=None, focus="保存評価", note="情報不足")
    mode = view[0].get("mode", "jra")
    ctx = _map(view[0].get("race_context"))
    conditions = _norm(ctx.get("race_data2"))
    name = _norm(ctx.get("race_name") or ctx.get("レース名"))
    sample = conditions + " " + name
    if re.search(r"未勝利", sample):
        group = "未勝利"
    elif re.search(r"1勝クラス", sample):
        group = "1勝"
    elif re.search(r"2勝クラス", sample):
        group = "2勝"
    elif re.search(r"3勝クラス", sample):
        group = "3勝"
    elif re.search(r"オープン|リステッド|OP\b|G[123I]|Jpn[123]", sample, re.I):
        group = "OP・重賞"
    elif mode == "nar" and re.search(r"(?:^|\s)[ABC]\d?(?:級|\b)", sample):
        group = "地方クラス"
    else:
        group = "クラス未確認"
    if "2歳" in conditions and "以上" not in conditions:
        age = "2歳限定"
    elif "3歳" in conditions and "以上" not in conditions:
        age = "3歳限定"
    elif "3歳以上" in conditions or "4歳以上" in conditions:
        age = "古馬混合"
    else:
        age = "年齢未確認"
    desc = _norm(ctx.get("race_data1") or ctx.get("race_data") or "")
    surface = ("芝" if re.search(r"芝\s*\d", desc) else
               "ダート" if re.search(r"(?:ダ|ダート)\s*\d", desc) else
               "障害" if "障" in desc else "馬場未確認")
    front = sum(_int(h.get("corner"), 1) is not None and _int(h.get("corner"), 1) <= 3 for h in view)
    pace = _pace(view, ctx) if mode == "jra" else ""
    if mode == "nar":
        focus = "現行Top5＋補完根拠"
        note = "保存されたNARペースは切替判定に使用しません。開催場・頭数・4角隊列を確認。"
    elif group == "OP・重賞" and age != "2歳限定":
        focus = "相手関係・展開整合"
        note = "OP向けの研究仮説。正式評価と別の根拠を確認。"
    elif group in ("2勝", "3勝"):
        focus = "好走再現性"
        note = "前走の再現性を重視する研究表示。強制的な前残り判定はしません。"
    elif group == "未勝利" and age == "2歳限定":
        focus = "従来評価・好走根拠"
        note = "2歳未勝利では現行評価の捕捉力を基本として維持。"
    else:
        focus = "現行評価＋追加根拠"
        note = "クラス情報が不十分なときは研究で評価方法を切り替えません。"
    return dict(mode=mode, class_label=group, age_label=age, surface=surface,
                pace=pace, front_count=front, field_size=len(view),
                focus=focus, note=note)


def research_signals(horse, cells):
    """Separate evidence domains; no summed score, formal mark or probability."""
    cells = _map(cells)
    mode = horse.get("mode")
    result = []
    def add(code, label, detail):
        if code not in {x["code"] for x in result}:
            result.append(dict(code=code, label=label, detail=detail))
    runs = _recent_runs(horse)
    if sum(finish <= 3 for _, finish, _ in runs) >= 2:
        add("再", "近走安定", "日付のある直近3走中、2走以上が3着以内")
    condition = _condition_top3(horse)
    if condition:
        key, starts, top3 = condition
        label = "同条件実績" if key == "venue_distance" else "同距離実績"
        add("同", label, f"保存された近3走の条件別記録で{starts}戦{top3}回3着以内")
    corner = _int(cells.get("corner"), 1)
    course = _int(cells.get("course_rank"), 1)
    distance = _int(cells.get("distance_rank"), 1)
    ability = _int(cells.get("ability_rank"), 1)
    # A forecast position alone is NOT an advantage; require another independent condition.
    if corner is not None and corner <= 6 and (
        (course is not None and course <= 3) or
        (distance is not None and distance <= 3) or
        (mode == "nar" and ability is not None and ability <= 8)
    ):
        add("展", "位置×条件", "4角想定6番手以内＋適性指数上位（NARは能力8位以内も可）")
    if mode == "jra":
        if any(finish <= 5 and re.search(r"OP|オープン|リステッド|G[123I]|Jpn[123]", cls, re.I) for _, finish, cls in runs):
            add("相", "上級戦好走", "日付のある近3走でOP以上の5着以内を確認。相手の実力差は未校正")
        indices = [_float(_map(x).get("time_index")) for x in _map(horse.get("explorer_facts")).get("runs") or () if isinstance(x, Mapping)]
        if len(indices) == 3 and all(x is not None for x in indices) and indices[0] < indices[1] < indices[2]:
            add("伸", "指数上昇", "保存された近3走の指数が連続上昇。成長を断定するものではありません")
    source = _map(horse.get("research_inputs"))
    starts = _int(source.get("jockey_n"), 0)
    rate = _float(source.get("jockey_rate"))
    threshold = 30 if mode == "jra" else 35
    if starts is not None and starts >= 20 and rate is not None and rate >= threshold:
        add("騎", "騎手コース適性", f"同条件騎乗{starts}走・複勝率{rate:g}%")
    return tuple(result)


def research_warning(horse, cells):
    if horse.get("mode") == "jra":
        rest = _int(cells.get("rest_days"), 0)
        training = cells.get("training")
        if rest is not None and rest >= 70 and training in ("C", "D"):
            return "休養70日以上＋調教C/D"
    delta = _float(cells.get("weight_delta"))
    if delta is not None and delta >= 2:
        return "斤量＋2kg以上"
    return None


def research_plan(view, cells=None):
    """Retain baseline Top5; JRA open-class research can compare replacements.

    Research membership is not official membership.  No automatic buys, no
    inference from odds, no influence on the saved result or predictor.
    """
    cells = cells if isinstance(cells, Mapping) else {}
    info = race_profile(view)
    if not view:
        return dict(indices=[], reasons={}, signs={}, warnings={}, base_indices=[], profile=info, roles={})
    signs = {str(h.get("no")): research_signals(h, cells.get(str(h.get("no")), {})) for h in view}
    warnings = {str(h.get("no")): research_warning(h, cells.get(str(h.get("no")), {})) for h in view}
    base_indices = select_indices(view, "no")
    formal = sorted((i for i, h in enumerate(view) if h.get("formal_member") is True),
                    key=lambda i: (_int(view[i].get("rank"), 1) or 999, _int(view[i].get("no"), 1) or 999))
    formal = formal[:5]
    refs = [i for i in base_indices if i not in formal]
    selected = list(formal)
    roles = {i: "既存" for i in selected}

    def qualifying(i):
        h = view[i]
        tags = {x["code"] for x in signs[str(h.get("no"))]}
        # At least two distinct evidence domains; not two differently labelled indices.
        domains = [bool(tags & {"相", "再", "伸"}), bool(tags & {"同", "展"}), bool("騎" in tags)]
        return sum(domains) >= 2 and not warnings[str(h.get("no"))]

    others = [i for i in range(len(view)) if i not in selected and qualifying(i)]
    def priority(i):
        tags = {x["code"] for x in signs[str(view[i].get("no"))]}
        # Grouped evidence tiers, not a weighted numeric model.
        high = "相" in tags and bool(tags & {"同", "展", "騎"})
        good = bool(tags & {"再", "相"}) and bool(tags & {"同", "展", "騎"})
        return (0 if high else 1 if good else 2,
                0 if "同" in tags else 1,
                _int(view[i].get("rank"), 1) or 999,
                _int(view[i].get("no"), 1) or 999)
    others.sort(key=priority)

    if (info["mode"] == "jra" and info["class_label"] == "OP・重賞"
            and info["age_label"] != "2歳限定"):
        # An explicit, EXPERIMENTAL OP comparison; preserve leading three
        # official runners, allow max two evidenced challengers for ranks 4/5.
        selected = formal[:3]
        roles = {i: "既存" for i in selected}
        for i in others[:2]:
            if i not in selected:
                selected.append(i)
                roles[i] = "研究補完"
        for i in formal[3:] + refs:
            if len(selected) >= 6:
                break
            if i not in selected:
                selected.append(i)
                roles[i] = "既存" if i in formal else "参考"
    else:
        for i in refs:
            if len(selected) < 6 and i not in selected:
                selected.append(i)
                roles[i] = "参考"
        for i in others:
            if len(selected) >= 6:
                break
            if i not in selected:
                selected.append(i)
                roles[i] = "研究補完"
    selected = sorted(selected[:6], key=lambda i: (_int(view[i].get("no"), 1) or 999, i))
    return dict(indices=selected, base_indices=base_indices, profile=info,
                signs=signs, warnings=warnings, roles=roles)


def race_gate_html(view, plan):
    profile = plan["profile"]
    pace = profile["pace"] if profile["mode"] == "jra" else ""
    pace_text = "予測ペース " + pace if pace else "予測ペースは切替保留"
    if profile["mode"] == "nar":
        pace_text = "NAR保存ペースは切替に使わない"
    pairs = (("クラス", profile["class_label"]), ("年齢", profile["age_label"]),
             ("馬場", profile["surface"]), ("頭数", str(profile.get("field_size") or 0) + "頭"),
             ("展開", pace_text), ("前方想定", str(profile.get("front_count") or 0) + "頭"))
    metadata = "".join('<span><small>'+plain(label)+'</small>'+plain(val)+'</span>' for label,val in pairs)
    return ('<section class="race-gate-research" aria-label="研究用レース判定">'
            '<div class="race-gate-head"><strong>レース判定 <small>研究版</small></strong>'
            '<span>重視：'+plain(profile["focus"])+'</span></div>'
            '<div class="race-gate-facts">'+metadata+'</div>'
            '<p>'+plain(profile["note"])+' 研究候補と正式評価は別物。実績・回収率の優位性は未確認です。</p>'
            '</section>')


def formal_reference_html(view):
    """Collapsed, source-faithful review. No fake scores for NAR outside Top5."""
    selected = sorted((h for h in view if h.get("formal_member") is True),
                      key=lambda h: (_int(h.get("rank"), 1) or 999, _int(h.get("no"), 1) or 999))[:5]
    lines = []
    for h in selected:
        score = formal_score(h)
        lines.append('<tr><td>'+value(h.get("no"))+'</td><td>'+plain(h.get("name"))+
                     '</td><td>'+value(h.get("rank"))+'</td><td>'+value(h.get("mark"))+
                     '</td><td>'+value(score)+'</td></tr>')
    return ('<details class="formal-reference" id="formal-reference"><summary>従来の正式評価を確認（比較用）</summary>'
            '<p>正式順位と印は保存値そのまま。研究候補の表示や馬券購入判定には加点しません。</p>'
            '<div class="formal-table-wrap"><table><thead><tr><th>馬番</th><th>馬名</th><th>正式順位</th><th>正式印</th><th>保存スコア</th></tr></thead>'
            '<tbody>'+''.join(lines)+'</tbody></table></div></details>')
