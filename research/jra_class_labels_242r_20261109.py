"""Historical race class and age classification, from public post-race HTML.
Research-only; no changes to Dashboard prediction logic."""
from __future__ import annotations
import csv, json, re, time, unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests
from bs4 import BeautifulSoup

GROUPS = """
2026060408:1,2,4,6,7,8,9,10,11,12
2026090408:1,2,3,6,7,8,9,10,11,12
2026060409:2,3,6,7,9,10,11,12
2026090409:2,3,4,7,8,9,10,11,12
2026080402:1,2,6,7,8,9,10,11,12
2026050402:1,2,7,8,9,10,11,12
2026080403:1,2,3,7,8,9,10,11,12
2026050403:1,2,3,7,8,9,10,11,12
2026080404:1,2,6,7,8,9,10,11,12
2026050404:1,2,3,6,7,8,9,10,11,12
2026080406:1,2,3,4,7,8,9,10,11,12
2026040401:1,2,3,4,6,7,8,9,10,11,12
2026050406:1,2,3,6,7,8,9,10,11,12
2026080407:1,2,3,4,7,8,9,10,11,12
2026040402:1,2,3,4,6,7,8,9,10,11,12
2026050407:1,2,3,6,7,8,9,10,11,12
2026080408:1,2,4,6,7,8,9,10,11,12
2026040403:1,2,3,4,6,7,8,9,10,11,12
2026050408:1,2,3,7,8,9,10,11,12
2026080501:1,2,3,4,7,9,10,11,12
2026050501:1,2,3,4,5,8,9,10,11,12
2026030301:1,2,3,4,6,7,8,9,10,11,12
2026080502:1,2,3,4,7,8,9,10,11,12
2026050502:1,2,3,6,7,8,9,10,11,12
2026030302:1,2,3,7,8,9,10,11,12
"""
RIDS=[]
for line in GROUPS.strip().splitlines():
    group,ns=line.strip().split(":")
    RIDS.extend(group+str(int(i)).zfill(2) for i in ns.split(","))
assert len(RIDS)==242,len(RIDS)
def norm(s): return unicodedata.normalize("NFKC",s or "").strip()
HEAD={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36","Accept-Language":"ja-JP,ja;q=0.9"}
OUT=Path("research/class_labels_242");OUT.mkdir(parents=True,exist_ok=True)

def classify(title,data):
    whole=norm(title+" "+data)
    if "障害" in whole: return "障害"
    if re.search(r"新馬|メイクデビュー",whole): return "新馬"
    if re.search(r"未勝利",whole): return "未勝利"
    if re.search(r"1勝クラス|500万下",whole): return "1勝"
    if re.search(r"2勝クラス|1000万下",whole): return "2勝"
    if re.search(r"3勝クラス|1600万下",whole): return "3勝"
    if re.search(r"\bG1\b|\bGI\b",whole,re.I):return "G1"
    if re.search(r"\bG2\b|\bGII\b",whole,re.I):return "G2"
    if re.search(r"\bG3\b|\bGIII\b",whole,re.I):return "G3"
    if re.search(r"オープン|OP\b|リステッド|\(L\)",whole,re.I):return "OP・重賞"
    return "未分類"
def worker(rid):
    url="https://race.netkeiba.com/race/result.html?race_id="+rid
    status=""
    for attempt in range(3):
        try:
            r=requests.get(url,timeout=22,headers=HEAD)
            if r.status_code==200 and len(r.content)>10000:
                sp=BeautifulSoup(r.content,"html.parser")
                race_name=sp.select_one(".RaceName")
                race_data=sp.select_one(".RaceData02")
                race_meta=sp.select_one(".RaceData01")
                race_text=norm(race_name.get_text(" ",strip=True) if race_name else "")
                data_text=norm(race_data.get_text(" ",strip=True) if race_data else "")
                meta_text=norm(race_meta.get_text(" ",strip=True) if race_meta else "")
                title=norm(sp.title.get_text(" ",strip=True) if sp.title else "")
                cat=classify(race_text+" "+title,data_text)
                # Titles are JRA grade names; a grade icon may not be visible as text. We only need OP-level grouping.
                age_m=re.search(r"(2歳|3歳|4歳|5歳|3歳以上|4歳以上)",data_text)
                if not age_m: age_m=re.search(r"(2歳|3歳|4歳|5歳|3歳以上|4歳以上)",race_text)
                age=age_m.group(1) if age_m else "年齢未確認"
                dist=re.search(r"(芝|ダ|障)(\d{3,4})m",meta_text)
                surface={"芝":"芝","ダ":"ダート","障":"障害"}.get(dist.group(1),"不明") if dist else "不明"
                distance=int(dist.group(2)) if dist else None
                field_m=re.search(r"(\d+)頭",data_text)
                num_horses=int(field_m.group(1)) if field_m else None
                return [rid,cat,age,surface,distance,num_horses,race_text,data_text,meta_text,url,"OK" if cat!="未分類" else "UNKNOWN_CLASS"]
            status=f"HTTP {r.status_code} / {len(r.content)} bytes"
        except Exception as e: status=repr(e)
        time.sleep(1.0*(attempt+1))
    return [rid,"取得失敗","不明","不明",None,None,"","","",url,status[:150]]
def main():
    arr=[]
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures={ex.submit(worker,r):r for r in RIDS}
        for i,f in enumerate(as_completed(futures),1):
            x=f.result();arr.append(x)
            print(f"{i:03d}/242 {x[0]} {x[1]} {x[2]} {x[3]} {x[4]} status={x[-1]}",flush=True)
    arr.sort(key=lambda x:x[0])
    with (OUT/"classes_all_242r.csv").open("w",newline="",encoding="utf-8-sig") as fl:
        w=csv.writer(fl);w.writerow(["race_id","class","age","surface","distance","field_size","race_name","race_conditions","track_details","source_url","status"]);w.writerows(arr)
    counts={k:sum(x[1]==k for x in arr) for k in sorted({x[1] for x in arr})}
    manifest={"total":len(arr),"known":sum(x[1] not in ("未分類","取得失敗") for x in arr),"by_class":counts,"by_status":{s:sum(x[-1]==s for x in arr) for s in sorted({x[-1] for x in arr})}}
    (OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print("MANIFEST",json.dumps(manifest,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
