"""Probe public NAR/JRA older race result page structure (no private inputs)."""
import requests,json
from bs4 import BeautifulSoup
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
p=Path("research/lead_history_debug");p.mkdir(parents=True,exist_ok=True)
urls={
 "jra1":"https://race.netkeiba.com/race/result.html?race_id=202609040704",
 "jra2":"https://race.netkeiba.com/race/result.html?race_id=202608040211",
 "nar1":"https://nar.netkeiba.com/race/result.html?race_id=202655101701",
 "nar2":"https://race.netkeiba.com/race/result.html?race_id=202655101701",
 "nar3":"https://db.netkeiba.com/race/202655101701/",
}
def work(arg):
 name,url=arg
 try:
  r=requests.get(url,timeout=22,headers={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/132.0.0.0 Safari/537.36"})
  soup=BeautifulSoup(r.content,"html.parser")
  tab=soup.select_one("table.RaceTable01")
  rows=[]
  for tr in (tab.select("tbody tr")[:5] if tab else []):
   rows.append([td.get_text(" ",strip=True) for td in tr.find_all("td",recursive=False)])
  data={"name":name,"url":r.url,"status":r.status_code,"bytes":len(r.content),
   "title":soup.title.get_text(" ",strip=True) if soup.title else "",
   "table_header":tab.select_one("thead").get_text(" ",strip=True)[:850] if tab and tab.select_one("thead") else "",
   "rows":rows,"text_snippet":soup.get_text(" ",strip=True)[:2200]}
  (p/f"{name}.html").write_bytes(r.content)
  return data
 except Exception as e:return {"name":name,"error":str(e)}
with ThreadPoolExecutor(max_workers=3) as ex: data=list(ex.map(work,urls.items()))
(p/"diagnostic.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf8")
for d in data:print(json.dumps(d,ensure_ascii=False)[:2200],flush=True)
