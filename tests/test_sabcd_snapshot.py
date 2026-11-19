from copy import deepcopy
from unittest.mock import patch
import pytest
from core.models import PredictionResult
from core.sabcd_snapshot import KEY, freeze, apply_saved, restore


def result():
    return PredictionResult(race_mode='nar', created_at='2026-11-20T08:00:00',
        race_info=dict(race_id='202650112001', race_date='2026-11-20', race_data='10:00発走'))


def view():
    return [dict(no='1', name='テスト', mode='nar', ability_rank=1,
        profile=dict(class_shift='判定不可', runs=[dict(date='2026-11-01', finish=2)]),
        unified_sabcd=dict(grade='A', rank=1), research_sabcd_weight_class=dict(score=.6))]


def test_capture_time_not_prediction_time_and_detached_inputs():
    r=result();v=view();before=deepcopy(v)
    a=freeze(r,v,now='2026-11-20T09:00:00')
    assert a['status']=='pre_race' and a['captured_at'].startswith('2026-11-20T09:00')
    assert a['identity']['prediction_created_at']==r.created_at
    assert freeze(r,v,now='2026-11-20T11:00:00')['status']=='post_start'
    assert freeze(r,v,now='2026-11-20T07:00:00')['status']=='time_unverified'
    r.race_info.pop('race_data')
    assert freeze(r,v,now='2026-11-20T09:00:00')['status']=='time_unverified'
    assert v==before and KEY not in r.debug_info
    a['horses'][0]['inputs']['profile']['runs'][0]['finish']=9
    assert v==before


def test_replay_preserves_actual_display_against_changed_model():
    r=result();v=view();apply_saved(r,v,now='2026-11-20T09:00:00')
    capture=deepcopy(r.debug_info[KEY]);r2=result();restore(r2,{KEY:capture})
    changed=view();changed[0]['unified_sabcd']['grade']='D'
    with patch('core.sabcd_snapshot._view',side_effect=AssertionError('must not recompute')):
        assert freeze(r2)==capture
        assert apply_saved(r2,changed)[0]['unified_sabcd']['grade']=='A'
    changed[0]['unified_sabcd']['grade']='C'
    assert r2.debug_info[KEY]==capture


def test_old_archive_is_not_backfilled_and_field_mismatch_is_rejected():
    r=result();restore(r,{})
    assert freeze(r,view()) is None
    assert apply_saved(r,view())[0]['sabcd_origin']=='historical_recalculation'
    fresh=result();apply_saved(fresh,view(),now='2026-11-20T09:00:00')
    wrong=view();wrong[0]['name']='別馬'
    with pytest.raises(ValueError):apply_saved(fresh,wrong)
    duplicated=view()*2
    with pytest.raises(ValueError):freeze(result(),duplicated,now='2026-11-20T09:00:00')


def test_outcomes_and_odds_are_not_evidence():
    r=result();a=freeze(r,view(),now='2026-11-20T09:00:00')
    v=view();v[0].update(actual_finish=1,actual_corner=1,odds=1.1,payout=99999)
    b=freeze(r,v,now='2026-11-20T09:00:00')
    assert a['input_sha256']==b['input_sha256']
    v[0]['profile']['class_shift']='昇級'
    assert freeze(r,v,now='2026-11-20T09:00:00')['input_sha256']!=a['input_sha256']


def test_real_export_restore_roundtrip():
    from core.prediction_snapshot import race_snapshot_from_result, build_event_snapshot, keiba_bytes, load_keiba, restore_prediction_result
    from tests.test_prediction_snapshot import result_for
    r=result_for(mode='nar',venue='園田');r.created_at='2026-11-20T08:00:00'
    # Capture an exact displayed field, then ensure both export copies and restore agree.
    from core.sabcd_snapshot import _view
    v=_view(r);apply_saved(r,v,now='2026-11-20T09:00:00')
    snap=race_snapshot_from_result(r)
    loaded=load_keiba(keiba_bytes(build_event_snapshot([snap])))['races'][0]
    assert loaded[KEY]==loaded['mobile_snapshot'][KEY]==loaded['prediction_result']['debug_info'][KEY]
    restored=restore_prediction_result(loaded)
    assert freeze(restored)==loaded[KEY]
    legacy=deepcopy(loaded);legacy.pop(KEY);legacy['mobile_snapshot'].pop(KEY);legacy['prediction_result']['debug_info'].pop(KEY)
    assert freeze(restore_prediction_result(legacy)) is None


def test_missing_numeric_inputs_hash_the_serialized_evidence():
    import hashlib,json
    v=view();v[0]["weight_delta"]=float("nan")
    a=freeze(result(),v,now="2026-11-20T09:00:00")
    assert a["horses"][0]["inputs"]["weight_delta"] is None
    body=dict(identity=a["identity"],horses=[{k:h[k] for k in ("no","name","inputs")} for h in a["horses"]])
    encoded=json.dumps(body,sort_keys=True,ensure_ascii=False,allow_nan=False).encode("utf8")
    assert a["input_sha256"]==hashlib.sha256(encoded).hexdigest()
