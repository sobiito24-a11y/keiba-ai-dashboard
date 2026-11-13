"""Official course-turn lookup for all 10 active JRA and 15 NAR venues.

Read-only display metadata: never changes ranks, marks or position estimates.
JRA: https://jra.jp/facilities/race/niigata/course/
NAR: https://www.keiba.go.jp/guide/course/
Oi both directions: https://www.nankankeiba.com/course_info/20.do
Oi left 1650m: official TCK course chart. On unknown/Oi ambiguous
course do not invent a clockwise direction.

A course's rotation and the cartoon's facing direction are distinct:
the supplied visual's convention is clockwise => silhouette faces left,
counterclockwise => silhouette faces right.
"""
from collections.abc import Mapping
import re
import unicodedata

JRA_TURNS = {
    "札幌": "right", "函館": "right", "福島": "right",
    "新潟": "left", "東京": "left", "中山": "right",
    "中京": "left", "京都": "right", "阪神": "right", "小倉": "right",
}
NAR_TURNS = {
    "帯広": "straight", "門別": "right", "盛岡": "left",
    "水沢": "right", "浦和": "left", "船橋": "left",
    "大井": "mixed", "川崎": "left", "金沢": "right",
    "笠松": "right", "名古屋": "right", "園田": "right",
    "姫路": "right", "高知": "right", "佐賀": "right",
}
JRA_CODES = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟",
    "05": "東京", "06": "中山", "07": "中京", "08": "京都",
    "09": "阪神", "10": "小倉",
}
LABELS = {
    "right": "右回り", "left": "左回り",
    "straight": "直線コース", "unknown": "回り方向未取得",
}
COURSE_KEYS = (
    "turn", "turn_direction", "course_turn", "race_turn", "race_direction",
    "rotation", "回り", "回り方向", "コース回り", "コース方向",
)
VENUE_KEYS = (
    "racecourse", "venue", "競馬場", "開催場", "会場", "place", "場名",
)
DISTANCE_KEYS = ("distance", "distance_label", "距離", "距離表示", "距離m")
SURFACE_KEYS = ("surface", "surface_label", "芝ダート", "馬場種別", "course_surface")
TEXT_KEYS = ("course", "course_label", "race_course", "コース", "コース情報")
_STRAIGHT_TOKENS = ("直線", "直千", "直1000", "straight")


def _str(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if value >= 1 and float(value).is_integer() else None
    match = re.search(r"(?<!\d)(\d[\d,]{2,4})\s*(?:m|メートル)?(?!\d)",
                      _str(value), re.IGNORECASE)
    return int(match.group(1).replace(",", "")) if match else None


def _venue(value, mode):
    raw = _str(value).replace(" ", "").replace("　", "")
    raw = re.sub(r"^(?:JRA|NAR|地方|中央)", "", raw, flags=re.IGNORECASE)
    raw = raw.removesuffix("競馬場")
    # Do not match arbitrary substrings such as 北海道/南関東/岩手;
    # only exact course names are unambiguous.
    table = JRA_TURNS if mode == "jra" else NAR_TURNS
    if raw in table:
        return raw
    # 'ばんえい帯広' is the actual local racecourse display name.
    if mode == "nar" and raw in ("帯広ば", "ばんえい帯広", "帯広ばんえい"):
        return "帯広"
    return ""


def _turn_text(value):
    raw = _str(value).lower().replace(" ", "")
    if not raw:
        return None
    if any(key in raw for key in _STRAIGHT_TOKENS):
        return "straight"
    right = bool(re.search(r"右(?:回り|廻り|コース)?", raw)) or raw in (
        "r", "clockwise", "cw", "right")
    left = bool(re.search(r"左(?:回り|廻り|コース)?", raw)) or raw in (
        "l", "counterclockwise", "counter-clockwise", "ccw", "left")
    if left and right:
        return "unknown"
    return "left" if left else "right" if right else None


def _info(view, race_info):
    if isinstance(race_info, Mapping) and race_info:
        return race_info
    for horse in view or ():
        if isinstance(horse, Mapping):
            context = horse.get("race_context")
            if isinstance(context, Mapping) and context:
                return context
    return {}


def course_direction(view, race_info=None, race_key=""):
    """Return venue, directional label, evidence and corner applicability.

    Explicit, unambiguous race-level direction overrides venue defaults.
    Even if the race is at Oi, missing distance+direction is an UNKNOWN,
    not an invented right turn. Straight-track starts have no 3rd/4th corner.
    """
    view = list(view or ())
    info = _info(view, race_info)
    mode = str(next((h.get("mode") for h in view if isinstance(h, Mapping)
                     and h.get("mode")), "")).lower()
    raw_venue = next((_str(info[k]) for k in VENUE_KEYS
                     if _str(info.get(k))), "")
    venue = _venue(raw_venue, mode)
    if not venue and mode == "jra":
        rid = _str(info.get("race_id") or race_key)
        if re.fullmatch(r"20\d{10}", rid):
            venue = JRA_CODES.get(rid[4:6], "")
    surface = next((_str(info[k]) for k in SURFACE_KEYS
                    if _str(info.get(k))), "")
    dist = next((_number(info.get(k)) for k in DISTANCE_KEYS
                 if _number(info.get(k)) is not None), None)
    if dist is None:
        for key in TEXT_KEYS:
            dist = _number(info.get(key))
            if dist is not None:
                break
    if not surface:
        for key in TEXT_KEYS + ("distance_label",):
            value = _str(info.get(key))
            if re.search("芝|turf", value, re.IGNORECASE):
                surface = "芝"
                break
            if re.search("ダート|ダ\\d|dirt", value, re.IGNORECASE):
                surface = "ダ"
                break
    # Exact special courses must override a generic venue's turn, even
    # when no explicit direction field is saved.
    straight = (
        venue == "帯広" and mode == "nar" or
        venue == "新潟" and mode == "jra" and dist == 1000
        and bool(re.search(r"芝|turf", surface, re.IGNORECASE))
    )
    if straight:
        turn, source = "straight", "course"
    else:
        explicit = [
            _turn_text(info[k]) for k in COURSE_KEYS + TEXT_KEYS
            if _str(info.get(k))
        ]
        explicit = [item for item in explicit if item is not None]
        # Contradictory saved turn indicators must not silently choose one.
        if "unknown" in explicit or len(set(explicit)) > 1:
            turn, source = "unknown", "conflicting_race_info"
        elif explicit:
            turn, source = explicit[0], "saved_race_info"
        elif venue == "大井" and mode == "nar":
            # Only 1650m races run left-handed at modern TCK.
            # Avoid defaulting when course/distance is unknown.
            turn = "left" if dist == 1650 else "right" if dist is not None else "unknown"
            source = "official_oi_distance" if dist is not None else "missing_oi_course"
        else:
            turn = (JRA_TURNS if mode == "jra" else NAR_TURNS).get(venue, "unknown")
            source = "official_venue" if turn != "unknown" else "missing_venue"
    return dict(mode=mode, venue=venue, turn=turn, label=LABELS[turn],
                source=source, distance=dist, surface=surface,
                has_corners=turn != "straight")
