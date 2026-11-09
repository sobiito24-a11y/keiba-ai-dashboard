"""Collect first-corner passage of every runner in public previous-race results.

The inputs here are only 729 publicly available race IDs (compressed) and the
outputs only public historical race facts. No proprietary prediction snapshots.
Uses a capped concurrency and public HTML; no paid APIs.
"""
import base64,csv,json,re,time,zlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import requests
from bs4 import BeautifulSoup

OUT=Path("research/lead_history_public_results")
OUT.mkdir(parents=True,exist_ok=True)
NAMES=zlib.decompress(base64.b64decode(Path("research/lead_history_public_race_ids_zlib.b64").read_text().strip())).decode("utf-8").splitlines()
assert len(NAMES)==729,len(NAMES)
HEAD={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36","Accept-Language":"ja-JP,ja;q=0.9,en;q=0.8"}

def first_passage(tr):
    # Old netkeiba database HTML nests 'passage' in <diary_snap_cut>.
    # Never infer it from finish or from an existing prediction index.
    for node in tr.select("diary_snap_cut td"):
        text=node.get_text(" ",strip=True)
        if re.fullmatch(r"\d{1,2}(?:\s*-\s*\d{1,2}){1,6}",text):
            return re.sub(r"\s+","",text)
    return ""

def parse_page(rid,soup,mode,url):
    table=soup.select_one("table.RaceTable01") if mode=="JRA" else soup.select_one("table.race_table_01")
    if not table:
        return [],"TABLE_MISSING"
    result=[]
    for tr in table.find_all("tr"):
        direct=tr.find_all("td",recursive=False)
        if len(direct)<4:continue
        number=direct[2].get_text(" ",strip=True)
        if not number.isdigit():continue
        horse_name=direct[3].get_text(" ",strip=True).replace(" ","")
        if not horse_name:continue
        if mode=="JRA":
            passage=direct[12].get_text(" ",strip=True) if len(direct)>12 else ""
        else:
            passage=first_passage(tr)
        positions=[int(x) for x in re.findall(r"\d+",passage)] if passage else []
        result.append([rid,mode,int(number),horse_name,
                       positions[0] if positions else None,
                       positions[-1] if positions else None,
                       passage,url])
    return result,("OK" if any(h[4] is not None for h in result) else "NO_PASSAGE")

def fetch_one(rid):
    mode="NAR" if int(rid[4:6])>20 else "JRA"
    url=(f"https://nar.netkeiba.com/race/result.html?race_id={rid}" if mode=="NAR"
         else f"https://race.netkeiba.com/race/result.html?race_id={rid}")
    # NAR netkeiba race page includes corner grouping, not individual passage in the table.
    # Its public database route has each horse's passage in a hidden HTML element.
    if mode=="NAR":url=f"https://db.netkeiba.com/race/{rid}/"
    last=""
    for attempt in range(3):
        try:
            r=requests.get(url,timeout=25,headers=HEAD)
            if r.status_code==200 and len(r.content)>10000:
                soup=BeautifulSoup(r.content,"html.parser")
                result,status=parse_page(rid,soup,mode,url)
                if result:return result,[rid,mode,status,len(result),sum(h[4] is not None for h in result),url]
                last=status
            else:last=f"HTTP {r.status_code}, bytes {len(r.content)}"
            if r.status_code in (403,404):break
        except Exception as e:last=f"{type(e).__name__} {str(e)[:100]}"
        time.sleep(1.2*(attempt+1))
    return [],[rid,mode,"FAIL "+last,0,0,url]
def main():
    all_horses=[];audit=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(fetch_one,rid):rid for rid in NAMES}
        for i,f in enumerate(as_completed(futures),1):
            rid=futures[f]
            try:
                hs,record=f.result()
                all_horses.extend(hs);audit.append(record)
                if i%25==0 or i==len(NAMES):
                    print(f"{i:03}/{len(NAMES)} matched={len(all_horses)} passed={sum(x[2]=='OK' for x in audit)} latest={rid} {record[2]}",flush=True)
            except Exception as e:
                audit.append([rid,"","EXCEPTION "+str(e)[:100],0,0,""])
    all_horses.sort(key=lambda x:(x[0],x[2]));audit.sort(key=lambda x:x[0])
    def output(name,head,body):
        with (OUT/name).open("w",newline="",encoding="utf-8-sig") as fl:
            w=csv.writer(fl);w.writerow(head);w.writerows(body)
    output("historical_first_corner_horse_all.csv",["past_race_id","mode","horse_no","horse_name","first_corner_pos","last_corner_pos","passage","source_url"],all_horses)
    output("historical_first_corner_source_audit.csv",["past_race_id","mode","status","runner_count","passage_count","source_url"],audit)
    states={v:sum(x[2]==v for x in audit) for v in sorted({a[2] for a in audit})}
    manifest={"requested":len(NAMES),"result_horses":len(all_horses),"ok_races":sum(x[2]=="OK" for x in audit),"covered_races":sum(x[4]>0 for x in audit),"states":states}
    (OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINISHED",json.dumps(manifest,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
