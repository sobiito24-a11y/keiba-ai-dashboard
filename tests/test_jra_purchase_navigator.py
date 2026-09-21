import copy
import json

import pytest

from core.jra_purchase_navigator import (
    build_jra_purchase_navigation, calculate_top5_swap_count,
    classify_jra_horse_role, classify_jra_race_structure,
)
from core.jra_purchase_navigation_ui import jra_purchase_navigation_html
from core.nar_race_diagnostics import build_full_field_comparison
from core.prediction_snapshot import (
    build_event_snapshot, keiba_bytes, load_keiba, race_snapshot_from_result,
    restore_prediction_result, serialize_prediction_result,
)
from tests.test_prediction_snapshot import result_for


def rows():
    # Pure top5 = 1,2,3,4,5; current top5 = 1,2,3,4,6; one replacement.
    order = [1, 2, 3, 4, 6, 5, 7]
    ability = {1: 100, 2: 97, 3: 96, 4: 95, 5: 94, 6: 93, 7: 92}
    return [dict(number=str(n), name=f"馬{n}", _v1_ability_rank=n,
                 jra_pure_ability_score=ability[n], jra_top5_rank=rank,
                 jra_top5_score=106 if rank == 1 else 102-rank,
                 v1_final_mark={1:'◎',2:'○',3:'▲',4:'△',5:'☆'}.get(rank,''))
            for rank,n in enumerate(order,1)]


def build(source=None, info=None, mode='jra'):
    return build_jra_purchase_navigation(rows() if source is None else source,
        race_mode=mode, race_info={'surface':'芝'} if info is None else info)


@pytest.mark.parametrize('ability,current,expected', [(5,5,'CORE'),(1,6,'ABILITY'),(6,1,'SETUP'),(6,6,'OTHER'),(None,1,None),(1,0,None)])
def test_roles(ability,current,expected):
    assert classify_jra_horse_role(ability,current)==expected


def test_swap_count_counts_one_direction_only():
    assert calculate_top5_swap_count({'1','2','3','4','5'},{'1','2','3','6','7'})==2


def test_strong_boundaries_groups_and_partners():
    nav=build()
    assert (nav['status'],nav['top5_score_gap'],nav['ability_gap'],nav['swap_count'])==('強軸',6,3,1)
    assert nav['axis']['number']=='1'
    assert {h['number'] for h in nav['partners']}=={'2','3','4','5','6'}
    assert {h['number'] for h in nav['groups']['ABILITY']}=={'5'}
    assert {h['number'] for h in nav['groups']['SETUP']}=={'6'}
    assert nav['groups']['OTHER'][0]['number']=='7'


@pytest.mark.parametrize('score,pure,swaps,match,status', [
    (6,3,0,True,'強軸'),(6,3,1,True,'強軸'),
    (5.9999,3,1,True,'上位混戦'),(6,2.9999,1,True,'上位混戦'),
    (6,3,2,True,'評価分裂'),(10,10,0,False,'評価分裂'),
    (1,1,1,True,'上位混戦'),(None,3,0,True,'判定材料不足'),
])
def test_structure_priority_and_boundaries(score,pure,swaps,match,status):
    assert classify_jra_race_structure(leaders_match=match,top5_score_gap=score,ability_gap=pure,swap_count=swaps)==status


def test_decimal_subtraction_does_not_reject_exact_threshold():
    rr=rows()
    rr[0]['jra_top5_score']=9.2
    for h in rr[1:]: h['jra_top5_score']=5.2-h['jra_top5_rank']
    assert build(rr)['status']=='強軸'
    assert build(rr)['top5_score_gap']==6.0


def test_leader_mismatch_and_two_swaps():
    rr=rows();rr[0]['number'],rr[1]['number']=rr[1]['number'],rr[0]['number']
    for h in rr[:2]:
        h['_v1_ability_rank']=int(h['number'])
        h['jra_pure_ability_score']=100 if h['number']=='1' else 97
    nav=build(rr);assert nav['status']=='評価分裂' and nav['axis'] is None
    rr=rows();rr[3]['jra_top5_rank'],rr[6]['jra_top5_rank']=7,4
    rr[3]['jra_top5_score'],rr[6]['jra_top5_score']=95,98
    assert build(rr)['swap_count']==2 and build(rr)['status']=='評価分裂'


@pytest.mark.parametrize('field', ['_v1_ability_rank','jra_pure_ability_score','jra_top5_rank','jra_top5_score'])
@pytest.mark.parametrize('bad', [None,'—',float('nan'),float('inf')])
def test_missing_any_horse_not_coerced_to_zero(field,bad):
    rr=rows();rr[-1][field]=bad
    assert build(rr)['status']=='判定材料不足'


def test_invalid_or_incomplete_field():
    assert build([])['status']=='判定材料不足'
    assert build(rows()[:1])['status']=='判定材料不足'
    rr=rows();rr[-1]['number']='1';assert build(rr)['status']=='判定材料不足'
    rr=rows();rr[-1]['jra_top5_rank']=1;assert build(rr)['status']=='判定材料不足'
    rr=rows();rr[0]['jra_top5_score']=0;assert build(rr)['status']=='判定材料不足'
    rr=rows();rr[0]['_v1_ability_rank']=0;assert build(rr)['status']=='判定材料不足'


@pytest.mark.parametrize('info',[{'surface':'障'},{'surface':'芝','race_name':'障害未勝利'},{'course_type':'steeplechase'}])
def test_jump_excluded(info):
    nav=build(info=info)
    assert nav['status']=='対象外' and nav['axis'] is None and not nav['horses']
    assert '障害レース：買い方ナビ対象外' in jra_purchase_navigation_html(nav)


def test_unknown_race_type_is_not_assumed_flat():
    assert build(info={})['status']=='判定材料不足'


def test_odds_popularity_and_result_fields_ignored_and_input_unchanged():
    rr=rows();original=copy.deepcopy(rr)
    expected=build(rr)
    assert rr==original
    for h in rr:
        h.update(odds=999,actual_odds=.1,popularity=1,market_rank=1,当日オッズ=1,
                 単勝オッズ=.1,人気=1,市場順位=1,finish=1,payout=99999)
    assert build(rr)==expected
    assert not any(k in json.dumps(expected) for k in ('odds','popularity','market_rank','payout','finish'))


def test_saved_snapshot_compatibility_and_existing_jra_unchanged():
    prediction=result_for()
    original=serialize_prediction_result(prediction)
    event=build_event_snapshot([race_snapshot_from_result(prediction)])
    loaded=load_keiba(keiba_bytes(event));frozen=copy.deepcopy(loaded)
    restored=restore_prediction_result(loaded['races'][0])
    source=restored.overall_table.to_dict('records')
    before=build_full_field_comparison(source,race_mode='jra',race_info=restored.race_info)
    before_copy=copy.deepcopy(before)
    nav=build_jra_purchase_navigation(before['rows'],race_mode='jra',race_info=restored.race_info)
    assert nav['show']
    assert before==before_copy
    assert build_full_field_comparison(source,race_mode='jra',race_info=restored.race_info)==before
    assert loaded==frozen
    assert serialize_prediction_result(prediction)==original


def test_nar_untouched_and_no_ui_output():
    prediction=result_for(mode='nar')
    source=prediction.overall_table.to_dict('records')
    before=build_full_field_comparison(source,race_mode='nar',race_info=prediction.race_info)
    nav=build_jra_purchase_navigation(before['rows'],race_mode='nar',race_info=prediction.race_info)
    assert nav=={'show':False} and jra_purchase_navigation_html(nav)==''
    assert build_full_field_comparison(source,race_mode='nar',race_info=prediction.race_info)==before


def test_html_roles_visible_safely_and_no_purchase_tickets():
    rr=rows();rr[0]['name']='<script>alert(1)</script>'
    html=jra_purchase_navigation_html(build(rr))
    assert '<script>' not in html and '&lt;script&gt;' in html
    for label in ('JRA 買い方ナビ','CORE','ABILITY','SETUP','軸候補','相手候補','◎は現行Top5','flex-wrap:wrap'):
        assert label in html
    assert 'OTHER' not in html and 'WATCH' not in html
    assert '円' not in html


def test_crowded_and_split_do_not_offer_single_axis():
    rr=rows();rr[0]['jra_top5_score']=105
    nav=build(rr);html=jra_purchase_navigation_html(nav)
    assert nav['status']=='上位混戦' and nav['axis'] is None
    assert 'ABILITY' in html and 'BOXまたは複数軸' in html
    nav['status']='評価分裂'  # Separate renderer test uses the actual split guide.
    from core.jra_purchase_navigator import GUIDES
    nav['guides']=GUIDES['評価分裂']
    assert '見送り優先' in jra_purchase_navigation_html(nav)


def test_streamlit_jra_section_and_nar_absence():
    from streamlit.testing.v1 import AppTest
    # Exercise the actual app entry point; the comparison is already calculated.
    script='''
import app
from core.models import PredictionResult
from tests.test_jra_purchase_navigator import rows
from unittest.mock import patch
with patch.object(app, 'jra_comparison_from_result', return_value={'rows':rows(),'race_mode':'jra'}), patch.object(app, 'jra_top5_conclusion_html', return_value='<p>Existing JRA prediction</p>'):
    app.render_jra_top5_result_summary(PredictionResult(race_mode='jra',race_info={'surface':'芝'}))
'''
    at=AppTest.from_string(script,default_timeout=20).run()
    assert not at.exception
    assert 'Existing JRA prediction' in at.markdown[0].value
    assert 'JRA 買い方ナビ' in at.markdown[1].value
    nar=AppTest.from_string(script.replace("race_mode='jra',race_info", "race_mode='nar',race_info"),default_timeout=20).run()
    assert not nar.exception
    assert all('JRA 買い方ナビ' not in m.value for m in nar.markdown)


def test_buy_candidates_canonical_marks_dedup_attention_and_odds():
    from core.jra_purchase_navigator import build_jra_buy_candidates
    rr=rows()
    for r in rr:
        r['v1_final_mark']={1:'✔︎',2:'✔',3:'▲',4:'△',5:'✔︎',6:'✓',7:'✓'}.get(r['number'] if isinstance(r['number'],int) else int(r['number']))
        r['odds']=2.0
    original=copy.deepcopy(rr)
    nav=build(rr)
    assert [(h['number'],h['role']) for h in nav['buy_candidates']]==[('1','中心'),('2','本線'),('3','本線'),('5','狙い')]
    assert [h['number'] for h in nav['hole_attention']]==['6','7']
    assert rr==original
    assert build_jra_buy_candidates(rr+rr)==build_jra_buy_candidates(rr)
    for r in rr:r.update(odds=999,popularity=99,market_rank=88,finish=1)
    assert build(rr)==nav


def test_warning_flag_without_visible_mark_is_not_attention():
    rr=rows()
    for r in rr:
        r['v1_mark']='✔︎'
        r['jra_warning_candidate']=int(r['number'])==7
    nav=build(rr)
    assert len(nav['buy_candidates'])==3
    assert nav['hole_attention']==[]


@pytest.mark.parametrize('status,label',[('強軸','軸あり'),('上位混戦','複数候補'),('評価分裂','見送り寄り')])
def test_compact_main_and_details_preserved(status,label):
    from bs4 import BeautifulSoup
    nav=build(rows());nav['status']=status
    soup=BeautifulSoup(jra_purchase_navigation_html(nav),'html.parser')
    details=soup.find('details')
    assert details is not None and not details.has_attr('open')
    assert details.find('summary').get_text()=='詳細を見る'
    for text in ('CORE','ABILITY','SETUP','Top5 2位差','純能力2位差','Top5入替','運用ガイド'):
        assert text in details.get_text()
    details.decompose();main=soup.get_text()
    assert label in main
    title = '今回の判断' if status == '評価分裂' else '今回の買い候補'
    for text in (title,'本線','狙い','穴注意','買い方'):assert text in main
    assert ('中心' in main) == (status == '強軸')
    assert ('押さえ' in main) == (status == '上位混戦')
    assert ('本線参考' in main) == (status == '評価分裂')
    for text in ('CORE','ABILITY','SETUP','Top5 2位差','運用ガイド',status):assert text not in main


def test_saved_snapshot_candidates_roundtrip():
    prediction=result_for()
    prediction.horse_evaluation=__import__('pandas').DataFrame(rows())
    prediction.horse_evaluation.loc[4,'v1_final_mark']='✔︎'
    original=serialize_prediction_result(prediction)
    event=build_event_snapshot([race_snapshot_from_result(prediction)])
    restored=restore_prediction_result(load_keiba(keiba_bytes(event))['races'][0])
    from core.jra_purchase_navigator import build_jra_buy_candidates
    assert build_jra_buy_candidates(restored.horse_evaluation.to_dict('records'))==build_jra_buy_candidates(prediction.horse_evaluation.to_dict('records'))
    assert serialize_prediction_result(prediction)==original


@pytest.mark.parametrize('status', ['強軸','上位混戦','評価分裂'])
def test_final_structure_specific_candidate_ranges(status):
    from core.jra_purchase_navigator import build_jra_buy_candidates
    rr=rows()
    for r in rr:
        r['v1_final_mark']='✔︎' if r['jra_top5_rank'] in (1,4,6) else '✓' if r['jra_top5_rank']==7 else ''
    frozen=copy.deepcopy(rr)
    nav=build_jra_buy_candidates(rr+rr,status)
    chosen=nav['reference_candidates'] if status=='評価分裂' else nav['buy_candidates']
    expected={
        '強軸':[('1','中心'),('2','本線'),('3','本線'),('4','狙い'),('5','狙い')],
        '上位混戦':[('1','本線'),('2','本線'),('3','本線'),('4','押さえ'),('6','押さえ'),('5','狙い')],
        '評価分裂':[('1','本線参考'),('2','本線参考'),('3','本線参考'),('4','狙い'),('5','狙い')],
    }
    assert [(h['number'],h['role']) for h in chosen]==expected[status]
    assert [h['number'] for h in nav['hole_attention']]==['7']
    if status=='評価分裂':assert nav['buy_candidates']==[]
    assert rr==frozen
    for r in rr:r.update(odds=999,popularity=999,finish=1)
    assert build_jra_buy_candidates(rr,status)==nav


@pytest.mark.parametrize('days,warning',[(89,False),(90,True),(365,True),(None,False),(-1,False),('不明',False),(float('nan'),False),(True,False)])
def test_layoff_boundary_display_only(days,warning):
    rr=rows();rr[0]['_days_since_last']=days
    frozen=copy.deepcopy(rr)
    nav=build(rr)
    assert bool(nav['layoff_warnings'])==warning
    if warning:
        assert nav['layoff_warnings'][0]['days']==days
        html=jra_purchase_navigation_html(nav)
        assert f'長期休養明け：{days}日' in html
        assert '軸評価は高いが、休養明けのため固定は慎重' in html
    assert json.dumps(rr,sort_keys=True)==json.dumps(frozen,sort_keys=True)
    rr[0].pop('_days_since_last');base=build(rr)
    assert {k:v for k,v in nav.items() if k!='layoff_warnings'}=={k:v for k,v in base.items() if k!='layoff_warnings'}


def test_saved_previous_date_join_and_no_guessed_dates():
    rr=rows()
    saved=[{'馬番':'1','_past_runs':[{'label':'前走','race_date':'2025-09-20'}], 'jra_top5_rank':99,'v1_final_mark':'✓'}]
    frozen=copy.deepcopy(saved)
    nav=build_jra_purchase_navigation(rr,race_mode='jra',race_info={'surface':'芝','race_date':'2026-09-20'},saved_rows=saved)
    assert nav['layoff_warnings']==[{'number':'1','name':'馬1','days':365,'is_top1':True}]
    assert nav['buy_groups']['中心'][0]['number']=='1'
    assert saved==frozen
    for past in [{'label':'2走前','race_date':'2025-09-20'}, {'label':'前走','race_date':'09/20'}, {'label':'前走','race_date':'2027-09-20'}]:
        saved[0]['_past_runs']=[past]
        assert not build_jra_purchase_navigation(rr,race_mode='jra',race_info={'surface':'芝','race_date':'2026-09-20'},saved_rows=saved)['layoff_warnings']


def test_layoff_snapshot_roundtrip_and_nar_jump_exclusion():
    from core.jra_purchase_navigator import build_jra_layoff_warnings
    p=result_for();p.overall_table=__import__('pandas').DataFrame([{'馬番':'1','_days_since_last':365}])
    original=serialize_prediction_result(p)
    restored=restore_prediction_result(load_keiba(keiba_bytes(build_event_snapshot([race_snapshot_from_result(p)])))['races'][0])
    assert build_jra_layoff_warnings(rows(),{},restored.overall_table.to_dict('records'))[0]['days']==365
    assert serialize_prediction_result(p)==original
    assert build_jra_purchase_navigation(rows(),race_mode='nar',race_info={'surface':'芝'},saved_rows=p.overall_table.to_dict('records'))=={'show':False}
    jump=build_jra_purchase_navigation(rows(),race_mode='jra',race_info={'surface':'障害'},saved_rows=p.overall_table.to_dict('records'))
    assert jump['status']=='対象外' and 'layoff_warnings' not in jump


def test_hanshin_20260921_r8_actual_display_mark_regression():
    from pathlib import Path
    from core.jra_display_mark import jra_display_mark_from_row
    fixture=json.loads((Path(__file__).parent/'fixtures/jra_20260921_hanshin8_display_marks.json').read_text(encoding='utf-8'))
    rr=fixture['rows'];frozen=copy.deepcopy(rr)
    nav=build_jra_purchase_navigation(rr,race_mode='jra',race_info=fixture['race_info'])
    assert nav['status']=='上位混戦'
    for role,numbers in [('本線',['4','8','6']),('押さえ',['3','2']),('狙い',['7','12'])]:
        assert [h['number'] for h in nav['buy_groups'][role]]==numbers
    assert [h['number'] for h in nav['hole_attention']]==['10']
    assert len({h['number'] for h in nav['buy_candidates']})==7
    assert {h['number']:jra_display_mark_from_row(h) for h in rr}=={'4':'◎','8':'○','6':'▲','3':'△','2':'△','7':'✔︎','10':'✓','11':'','9':'','1':'','5':'','12':'✔︎'}
    assert rr==frozen
    for r in rr:r.update(odds=999,popularity=99)
    assert build_jra_purchase_navigation(rr,race_mode='jra',race_info=fixture['race_info'])==nav


@pytest.mark.parametrize('row,expected',[
    ({'v1_final_mark':'△','ver3_final_mark':'✔︎','表示印':'✓'},'△'),
    ({'v1_final_mark':'','ver3_final_mark':'✔︎','表示印':'✓'},'✔︎'),
    ({'v1_final_mark':None,'ver3_final_mark':'','表示印':'✓'},'✓'),
    ({'mark_v4':'✔︎','表示印':'✓'},'✔︎'),
    ({'mark_v4':float('nan'),'表示印':'','display_mark':'✓'},''),
    ({'display_mark':'✓'},'✓'),
    ({'印':'','最終印':'✔︎'},'✔︎'),
])
def test_jra_shared_display_precedence(row,expected):
    import app
    from core.jra_display_mark import jra_display_mark_from_row
    assert jra_display_mark_from_row(row)==expected
    assert app.display_mark_from_row(row,'jra')==expected


@pytest.mark.parametrize('status',['強軸','上位混戦','評価分裂'])
def test_display_checks_obey_rank_role_priority(status):
    from core.jra_purchase_navigator import build_jra_buy_candidates
    rr=rows()
    for r in rr:r['v1_final_mark']='✓' if r['jra_top5_rank']==1 else '✔︎'
    nav=build_jra_buy_candidates(rr,status)
    chosen=nav['reference_candidates'] if status=='評価分裂' else nav['buy_candidates']
    assert chosen[0]['role']=={'強軸':'中心','上位混戦':'本線','評価分裂':'本線参考'}[status]
    assert not nav['hole_attention']
    assert len(chosen)==len({h['number'] for h in chosen})


def test_real_snapshot_display_merge_used_by_navigation():
    import app
    from pathlib import Path
    from unittest.mock import patch
    from bs4 import BeautifulSoup
    f=json.loads((Path(__file__).parent/'fixtures/jra_20260921_hanshin8_display_marks.json').read_text(encoding='utf-8'))
    source=copy.deepcopy(f['rows'])
    # The comparison omits legacy display fields; the real table restores them from the saved rows.
    comparison={'rows':[{k:v for k,v in r.items() if k not in ('ver3_final_mark','表示印')} for r in source]}
    p=result_for();p.race_info=f['race_info'];p.horse_evaluation=__import__('pandas').DataFrame(source)
    original=serialize_prediction_result(p)
    merged=app.jra_enriched_display_rows(p,comparison=comparison)
    assert [app.display_mark_from_row(h,'jra') for h in merged]==['◎','○','▲','△','△','✔︎','✓','','','','','✔︎']
    with patch.object(app,'jra_comparison_from_result',return_value=comparison),patch.object(app.st,'markdown') as render:
        app.render_jra_top5_result_summary(p)
    html=render.call_args_list[-1].args[0]
    text=BeautifulSoup(html,'html.parser').get_text()
    assert '狙い：7番 レッドフレーザー / 12番 リリーサンダー' in text
    assert '穴注意：10番 エアフォースワン' in text
    assert serialize_prediction_result(p)==original
