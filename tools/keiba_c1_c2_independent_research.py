#!/usr/bin/env python3
"""Chronological, index-free C1/C2 exploratory ranking for archived JRA .keiba.

C1 uses only observed prior finishes/classes/surface/distance/course, layoff,
training, and current field facts. C2 adds partial historical head-to-head links
against identifiable peers in the as-of-date corpus, weighted by peer's prior
form and class. Both are deliberately independent of legacy speed/ability indexes.

No web/network, no betting, no model mutation. Exact race outcome and legacy
rank are loaded *after scoring* for evaluation only. This is research, not a
calibrated probability predictor.
"""
from __future__ import annotations
import csv,zipfile,json,collections,math,datetime,re,sys,os,statistics,itertools,hashlib,argparse
from pathlib import Path

HERE=Path(__file__).resolve().parent
SOURCE=HERE/'files'
OUT=HERE
DATES=['20260926','20260927','20261004','20261010','20261011','20261017','20261018','20261024','20261107','20261108']
RESULTS=HERE/'競馬AI_全頭検証242R_前走格斤量成長.csv'
HOLDOUT='2026-11-07'
# Fixed before looking at holdout C1/C2 outcomes. No coefficient tuning on 11/7-8.
C1_COEFF={'previous_finishes_recency_weights':[.53,.30,.17],
          'class_difference_factor':.35,'class_difference_clip':1.8,
          'same_surface_close_distance_threshold_m':200,
          'training_points':{'A':.35,'B':.10,'C':-.20,'D':-.40},
          'layoff_points':{'70_to_179_days':-.45,'180_plus_days':-1.0}}
C2_LAMBDA=2.0

# Only the keys below may enter scores. Do not read labels/odds/indexes in scoring.
BANNED_FEATURES=('ability_rank','ability_value','official_rank','time_index',
                  'index','star','raw_score','market_ability','ai_current','jra_top5')


def number(x):
 if x is None or isinstance(x,bool):return None
 try:
  if isinstance(x,(int,float)):
   z=float(x)
  else:
   m=re.search(r'[-+]?\d+(?:\.\d+)?',str(x).replace(',',''))
   if not m:return None
   z=float(m.group(0))
  return z if math.isfinite(z) else None
 except (TypeError, ValueError):return None

def integer(x):
 v=number(x)
 return int(v) if v is not None else None

def date(x):
 try:return datetime.date.fromisoformat(str(x)[:10])
 except Exception:return None

def norm(x):return re.sub(r'\s+','',str(x or '')).replace('ダート','ダ').upper()

def level_of(s):
 s=norm(s)
 # Standard JRA race labels; unknown is NOT imputed from official rank.
 for pattern,val in [(r'GⅠ|Ｇ１|\bG1\b|\bGI\b',8),(r'GⅡ|Ｇ２|\bG2\b|\bGII\b',7),(r'GⅢ|Ｇ３|\bG3\b|\bGIII\b',6),
                     (r'リステッド|\(L\)|^L$|\bLISTED\b',5),(r'\bOP\b|オープン',4),('3勝|３勝',3),('2勝|２勝',2),('1勝|１勝',1),('未勝利|新馬',0)]:
  if re.search(pattern,s):return val
 return None

def fit(a,b):
 a=norm(a);b=norm(b)
 return a==b and a in ('芝','ダ')

def event_key(run):
 d=date(run.get('date'));v=norm(run.get('venue'));s=norm(run.get('surface'))
 dist=integer(run.get('distance'));n=norm(run.get('race_name'))
 if not (d and v and s in ('芝','ダ') and dist and n):return None
 return (d.isoformat(),v,s,dist,n)

def run_clean(run):
 # Exact untrusted source fact fields allowlist: deliberately no time indexes.
 return {'date':str(run.get('date') or ''),'venue':str(run.get('venue') or ''),
         'surface':str(run.get('surface') or ''),'distance':integer(run.get('distance')),
         'race_name':str(run.get('race_name') or ''),'finish':integer(run.get('finish')),
         'passing_order':str(run.get('passing_order') or ''),
         'race_id':str(run.get('race_id') or '')}

def form_component(run):
 fin=integer(run.get('finish'))
 if fin is None or fin<1:return 0.0
 return {1:3.6,2:2.65,3:1.9,4:1.1,5:.45,6:-.25,7:-.5,8:-.8}.get(fin,-1.4)

def scoring_facts(row):
 """Return index-free C1 + audit. No outcome or legacy rank accepted here."""
 assert not any(k in row for k in BANNED_FEATURES), 'Forbidden leakage in model input'
 d=date(row['date']); cur_level=row.get('current_level'); dist=row.get('distance');surface=row.get('surface');venue=row.get('venue')
 runs=[r for r in row['runs'] if date(r.get('date')) and date(r.get('date'))<d and integer(r.get('finish')) is not None]
 prior=runs[:3]; n=len(prior)
 weighted=[.53,.30,.17]
 # Penalize low information modestly; new horses are not automatically last.
 perf=sum(form_component(run)*weighted[i] for i,run in enumerate(prior))
 if n==0:perf=-.35
 elif n==1:perf*=.85
 elif n==2:perf*=.95
 latest=prior[0] if prior else {}
 last_lv=level_of(latest.get('race_name'))
 class_diff=(last_lv-cur_level) if last_lv is not None and cur_level is not None else None
 # Class difference affects only match relevance; no blanket G1 uplift.
 cls=(max(-1.8,min(1.8,class_diff))*.35) if class_diff is not None else 0
 cls *= (1. if n else 0.)
 match=[];matched_place=0
 for run in prior:
  if not fit(run.get('surface'),surface):continue
  gap=abs((integer(run.get('distance')) or -99999)-(dist or 0))
  if gap<=200:
   match.append(run)
   if integer(run.get('finish'))<=3:matched_place+=1
 fit_score=0
 if match:
  fit_score+=.30
  fit_score+=min(.95,.44*matched_place)
  # Repeated same-venue evidence only if prior was at least competitive.
  if any(norm(x.get('venue'))==norm(venue) and integer(x.get('finish'))<=5 for x in match):fit_score+=.30
 else:
  if prior and not fit(latest.get('surface'),surface):fit_score-=.50
  elif prior:fit_score-=.12
 # A single good but old race does not count twice; components purposefully small.
 layoff=0
 if prior:
  days=(d-date(prior[0]['date'])).days
  layoff= -1.0 if days>=180 else -.45 if days>=70 else -.12 if days<=7 else 0
 training=str(row.get('training') or '').upper().strip()
 train_grade=re.search(r'(?<![A-Z])([ABCD])(?![A-Z])',training)
 grade=train_grade.group(1) if train_grade else ''
 train={'A':.35,'B':.10,'C':-.20,'D':-.40}.get(grade,0.)
 components={'past_finish':perf,'class_shift':cls,'condition_fit':fit_score,'layoff':layoff,'training':train}
 score=round(sum(components.values()),6)
 confidence='低' if n<2 else '中' if n<3 else '高'
 return score,components,confidence,len(prior)

def read_snapshots():
 races=[];byid={};issues=[]
 for ymd in DATES:
  path=SOURCE/(ymd+'_all.keiba')
  if not path.exists():issues.append('missing:'+str(path));continue
  with zipfile.ZipFile(path) as z:
   root=json.loads(z.read('snapshot.json'))
  for race in root.get('races',[]):
   if race.get('race_mode')!='jra' or norm(race.get('surface'))=='障':continue
   rid=str(race.get('race_id') or '')
   if rid in byid:
    issues.append(f'duplicate race:{rid}');continue
   currlev=level_of(race.get('race_name'))
   # Race name alone cannot always identify G/L; use explicit race_info.class_label only when unambiguous.
   if currlev is None:
    info=(race.get('mobile_snapshot') or {}).get('race_info') or {}
    currlev=level_of(info.get('class_label'))
   raw={integer(h.get('horse_no')):h for h in (race.get('horses') or [])}
   if currlev is None:
    explicit={level_of(x.get('class')) for x in raw.values()}
    explicit.discard(None)
    if len(explicit)==1:currlev=next(iter(explicit))
   evidence=((race.get('model_b_prediction') or {}).get('evidence') or {})
   horses=[]
   for mobile in (race.get('mobile_snapshot') or {}).get('horses',[]):
    no=integer(mobile.get('horse_no'))
    if no is None:continue
    other=raw.get(no,{})
    name=str(mobile.get('horse_name') or other.get('horse_name') or '').strip()
    runs=[run_clean(x) for x in (mobile.get('recent_races') or []) if isinstance(x,dict)]
    # Exact historical race IDs are available for some recent snapshots only.
    # Match IDs to recent_races using immutable date/finish/distance facts.
    peer_runs=(evidence.get(str(no)) or {}).get('past_runs') or []
    for past in runs:
     matches={str(e.get('race_id')) for e in peer_runs
              if e.get('race_id') and str(e.get('date') or '')==past['date']
              and integer(e.get('finish'))==integer(past.get('finish'))
              and integer(e.get('distance'))==integer(past.get('distance'))}
     if len(matches)==1:past['race_id']=next(iter(matches))
    row={'race_id':rid,'date':race.get('date'),'venue':race.get('venue'),
         'race_name':race.get('race_name'),'surface':race.get('surface'),
         'distance':integer(race.get('distance')),'current_level':currlev,
         'horse_no':no,'horse_name':name,'runs':runs,
         'training':other.get('training_short'),
         # For identification in audited outputs ONLY; none enter score.
         'pure_rank_audit':integer(other.get('ability_rank')),
         'pure_score_audit':number(other.get('ability_value'))}
    horses.append(row)
   out={'race_id':rid,'date':str(race.get('date')),'race_name':race.get('race_name'),'venue':race.get('venue'),
        'surface':race.get('surface'),'distance':integer(race.get('distance')),'horses':horses}
   races.append(out);byid[rid]=out
 return sorted(races,key=lambda r:(r['date'],r['race_id'])),issues

def get_results():
 # Evaluation-only. NEVER passed into scoring or as-of graph.
 result={};raw=[]
 if not RESULTS.exists():return result,raw
 with RESULTS.open(encoding='utf-8-sig',newline='') as f:
  for row in csv.DictReader(f):
   x=integer(row.get('finish'));key=(row['race_id'],integer(row['horse_no']))
   if x is not None:result[key]=x
   raw.append(row)
 return result,raw

def all_asof_profiles(current,older):
 """One latest pre-race profile per horse as of the target date.

 All observed past-race facts are from archived pre-race snapshots with snapshot
 date <= current date, filtered to dates strictly before current race date.
 This avoids post-race data and avoids using later snapshot history.
 """
 target=date(current['date']); profiles={}
 for race in older:
  if date(race['date'])>target:break
  for row in race['horses']:
   name=norm(row['horse_name']);
   if not name:continue
   profile={key:row[key] for key in ('date','venue','race_name','surface','distance','current_level','runs','training')}
   # Avoid form-index data in competitor scoring. For same-day profile, prefer more runs.
   prev=profiles.get(name)
   if prev is None or str(prev['date'])<str(row['date']) or (prev['date']==row['date'] and len(row['runs'])>len(prev['runs'])):
    profiles[name]=profile
 return profiles

def opponent_graph(targetdate, profiles, ambiguous=frozenset(), exact=False):
 """Historical event->partial participant ledger, with conservative identity key.

 A match uses exact date+venue+surface+distance+race_name and two observed
 names with different integer finish. Does not infer entire historical field.
 """
 events=collections.defaultdict(dict)
 for name,profile in profiles.items():
  for run in profile['runs']:
   d=date(run.get('date'))
   if d is None or d>=targetdate:continue
   event=event_key(run)
   key=str(run.get('race_id')) if exact else event
   fin=integer(run.get('finish'))
   if event not in ambiguous and key and fin and fin>0:events[key][name]=fin
 valid={key:pair for key,pair in events.items() if len(pair)>=2 and len(set(pair.values()))>=2}
 # Opponent quality at target date derives from own prior forms known as of date.
 quality={}
 for name,profile in profiles.items():
  d=date(profile['date']);runs=[run for run in profile['runs'] if date(run.get('date')) and date(run.get('date'))<targetdate]
  if not runs:quality[name]=.8;continue
  weighted=sum(form_component(r)*[.53,.30,.17][i] for i,r in enumerate(runs[:3]))
  maxlv=max([level_of(r.get('race_name')) for r in runs if level_of(r.get('race_name')) is not None] or [0])
  quality[name]=min(1.5,max(.55,1.0+.10*weighted+.025*maxlv))
 return valid,quality,len(events)

def h2h_feature(row,graph,quality,exact=False):
 """C2: weighted win/loss over identifiable actual prior opponents.

 Only pairs known in pre-race files are eligible. Multi-step indirect ratings
 are not invented from incomplete non-runner observations.
 """
 name=norm(row['horse_name']);rd=date(row['date']);races_seen=set();signed=0;count=0
 for run in row['runs'][:4]:
  k=str(run.get('race_id')) if exact else event_key(run)
  f=integer(run.get('finish'))
  if not k or not f or k not in graph or date(run.get('date'))>=rd:continue
  peers=graph[k]
  if name not in peers or k in races_seen:continue
  races_seen.add(k)
  days=(rd-date(run.get('date'))).days
  for peer,peerfinish in peers.items():
   if peer==name or peerfinish==f:continue
   # Previous result is relative within the known partial field, not all runners.
   outcome=1.0 if f<peerfinish else -1.0
   signed+=outcome*quality.get(peer,1.0)*math.exp(-days/240)
   count+=1
 # Prior shrinkage: a single accessible match is weak evidence.
 signal=signed/(count+3) if count else 0.0
 return round(signal,6),count,len(races_seen)

def ranks(rows,key):
 order=sorted(rows,key=lambda x:(-x[key],x['horse_no']))
 for rank,x in enumerate(order,1):x[key+'_rank']=rank
 return [x['horse_no'] for x in order]

def ambiguous_event_keys(races):
 '''Blacklist event signatures with multiple confirmed race IDs.

 These sources are used only for metadata QA, not outcomes or scoring.
 '''
 confirmed=collections.defaultdict(set)
 for race in races:
  k=event_key({'date':race['date'],'venue':race['venue'],'surface':race['surface'],
       'distance':race['distance'],'race_name':race['race_name']})
  if k:confirmed[k].add(race['race_id'])
  for horse in race['horses']:
   for run in horse['runs']:
    k=event_key(run)
    if k and run.get('race_id'):confirmed[k].add(run['race_id'])
 return {k for k,ids in confirmed.items() if len(ids)>1}

def measure(races):
 result,raw=get_results();counts=collections.defaultdict(lambda:collections.Counter())
 ambiguous=ambiguous_event_keys(races)
 daily_graph_cache={}
 details=[];race_metrics=[]
 pure_vs_c1=collections.Counter();c1c2change=collections.Counter();graph_audit=[]
 for race in races:
  evaluated=[dict(x) for x in race['horses']]
  for x in evaluated:
   feature_input={k:x[k] for k in ('date','venue','surface','distance','current_level','runs','training')}
   score,c,conf,n=scoring_facts(feature_input)
   x['c1_score']=score;x['component']=c;x['confidence']=conf;x['history_n']=n
  if race["date"] not in daily_graph_cache:
   profiles=all_asof_profiles(race,races)
   graph,quality,ngroups=opponent_graph(date(race["date"]),profiles,ambiguous=ambiguous)
   strict_graph,_,strict_ngroups=opponent_graph(date(race["date"]),profiles,ambiguous=ambiguous,exact=True)
   daily_graph_cache[race["date"]]=(graph,quality,ngroups,strict_graph,strict_ngroups)
  graph,quality,ngroups,strict_graph,strict_ngroups=daily_graph_cache[race["date"]]
  for x in evaluated:
   sig,num,events=h2h_feature(x,graph,quality)
   x['h2h_score']=sig;x['h2h_pairs']=num;x['h2h_events']=events
   strict_sig,strict_num,strict_events=h2h_feature(x,strict_graph,quality,exact=True)
   x['strict_h2h_score']=strict_sig;x['strict_h2h_pairs']=strict_num
   x['c2_score']=round(x['c1_score']+C2_LAMBDA*sig,6)
   x['c2_exact_score']=round(x['c1_score']+C2_LAMBDA*strict_sig,6)
  for key in ('c1_score','c2_score','c2_exact_score'):
   ranks(evaluated,key)
  # Pure ability is a research-only comparison, no formal marks/Top5 used.
  pureok=all(x['pure_rank_audit'] is not None for x in evaluated)
  if pureok:
   # Exactly k comparison picks even if saved ability ranks have ties.
   # Stable horse number tie-break; never feed this reference rank into C1/C2.
   for i,x in enumerate(sorted(evaluated,key=lambda x:(x['pure_rank_audit'],x['horse_no'])),1):
    x['pure_ref_rank']=i
  complete=all((race['race_id'],x['horse_no']) in result for x in evaluated)
  split='開発:9-10月' if race['date']<HOLDOUT else '時系列評価:11/7-8'
  eligible=bool(complete and len(evaluated)>=5)
  metric={'date':race['date'],'race_id':race['race_id'],'race_name':race['race_name'],'venue':race['venue'],
          'horse_count':len(evaluated),'complete':int(eligible),'split':split,'pure_reference_eligible':int(pureok),
          'h2h_linked_horses':sum(x['h2h_pairs']>0 for x in evaluated),'h2h_links':sum(x['h2h_pairs'] for x in evaluated),
          'h2h_exact_linked_horses':sum(x['strict_h2h_pairs']>0 for x in evaluated),
          'c1_top3_podium':0,'c2_top3_podium':0,'c2_exact_top3_podium':0,'pure_top3_podium':0,'c1_top5_podium':0,'c2_top5_podium':0,'c2_exact_top5_podium':0,'pure_top5_podium':0,
          'c1_winner_rank':None,'c2_winner_rank':None,'c2_exact_winner_rank':None,'pure_winner_rank':None}
  for x in evaluated:
   fin=result.get((race['race_id'],x['horse_no']))
   x['finish']=fin;x['top3']=int(fin<=3) if fin is not None else None
   x['split']=split;x['complete_race']=int(eligible)
   # IMPORTANT only audit; not fed into model features.
   if eligible:
    metric['c1_top3_podium']+=int(x['c1_score_rank']<=3 and fin<=3)
    metric['c2_exact_top3_podium']+=int(x['c2_exact_score_rank']<=3 and fin<=3)
    metric['c2_exact_top5_podium']+=int(x['c2_exact_score_rank']<=5 and fin<=3)
    metric['c2_top3_podium']+=int(x['c2_score_rank']<=3 and fin<=3)
    metric['c1_top5_podium']+=int(x['c1_score_rank']<=5 and fin<=3)
    metric['c2_top5_podium']+=int(x['c2_score_rank']<=5 and fin<=3)
    if pureok:
     metric['pure_top3_podium']+=int(x['pure_rank_audit']<=3 and fin<=3)
     metric['pure_top5_podium']+=int(x['pure_rank_audit']<=5 and fin<=3)
    if fin==1:
     metric['c1_winner_rank']=x['c1_score_rank']
     metric['c2_winner_rank']=x['c2_score_rank']
     metric['c2_exact_winner_rank']=x['c2_exact_score_rank']
     metric['pure_winner_rank']=x['pure_ref_rank'] if pureok else None
    if x['pure_rank_audit'] is not None:
     band='純能力1-3' if x['pure_rank_audit']<=3 else '純能力4-5' if x['pure_rank_audit']<=5 else '純能力6+' 
     pure_vs_c1[(split,band,'all')]+=1
     pure_vs_c1[(split,band,'podium')]+=int(fin<=3)
     if x['c1_score_rank']<=3:
      pure_vs_c1[(split,band,'c1_selected')]+=1
      pure_vs_c1[(split,band,'c1_selected_podium')]+=int(fin<=3)
    if x['c1_score_rank']!=x['c2_score_rank']:c1c2change[(split,'changed')]+=1
    if x['h2h_pairs']>0:c1c2change[(split,'linked')]+=1
   details.append({'split':split,'date':x['date'],'race_id':x['race_id'],'venue':x['venue'],'race_name':x['race_name'],
      'horse_no':x['horse_no'],'horse_name':x['horse_name'],'finish':fin,'top3':x['top3'],'complete_race':int(eligible),
      'c1_score':x['c1_score'],'c1_rank':x['c1_score_rank'],'c2_score':x['c2_score'],'c2_rank':x['c2_score_rank'],
      'c2_exact_score':x['c2_exact_score'],'c2_exact_rank':x['c2_exact_score_rank'],
      'strict_h2h_signal':x['strict_h2h_score'],'strict_h2h_pairs':x['strict_h2h_pairs'],
      'h2h_signal':x['h2h_score'],'h2h_pairs':x['h2h_pairs'],'h2h_events':x['h2h_events'],
      'prior_history_n':x['history_n'],'data_confidence':x['confidence'],
      'past_finish_part':x['component']['past_finish'],'class_shift_part':x['component']['class_shift'],
      'condition_part':x['component']['condition_fit'],'layoff_part':x['component']['layoff'],
      'training_part':x['component']['training'],
      'pure_rank_RESEARCH_ONLY':x['pure_rank_audit'],'pure_rank_exact3_RESEARCH_ONLY':x.get('pure_ref_rank'),
      'pure_score_RESEARCH_ONLY':x['pure_score_audit']})
  if eligible:race_metrics.append(metric)
  graph_audit.append({'race_id':race['race_id'],'date':race['date'],'partial_historical_races':ngroups,
     'two_horse_verifiable_events':len(graph),'strict_id_events':len(strict_graph),
     'ambiguous_event_signatures_excluded':len(ambiguous),'linked_horses':metric['h2h_linked_horses'],'eligible':int(eligible)})
 return details,race_metrics,graph_audit,pure_vs_c1,c1c2change

def stats(details,metrics,graph):
 result={}
 for split in ['開発:9-10月','時系列評価:11/7-8','全体']:
  rr=[r for r in metrics if split=='全体' or r['split']==split]
  d=[x for x in details if x['complete_race'] and (split=='全体' or x['split']==split)]
  count=len(rr)
  d2=[x for x in d if x['pure_rank_exact3_RESEARCH_ONLY'] is not None]
  datum={'races':count,'horses':len(d),'c2_linked_horses':sum(x['h2h_pairs']>0 for x in d),
         'c2_linked_horses_pct':round(100*sum(x['h2h_pairs']>0 for x in d)/len(d),1) if d else None,
         'c1_c2_rank_changes':sum(x['c1_rank']!=x['c2_rank'] for x in d),
         'c2_exact_linked_horses':sum(x['strict_h2h_pairs']>0 for x in d)}
  for method in ['c1','c2','c2_exact']:
   datum.update({f'{method}_top1_win':sum(r.get(method+'_winner_rank')==1 for r in rr),
                 f'{method}_top3_win_capture':sum(0<r.get(method+'_winner_rank',99)<=3 for r in rr),
                 f'{method}_top5_win_capture':sum(0<r.get(method+'_winner_rank',99)<=5 for r in rr),
                 f'{method}_top3_podium_horses':sum(r[method+'_top3_podium'] for r in rr),
                 f'{method}_top5_podium_horses':sum(r[method+'_top5_podium'] for r in rr)})
  pr=[r for r in rr if r['pure_reference_eligible']]
  datum.update({'pure_comparison_races':len(pr),'pure_top1_win':sum(r.get('pure_winner_rank')==1 for r in pr),
     'pure_top3_win_capture':sum(0<r.get('pure_winner_rank',99)<=3 for r in pr),
     'pure_top5_win_capture':sum(0<r.get('pure_winner_rank',99)<=5 for r in pr),
     'pure_top3_podium_horses':sum(r['pure_top3_podium'] for r in pr),
     'pure_top5_podium_horses':sum(r['pure_top5_podium'] for r in pr)})
  # Head-to-head C1-only vs C2-only in the same races, no top5 official reference.
  diff=collections.Counter()
  by_race=collections.defaultdict(list)
  for x in d:by_race[x['race_id']].append(x)
  for race,rows in by_race.items():
   for k in [3,5]:
    set1={x['horse_no'] for x in rows if x['c1_rank']<=k};set2={x['horse_no'] for x in rows if x['c2_rank']<=k}
    if set1!=set2:
     diff[f'top{k}_changed_races']+=1
     diff[f'top{k}_c1_only_podium']+=sum(x['top3'] for x in rows if x['horse_no'] in set1-set2)
     diff[f'top{k}_c2_only_podium']+=sum(x['top3'] for x in rows if x['horse_no'] in set2-set1)
  datum.update(diff)
  result[split]=datum
 # high pure misses / low pure hits
 contradictions={}
 for split in ['開発:9-10月','時系列評価:11/7-8']:
  rows=[x for x in details if x['complete_race'] and x['split']==split and x['pure_rank_RESEARCH_ONLY']]
  top=[x for x in rows if x['pure_rank_exact3_RESEARCH_ONLY']<=3]
  lows=[x for x in rows if x['pure_rank_exact3_RESEARCH_ONLY']>=6]
  discoveries=[x for x in lows if x['c1_rank']<=3]
  contradictions[split]={'pure_top3_n':len(top),'pure_top3_missed_podium':sum(x['top3']==0 for x in top),
    'pure_6plus_n':len(lows),'pure_6plus_podium':sum(x['top3']==1 for x in lows),
    'c1_discover_pure_6plus_n':len(discoveries),'c1_discover_pure_6plus_podium':sum(x['top3']==1 for x in discoveries)}
 result['contradictions']=contradictions
 return result

def save_csv(filename,rows):
 if not rows:return
 with (OUT/filename).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),extrasaction='ignore');w.writeheader();w.writerows(rows)

def main():
 global SOURCE, OUT, RESULTS, DATES, HOLDOUT
 parser=argparse.ArgumentParser(description='Index-free research C1 and historical opponent-link C2; no networking or payment')
 parser.add_argument('--archives-dir',type=Path,default=SOURCE,help='folder with YYYYMMDD_all.keiba files')
 parser.add_argument('--results-csv',type=Path,default=RESULTS,help='optional race_id,horse_no,finish CSV, evaluation only')
 parser.add_argument('--output-dir',type=Path,default=OUT)
 parser.add_argument('--dates',default='',help='comma-separated YYYYMMDD; default discovers YYYYMMDD_all.keiba files')
 parser.add_argument('--holdout-date',default=HOLDOUT)
 args=parser.parse_args()
 SOURCE=args.archives_dir;OUT=args.output_dir;RESULTS=args.results_csv;HOLDOUT=args.holdout_date
 OUT.mkdir(parents=True,exist_ok=True)
 DATES=[x for x in args.dates.split(',') if x.strip()] if args.dates else sorted([m.group(1) for f in SOURCE.glob('*.keiba') if (m:=re.fullmatch(r'(20\d{6})_all\.keiba',f.name))])
 if not DATES:parser.error('No YYYYMMDD_all.keiba found')
 races,issues=read_snapshots()
 details,metrics,graph,pure,diff=measure(races)
 summary=stats(details,metrics,graph)
 meta={'source_dates':DATES,'holdout_date':HOLDOUT,'all_races':len(races),'all_horses':len(details),
       'missing_result_races':len(races)-len(metrics),'issues':issues,'C1_formula':C1_COEFF,
       'C2_lambda':C2_LAMBDA,'C2_method':'C1 + 2*sum(weighted prior direct h2h)/ (known opponents+3)',
       'C2_exact_method':'Same formula but only exact past race_id identity (coverage-limited sensitivity analysis)',
       'ambiguous_event_signatures_excluded':len(ambiguous_event_keys(races)),
       'score_inputs':['past finish','past class','current class','same surface/distance/venue past placing','prior race dates','training grade'],
       'banned':['pure ability score/rank','speed index including 3-run mean','current formal rank/marks','odds','future race results'],
       'caveats':['Inexact event identity when no historical race_id: date+venue+surface+distance+race_name; multiple races same attributes may collide.',
                  'Partial opponent coverage, not a full national historical matchup network.',
                  'Archived snapshots have unknown generation time; dates strictly precede target and outcomes kept only in evaluation.',
                  'Holdout is later archive dates but previous analysis saw their results; not fully untouched prospective sample.',
                  'All coefficients are exploratory fixed heuristics and not fitted win probabilities.']}
 save_csv('競馬AI_独立C1_C2_全頭結果.csv',details)
 save_csv('競馬AI_独立C1_C2_レース比較.csv',metrics)
 save_csv('競馬AI_独立C1_C2_対戦網カバレッジ.csv',graph)
 (OUT/'競馬AI_独立C1_C2_結果集計.json').write_text(json.dumps({'summary':summary,'metadata':meta},ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'summary':summary,'metadata':{'all_races':len(races),'all_horses':len(details),'missing_result_races':len(races)-len(metrics)}},ensure_ascii=False,indent=2))

if __name__=='__main__':main()