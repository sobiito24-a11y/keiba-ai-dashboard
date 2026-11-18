"""Read-only warning for a conflict between stored running style and start position.

This module never alters official rankings, marks, model scores, or saved snapshots.
A missing or ambiguous style/position is not a warning.
"""
from collections.abc import Mapping

_EARLY_STYLES = {"逃", "逃げ", "先", "先行"}


def find_position_conflicts(race_snapshot: Mapping) -> list[dict[str, str]]:
    mobile = race_snapshot.get("mobile_snapshot") or {}
    market = mobile.get("market_compare") or {}
    horses = market.get("horses") or []
    if not isinstance(horses, list):
        return []
    conflicts = []
    for horse in horses:
        if not isinstance(horse, Mapping):
            continue
        style = str(horse.get("running_style_market") or "").strip()
        start = str(horse.get("position_start_label_market") or "").strip()
        if style not in _EARLY_STYLES or not start.startswith("後方"):
            continue
        no = str(horse.get("馬番") or horse.get("horse_no") or "").strip()
        name = str(horse.get("馬名") or horse.get("horse_name") or "").strip()
        if not no or not name:
            continue
        conflicts.append({"horse_no": no, "horse_name": name, "style": style, "start": start})
    def order(item):
        return (0, int(item["horse_no"])) if item["horse_no"].isdigit() else (1, item["horse_no"])
    return sorted(conflicts, key=order)
