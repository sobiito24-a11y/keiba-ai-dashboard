"""Frozen, shadow-only weight/class SABCD study (2026-11-12).

Never writes formal ranks, marks, betting recommendations, or saved snapshots.
Fitted on archived pre-race features through 2026-10-23 (JRA) / 11-08
(NAR); tested on subsequent 207 races.  These are research model scores,
NOT calibrated odds/guaranteed 3着内率.  No H2H or unverified pace is added.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping

from .research_sabcd import feature_vector, grade_from_probability, _number

VERSION = "weight-class-shadow-20261112"
FEATURES = (
    "ability_rank_rel", "head_count", "corner_rank_rel", "start_rank_rel",
    "jockey_strength", "last_finish_rel", "recent_podium",
    "same_course_place", "weight_delta", "weight_vs_field",
    "female", "age_years", "upclass", "downclass", "class_unknown",
)
# sklearn: SimpleImputer(fill_value=0) -> StandardScaler -> LogisticRegression(C=.20).
# These constants reproduce the frozen, previous-date-only fit without sklearn.
PARAMS = {
    "jra": {
        "mean": (0.49875516,14.32688588,0.49955301,0.49914666,0.15588008,0.45802230,0.77949710,0.,0.18471954,0.,0.40296583,3.50999355,0.37588652,0.08252740,0.00322373),
        "scale": (0.31099093,2.81234142,0.31077602,0.31048510,0.15238354,0.34748609,0.87023567,1.,1.37510983,1.23188681,0.49049401,1.33581211,0.48435095,0.27516655,0.05668628),
        "coef": (-0.54436108,-0.31351354,-0.20416190,-0.14275505,0.22958287,-0.39355323,0.05114387,0.,-0.08031336,-0.03520550,-0.07352889,-0.14337887,-0.04126527,0.11638671,0.00497019),
        "intercept": -1.5547277284543801,
        "train_through": "2026-10-23",
    },
    "nar": {
        "mean": (0.5,10.52040816,0.5,0.5,0.26982993,0.52685415,0.79591837,0.26020408,-0.04761905,0.,0.44557823,4.29081633,0.07653061,0.09183673,0.25680272),
        "scale": (0.31822957,1.43732739,0.31822957,0.31822957,0.14106243,0.36680686,0.94537021,0.43874585,0.89087081,1.19895888,0.49702945,1.77437850,0.26584521,0.28879534,0.43686964),
        "coef": (-0.61186900,-0.25154896,-0.55378866,-0.10506160,0.25171467,-0.16891566,0.03029556,0.08982582,0.04968896*-1,0.00977450,-0.20403247,-0.04803900,0.22688216,-0.09958705,-0.16321549),
        "intercept": -1.2699174133573525,
        "train_through": "2026-11-08",
    },
}


def _weight_kg(horse):
    raw = str(horse.get("weight") or "")
    match = re.search(r"(?<!\d)(\d{2}(?:\.\d)?)(?:\s*kg)?", raw, re.I)
    value = _number(match.group(1)) if match else None
    return value if value is not None and 43 <= value <= 70 else None


def _age_and_sex(horse):
    label = str(horse.get("age") or "").replace("セン", "セ")
    match = re.search(r"(\d+)\s*$", label)
    return (1. if label.startswith("牝") else 0. if label.startswith(("牡", "セ")) else None,
            float(match.group(1)) if match else None)


def feature_values(horse, field_size, mean_weight):
    """Return only archived pre-race materials from the display projection."""
    base, _notes = feature_vector(horse, field_size)
    if base is None:
        return None, {}
    kg = _weight_kg(horse)
    relative = kg - mean_weight if kg is not None and mean_weight is not None else None
    delta = _number(horse.get("weight_delta"))
    female, age = _age_and_sex(horse)
    raw_shift = str((horse.get("profile") or {}).get("class_shift") or "")
    # The UI's conservative class parser returns 昇級/降級, whereas the
    # original research CSV used クラス昇級/クラス降級.
    shift = ("クラス昇級" if raw_shift in ("昇級", "クラス昇級") else
             "クラス降級" if raw_shift in ("降級", "クラス降級") else
             "同級" if raw_shift == "同級" else "判定不可")
    vec = (*base, delta, relative, female, age,
           float(shift == "クラス昇級"),
           float(shift == "クラス降級"),
           float(shift == "判定不可"))
    materials = dict(weight_kg=kg, weight_delta=delta,
                     weight_vs_field=round(relative, 2) if relative is not None else None,
                     age=age, female=female, class_shift=shift,
                     missing_inputs=[name for name, x in zip(FEATURES, vec) if x is None])
    return vec, materials


def predict(mode, values):
    if mode not in PARAMS or values is None:
        return None
    p = PARAMS[mode]
    z = p["intercept"]
    for raw, mean, scale, coef in zip(values, p["mean"], p["scale"], p["coef"]):
        x = raw if raw is not None and math.isfinite(raw) else 0.
        z += (x - mean) / scale * coef
    z = min(35., max(-35., z))
    return 1. / (1. + math.exp(-z))


def _normalise_to_podium_slots(scores):
    """Reference only: logit-shift all runners' scores to sum to 3."""
    if len(scores) < 3:
        return None
    logit = [math.log(max(1e-6, min(1-1e-6, p)) /
                      (1-max(1e-6, min(1-1e-6, p)))) for p in scores]
    low, high = -40., 40.
    for _ in range(80):
        m = (low + high) / 2.
        total = sum(1/(1+math.exp(-max(-60., min(60., v+m)))) for v in logit)
        if total > 3:
            high = m
        else:
            low = m
    offset = (low + high) / 2.
    return [1/(1+math.exp(-max(-60., min(60., v+offset)))) for v in logit]


def evaluate_race(view):
    horses = [h for h in view or () if isinstance(h, Mapping)]
    if not horses:
        return {}
    mode = horses[0].get("mode")
    if mode not in PARAMS:
        return {}
    weights = [value for h in horses if (value := _weight_kg(h)) is not None]
    mean_weight = sum(weights)/len(weights) if weights else None
    date = str((horses[0].get("race_context") or {}).get("race_date") or
               (horses[0].get("race_context") or {}).get("date") or "")[:10]
    retro = bool(date and date <= PARAMS[mode]["train_through"])
    result = {}
    scored = []
    for horse in horses:
        no = str(horse.get("no", ""))
        if not no:
            continue
        vec, materials = feature_values(horse, len(horses), mean_weight)
        prob = predict(mode, vec) if horse.get("mode") == mode else None
        if prob is None:
            result[no] = dict(grade=None, score=None, normalized_score=None,
                              reason="基本8項目の順位・予測4角がないため判定不可",
                              materials=materials, version=VERSION, retro=retro)
            continue
        scored.append((no, prob))
        label = grade_from_probability(prob)
        kg = materials.get("weight_kg")
        kg_delta = materials.get("weight_delta")
        rel = materials.get("weight_vs_field")
        class_shift = materials.get("class_shift")
        reasons = (
            f"研究比較{label}／今回斤量：{kg:g}kg" if kg is not None else
            f"研究比較{label}／今回斤量：未取得"
        )
        reasons += (
            f"、前走差：{kg_delta:+g}kg" if kg_delta is not None else "、前走差：未取得"
        )
        reasons += (
            f"、出走馬平均との差：{rel:+.2f}kg" if rel is not None else
            "、出走馬平均との差：未取得"
        )
        reasons += f"、クラス：{class_shift}。"
        if materials["missing_inputs"]:
            reasons += "欠損材料は研究時と同じ0補完：" + "・".join(materials["missing_inputs"]) + "。"
        reasons += "推定値は未校正の研究スコア。正式印・純能力・購入判断には不使用。"
        if retro:
            reasons += "過去開催に研究モデルを後日適用した結果（当時の予想ではありません）。"
        result[no] = dict(grade=label, score=round(prob, 4),
                          normalized_score=None, reason=reasons,
                          materials=materials, version=VERSION, retro=retro)
    # Normalise ONLY when every runner can be evaluated.  A sum of 300%
    # is an arithmetic constraint, not evidence that each horse is calibrated.
    if len(scored) == len(horses):
        adjusted = _normalise_to_podium_slots([p for _, p in scored])
        if adjusted is not None:
            for (no, _), p in zip(scored, adjusted):
                result[no]["normalized_score"] = round(p, 4)
    total = round(sum(p for _, p in scored), 4)
    for item in result.values():
        item["race_score_sum"] = total
    return result


def assign_to_view(view):
    result = evaluate_race(view)
    for horse in view:
        horse["research_sabcd_weight_class"] = result.get(str(horse.get("no")), {})
    return view
