import copy
from unittest.mock import patch
import pandas as pd
from core.models import PredictionResult
from core.newspaper_v2_engine import attach_newspaper_v2_shadow
from core.newspaper_v2_snapshot import newspaper_v2_snapshot
from core.prediction_snapshot import (race_snapshot_from_result, build_event_snapshot,
                                     keiba_bytes, load_keiba, restore_prediction_result)


def test_new_keiba_freezes_v2_and_old_keiba_stays_without_it():
    r=PredictionResult(race_mode='nar',race_name='一般 C2',race_info={'race_id':'202655100101','race_date':'2026-10-01','racecourse':'佐賀'},
                       overall_table=pd.DataFrame([{'馬番':1,'馬名':'test','ver3_ability_core':42.,'market_ability_score':42.,'ability_rank':1}]))
    old=race_snapshot_from_result(r)
    attach_newspaper_v2_shadow(r)
    new=race_snapshot_from_result(r)
    original=copy.deepcopy(new)
    with patch('core.newspaper_v2_engine.evaluate_shadow',side_effect=AssertionError('must not recalculate')):
        result=restore_prediction_result(load_keiba(keiba_bytes(build_event_snapshot([new])))['races'][0])
        assert newspaper_v2_snapshot(result)==newspaper_v2_snapshot(r)
        assert newspaper_v2_snapshot(restore_prediction_result(old))=={}
    assert new==original
