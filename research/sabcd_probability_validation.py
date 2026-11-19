"""Fixed, chronological experiment; consumes pre-race features, never actual corners."""
import json,pathlib,collections,hashlib,math
import numpy as np
import argparse
parser=argparse.ArgumentParser(description='Reproduce the frozen 2026-11-19 retrospective experiment')
parser.add_argument('--rows',type=pathlib.Path,required=True)
parser.add_argument('--races',type=pathlib.Path,required=True)
parser.add_argument('--output',type=pathlib.Path,required=True)
args=parser.parse_args()
P=args.output;P.mkdir(parents=True,exist_ok=True)
CONFIG=dict(version='small-probability-correction-v1',ridge=50,cap=.08,boundary_window=.05,
 folds=[['2026-11-11','2026-11-12','2026-11-13'],['2026-11-13','2026-11-14','2026-11-15'],['2026-11-15','2026-11-16','2026-11-17']],
 bootstrap=2000,seed=1119,production_enabled=False)
(P/'確率補正_検証条件.json').write_text(json.dumps(CONFIG,ensure_ascii=False,indent=2),encoding='utf8')
rows=json.loads(args.rows.read_text(encoding='utf8'))
source=json.loads(args.races.read_text(encoding='utf8'))
lookup={(r['race_id'],str(h['馬番'])):(r,h) for r in source for h in r['prediction_result']['overall_table']['records']}
def num(v):
 try:
  x=float(v);return x if math.isfinite(x) else None
 except (TypeError,ValueError):return None
def rel(v,n):return (v-1)/max(1,n-1) if v is not None else None
def mul(a,b):return a*b if a is not None and b is not None else None
def features(row):
 race,h=lookup[row['race_id'],row['no']];n=len(race['horses'])
 out={k:num(row.get(k)) for k in ['days','age','weight_delta','jockey_rate','run_count','exact_starts','exact_podiums']}
 for k in ['ability_rank','pred_corner','course_rank','distance_rank','average_rank']:
  out[k+'_relative']=rel(num(row.get(k)),n)
 out['field_size']=n
 out['last_finish']=num(row['last_finish']);out['recent_podiums']=num(row['podiums'])
 avg=num(h.get('平均指数'));last=num(row.get('last_index'))
 out['last_vs_average']=last-avg if last is not None and avg is not None else None
 ix=[num(x) for x in row['indices']]
 out['trend']=ix[0]-ix[-1] if row['chronology_ok'] and len(ix)==3 and all(x is not None for x in ix) else None
 out['volatility']=float(np.std(ix)) if len(ix)==3 and all(x is not None for x in ix) else None
 for k in ['保存元で昇級','保存元で降級','200m以上延長','200m以上短縮','騎手乗替','牝馬','予測ハイペース','差し追込脚質','正式Top5']:
  v=row['features'][k];out[k]=float(v) if v is not None else None
 out['class_unverified']=float(row['class_shift'] not in ('同級','昇級','降級'))
 out['chronology_problem']=float(not row['chronology_ok'] or row['dropped_runs']>0)
 vals=[num(x.get('平均指数')) for x in race['prediction_result']['overall_table']['records']];vals=[x for x in vals if x is not None]
 out['average_vs_field']=avg-float(np.mean(vals)) if avg is not None and vals else None
 out['field_index_spread']=float(np.std(vals)) if len(vals)>=2 else None
 course=out['course_rank_relative'];dist=out['distance_rank_relative'];ability=out['ability_rank_relative'];corner=out['pred_corner_relative']
 out['ability_suitability_disagreement']=abs(ability-dist) if ability is not None and dist is not None else None
 out['ability_position_disagreement']=abs(ability-corner) if ability is not None and corner is not None else None
 out['course_distance_agreement']=mul(course,dist)
 out['distance_jockey']=mul(dist,out['jockey_rate'])
 out['change_distance_decline']=mul(out['last_vs_average'],(out['200m以上延長'] or 0)+(out['200m以上短縮'] or 0))
 out['upclass_recent']=mul(out['保存元で昇級'],out['recent_podiums'])
 out['pace_position']=mul(out['予測ハイペース'],corner)
 out['rest_decline']=mul(out['days'],out['last_vs_average'])
 out['condition_evidence_recent']=mul(out['exact_starts'],out['recent_podiums'])
 return out
eligible=[r for r in rows if r['grade'] in 'SABCD' and len(r['grade'])==1]
feature_rows=[features(r) for r in eligible];names=list(feature_rows[0]);raw=np.array([[r[k] if r[k] is not None else np.nan for k in names] for r in feature_rows]);y=np.array([r['placed'] for r in eligible],dtype=float)
sigmoid=lambda z:1/(1+np.exp(-np.clip(z,-30,30)))
logit=lambda p:np.log(np.clip(p,.001,.999)/(1-np.clip(p,.001,.999)))
def fit(train):
 global_rate=float(np.mean(y[train]));rates={g:(sum(y[i] for i in train if eligible[i]['grade']==g)+20*global_rate)/(sum(eligible[i]['grade']==g for i in train)+20) for g in 'SABCD'}
 x=raw[train];med=np.array([float(np.median(c[np.isfinite(c)])) if np.any(np.isfinite(c)) else 0 for c in x.T]);filled=np.where(np.isfinite(x),x,med);mean=filled.mean(axis=0);sd=filled.std(axis=0);sd[sd<1e-8]=1
 def design(indices):
  a=raw[indices];return np.column_stack([np.ones(len(indices)),np.clip((np.where(np.isfinite(a),a,med)-mean)/sd,-5,5),~np.isfinite(a)])
 X=design(train);offset=logit(np.array([rates[eligible[i]['grade']] for i in train]));beta=np.zeros(X.shape[1]);penalty=np.full(len(beta),CONFIG['ridge']);penalty[0]=10
 for _ in range(60):
  prob=sigmoid(offset+X@beta);grad=X.T@(prob-y[train])+penalty*beta;hess=(X.T*(prob*(1-prob)))@X+np.diag(penalty);step=np.linalg.solve(hess,grad);beta-=step
  if np.max(np.abs(step))<1e-8:break
 return rates,design,beta,dict(rates=rates,median=med.tolist(),mean=mean.tolist(),scale=sd.tolist(),coefficients=beta.tolist(),features=['intercept']+names+[k+'__missing' for k in names])
def metrics(ys,p):return dict(n=len(p),brier=float(np.mean((ys-p)**2)),logloss=float(-np.mean(ys*np.log(p)+(1-ys)*np.log(1-p))))
def moving_grade(g,p0,p1,rates):
 order='DCBAS';i=order.index(g)
 if p1>p0 and i<4:
  boundary=(rates[g]+rates[order[i+1]])/2
  if rates[g]<rates[order[i+1]] and abs(p0-boundary)<=CONFIG['boundary_window'] and p0<boundary<=p1:return order[i+1]
 if p1<p0 and i>0:
  boundary=(rates[g]+rates[order[i-1]])/2
  if rates[g]>rates[order[i-1]] and abs(p0-boundary)<=CONFIG['boundary_window'] and p1<boundary<=p0:return order[i-1]
 return g
oof=[];folds=[]
for end,start,stop in CONFIG['folds']:
 train=[i for i,r in enumerate(eligible) if r['date']<=end];test=[i for i,r in enumerate(eligible) if start<=r['date']<=stop]
 assert max(eligible[i]['date'] for i in train)<min(eligible[i]['date'] for i in test)
 rates,design,beta,model=fit(train);p0=np.array([rates[eligible[i]['grade']] for i in test]);p1=np.clip(sigmoid(logit(p0)+design(test)@beta),p0-CONFIG['cap'],p0+CONFIG['cap']);p1=np.clip(p1,.001,.999)
 fold=dict(train_through=end,test_from=start,test_to=stop,train_n=len(train),baseline=metrics(y[test],p0),candidate=metrics(y[test],p1),model=model)
 folds.append(fold)
 for i,a,b in zip(test,p0,p1):
  r=eligible[i];oof.append({**{k:r[k] for k in ['date','race_id','venue','race','no','name','grade','finish','placed']},'baseline_probability':float(a),'candidate_probability':float(b),'candidate_grade':moving_grade(r['grade'],a,b,rates),'train_through':end})
ys=np.array([r['placed'] for r in oof]);p0=np.array([r['baseline_probability'] for r in oof]);p1=np.array([r['candidate_probability'] for r in oof]);delta=(ys-p1)**2-(ys-p0)**2
by=collections.defaultdict(list)
for i,r in enumerate(oof):by[r['race_id']].append(i)
groups=list(by.values());rng=np.random.default_rng(CONFIG['seed']);boots=[]
for _ in range(CONFIG['bootstrap']):
 sample=[j for k in rng.integers(len(groups),size=len(groups)) for j in groups[k]];boots.append(float(np.mean(delta[sample])))
ci=np.quantile(boots,[.025,.975]).tolist()
summary=dict(config=CONFIG,source_grade='historical_reconstruction_class_unknown',unknown_excluded=len(rows)-len(eligible),folds=folds,
 baseline=metrics(ys,p0),candidate=metrics(ys,p1),brier_delta_ci=ci,races=len(groups),
 days={},venues={},grades={},diagnostics={},adoption='research_only',reason='Historical reconstruction and previously examined dates; prospective validation required regardless of retrospective gains.')
for label,key in [('days','date'),('venues','venue'),('grades','grade')]:
 for v in sorted({r[key] for r in oof}):
  ix=[i for i,r in enumerate(oof) if r[key]==v];summary[label][v]=dict(baseline=metrics(ys[ix],p0[ix]),candidate=metrics(ys[ix],p1[ix]),actual_rate=float(np.mean(ys[ix])),predicted_before=float(np.mean(p0[ix])),predicted_after=float(np.mean(p1[ix])))
# Descriptive residuals, not candidate discovery or re-fitting on the test labels.
features_by={(r['race_id'],r['no']):f for r,f in zip(eligible,feature_rows)}
for name,fn in [('適性と能力の順位差大',lambda f:f['ability_suitability_disagreement'] is not None and f['ability_suitability_disagreement']>=.4),('能力と位置取りの順位差大',lambda f:f['ability_position_disagreement'] is not None and f['ability_position_disagreement']>=.4),('同条件経験なし',lambda f:f['exact_starts']==0),('近走材料3走未満',lambda f:f['run_count']<3),('日付矛盾あり',lambda f:f['chronology_problem']==1),('昇級',lambda f:f['保存元で昇級']==1),('距離変更200m以上',lambda f:f['200m以上延長']==1 or f['200m以上短縮']==1)]:
 summary['diagnostics'][name]={}
 for g in 'SABCD':
  ix=[i for i,r in enumerate(oof) if r['grade']==g and fn(features_by[r['race_id'],r['no']])]
  if ix:summary['diagnostics'][name][g]=dict(n=len(ix),placed=int(sum(ys[ix])),observed=float(np.mean(ys[ix])),baseline=float(np.mean(p0[ix])),candidate=float(np.mean(p1[ix])))
train=list(range(len(eligible)));_,_,_,model=fit(train);model.update(CONFIG);model['train_through']='2026-11-17';model['source_grade']=summary['source_grade']
for name,obj in [('確率補正_期間別検証.json',summary),('確率補正_検証馬明細.json',oof),('確率補正_研究用モデル.json',model)]:
 (P/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:summary[k] for k in ['baseline','candidate','brier_delta_ci','races','unknown_excluded']},ensure_ascii=False));print('folds',[(f['test_from'],f['baseline']['brier'],f['candidate']['brier']) for f in folds]);print('moves',dict(collections.Counter(r['grade']+'→'+r['candidate_grade'] for r in oof if r['grade']!=r['candidate_grade'])))
