"""Research-only five-grade ranking from verified pre-race facts.

Frozen coefficients derived separately for JRA/NAR from 764 archived races
with verifiable podium outcomes. Walk-forward tests evaluated 612 later
races; no race outcome/odds/official mark is used as a prediction feature.

The 0.70/0.50/0.30/0.15 thresholds are *model scores*, not guaranteed
true 3着内率. S(1), A(2), B(3) are capped per race, C/D unlimited.
Intended only for the projection/UI; NEVER override official ranks or marks.
"""
from __future__ import annotations

import math
import re
from datetime import date
from collections.abc import Mapping

VERSION = "archive-20261112"
CUTOFFS = (("S", .70, 1), ("A", .50, 2),
           ("B", .30, 3), ("C", .15, 9999), ("D", 0., 9999))
MODEL = {
 "jra": {
  "median": (.5,15.,.5,.5,.2,.4,1.,0.),
  "mean": (.4981952417297248,14.125815470643056,.49950503966731147,
           .4993403139447764,.21896551724138077,.4515067148941391,
           .8151599875737807,.13730972351662007),
  "scale": (.31095056663602205,2.7945073681024506,.31001111807858217,
            .30990582569177355,.11372051870880981,.3522937022825458,
            .8796869223021581,.3441740306072131),
  "coef": (-.4612935418180747,-.35503739487402275,-.22022974516176885,
           -.06678721645540785,.25027346266573264,-.33714873687379726,
           .09665739835193557,-.017055033770763794),
  "intercept": -1.485221315043272,
  "trained_through": "2026-11-08",
 },
 "nar": {
  "median": (.5,12.,.5,.5,.26,.45454545454545453,1.,0.),
  "mean": (.49942693232236535,11.17404337859284,.4994990461839342,
           .4993251022963595,.2763727737612415,.5044499750724375,
           .829130664785752,.3248104390760007),
  "scale": (.3167630491792439,1.779862432264552,.3089239850886418,
            .30899423484973954,.11545642708617432,.355286129828977,
            .9136041136567173,.46830398006344637),
  "coef": (-.5735817705424847,-.2876507077873049,-.40050355360129464,
           -.048034955475203804,.2913030978267782,-.17035951866228224,
           .09796699052425464,.039337371643132266),
  "intercept": -1.2395738394146685,
  "trained_through": "2026-11-11",
 }
}
_FINISH = re.compile(r"^\s*(\d+)(?:着)?\s*$")


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        v = float(str(value).strip())
    except (ValueError, TypeError, OverflowError):
        return None
    return v if math.isfinite(v) else None


def _rank(value):
    v = _number(value)
    return v if v is not None and v >= 1 else None


def _finish(value):
    m = _FINISH.fullmatch(str(value or ""))
    return int(m[1]) if m and int(m[1]) > 0 else None


def _ground(value):
    raw = str(value or "").strip()
    return "ダ" if raw in ("ダ", "ダート") else "芝" if raw == "芝" else raw


def _venue(value):
    return "".join(str(value or "").replace("競馬場", "").split())


def _distance(value):
    text = str(value or "").replace("m", "").replace("ｍ", "").strip()
    return _number(text)


def _same_course_distance(horse, runs):
    context = horse.get("race_context") or {}
    venue = _venue(context.get("venue") or context.get("racecourse"))
    surface = _ground(context.get("surface") or context.get("芝ダート"))
    dist = _distance(context.get("distance"))
    if not venue or not surface or dist is None:
        return 0.
    for run in runs:
        if not isinstance(run, Mapping):
            continue
        if (1 <= (_finish(run.get("finish")) or 1000) <= 3 and
                _venue(run.get("venue")) == venue and
                _ground(run.get("surface")) == surface and
                _distance(run.get("distance")) == dist):
            return 1.
    return 0.


def feature_vector(horse, head_count):
    """Match the 8 documented research features, without race outcomes."""
    if not isinstance(horse, Mapping) or horse.get("mode") not in MODEL:
        return None, ()
    h = max(2, int(head_count))
    rank = _rank(horse.get("ability_rank"))
    corner = _rank(horse.get("corner"))
    if corner is None:
        corner = _rank((horse.get("final_metrics") or {}).get("corner"))
    if rank is None or corner is None:
        return None, ()
    start = _rank(horse.get("start_rank"))
    profile = horse.get("profile") or {}
    runs = [run for run in profile.get("runs", []) or [] if isinstance(run, Mapping)]
    by_label = {run.get("label"): run for run in runs}
    last = _finish((by_label.get("前走") or {}).get("finish"))
    last_rank = (last - 1) / (h - 1) if last is not None else None
    recent = sum((_finish(r.get("finish")) or 1000) <= 3 for r in runs)
    jockey = horse.get("research_inputs") or {}
    starts = _number(jockey.get("jockey_n"))
    rate = _number(jockey.get("jockey_rate"))
    strength = rate / 100 if starts is not None and starts >= 20 and rate is not None else None
    x = ((rank-1)/(h-1), float(h), (corner-1)/(h-1),
         (start-1)/(h-1) if start is not None else None,
         strength, last_rank, float(recent),
         _same_course_distance(horse, runs))
    notes = []
    if 4 <= rank <= 8 and corner <= 3:
        notes.append("中位×4角前")
    if horse["mode"] == "jra" and last is not None and last <= 3:
        notes.append("前走好走")
    if horse["mode"] == "nar" and starts is not None and starts >= 20 and rate is not None and rate >= 35:
        notes.append("騎手適性")
    if rank <= 3 and corner > 6:
        notes.append("位置?")
    return x, tuple(notes)


def model_probability(mode, vector):
    """Pure-Python exact equivalent of the frozen sklearn median/scale/logit."""
    conf = MODEL[mode]
    z = conf["intercept"]
    for x, median, mean, scale, coef in zip(
            vector, conf["median"], conf["mean"], conf["scale"], conf["coef"]):
        v = median if x is None or not math.isfinite(x) else x
        z += (v-mean)/scale*coef
    return 1 / (1 + math.exp(-max(-35., min(35., z))))


def grade_from_probability(p):
    return next(tier for tier, cut, _cap in CUTOFFS if p >= cut)


def evaluate_race(view):
    """Assign independent research grades to a complete pre-race field.

    All horses are considered simultaneously; moving S to A when capped is
    an allocation constraint, not evidence that its probability worsened.
    Unknown ability/4角 remains unknown (never guessed D).
    """
    horses = [h for h in view or () if isinstance(h, Mapping)]
    if not horses:
        return {}
    mode = horses[0].get("mode")
    if mode not in MODEL:
        return {}
    head_count = len(horses)
    race_context = horses[0].get("race_context") or {}
    current = str(race_context.get("race_date") or race_context.get("date") or "")[:10]
    posthoc = bool(current and current <= MODEL[mode]["trained_through"])
    computed, missing = [], []
    for h in horses:
        no = str(h.get("no", ""))
        vector, notes = feature_vector(h, head_count)
        if not no or h.get("mode") != mode or vector is None:
            missing.append((no, dict(grade=None, reason="純能力順位・予測4角・主催が確認できないため判定不可",
                                    score=None, raw_grade=None, demoted=False,
                                    notes=(), retro=posthoc, version=VERSION)))
            continue
        p = model_probability(mode, vector)
        computed.append(dict(no=no, p=p, raw=grade_from_probability(p), notes=notes,
                             ability_rank=_rank(h.get("ability_rank")) or 999))
    computed.sort(key=lambda r: (-r["p"], r["ability_rank"],
                                 int(r["no"]) if r["no"].isdigit() else 9999))
    usage = {t: 0 for t, _, _ in CUTOFFS}
    cap = {t: limit for t, _, limit in CUTOFFS}
    order = [t for t, _, _ in CUTOFFS]
    result = {}
    for row in computed:
        position = order.index(row["raw"])
        while usage[order[position]] >= cap[order[position]]:
            position += 1
        tier = order[position];usage[tier] += 1
        demoted = tier != row["raw"]
        why = ("・".join(row["notes"]) or "能力順位・予測位置・騎手・近走")
        explanation = (
            f"研究{tier}／材料：{why}。"
            + (f"本来{row['raw']}相当→1レース人数上限による繰下げ。" if demoted else "")
            + "モデルの推定値は馬券内率を保証しません。正式印・純能力は不変。"
            + ("過去開催は後付け再計算（学習期間と重複）で、当時の予想ではありません。" if posthoc else "")
        )
        result[row["no"]] = dict(
            grade=tier, score=round(row["p"], 4), raw_grade=row["raw"],
            demoted=demoted, notes=row["notes"], reason=explanation,
            retro=posthoc, version=VERSION,
        )
    result.update(missing)
    return result


def assign_to_view(view):
    """Mutate only the transient *display projection*, not saved race rows."""
    ranked = evaluate_race(view)
    for horse in view:
        horse["research_sabcd"] = ranked.get(str(horse.get("no")), {})
    return view
