"""Read-only class/graded-race attention signals for the all-runner dashboard.

Never uses odds, outcomes for the upcoming race, points, official marks, or
an unverified NAR nationwide class ladder.  Prior runs are pre-race
snapshots, filtered for dates by candidate_profile.facts().
"""
from __future__ import annotations

import re
from collections.abc import Mapping

_GRADE = re.compile(r"^(?:G[123]|Jpn[123]|重賞)$", re.IGNORECASE)
_FINISH = re.compile(r"^([1-9][0-9]*)(?:着)?$")


def _finish(value):
    if isinstance(value, bool):
        return None
    text = str(value or "").strip()
    matched = _FINISH.fullmatch(text)
    return int(matched[1]) if matched else None


def _known(value):
    return value not in (None, "", "不明", "unknown")


def _comparable(current, past):
    """Require independently identified class, age group, discipline and venue.

    NAR class levels are compared only within the same venue.  JRA flat
    and jump races are separate. Cross-age categories are not treated as
    a common calibrated ability scale.
    """
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
    """Return one factual headline plus a short explanation; no score changes.

    past_runs: [{label, class_context, finish, surface}] in most-recent order.
    Each context must derive from a verified pre-race source.  Incomplete class
    evidence yields a missing signal, never a guessed bonus.
    """
    current = current if isinstance(current, Mapping) else {}
    past_runs = past_runs if isinstance(past_runs, (list, tuple)) else ()
    upper, same, graded_placed, graded_seen, promoted = [], [], [], [], []
    grade_tags = []
    checked = 0
    comparable_count = 0
    for run in past_runs:
        if not isinstance(run, Mapping):
            continue
        ctx = run.get("class_context")
        if not isinstance(ctx, Mapping):
            continue
        label = str(run.get("label") or "過去走")
        finish = _finish(run.get("finish"))
        ctx_label = str(ctx.get("class_label_v2") or "クラス未取得").strip()
        finish_label = str(finish) + "着" if finish is not None else "着順未取得"
        evidence = f"{label}{ctx_label} {finish_label}"
        checked += 1

        # Grade achievement is a historical fact; not a blanket class bonus.
        grade = _GRADE.fullmatch(ctx_label)
        if grade:
            # Factual grade/finish labels survive JRA-versus-NAR differences.
            # A Jpn2 4th is not a proven positive adjustment, but it must not
            # disappear behind a lower numerical time index either.
            grade_name = "交流" + ctx_label if ctx_label.lower().startswith("jpn") else ctx_label
            grade_tag = grade_name + (
                f" {finish}着" if finish is not None and finish <= 5
                else " 出走")
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
        if _comparable(current, ctx) and finish is not None:
            if ctx["class_level_v2"] > current["class_level_v2"] and finish <= 3:
                upper.append(evidence)
            elif ctx["class_level_v2"] == current["class_level_v2"] and finish <= 3:
                same.append(evidence)

        # Only the immediate past race may establish a first-step promotion note.
        # Do not label it 'first-ever' promotion across the horse's whole career.
        if label == "前走" and _comparable(current, ctx) and current["class_level_v2"] > ctx["class_level_v2"]:
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

    # Preserve the legacy headline for compatibility, but show multiple
    # independently verified facts in the compact dashboard.  No weights.
    tags = []
    def add(value):
        if value not in tags:
            tags.append(value)

    for _, grade_tag in sorted(grade_tags, key=lambda item: item[0]):
        add(grade_tag)
    if upper:
        add("格上好走")
    if same:
        add("同級好走")
    if promoted:
        add("昇級")
    if not tags:
        add(name)

    all_evidence = list(dict.fromkeys(
        graded_placed + upper + same + promoted + graded_seen))
    reason = " / ".join(all_evidence[:5]) if all_evidence else (
        "比較可能な過去走に指定の好走材料なし" if comparable_count else
        "今回級と過去走のクラス・年齢条件・主催・競馬場の照合が不足")
    return dict(label=name, display=" · ".join(tags[:2]), tags=tags,
                reason=reason + "｜過去3走の保存根拠（加点なし）",
                evidence_count=len(all_evidence), inspected_runs=checked,
                scoring_effect=0)
