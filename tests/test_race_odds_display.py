import json
from copy import deepcopy
import pytest
from core import race_odds as o
from tests.test_race_odds import identity,quote

def test_reimport_popularity_partial_no_old_values():
 q=quote(n=3);q['popularity']={'1':2,'2':1};v=o.validate(q,identity(n=3))
 rows=[dict(no=str(i),score='80',rank=str(i),mark='◎',sort_values={}) for i in range(1,4)]
 before=deepcopy(rows);out=o.overlay(rows,v,'取込')
 assert rows==before and out[0]['popularity']==2 and out[2]['popularity'] is None
 q['prices']=[dict(kind='win',horses=[2],low=8.6,high=8.6)];q['popularity']={'2':3}
 new=o.validate(q,identity(n=3));out2=o.overlay(out,new,'再取込')
 assert out2[0]['odds']=='—' and out2[0]['popularity'] is None
 assert out2[1]['odds']=='8.6' and out2[1]['sort_values']['popularity']==3
 assert all(h['score']=='80' and h['mark']=='◎' for h in out2)
 assert new['observation_id']!=v['observation_id']

@pytest.mark.parametrize('p',[{'4':1},{'1':0},{'1':1.5},{'1':True}])
def test_invalid_popularity_rejected(p):
 q=quote(n=3);q['popularity']=p
 with pytest.raises(ValueError):o.validate(q,identity(n=3))

def test_explicit_html_popularity_only():
 html='''<link rel="canonical" href="https://race.netkeiba.com/odds/index.html?race_id=202608040511"><table><tr><th>馬番</th><th>馬名</th><th>単勝</th><th>人気</th></tr><tr><td>2</td><td>馬2</td><td>8.6</td><td>3</td></tr><tr><td>1</td><td>馬1</td><td>2.1</td><td>—</td></tr></table>'''
 q=o.import_files([('odds.html',html.encode())],identity(n=3))[0]
 assert q['popularity']=={'2':3}
 out=o.overlay([dict(no='1'),dict(no='2')],q,'HTML')
 assert out[0]['popularity'] is None and out[1]['popularity']==3


def test_screenshot_explicit_popularity_preserved():
 from core import race_odds_screenshot as s
 from tests.test_race_odds_screenshot import identity as sid,rows as srows
 r=srows();r[0]['人気']='2'
 draft=dict(imported_at='2026-10-18T14:35:00+09:00',version='fixture',sources=[],rows=r)
 q=s.confirmed_quote(r,sid(),draft,confirmed=True)
 assert q['popularity']=={str(r[0]['馬番']):2}


def test_place_overlay_clears_previous_batch_and_does_not_infer_from_win():
 from core.race_explorer_columns import records
 ident=identity(n=3)
 first=quote(n=3)
 # This fixture already contains a place quote for horse 1; replace it,
 # never add a conflicting duplicate combination.
 first["prices"]=[p for p in first["prices"]
                 if not (p["kind"]=="place" and p["horses"]==[1])]
 first["prices"].append(dict(kind="place",horses=[1],low=1.2,high=1.7))
 first=o.validate(first, ident)
 view=[dict(no=str(i),score="80",rank=str(i),mark="◎",sort_values={}) for i in range(1,4)]
 full=o.overlay(view,first,"過去単複")
 assert records(full)["1"]["place_odds"]==1.2
 assert records(full)["1"]["place_odds_high"]==1.7
 win_only=quote(n=3)
 win_only["prices"]=[p for p in win_only["prices"] if p["kind"]=="win"]
 win_only=o.validate(win_only,ident)
 partial=o.overlay(full,win_only,"単勝のみ")
 assert partial[0]["place_odds"]=="—"
 assert records(partial)["1"]["place_odds"] is None
 assert partial[0]["sort_values"]["place_odds_low"] is None
 assert all(a["score"]==b["score"] and a["mark"]==b["mark"] for a,b in zip(view,partial))
