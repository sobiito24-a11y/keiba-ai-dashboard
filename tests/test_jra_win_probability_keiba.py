import json
from pathlib import Path
import pandas as pd

from core.models import PredictionResult
from core.prediction_snapshot import race_snapshot_from_result, build_event_snapshot, keiba_bytes, load_keiba, restore_prediction_result
from core.jra_win_probability import jra_win_probability_snapshot


def test_old_keiba_compatible_and_new_probability_roundtrip(monkeypatch):
    import app
    f=json.loads((Path(__file__).parent/'fixtures/purchase_hanshin_20260921_r8.json').read_text(encoding='utf-8'))
    result=PredictionResult(race_mode='jra',race_info=dict(f['race_info'],race_id='202609040608'),
                            horse_evaluation=pd.DataFrame(f['rows']),overall_table=pd.DataFrame(f.get('overall', f['rows'])))
    before=app.sorted_display_rows(result)
    race=race_snapshot_from_result(result)
    restored=restore_prediction_result(load_keiba(keiba_bytes(build_event_snapshot([race])))['races'][0])
    assert restored.debug_info['jra_win_probability_calibration']==race['jra_win_probability_calibration']
    assert jra_win_probability_snapshot(restored)==race['jra_win_probability_calibration']
    after=app.sorted_display_rows(restored)
    fields=['jra_top5_rank','jra_top5_score','v1_final_mark','jra_pure_ability_score','jra_position_bonus']
    assert {str(h['number']): {k:h.get(k) for k in fields} for h in after}=={str(h['number']): {k:h.get(k) for k in fields} for h in before}
    race.pop('jra_win_probability_calibration')
    old=restore_prediction_result(race)
    # Missing historical probabilities must stay missing, never be regenerated.
    saved_rows = old.horse_evaluation.copy(deep=True)
    def forbidden_recalculation(*args, **kwargs):
        raise AssertionError("Frozen snapshot must not recalculate formal predictions")
    monkeypatch.setattr("core.nar_race_diagnostics.build_full_field_comparison", forbidden_recalculation)
    assert jra_win_probability_snapshot(old) is None
    pd.testing.assert_frame_equal(old.horse_evaluation, saved_rows)
