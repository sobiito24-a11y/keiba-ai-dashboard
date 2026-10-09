from copy import deepcopy
from unittest.mock import patch
import pytest
from tests.test_prediction_snapshot import result_for
from core.prediction_snapshot import (race_snapshot_from_result,build_event_snapshot,
                                      keiba_bytes,load_keiba,restore_prediction_result,
                                      serialize_prediction_result)
from core.race_insight_snapshot import KEY,resolve


@pytest.mark.parametrize('mode',['jra','nar'])
def test_real_keiba_archive_preserves_prose_across_generator_update(mode):
    result=result_for(mode=mode)
    before=serialize_prediction_result(result)
    race=race_snapshot_from_result(result)
    expected=race['prediction_result']['debug_info'][KEY]
    assert expected==race['mobile_snapshot'][KEY]
    raw=keiba_bytes(build_event_snapshot([race]))
    loaded=load_keiba(raw);unchanged=deepcopy(loaded)
    with patch('core.race_insight.generate',side_effect=AssertionError('updated code')):
        restored=restore_prediction_result(loaded['races'][0])
        assert resolve(restored)[0]==expected['insight']
        again=race_snapshot_from_result(restored)
        assert again['prediction_result']['debug_info'][KEY]==expected
    assert loaded==unchanged
    assert serialize_prediction_result(result)==before
