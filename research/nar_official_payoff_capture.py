"""Read public NAR official historical settled dividends; research only, no paid APIs."""
import requests,json,re,os
from bs4 import BeautifulSoup
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
out=Path("research/nar_payout_capture");out.mkdir(parents=True,exist_ok=True)
groups=[("2026-11-07","佐賀",32),("2026-11-07","高知",31),
        ("2026-11-08","佐賀",32),("2026-11-08","高知",31),("2026-11-08","盛岡",10)]
def work(group):
 date,venue,code=group
 url="https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/RefundMoneyList"
 try:
  r=requests.get(url,params={"k_babaCode":str(code),"k_raceDate":date.replace("-","/"),"k_raceNo":"1","odds_flg":"5"},headers={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/132.0.0.0 Safari/537.36","Accept-Language":"ja-JP,ja;q=0.9"},timeout=30)
  r.encoding=r.apparent_encoding
  html=r.text
  soup=BeautifulSoup(html,"html.parser")
  text=soup.get_text(" ",strip=True)
  tag=f"{date}_{venue}"
  (out/(tag+".html")).write_text(html,encoding="utf8")
  (out/(tag+".txt")).write_text(text,encoding="utf8")
  return {"date":date,"venue":venue,"url":r.url,"status":r.status_code,"bytes":len(r.content),"title":soup.title.get_text(" ",strip=True) if soup.title else "","text_snippet":text[:2500],"tables":[t.get_text(" ",strip=True)[:650] for t in soup.select("table")[:4]]}
 except Exception as e:return {"date":date,"venue":venue,"error":repr(e)}
def main():
 with ThreadPoolExecutor(max_workers=3) as ex:
  results=list(ex.map(work,groups))
 for r in results:print(json.dumps(r,ensure_ascii=False)[:1700],flush=True)
 (out/"manifest.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf8")
if __name__=="__main__":main()
