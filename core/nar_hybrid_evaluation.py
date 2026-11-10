"""Read-only NAR '今回評価' shadow for the main all-runner comparison.

Fixed research v0.1: pure ability + 6 * (same-track-near-distance +
verified historical 4th-corner/finish + jockey course + 1.2 * exact H2H).
Never reads current results, odds, popularity, marks or formal ranks. This
projection does not write to PredictionResult or archived .keiba files.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence

VERSION = "nar_pure_n1_evidence_hybrid_shadow_v0_1_20261110"
COEFFICIENT = 6.0


def _text(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _norm(value):
    return re.sub(r"\s+", "", _text(value)).replace("ダート", "ダ").upper()


def _int(value):
    if value is None or isinstance(value, bool):
        return None
    m = re.search(r"-?\d+", _text(value))
    return int(m.group()) if m else None


def _float(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError):
        return None


def _date(value):
    try:
        return date.fromisoformat(_text(value)[:10])
    except ValueError:
        return None


def _surface(value):
    s = _norm(value)
    return "ダ" if "ダ" in s else "芝" if "芝" in s else ""


def _clamp(value, lo, hi):
    return max(lo, min(value, hi))


def _jockey_pct(value):
    # Match the frozen research parser: only the third percentage in a
    # 3-percentage stats string is used. Never infer a rate from a name.
    p = [int(x) for x in re.findall(r"(\d{1,3})\s*%", _text(value))]
    return p[-1] if len(p) >= 3 and 0 <= p[-1] <= 100 else None


def _run(raw):
    return dict(
        date=_text(raw.get("date"))[:10],
        venue=_text(raw.get("venue")),
        surface=_surface(raw.get("surface")),
        distance=_int(raw.get("distance")),
        race_name=_text(raw.get("race_name")),
        finish=_int(raw.get("finish")),
        race_id=_text(raw.get("race_id")),
        label=_text(raw.get("label")),
        past_corner4=None,
        past_head_count=None,
    )


def _attach_newspaper_runs(runs, horse, shadow):
    """Require horse number+name and past date/venue/distance/finish identity."""
    indexed = [x for x in (shadow.get("horses") or [])
               if isinstance(x, Mapping)
               and _text(x.get("horse_no")) == _text(horse.get("horse_no"))
               and _norm(x.get("horse_name")) == _norm(horse.get("horse_name"))]
    if len(indexed) != 1:
        return
    source = indexed[0].get("recent_runs") or []
    for r in runs:
        day = _date(r.get("date"))
        if day is None:
            continue
        mmdd = f"{day.month}/{day.day}"
        matches = [x for x in source if isinstance(x, Mapping)
                   and _text(x.get("label")) == r.get("label")
                   and _text(x.get("date")).lstrip("0").replace("/0", "/") == mmdd
                   and _norm(x.get("venue")) == _norm(r.get("venue"))
                   and _int(x.get("distance")) == r.get("distance")
                   and _int(x.get("finish")) == r.get("finish")]
        if len(matches) != 1:
            continue
        raw = _text(matches[0].get("passing_order"))
        if not raw or not re.fullmatch(r"[0-9\s,\-/出]+", raw):
            continue
        numbers = [int(x) for x in re.findall(r"\d+", raw)]
        head = _int(matches[0].get("head_count"))
        if numbers and head and 1 <= numbers[-1] <= head:
            r["past_corner4"] = numbers[-1]
            r["past_head_count"] = head


def _past_id_join(runs, evidence):
    history = evidence.get("past_runs") or []
    for r in runs:
        ids = {_text(x.get("race_id")) for x in history
               if isinstance(x, Mapping) and x.get("race_id")
               and _text(x.get("date")) == r["date"]
               and _int(x.get("finish")) == r["finish"]
               and _int(x.get("distance")) == r["distance"]
               and _norm(x.get("venue")) == _norm(r["venue"])}
        if len(ids) == 1:
            r["race_id"] = next(iter(ids))


def _extract(snapshot):
    if not isinstance(snapshot, Mapping) or snapshot.get("race_mode") != "nar":
        return None
    mobile = snapshot.get("mobile_snapshot") or {}
    if not isinstance(mobile, Mapping):
        return None
    top = {str(_int(h.get("horse_no"))): h for h in snapshot.get("horses", [])
           if isinstance(h, Mapping) and _int(h.get("horse_no")) is not None}
    saved = (snapshot.get("model_b_prediction") or {}).get("evidence") or {}
    shadow = mobile.get("nar_newspaper_v2_shadow") or {}
    by = []
    for h in mobile.get("horses", []):
        if not isinstance(h, Mapping):
            continue
        no = _int(h.get("horse_no"))
        if no is None or str(no) not in top:
            continue
        source = top[str(no)]
        if _norm(source.get("horse_name")) != _norm(h.get("horse_name")):
            continue
        runs = [_run(x) for x in h.get("recent_races", []) if isinstance(x, Mapping)]
        _attach_newspaper_runs(runs, h, shadow)
        _past_id_join(runs, saved.get(str(no)) or {})
        by.append(dict(
            no=str(no), name=_text(h.get("horse_name")),
            pure=_float(source.get("ability_value")),
            saved_pure_rank=_int(source.get("ability_rank")),
            facts=dict(
                date=_text(snapshot.get("date")), venue=_text(snapshot.get("venue")),
                surface=_surface(snapshot.get("surface")), distance=_int(snapshot.get("distance")),
                recent_runs=runs, jockey_pct=_jockey_pct(source.get("jockey_course_stats")),
            )
        ))
    if len(by) != len(top) or len({h["no"] for h in by}) != len(by):
        # Partial or identity-conflicted inputs should not yield invented ranks.
        return None
    return dict(date=_text(snapshot.get("date")), race_id=_text(snapshot.get("race_id")),
                horses=by)


def _components(h):
    """Exactly the three fixed N1 evidence components, excluding N1 form score."""
    f = h["facts"]
    day = _date(f["date"])
    if day is None:
        return None
    runs = sorted([r for r in f["recent_runs"]
                   if _date(r["date"]) and _date(r["date"]) < day and r["finish"] is not None],
                  key=lambda r: r["date"], reverse=True)[:3]
    venue, sf, dist = _norm(f["venue"]), f["surface"], f["distance"]
    same = [r for r in runs if _norm(r["venue"]) == venue
            and sf == r["surface"] and r["distance"] is not None and dist is not None
            and abs(r["distance"] - dist) <= 200]
    count_place = sum(r["finish"] <= 3 for r in same)
    count_top5 = sum(r["finish"] <= 5 for r in same)
    condition = min(.9, .44 * count_place) + (.15 if count_top5 >= 2 else 0.0)
    if runs and runs[0]["surface"] and sf != runs[0]["surface"]:
        condition -= .20

    corner, corner_count = 0.0, 0
    for i, r in enumerate(runs):
        c, size = r.get("past_corner4"), r.get("past_head_count")
        if c is None or size is None or size < 4 or not 1 <= c <= size:
            continue
        corner_count += 1
        w = [.55, .30, .15][i]
        front = c <= max(2, math.ceil(size / 3))
        rear = c > math.ceil(2 * size / 3)
        if front and r["finish"] <= 3:
            corner += w * .70
        if front and r["finish"] >= 6:
            corner -= w * .48
        if rear and r["finish"] <= 3:
            corner += w * .55
    jockey = _clamp(((f["jockey_pct"] - 25) / 100 * .75), -.20, .20) if f["jockey_pct"] is not None else 0.0
    return dict(near=condition, corner=corner, jockey=jockey, past_corner_n=corner_count)


def _graph_asof(extracted, day):
    latest = {}
    for race in sorted(extracted, key=lambda r: (r["date"], r["race_id"])):
        if race["date"] > day:
            break
        for h in race["horses"]:
            name = _norm(h["name"])
            if not name:
                continue
            current = latest.get(name)
            history = h["facts"]["recent_runs"]
            if current is None or current[0] < race["date"] or (current[0] == race["date"] and len(history) > len(current[1])):
                latest[name] = (race["date"], history)
    events, quality = defaultdict(dict), {}
    for name, (_, history) in latest.items():
        values = []
        for r in history:
            if r.get("race_id") and r["date"] < day and (r["finish"] or 0) > 0:
                events[r["race_id"]][name] = r["finish"]
                values.append(r["finish"])
        if values:
            quality[name] = _clamp(.85 + (.20 if any(x <= 3 for x in values) else -.10), .65, 1.15)
    good = {k: v for k, v in events.items() if len(v) >= 2 and len(set(v.values())) >= 2}
    return good, quality


def _head_to_head(h, graph, quality):
    date_str, name = h["facts"]["date"], _norm(h["name"])
    used = set()
    value = 0.0
    pairs = 0
    for run in h["facts"]["recent_runs"]:
        event_id, finish = run.get("race_id"), run.get("finish")
        if not event_id or event_id in used or not finish or run["date"] >= date_str or event_id not in graph:
            continue
        used.add(event_id)
        other = graph[event_id]
        if other.get(name) != finish:
            continue
        for rival, rival_finish in other.items():
            if rival == name or rival_finish == finish:
                continue
            value += (1 if finish < rival_finish else -1) * quality.get(rival, 1.0)
            pairs += 1
    return _clamp(value / (pairs + 4), -.55, .55) if pairs else 0.0, pairs


def with_nar_hybrid_evaluation(view, snapshot, archive_races=()):
    """Copy-only projection. If data cannot be independently validated, show nulls."""
    out = [dict(row) for row in view]
    if not out or not all(row.get("mode") == "nar" for row in out):
        return out
    current = _extract(snapshot)
    if not current:
        return out
    other = [x for x in (_extract(e) for e in archive_races)
             if x and x["date"] <= current["date"]]
    if not any(x["race_id"] == current["race_id"] for x in other):
        other.append(current)
    graph, quality = _graph_asof(other, current["date"])
    candidates = []
    for h in current["horses"]:
        c = _components(h)
        if not c or h["pure"] is None:
            return out
        h2h, pairs = _head_to_head(h, graph, quality)
        impacts = dict(
            near=6 * c["near"], corner=6 * c["corner"],
            jockey=6 * c["jockey"], opponent=6 * 1.2 * h2h,
        )
        score = round(h["pure"] + sum(impacts.values()), 5)
        labels = [("同会場近距離", impacts["near"]), ("実4角と着順", impacts["corner"]),
                  ("騎手コース複勝率", impacts["jockey"]), ("直接対戦", impacts["opponent"])]
        ordered = sorted(((k, x) for k, x in labels if abs(x) > .0001), key=lambda x: -abs(x[1]))
        why = " / ".join(f"{k}{x:+.1f}" for k, x in ordered) or "補正根拠なし・純能力維持"
        if not pairs:
            why += " / 対戦データ不足"
        candidates.append(dict(no=h["no"], value=score, pure=h["pure"], saved_rank=h["saved_pure_rank"],
                               reason=why, status="partial" if not pairs else "linked", version=VERSION))
    if len(candidates) != len(out):
        return out
    # Require strict source identity and saved ability-rank consistency, as in
    # the research; never backfill missing ability values from final score.
    if any(h["saved_rank"] is None for h in candidates):
        return out
    by_pure = sorted(candidates, key=lambda x: (x["saved_rank"], int(x["no"])))
    by_score = sorted(candidates, key=lambda x: (-x["pure"], x["saved_rank"], int(x["no"])))
    if [x["no"] for x in by_pure] != [x["no"] for x in by_score]:
        return out
    for idx, h in enumerate(sorted(candidates, key=lambda x: (-x["value"], x["saved_rank"], int(x["no"]))), 1):
        h["rank"] = idx
    mapped = {h["no"]: h for h in candidates}
    if {str(row.get("no")) for row in out} != set(mapped):
        return out
    for row in out:
        x = mapped[str(row["no"])]
        row["nar_hybrid_score"] = x["value"]
        row["nar_hybrid_rank"] = x["rank"]
        row["nar_hybrid_reason"] = x["reason"]
        row["nar_hybrid_version"] = VERSION
    return out
