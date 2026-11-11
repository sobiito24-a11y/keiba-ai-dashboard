"""Research-only class-history bridge: does not change formal scores or marks."""
from __future__ import annotations
from datetime import datetime

UNKNOWN = (None, "", "不明")


def _timestamp(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _known(value):
    return value not in UNKNOWN


def verified_past_context(*, target, past, prior_race):
    """Use a prior race's pre-start header only with verified horse/race identity.

    target: mode, horse_id, prediction_created_at
    past: race_id, venue, class_context
    prior_race: race_id, mode, venue, saved_at, horse_ids, class_context

    Do not infer NAR age categories from age of the horse or today's class.
    Missing or contradictory evidence remains explicitly unknown.
    """
    original = dict(past.get("class_context") or {})
    if not isinstance(prior_race, dict):
        return original, "past_run_only"
    if not (target.get("horse_id") and past.get("race_id") and
            past["race_id"] == prior_race.get("race_id") and
            target.get("mode") == prior_race.get("mode")):
        return original, "race_or_horse_identity_unknown"
    if _known(past.get("venue")) and prior_race.get("venue") != past["venue"]:
        return original, "venue_conflict"
    if str(target["horse_id"]) not in {str(h) for h in prior_race.get("horse_ids", ())}:
        return original, "horse_not_in_prior_race"
    seen = _timestamp(prior_race.get("saved_at"))
    target_time = _timestamp(target.get("prediction_created_at"))
    if not seen or not target_time or seen > target_time:
        return original, "header_not_available_as_of_prediction"
    header = prior_race.get("class_context") or {}
    if original.get("class_family") != header.get("class_family"):
        return original, "class_family_conflict"
    fields = ("class_level_v2", "age_restriction_v2", "venue_v2", "race_discipline_v2")
    if any(_known(original.get(k)) and _known(header.get(k)) and original[k] != header[k]
           for k in fields):
        return original, "conflicting_class_evidence"
    merged = dict(original)
    for key in ("class_level_v2", "class_label_v2", "age_restriction_v2",
                "venue_v2", "race_discipline_v2", "class_raw_v2"):
        if not _known(merged.get(key)) and _known(header.get(key)):
            merged[key] = header[key]
    return merged, "verified_saved_header"


def class_transition(current, past):
    """Compare only same authority, age category, discipline and NAR venue.

    The levels are class-order labels, not an absolute national ability score.
    """
    if current.get("class_family") != past.get("class_family") or current.get("class_family") not in ("JRA", "NAR"):
        return "比較不能", "主催不明・不一致"
    now, before = current.get("class_level_v2"), past.get("class_level_v2")
    if not isinstance(now, (int, float)) or not isinstance(before, (int, float)):
        return "比較不能", "クラスの実測情報不足"
    if not _known(current.get("age_restriction_v2")) or current.get("age_restriction_v2") != past.get("age_restriction_v2"):
        return "比較不能", "年齢条件の実測情報不足・不一致"
    if current.get("race_discipline_v2") not in ("flat", "jump") or current.get("race_discipline_v2") != past.get("race_discipline_v2"):
        return "比較不能", "平地・障害の実測情報不足・不一致"
    if current["class_family"] == "NAR" and (not _known(current.get("venue_v2")) or current.get("venue_v2") != past.get("venue_v2")):
        return "比較不能", "競馬場の実測情報不足・不一致"
    label = "昇級" if now > before else "降級" if now < before else "同級"
    return label, "明示的な比較可能クラス"
