from pathlib import Path
import requests
from bs4 import BeautifulSoup
import json
out=Path("research/final_odds_output");out.mkdir(parents=True,exist_ok=True)
urls={
"netkeiba":"https://race.netkeiba.com/race/result.html?race_id=202608050101",
"yahoo_wide":"https://sports.yahoo.co.jp/keiba/race/odds/wide/2608050101?ninki=0",
"yahoo_tfw":"https://sports.yahoo.co.jp/keiba/race/odds/tfw/2608050101?ninki=0"
}
results={}
for name,url in urls.items():
 try:
  r=requests.get(url,timeout=25,headers={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/132.0.0.0 Safari/537.36","Accept-Language":"ja,en;q=0.9"})
  soup=BeautifulSoup(r.content,"html.parser")
  text=soup.get_text(" ",strip=True)
  results[name]={"status":r.status_code,"url":r.url,"bytes":len(r.content),"title":soup.title.get_text(" ",strip=True) if soup.title else None,"snippet":text[:9000],"tables":[{"classes":t.get("class"),"text":t.get_text(" ",strip=True)[:900]} for t in soup.select("table")[:5]]}
  (out/(name+".html")).write_bytes(r.content)
  print(name,results[name]["status"],results[name]["bytes"],text[:200].replace("\n"," "))
 except Exception as e:results[name]={"error":str(e)};print(name,repr(e))
(out/"diagnostic.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
