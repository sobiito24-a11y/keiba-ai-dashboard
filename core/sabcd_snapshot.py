"""Persist the displayed integrated grade, with an honest capture time and origin."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re

KEY = 'integrated_sabcd_snapshot'
VERSION = 'integrated-grade-capture-v1'
JST = timezone(timedelta(hours=9))
INPUT_KEYS = ('mode', 'ability_rank', 'corner', 'start_rank', 'research_inputs',
              'weight', 'weight_delta', 'age', 'rank', 'course', 'distance', 'average')
OUTPUT_KEYS = ('unified_sabcd', 'research_sabcd_weight_class', 'research_sabcd',
               'research_index_rescue', 'research_age_suitability', 'research_positioning',
               'research_formal_sabcd_fusion')


def _time(value):
    try:
        t = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return t.replace(tzinfo=JST) if t.tzinfo is None else t.astimezone(JST)
    except (TypeError, ValueError):
        return None


def _identity(result):
    info = result.race_info or {}
    return dict(race_id=str(info.get('race_id') or ''), mode=result.race_mode,
                prediction_created_at=result.created_at)


def saved(result):
    value = (result.debug_info or {}).get(KEY)
    if isinstance(value, dict) and value.get('identity') == _identity(result):
        return deepcopy(value)
    return None


def _view(result):
    # The same adapters as the table; export and rendering subsequently use
    # this saved grade, so no alternative reconstruction is labelled original.
    from .race_insight_snapshot import display_rows
    from .prediction_table_ui import prediction_table_records
    from .game_race_ui import build_view
    from .material_reconsideration import saved_materials
    rows = display_rows(result)
    sources = result.overall_table.to_dict('records') if result.overall_table is not None else []
    materials = saved_materials(result)
    records = prediction_table_records(rows, sources, result.race_info or {}, result.race_mode, materials=materials)
    return build_view(rows, records, sources, result.race_mode, result.race_info, materials)


def freeze(result, view=None, *, now=None):
    existing = saved(result)
    if existing is not None:
        return existing
    if getattr(result, '_sabcd_restored', False) or getattr(result, '_material_snapshot_restored', False):
        return None  # Never backfill a historical original with today's model.
    now = _time(now) if now is not None else datetime.now(JST)
    if now is None:
        raise ValueError('Invalid capture time')
    info = result.race_info or {}
    start = _time(info.get('scheduled_start_time') or info.get('scheduled_post_time'))
    day = str(info.get('race_date') or info.get('date') or '')[:10]
    if start is None and re.fullmatch(r'\d{4}-\d\d-\d\d', day):
        match = re.search(r'(\d{1,2}:\d{2})発走', str(info.get('race_data') or info.get('raw') or ''))
        if match:
            start = _time(day + 'T' + match[1])
    created = _time(result.created_at)
    status = ('pre_race' if created and start and created <= now < start else
              'post_start' if start and now >= start else 'time_unverified')
    horses = []
    for h in view if view is not None else _view(result):
        inputs = {k: deepcopy(h.get(k)) for k in INPUT_KEYS}
        context = h.get('race_context') or {}
        inputs['race_context'] = {k: deepcopy(context.get(k)) for k in
                                  ('race_id', 'race_date', 'date', 'venue', 'distance', 'surface')}
        profile = h.get('profile') or {}
        inputs['profile'] = {k: deepcopy(profile.get(k)) for k in ('runs', 'class_shift', 'state')}
        horses.append(dict(no=str(h['no']), name=h['name'], inputs=inputs,
                           outputs={k: deepcopy(h.get(k)) for k in OUTPUT_KEYS}))
    from .prediction_snapshot import _json_ready
    horses = _json_ready(horses)
    if len({h['no'] for h in horses}) != len(horses):
        raise ValueError('Duplicate horse numbers in integrated grade capture')
    modules = ('sabcd_snapshot', 'game_race_ui', 'candidate_profile', 'research_sabcd', 'research_sabcd_weight_class',
               'unified_sabcd', 'research_index_rescue', 'research_age_suitability')
    code = {m: hashlib.sha256(Path(__file__).with_name(m + '.py').read_bytes()).hexdigest() for m in modules}
    inputs = dict(identity=_identity(result), horses=[dict(no=h['no'], name=h['name'], inputs=h['inputs']) for h in horses])
    body = json.dumps(inputs, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf8')
    return dict(schema_version=1, version=VERSION, identity=_identity(result), captured_at=now.isoformat(),
                scheduled_start=start.isoformat() if start else None, status=status,
                origin='display' if view is not None else 'export_projection',
                input_sha256=hashlib.sha256(body).hexdigest(), code_sha256=code, horses=horses)


def apply_saved(result, view, *, now=None):
    value = freeze(result, view, now=now)
    if value is None:
        for h in view:
            h['sabcd_origin'] = 'historical_recalculation'
        return view
    by = {h['no']: h for h in value['horses']}
    if set(by) != {str(h['no']) for h in view} or any(by[str(h['no'])]['name'] != h['name'] for h in view):
        raise ValueError('Saved integrated grades do not match the displayed field')
    result.debug_info = {**(result.debug_info or {}), KEY: deepcopy(value)}
    for h in view:
        h.update(deepcopy(by[str(h['no'])]['outputs']))
        h['sabcd_origin'] = value['status']
    return view


def restore(result, payload):
    result._sabcd_restored = True
    value = payload.get(KEY) or (payload.get('mobile_snapshot') or {}).get(KEY)
    if isinstance(value, dict):
        result.debug_info = {**(result.debug_info or {}), KEY: deepcopy(value)}
