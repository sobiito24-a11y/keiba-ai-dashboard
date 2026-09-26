import copy
import json
from pathlib import Path
import pandas as pd
from core.models import PredictionResult
from core.prediction_snapshot import race_snapshot_from_result, build_event_snapshot, keiba_bytes, load_keiba, restore_prediction_result
from core.nar_win_probability import nar_win_probability_snapshot, NAR_WINPROB_FIELDS


def test_real_features_roundtrip_and_frozen_version():
    import app
    f=json.loads((Path(__file__).parent/'fixtures/nar_winprob_20260926_saga1.json').read_text(encoding='utf-8'))
    p=PredictionResult(race_mode='nar',race_info={'race_id':f['race_id'],'venue':'佐賀'},
                       overall_table=pd.DataFrame(f['rows']),horse_evaluation=pd.DataFrame(f['rows']))
    rows=copy.deepcopy(p.overall_table)
    race=race_snapshot_from_result(p)
    q=restore_prediction_result(load_keiba(keiba_bytes(build_event_snapshot([race])))['races'][0])
    assert nar_win_probability_snapshot(q)==race['nar_winprob_calibration']
    pd.testing.assert_frame_equal(q.overall_table[list(rows.columns)],rows,check_dtype=False)
    p1=app.prediction_detail_records(p);p2=app.prediction_detail_records(q)
    assert p1==p2
    # A future calibration must never replace saved probability or version.
    cal=race['nar_winprob_calibration']
    cal['model_version']='historic_test'
    for h in cal['horses']:
        h['nar_winprob_model_version']='historic_test'
        h['nar_win_probability']=1/len(cal['horses'])
    q=restore_prediction_result(race)
    assert race_snapshot_from_result(q)['nar_winprob_calibration']==cal
    assert all(h['AI推定勝率（参考）']=='11.1%' for h in app.prediction_detail_records(q))
