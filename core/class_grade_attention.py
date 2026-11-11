"""Read-only, dated class and graded-race notes for the all-runner dashboard.

Shows verified previous-race facts when no cross-class comparison is possible.
Never changes official marks, index values, odds, or ranking inputs.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

_FINISH = re.compile(r"^([1-9][0-9]*)(?:着)?$")
_GRADE_IN_NAME = re.compile(
    r"(?<![A-Za-z0-9])(?P<type>Jpn|G)(?P<rank>III|II|I|[123])"
    r"(?![A-Za-z0-9])", re.IGNORECASE)
_NAR_CLASS = re.compile(
    r"(?<![A-Za-z0-9])([ABC](?:[1-9][0-9]?)組|"
    r"[ABC][123](?![0-9])(?:[一二三四五六七八九十]+"
    r"(?:[・･、\s]+[一二三四五六七八九十]+)*)?)")
_NAR_AGE_GROUP = re.compile(r"(?:2歳|3歳)\s*\d{1,2}組")
_JRA_LEVEL = re.compile(r"(?:[123]勝(?:クラス)?|(?:2歳|3歳)?未勝利|"
                        r"(?:2歳|3歳)?新馬|オープン|OP|リステッド|L)")
_MISSING = frozenset(("", "-", "―", "—", "未取得", "不明", "unknown", "none"))


def _finish(value):
    if isinstance(value, bool):
        return None
    match = _FINISH.fullmatch(str(value or "").strip())
    return int(match[1]) if match else None


def _known(value):
    return str(value if value is not None else "").strip().casefold() not in _MISSING


def _grade(text):
    """A literal grade from the historical race name; Roman II != I."""
    match = _GRADE_IN_NAME.search(str(text or ""))
    if not match:
        return None
    level = {"I": "1", "II": "2", "III": "3"}.get(
        match.group("rank").upper(), match.group("rank"))
    prefix = "Jpn" if match.group("type").casefold() == "jpn" else "G"
    return prefix + level


def _past_class_text(run, context):
    """Keep local subclasses like C2一, and C23組 as C23組 (not C2).

    The named historical race is more specific than the legacy generic
    class_label; it also wins when legacy Jpn1 conflicts with JpnII/JpnIII.
    """
    title = str(run.get("race_name") or "").strip()
    raw = str(run.get("class_raw") or "").strip()
    ctx = str(context.get("class_label_v2") or "").strip()
    for candidate in (title, raw):
        if grade := _grade(candidate):
            return grade, True
    for candidate in (title, raw):
        if match := _NAR_CLASS.search(candidate):
            return match.group(1).replace(" ", ""), True
        if match := _NAR_AGE_GROUP.search(candidate):
            return match.group(0).replace(" ", ""), True
        if match := _JRA_LEVEL.search(candidate):
            return match.group(0), True
    # A saved context is less detailed, but can still name the previous class.
    if _known(ctx) and (grade := _grade(ctx)):
        return grade, True
    if _known(ctx) and (_NAR_CLASS.fullmatch(ctx) or
                        _JRA_LEVEL.fullmatch(ctx)):
        return ctx, True
    # Never turn a named NAR race into a guessed C1/C2 class.
    if _known(title):
        return title[:14] + ("…" if len(title) > 14 else ""), False
    return None, False


def _comparable(current, past):
    mode = current.get("class_family")
    if mode not in ("JRA", "NAR") or past.get("class_family") != mode:
        return False
    now, previous = current.get("class_level_v2"), past.get("class_level_v2")
    if (isinstance(now, bool) or isinstance(previous, bool)
            or not isinstance(now, (int, float))
            or not isinstance(previous, (int, float))):
        return False
    for field in ("age_restriction_v2", "race_discipline_v2"):
        if not _known(current.get(field)) or current.get(field) != past.get(field):
            return False
    if current.get("race_discipline_v2") not in ("flat", "jump"):
        return False
    if mode == "NAR":
        if not _known(current.get("venue_v2")) or current.get("venue_v2") != past.get("venue_v2"):
            return False
    return True


def evaluate(current, past_runs, *, current_surface=None):
    """One headline, up to two compact facts, and full source explanation.

    Input past_runs MUST be date-gated by candidate_profile.facts(). No
    class-promotion points are produced, even when past class is verifiable.
    """
    current = current if isinstance(current, Mapping) else {}
    past_runs = past_runs if isinstance(past_runs, (list, tuple)) else ()
    upper, same, graded_placed, graded_seen, promoted = [], [], [], [], []
    grade_tags = []
    prior_note = None
    checked = comparable_count = 0
    for run in past_runs:
        if not isinstance(run, Mapping):
            continue
        ctx = run.get("class_context")
        ctx = ctx if isinstance(ctx, Mapping) else {}
        label = str(run.get("label") or "過去走")
        finish = _finish(run.get("finish"))
        class_text, class_identified = _past_class_text(run, ctx)
        finish_label = str(finish) + "着" if finish is not None else "着順未取得"
        evidence = f"{label}{class_text or '級未取得'} {finish_label}"
        checked += 1

        if label == "前走":
            # Named-race fallback is factual but explicitly says that its
            # class could not be identified. Do not infer it from today's C2.
            prior_note = (f"前走 {class_text or '級未取得'} {finish_label}" +
                          ("（級未確認）" if class_text and not class_identified else ""))

        grade = _grade(class_text)
        if grade:
            grade_name = "交流" + grade if grade.startswith("Jpn") else grade
            grade_tag = grade_name + (
                f" {finish}着" if finish is not None and finish <= 5 else " 出走")
            grade_tags.append((0 if finish is not None and finish <= 3
                               else 1 if finish is not None and finish <= 5
                               else 2, grade_tag))
            if finish is not None and finish <= 3:
                same_ground = not (current_surface and run.get("surface") and
                                   str(current_surface).replace("ダート", "ダ") !=
                                   str(run["surface"]).replace("ダート", "ダ"))
                graded_placed.append(evidence + ("（馬場違い）" if not same_ground else ""))
            else:
                graded_seen.append(evidence)

        if _comparable(current, ctx):
            comparable_count += 1
            if finish is not None:
                if ctx["class_level_v2"] > current["class_level_v2"] and finish <= 3:
                    upper.append(evidence)
                elif ctx["class_level_v2"] == current["class_level_v2"] and finish <= 3:
                    same.append(evidence)
            if label == "前走" and current["class_level_v2"] > ctx["class_level_v2"]:
                promoted.append(evidence)

    if upper:
        name, evidence = "格上3着内", upper
    elif graded_placed:
        name, evidence = "重賞好走歴", graded_placed
    elif same:
        name, evidence = "同級3着内", same
    elif promoted:
        name, evidence = "前走から昇級", promoted
    elif graded_seen:
        name, evidence = "重賞出走歴", graded_seen
    else:
        name, evidence = ("特記事項なし" if comparable_count else "比較資料不足"), []

    tags = []
    def add(value):
        if value and value not in tags:
            tags.append(value)

    for _, tag in sorted(grade_tags, key=lambda item: item[0]):
        add(tag)
    if upper:
        add("格上好走")
    if same:
        add("同級好走")
    if promoted:
        add("昇級")
    # If only one notable item exists, let the user see the actual previous
    # class as well. When there is no highlight, show the previous class first.
    if len(tags) < 2:
        add(prior_note)
    if not tags:
        add("前走情報未取得")

    details = list(dict.fromkeys(graded_placed + upper + same + promoted + graded_seen))
    if prior_note:
        details.append(prior_note)
    reason = " / ".join(details[:6]) if details else (
        "前走の取得可能なクラス・レース名・着順がありません")
    return dict(label=name, display=" · ".join(tags[:2]), tags=tags,
                reason=reason + "｜保存された過去3走のみ（加点なし）",
                evidence_count=len(details), inspected_runs=checked,
                scoring_effect=0)
