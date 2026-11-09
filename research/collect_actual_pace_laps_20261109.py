"""Public actual pace / lap / first-corner facts for 2026-11-07/08. No private files.
Uses only free public race result pages; research-only CI job. """
import csv,re,os,time,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from bs4 import BeautifulSoup
import requests
OUT=Path("research/actual_pace_public_20261107_08")
OUT.mkdir(parents=True,exist_ok=True)
HEADERS={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36","Accept-Language":"ja-JP,ja;q=0.9,en;q=0.8"}
# Six JRA venue/day combinations; local filtering later uses the exact pre-race archive IDs.
JRA=[("2026080501","京都","2026-11-07"),("2026080502","京都","2026-11-08"),
     ("2026050501","東京","2026-11-07"),("2026050502","東京","2026-11-08"),
     ("2026030301","福島","2026-11-07"),("2026030302","福島","2026-11-08")]
# Official NAR codes: 佐賀32, 高知31, 盛岡10. We fetch 1-12 to avoid putting user snapshot data on GitHub.
NAR=[("2026-11-07","佐賀",32),("2026-11-07","高知",31),
     ("2026-11-08","佐賀",32),("2026-11-08","高知",31),("2026-11-08","盛岡",10)]
WORK=[]
for prefix,venue,date in JRA:
 for no in range(1,13):
  rid=prefix+str(no).zfill(2)
  WORK.append(("JRA",rid,date,venue,no,f"https://race.netkeiba.com/race/result.html?race_id={rid}"))
for date,venue,code in NAR:
 for no in range(1,13):
  rid=f"NAR-{date}-{venue}-{no:02}"
  url=f"https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/RaceMarkTable?k_babaCode={code}&k_raceDate={date.replace('-','%2F')}&k_raceNo={no}"
  WORK.append(("NAR",rid,date,venue,no,url))
def fetch(url):
 err=""
 for k in range(3):
  try:
   r=requests.get(url,headers=HEADERS,timeout=25)
   if r.status_code==200 and len(r.content)>5000:
    soup=BeautifulSoup(r.content,"html.parser")
    txt=soup.get_text(" ",strip=True)
    return soup,txt,"200"
   err=f"HTTP{r.status_code} bytes={len(r.content)}"
   if r.status_code in (403,404):break
  except Exception as e:err=repr(e)
  time.sleep((k+1)*1.2)
 return None,"",err
def compact(text,anchor,span=3200):
 k=text.find(anchor)
 return text[max(0,k-100):k+span] if k>=0 else ""
def parse_jra(text,soup):
 # Netkeiba publishes official postrace lap-based S/M/H label; never infer from pre-race.
 target=compact(text,"ラップタイム",450)
 if not target:target=compact(text,"ペース",550)
 pm=re.search(r"ペース\s*[:：]?\s*([SMH])(?=\s|[（(:]|$)",target,re.I)
 pace=pm.group(1).upper() if pm else ""
 cm=compact(text,"コーナー通過順位",950)
 if not cm:cm=compact(text,"コーナー",1200)
 lap=compact(text,"ラップタイム",2100)
 has_result=bool(re.search(r"着順\s+枠\s+馬番",text)) or ("コーナー通過順位" in text and "払戻金" in text)
 return pace,cm,lap,has_result
def parse_nar(text,soup):
 # Unlike JRA, official NAR results do not label pace S/M/H; preserve official lap rows.
 lap=compact(text,"ハロンタイム",3000)
 first=compact(text,"全馬コーナー通過順",1500)
 if not first:first=compact(text,"１角",1000)
 has_result="競走成績" in text and "ハロンタイム" in text
 return "",first,lap,has_result
def worker(it):
 mode,rid,date,venue,num,url=it
 soup,text,status=fetch(url)
 if soup is None:
  return [mode,rid,date,venue,num,"", "", "", status,"",0,url]
 pace,corner,lap,has_result=(parse_jra(text,soup) if mode=="JRA" else parse_nar(text,soup))
 title=soup.title.get_text(" ",strip=True) if soup.title else ""
 # Always also include the complete postrace text (up to 18000 chars) for robust local independent parsing.
 return [mode,rid,date,venue,num,pace,corner,lap,status,title,1 if has_result else 0,url,text[:18000]]
def main():
 result=[]
 with ThreadPoolExecutor(max_workers=4) as pool:
  tasks={pool.submit(worker,it):it for it in WORK}
  for i,f in enumerate(as_completed(tasks),1):
   try:
    x=f.result();result.append(x)
    print(f"{i:03}/{len(WORK)} {x[0]} {x[1]} pace={x[5] or '-'} exists={x[10]} status={x[8]} lap={len(x[7])}",flush=True)
   except Exception as e:
    it=tasks[f];print("ERROR "+str(it)+" "+repr(e),flush=True)
 result.sort(key=lambda x:(x[0],x[2],x[3],x[4]))
 names=["mode","race_id","date","venue","race_no","actual_pace_label","corner_text","lap_text","fetch_status","title","has_actual_result","source_url","result_text"]
 with (OUT/"public_actual_lap_corner_20261107_08.csv").open("w",newline="",encoding="utf-8-sig") as f:
  w=csv.writer(f);w.writerow(names);w.writerows(result)
 summary={"requested":len(WORK),"returned":len(result),
          "jra_labeled":sum(x[0]=="JRA" and x[5] in ("S","M","H") for x in result),
          "nar_lap":sum(x[0]=="NAR" and "ハロンタイム" in x[-1] for x in result),
          "jra_paces":{c:sum(x[0]=="JRA" and x[5]==c for x in result) for c in ("S","M","H")}}
 (OUT/"manifest.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf8")
 print("SUMMARY",json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
