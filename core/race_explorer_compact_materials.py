"""Short, non-mutating display of evidence on compact horse cards and tables.

Never alters raw saved materials, search/sort values, prediction, or marks.
Titles and expanded horse details retain the original, unabridged text.
"""
from html import escape
import re

_EMPTY = {"", "—", "―", "-", "未取得", "なし", "nan", "None"}
_SOURCE_PREFIX = re.compile(r"^(?:[＋+]\s*)?(?:保存材料|プラス材料|参考材料|今回プラス|今回注意|参考|注意|プラス)\s*[：:]\s*")
_RUN_SCOPE = re.compile(r"[（(]近[３3]走の範囲[）)]")
_TRAINING = re.compile(r"^(?:今回|今週)?調教\s*([ABCD])(?:評価)?$")
_SINGLE_METRIC = re.compile(r"^(?:純能力|能力|コース|距離)(?:指数)?(?:Top)?\s*(\d+)(?:位)?$")


def _split(raw):
    """Split on explicit evidence separators only; keep e.g. 芝/ダ unchanged."""
    source = raw if isinstance(raw, (list, tuple)) else [raw]
    for item in source:
        if not isinstance(item, str):
            continue
        for piece in re.split(r"\s+/\s+|[；;]\s*", item):
            piece = piece.strip()
            if piece not in _EMPTY:
                yield piece


def clean_short(raw, max_chars=23):
    """Remove redundant prefixes from *display only*, preserving content in title."""
    text = re.sub(r"^[◎○▲✔✓△][\ufe0e\ufe0f]?\s*", "", str(raw or "")).strip()
    text = _SOURCE_PREFIX.sub("", text)
    text = _RUN_SCOPE.sub("", text)
    text = text.replace("今回調教", "調教").replace("今週調教", "調教")
    text = text.replace("ペース想定", "ペース").replace("4角想定", "4角")
    text = re.sub(r"\s+", " ", text).strip(" ・/、:：")
    return text if len(text) <= max_chars else text[:max_chars-1] + "…"


def _redundant(text, full, badges=(), training=None, course_rank=None, distance_rank=None, ability_rank=None):
    """Suppress only facts already shown unambiguously elsewhere in the card."""
    if text in _EMPTY:
        return True
    grade = _TRAINING.fullmatch(text)
    if grade and training in ("A", "B", "C", "D") and grade[1] == training:
        return True  # separate 調教 column / pickup status already shows the grade
    metric = _SINGLE_METRIC.fullmatch(text)
    if metric:
        target = int(metric[1])
        if "コース" in text and course_rank == target:
            return True
        if "距離" in text and distance_rank == target:
            return True
        if ("純能力" in text or "能力" in text) and ability_rank == target:
            return True
    badge_labels = [clean_short(x.get("label"), 100) for x in badges]
    if any(text == b or text in b for b in badge_labels):
        return True
    return False


def _chip(label, original, level, more=False):
    # All dynamic source strings are escaped, including title and aria-label.
    label = ("注意：" if level == "caution" else "") + label
    name = "evidence-more" if more else "evidence-chip evidence-" + level
    return ('<span class="' + name + '" title="' + escape(original, quote=True) +
            '" aria-label="' + escape(label + "。詳細は馬名を開いて確認", quote=True) +
            '">' + escape(label) + '</span>')


def chips(raw, *, level="support", badges=(), training=None, course_rank=None,
          distance_rank=None, ability_rank=None, limit=2, existing=()):
    """Returns display HTML, with a count for additional *nonduplicate* facts."""
    visible, extras, seen = [], [], set(existing)
    for original in _split(raw):
        text = clean_short(original, 23)
        if _redundant(text, original, badges, training, course_rank, distance_rank, ability_rank):
            continue
        key = re.sub(r"\s+", "", text)
        if not text or key in seen:
            continue
        seen.add(key)
        actual_level = ("reference" if level == "support" and
                        ("参考" in original[:8] or "裏付け" in original[:8]) else level)
        entry = _chip(text, original, actual_level)
        if len(visible) < limit:
            visible.append(entry)
        else:
            extras.append(original)
    if extras:
        visible.append(_chip("ほか" + str(len(extras)) + "件", " / ".join(extras), "reference", more=True))
    return "".join(visible)


def feature_chips(raw, *, training=None, limit=2):
    """Pickup facts: ensure caution remains visible even if listed after two positives."""
    entries, seen = [], set()
    for original in _split(raw):
        text = clean_short(original, 23)
        if _redundant(text, original, training=training):
            continue
        key = re.sub(r"\s+", "", text)
        if not text or key in seen:
            continue
        seen.add(key)
        count = re.search(r"(\d+)回3着以内", original)
        positive = bool(re.search(r"調教A", original) or
                        (count and int(count[1]) > 0) or
                        "好走" in original or "斤量減" in original)
        caution = bool(re.search(r"休養|注意|斤量増|調教[CD]", original))
        level = "caution" if caution else "support" if positive else "reference"
        entries.append((text, original, level))
    included = list(range(min(len(entries), limit)))
    # An existing concern must not disappear under "ほかn件".
    missing_caution = next((idx for idx, item in enumerate(entries)
                            if item[2] == "caution" and idx not in included), None)
    if missing_caution is not None and included:
        replaced = next((idx for idx in reversed(included) if entries[idx][2] != "caution"), None)
        if replaced is not None:
            included[included.index(replaced)] = missing_caution
    included.sort()
    result = [_chip(*entries[idx][:2], entries[idx][2]) for idx in included]
    omitted = [entry[1] for idx, entry in enumerate(entries) if idx not in included]
    if omitted:
        result.append(_chip("ほか" + str(len(omitted)) + "件", " / ".join(omitted), "reference", more=True))
    return "".join(result)
