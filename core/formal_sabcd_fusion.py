"""Read-only formal-rank x research-SABCD fusion, measured before promotion.

Train: frozen archived pre-race features, JRA 2026-11-07/08 (823 runners),
NAR 2026-11-11 (532 runners). Test: untrained 2026-11-14/15.
The original model is only reconstructible from archives approximately: its
transient profile was not frozen. These weights are RESEARCH-ONLY and must
NEVER replace the visible SABCD, official Top5, official marks or snapshots.
The strongest non-market fusion FAILED to beat standalone SABCD on the JRA
held-out winner and podium coverage. In particular, there is no permission to
promote it automatically after one date or to make betting recommendations.

Observed live odds are deliberately *not* included in this read-only fusion:
their timestamps and completeness are not verified as prestart data.
"""
from __future__ import annotations

from collections.abc import Mapping
import math

VERSION = "formal-sabcd-fusion-shadow-20261116"
# SimpleImputer was unnecessary on train: both features were observed.
# StandardScaler -> LogisticRegression(C=0.3, max_iter=300).
# Features: (formal_rank-1)/(field_size-1), 2026-11-12 weight-class
# research score. Coefficients frozen after training on dates above.
PARAMS = {
    "jra": {
        "mean": (0.498987444309437, 0.2337674024521083),
        "scale": (0.3098716006349134, 0.17538766004078324),
        "coef": (-0.12958731251585637, 0.6585153061859963),
        "intercept": -1.4353798240752196,
        "train_through": "2026-11-08",
    },
    "nar": {
        "mean": (0.49946604147731977, 0.26580893514942155),
        "scale": (0.31524186357079303, 0.23679631018573769),
        "coef": (-0.2960504099820652, 0.9104467168497657),
        "intercept": -1.2340914744605913,
        "train_through": "2026-11-11",
    },
}


def _finite_number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def research_score(mode, formal_rank, sabcd_score, field_size):
    """Exploratory scalar, NOT a calibrated podium probability.

    Exact archived formal rank, current active weight-class SABCD research
    score, and field size are required. Do not infer missing ranks from
    popularity, ability, marks or an old reference rank.
    """
    params = PARAMS.get(str(mode or "").lower())
    formal = _finite_number(formal_rank)
    sabcd = _finite_number(sabcd_score)
    count = _finite_number(field_size)
    if (params is None or count is None or count < 3 or formal is None or
            formal < 1 or formal > count or formal != int(formal) or
            sabcd is None or not 0 <= sabcd <= 1):
        return None
    x = ((formal - 1) / (count - 1), sabcd)
    z = params["intercept"] + sum(
        ((value - mean) / scale) * coef
        for value, mean, scale, coef in zip(
            x, params["mean"], params["scale"], params["coef"]
        )
    )
    return round(1 / (1 + math.exp(-max(-35., min(35., z)))), 4)


def evaluate_race(view):
    """Evaluate one exploratory score per horse with no upstream mutation."""
    horses = [h for h in view or () if isinstance(h, Mapping)]
    if not horses:
        return {}
    mode = horses[0].get("mode")
    if mode not in PARAMS:
        return {}
    from .race_explorer_columns import _a_values
    date = str((horses[0].get("race_context") or {}).get("race_date") or
               (horses[0].get("race_context") or {}).get("date") or "")[:10]
    retrospective = bool(date and date <= PARAMS[mode]["train_through"])
    result = {}
    for horse in horses:
        no = str(horse.get("no") or "")
        if not no:
            continue
        # _a_values disallows unverified NAR formal reference ranks; a plain
        # h['rank'] might wrongly imply a formal score was actually calculated.
        _, formal = _a_values(horse)
        sabcd = horse.get("research_sabcd_weight_class") or {}
        sabcd = sabcd.get("score") if isinstance(sabcd, Mapping) else None
        score = research_score(mode, formal, sabcd, len(horses))
        result[no] = {
            "score": score,
            "version": VERSION,
            "retrospective": retrospective,
            "status": "research_only" if score is not None else "insufficient_inputs",
            "reason": ("正式順位と研究SABCDから算出した未校正の研究スコア。"
                       "11/14・15検証で中央はSABCD単独を上回らず本番未採用。"
                       "公式印・SABCD・馬券判断には未反映。"
                       + ("過去開催への後日適用であり、当時の予想ではありません。"
                          if retrospective else "")
                       if score is not None else
                       "正式順位または研究SABCD値が欠損。埋め合わせはしません。"),
        }
    return result


def assign_to_view(view):
    """Only add diagnostic results to a transient display view."""
    results = evaluate_race(view)
    for horse in view:
        horse["research_formal_sabcd_fusion"] = results.get(
            str(horse.get("no")), {})
    return view
