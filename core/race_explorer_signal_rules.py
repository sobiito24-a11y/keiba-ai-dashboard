"""Exploratory JRA class-specific evidence badges. DISPLAY ONLY.

No prediction, rank, mark, Top5 selection, or betting recommendation is modified.
A match is a fact about pre-race inputs, NOT a purchase recommendation.
2026-10-10..24 result comparisons were selected retrospectively.
"""
from collections.abc import Mapping
from html import escape
from math import isfinite
import re
import unicodedata


def _mapping(obj):
    return obj if isinstance(obj, Mapping) else {}


def _norm(raw):
    return unicodedata.normalize("NFKC", str(raw or "")).strip()


def _rank(raw):
    if isinstance(raw, bool):
        return None
    try:
        n = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    return int(n) if isfinite(n) and n >= 1 and n.is_integer() else None


def race_group(horse):
    """Only well-supported race classes. No inference from horse's own age."""
    if horse.get("mode") != "jra":
        return None
    ctx = _mapping(horse.get("race_context"))
    # race_data2 distinguishes e.g. '稲光特別' from the misleading class_label 'A級'.
    desc = _norm(ctx.get("race_data2"))
    name = _norm(ctx.get("race_name") or ctx.get("レース名"))
    sample = desc or name
    if not sample or "障害" in sample:
        return None
    if "2歳" in sample and "未勝利" in sample and "勝クラス" not in sample:
        return "two_maiden"
    # A 2yo 1-win/OP/G race must never inherit the 3yo+ rule.
    if "2歳" in sample and "3歳以上" not in sample and "4歳以上" not in sample:
        return None
    if not ("3歳以上" in sample or "4歳以上" in sample):
        return None
    for grade, key in (("1勝クラス", "mixed1"), ("2勝クラス", "mixed2"),
                       ("3勝クラス", "mixed3")):
        if grade in sample:
            return key
    return None  # OP/G and unknown classes deliberately lack a fitted rule


def _previous_finish(horse):
    facts = _mapping(horse.get("explorer_facts"))
    for run in facts.get("runs") or ():
        if isinstance(run, Mapping) and run.get("label") == "前走":
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(run.get("date") or "")):
                return None
            m = re.fullmatch(r"([1-9]\d*)(?:着)?", _norm(run.get("finish")))
            return int(m.group(1)) if m else None
    return None


def signals(horse, cells):
    """Return at most two evidence tags (dicts), never a numeric grade."""
    group = race_group(horse)
    if not group:
        return ()
    cells = _mapping(cells)
    ability = _rank(cells.get("ability_rank"))
    corner = _rank(cells.get("corner"))
    course = _rank(cells.get("course_rank"))
    formal = _rank(cells.get("rank"))
    training = _norm(cells.get("training"))
    last = _previous_finish(horse)
    result = []
    def add(level, label, rationale):
        result.append(dict(level=level, label=label, detail=rationale))
    if group == "two_maiden":
        if ability == 1 and training in ("A", "B") and corner is not None and corner <= 6:
            add("match", "2歳：能力1位×調教AB×4角前方",
                "保存36R：該当26頭中20頭3着内（76.9%）。対象は26R。過去結果から選んだ条件で、買い推奨ではありません。")
        elif ability is not None and ability <= 3 and training in ("A", "B") and corner is not None and corner <= 6:
            add("reference", "2歳：能力Top3×調教AB×4角前方",
                "保存36R：該当67頭中43頭3着内（64.2%）。うち能力1位の該当を含む。事後探索の参考条件です。")
    elif group == "mixed1":
        if ability == 1:
            add("support", "純能力1位",
                "混合1勝・保存44R：44頭中21頭3着内（47.7%）、23頭は圏外。単独では軸確定ではありません。")
        if ability is not None and ability <= 3 and course is not None and course <= 3:
            add("reference", "能力×コース指数Top3",
                "混合1勝・保存44R：該当61頭中27頭3着内（44.3%）。純能力1位の単独より高精度な条件ではありません。")
    elif group == "mixed2":
        if ability is not None and ability <= 3 and last is not None and last <= 3:
            add("match", "能力Top3×前走3着以内",
                "混合2勝・保存21R：該当22頭中14頭3着内（63.6%）、8頭は圏外。該当しないレースもあります。")
    elif group == "mixed3":
        if formal is not None and formal <= 5 and last is not None and last <= 3:
            add("reference", "参考：正式Top5×前走好走",
                "混合3勝・保存11R：15頭中9頭3着内（60.0%）。レース数が少なく、正式候補は変更しません。")
    return tuple(result)


def compact_label(raw):
    """One short visual label; class and reference level live in color/aria/detail."""
    result = _norm(raw)
    result = re.sub(r"^(?:(?:参考|2歳)[：:])+\s*", "", result)
    return result


def badge_html(tags, compact=False):
    """Text plus color, never only color. Escape all HTML-facing data."""
    if not tags:
        return ""
    items = []
    for tag in tags:
        level = tag["level"] if tag["level"] in ("match", "support", "reference") else "reference"
        prefix = "＋ 条件一致：" if level == "match" else "＋ 確認：" if level == "support" else "参考："
        visible = compact_label(tag["label"]) if compact else prefix + tag["label"]
        items.append('<span class="evidence-chip evidence-' + level +
                     '" title="' + escape(tag["detail"], quote=True) +
                     '" aria-label="' + escape(prefix + tag["label"] + "。過去の探索的な比較条件であり、買い推奨ではありません。", quote=True) +
                     '">' + escape(visible) + '</span>')
    return '<span class="evidence-chips' + (' compact' if compact else '') + '">' + ''.join(items) + '</span>'


def evidence_note(tags):
    if not tags:
        return ""
    return '<p class="evidence-warning">過去の探索的な好走条件です。該当＝馬券購入の推奨ではありません。調教・休養・斤量・他馬との比較も確認してください。</p>'
