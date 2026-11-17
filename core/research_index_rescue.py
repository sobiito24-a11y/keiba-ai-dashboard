"""Display-only C floor for overlooked course/distance specialists.

When a unified research grade is D and independent pre-start evidence warrants
review, show C (not A/B/S). Frozen model scores, unified order, formal Top5,
marks, betting selections and archives are not changed.
The course/distance indices have no verified source-run provenance, so
coincident numerical values are never treated as independent evidence.
"""
from __future__ import annotations

from datetime import date
from math import isfinite
from collections.abc import Mapping
import re

VERSION = "index-suitability-review-20261117-v2-c-floor"


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        n = float(str(value).strip().replace('m', ''))
        return n if isfinite(n) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _day(raw):
    try:
        return date.fromisoformat(str(raw or '')[:10].replace('/', '-'))
    except (ValueError, TypeError):
        return None


def _past3(horse):
    """Deduplicate only dated pre-start evidence; never use current results."""
    profile = horse.get('profile') or {}
    context = horse.get('race_context') or {}
    today = _day(context.get('race_date') or context.get('date'))
    if today is None:
        return []
    seen = set()
    valid = []
    for raw in profile.get('runs', ()) or ():
        if not isinstance(raw, Mapping):
            continue
        when = _day(raw.get('date'))
        if when is None or when >= today:
            continue
        venue = str(raw.get('venue') or '').strip()
        surface = str(raw.get('surface') or '').replace('ダート', 'ダ')
        distance = _number(raw.get('distance'))
        race_id = str(raw.get('race_id') or '')
        key = ('id', race_id) if re.fullmatch(r'20\d{10}', race_id) else (when, venue, surface, distance)
        if key in seen:
            continue
        seen.add(key)
        m = re.fullmatch(r'\s*(\d+)(?:着)?\s*', str(raw.get('finish') or ''))
        finish = int(m.group(1)) if m else None
        valid.append(dict(day=when, race_id=race_id, venue=venue, surface=surface,
                          distance=distance, finish=finish,
                          index=_number(raw.get('time_index'))))
    return sorted(valid, key=lambda run: run['day'], reverse=True)[:3]


def _index_rank(horse, name):
    cell = horse.get(name) or {}
    r = _number(cell.get('rank')) if isinstance(cell, Mapping) else None
    return int(r) if r is not None and r >= 1 and r.is_integer() else None


def _grade(horse):
    unified = horse.get('unified_sabcd') or {}
    return unified.get('grade') if isinstance(unified, Mapping) else None


def _max_recent_index(horse):
    values = [run['index'] for run in _past3(horse) if run['index'] is not None]
    return max(values) if values else None


def recent_index_ranks(view):
    """Full-race recent-high rankings; insufficient field coverage = unknown."""
    values = {str(h.get('no')): _max_recent_index(h) for h in view or ()}
    valid = [n for n in values.values() if n is not None]
    if len(valid) < 5:
        return {key: None for key in values}
    return {key: (1 + sum(other > value for other in valid) if value is not None else None)
            for key, value in values.items()}


def assess(horse, *, recent_high_rank=None):
    result = dict(label=None, reason=None, version=VERSION, research_only=True,
                  ranked_index_signal=0, historical_success_starts=0,
                  class_status='未確認', recent_decline=False)
    if not isinstance(horse, Mapping) or horse.get('mode') not in ('jra', 'nar'):
        return result
    level = _grade(horse)
    if level not in ('C', 'D'):
        return result
    course = _index_rank(horse, 'course')
    distance = _index_rank(horse, 'distance')
    if not ((course is not None and course <= 3) or (distance is not None and distance <= 3)):
        return result
    runs = _past3(horse)
    wins = [run for run in runs if run['finish'] == 1]
    good_high = recent_high_rank is not None and 1 <= recent_high_rank <= 3
    ctx = horse.get('race_context') or {}
    venue = str(ctx.get('venue') or ctx.get('racecourse') or '').strip()
    surface = str(ctx.get('surface') or ctx.get('芝ダート') or '').replace('ダート', 'ダ')
    length = _number(ctx.get('distance'))
    matches = [run for run in runs if run['finish'] is not None and run['finish'] <= 3
               and run['venue'] == venue and run['surface'] == surface
               and run['distance'] is not None and length is not None
               and abs(run['distance'] - length) <= 200]
    if not wins and not (good_high and matches):
        return result
    status = str((horse.get('profile') or {}).get('class_shift') or '')
    comparable = status in ('同級', '昇級', '降級', 'クラス昇級', 'クラス降級')
    caution = str(horse.get('caution') or '')
    form = str((horse.get('profile') or {}).get('state') or '')
    decline = '下降' in caution or '下降' in form or form == '注意'
    facts = ' / '.join(f'{name}{rank}位' for name, rank in [('コース', course), ('距離', distance)] if rank is not None and rank <= 3)
    details = (f'近3走{len(wins)}勝' if wins else f'近3走最高指数{recent_high_rank}位')
    if matches:
        details += f'、同競馬場・同馬場・距離±200mの3着以内{len(matches)}走'
    else:
        details += '、同場近似距離の好走は未確認'
    reason = (f'研究統合{level}でも適性再点検：{facts}。{details}。'
              'コース・距離は同じ過去走に由来する可能性があるため独立加点しません。'
              + ('クラス比較不可（この点検では不利加点なし）。' if not comparable else f'クラス{status}。')
              + ('近走下降は警戒材料として維持。' if decline else '')
              + '統合Dのみ根拠確認後に表示Cへ引上げ。元モデル値・順位・正式印・購入候補は変更しません。')
    return dict(result, label='適性再点検', reason=reason, ranked_index_signal=1,
                historical_success_starts=len(matches),
                class_status=status if comparable else '比較不可', recent_decline=decline)


def _apply_display_c_floor(horse):
    """Only change the transient unified letter; NEVER recompute its score/order."""
    review = horse.get('research_index_rescue') or {}
    unified = horse.get('unified_sabcd') or {}
    if not isinstance(unified, Mapping) or unified.get('grade') != 'D':
        return False
    if review.get('label') != '適性再点検':
        return False
    original = dict(unified)
    original['grade'] = 'C'
    original['grade_before_suitability'] = 'D'
    original['suitability_c_floor'] = True
    original['status_before_suitability'] = unified.get('status')
    original['status'] = 'suitability_c_floor'
    original['reason'] = (
        str(unified.get('reason') or '')
        + '【適性補正】発走前の適性指数上位＋近走好走根拠により'
          'Dから表示上Cに引上げ。モデル値・統合順位は不変。'
          '原モデルの評価はDで、Cは校正済み好走確率を意味しません。'
    )
    horse['unified_sabcd'] = original
    return True


def assign_to_view(view):
    ranks = recent_index_ranks(view)
    for horse in view or ():
        horse['research_index_rescue'] = assess(horse, recent_high_rank=ranks.get(str(horse.get('no'))))
        _apply_display_c_floor(horse)
    return view
