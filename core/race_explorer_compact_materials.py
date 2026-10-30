"""Compact, factual JRA/NAR comparison snippets. Display-only.

Never rewrite saved positives/cautions, marks or ranks. Full source wording remains
in the horse detail and in the raw typed comparison cells for search/filter.
"""
from html import escape
import re

from .race_explorer_signal_rules import badge_html, compact_label


_JUDGEMENT = re.compile(r"^[\s◎○▲✔✓△＋+\-]+\s*")
_LEAD = re.compile(r"^(?:プラス材料|保存材料|今回プラス|参考|今回の好材料)[：:\s]+")
_SEP = re.compile(r"\s+[/／]\s+|\s*[；;\n]\s*")
_GRADE_ONLY = re.compile(r"^(?:今回)?調教(?:評価)?([ABCD])$")
_STRIP_SCOPE = re.compile(r"（近3走の範囲）|（近走の範囲）")


def _pieces(value):
    """Split only explicit material separators, not arithmetic / or dates."""
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple)) else [value]
    out = []
    for source in values:
        for part in _SEP.split(str(source or "")):
            item = _LEAD.sub("", _JUDGEMENT.sub("", part.strip())).strip()
            item = re.sub(r"^\+\s*", "", item)
            if item and item not in ("—", "未取得", "不明", "なし", "-"):
                out.append(item)
    return out


def _short(raw, limit=23):
    """Keep meaning first. Long raw material remains accessible in title/detail."""
    result = _STRIP_SCOPE.sub("", raw).strip()
    result = result.replace("3着以内", "3着内")
    result = re.sub(r"^今回調教", "調教", result)
    return result if len(result) <= limit else result[:limit - 1] + "…"


def _duplicated(piece, seen, labels, training, *, positive):
    canonical = re.sub(r"\s+", "", _short(piece, 9999))
    if not canonical or canonical in seen:
        return True
    if canonical in labels:
        return True
    if positive and _GRADE_ONLY.fullmatch(piece):
        # Grade already exists in the same row's "調教" column / pickup state.
        return bool(training and training in "ABCD" and _GRADE_ONLY.fullmatch(piece).group(1) == training)
    # Short elementary fragments already covered by a composite research tag.
    normalized = canonical.replace("純能力", "能力")
    if positive and (
        (normalized in ("能力Top3", "能力1位") and any(normalized in x for x in labels))
        or (normalized in ("4角前方", "4角6番手以内") and any("4角前方" in x for x in labels))
    ):
        return True
    return False


def _span(raw, level):
    summary = _short(raw)
    sign = "注意：" if level == "caution" else ""
    return ('<span class="evidence-chip evidence-' + level +
            '" title="' + escape(raw, quote=True) +
            '" aria-label="' + escape(("注意材料：" if level == "caution" else "保存済みプラス材料：") + raw, quote=True) +
            '">' + escape(sign + summary) + '</span>')


def compact_materials_html(tags, plus, caution, training=None):
    """Small summary: 2 positives (including study tags), 1 caution, +more.

    Details remain authoritative. The 'other N' is based on actual omitted
    nonduplicated facts, not duplicate wording.
    """
    tags = tuple(tags or ())
    shown_tags = tags[:2]
    signal_labels = {compact_label(str(t["label"])) for t in tags}
    labels = {x.replace("純能力", "能力") for x in signal_labels}
    positives, cautions = [], []
    seen_positive, seen_caution = set(), set()
    for raw in _pieces(plus):
        if _duplicated(raw, seen_positive, labels, training, positive=True):
            continue
        canonical = re.sub(r"\s+", "", _short(raw, 9999))
        seen_positive.add(canonical)
        positives.append(raw)
    for raw in _pieces(caution):
        if _duplicated(raw, seen_caution, set(), None, positive=False):
            continue
        canonical = re.sub(r"\s+", "", _short(raw, 9999))
        seen_caution.add(canonical)
        cautions.append(raw)

    remaining = max(0, 2 - len(shown_tags))
    visible_plus, hidden_plus = positives[:remaining], positives[remaining:]
    visible_caution, hidden_caution = cautions[:1], cautions[1:]
    output = badge_html(shown_tags, compact=True)
    output += "".join(_span(t, "support") for t in visible_plus)
    output += "".join(_span(t, "caution") for t in visible_caution)
    hidden = hidden_plus + hidden_caution
    if hidden:
        output += ('<span class="evidence-chip evidence-more" title="' +
                   escape(" / ".join(hidden), quote=True) +
                   '" aria-label="' + escape("その他の判断材料：" + " / ".join(hidden), quote=True) +
                   '">ほか' + str(len(hidden)) + '件</span>')
    return output


def pickup_feature_html(features, grade=None):
    """Make existing pickup facts concise without repeating the training box."""
    seen = set()
    out = []
    for raw in features or ():
        pieces = _pieces(raw)
        if not pieces:
            continue
        piece = pieces[0]
        matched = _GRADE_ONLY.fullmatch(piece)
        if matched and grade and grade == matched.group(1):
            continue
        normalized = _short(piece, 9999)
        if normalized in seen:
            continue
        seen.add(normalized)
        top3 = re.search(r"(\d+)回3着以内", piece)
        caution = any(word in piece for word in ("休養", "注意", "マイナス"))
        positive = bool("調教A" in piece or (top3 and int(top3.group(1)) > 0))
        level = "caution" if caution else "support" if positive else "reference"
        out.append(_span(piece, level))
        if len(out) >= 3:
            break
    return "".join(out)
