import unittest,sys,datetime,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import keiba_c1_c2_independent_research as m

BASE={'date':'2026-11-07','venue':'東京','surface':'芝','distance':1600,'current_level':1,
      'training':'B 良好','runs':[{'date':'2026-10-17','venue':'東京','surface':'芝','distance':1600,'race_name':'3歳以上1勝クラス','finish':2}]}

class TestIndexFreeIsolation(unittest.TestCase):
 def test_c1_does_not_accept_ability_inputs(self):
  inp=copy.deepcopy(BASE)
  expected=m.scoring_facts(inp)[0]
  self.assertTrue(isinstance(expected,float))
  for key in ('ability_rank','ability_value','time_index','jra_top5'):
   with self.subTest(field=key):
    inp2=copy.deepcopy(BASE);inp2[key]=999
    with self.assertRaises(AssertionError):m.scoring_facts(inp2)
 def test_future_history_discarded(self):
  inp=copy.deepcopy(BASE)
  a=m.scoring_facts(inp)[0]
  inp['runs'].append({'date':'2026-11-08','surface':'芝','distance':1600,'race_name':'G1','finish':1})
  self.assertEqual(a,m.scoring_facts(inp)[0])
 def test_h2h_never_reads_current_finish(self):
  row={'date':'2026-11-07','horse_name':'馬A','runs':[{'date':'2026-10-10','venue':'東京','surface':'芝','distance':1600,'race_name':'A','finish':2}]}
  key=m.event_key(row['runs'][0]);g={key:{'馬A':2,'馬B':6}};q={'馬B':1.0}
  a=m.h2h_feature(row,g,q)
  row['finish']=1;row['official_rank']=1;row['pure_rank']=1
  self.assertEqual(a,m.h2h_feature(row,g,q))
 def test_ambiguous_history_disallowed(self):
  t=datetime.date(2026,11,7)
  r={'date':'2026-11-07','horse_name':'馬A','runs':[{'date':'2026-10-10','venue':'東京','surface':'芝','distance':1600,'race_name':'1勝クラス','finish':2}]}
  q={'date':'2026-11-07','horse_name':'馬B','runs':[{'date':'2026-10-10','venue':'東京','surface':'芝','distance':1600,'race_name':'1勝クラス','finish':3}]}
  profiles={'馬A':r,'馬B':q}
  key=m.event_key(r['runs'][0]);normal,_,_=m.opponent_graph(t,profiles)
  excluded,_,_=m.opponent_graph(t,profiles,ambiguous={key})
  self.assertIn(key,normal)
  self.assertNotIn(key,excluded)
 def test_exact_race_id_required(self):
  t=datetime.date(2026,11,7)
  r={'date':'2026-11-07','horse_name':'馬A','runs':[{'date':'2026-10-10','venue':'東京','surface':'芝','distance':1600,'race_name':'1勝クラス','finish':2,'race_id':'202605050901'}]}
  q={'date':'2026-11-07','horse_name':'馬B','runs':[{'date':'2026-10-10','venue':'東京','surface':'芝','distance':1600,'race_name':'1勝クラス','finish':3,'race_id':'202605050902'}]}
  graph,_,_=m.opponent_graph(t,{'馬A':r,'馬B':q},exact=True)
  self.assertEqual(graph,{})

if __name__=='__main__':unittest.main()