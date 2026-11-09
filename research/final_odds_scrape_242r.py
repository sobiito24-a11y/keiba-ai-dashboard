"""Public, free, historical FINAL JRA odds audit. Runs only in isolated research PR.
No paid APIs, no account access, no Dashboard modifications."""
import csv
import re
import time
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

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
RIDS = []
for line in GROUPS.strip().splitlines():
    base, numbers = line.strip().split(":")
    RIDS.extend(base + str(int(v)).zfill(2) for v in numbers.split(","))
assert len(RIDS) == 242, len(RIDS)

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36", "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8"}
OUT = Path("research/final_odds_output")
OUT.mkdir(parents=True, exist_ok=True)

def request_page(url):
    last_error = ""
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=25, headers=HEADERS)
            if resp.status_code == 200 and len(resp.content) > 4000:
                return BeautifulSoup(resp.content, "html.parser"), "200"
            last_error = "status=" + str(resp.status_code) + " bytes=" + str(len(resp.content))
            if resp.status_code not in (403, 429, 500, 502, 503, 504):
                break
        except Exception as e:
            last_error = type(e).__name__ + ": " + str(e)[:150]
        time.sleep(1.5 * (attempt + 1))
    return None, last_error

def nums_payout(tag):
    if not tag:
        return []
    return [int(x.replace(",","")) for x in re.findall(r"(\d[\d,]*)\s*円", tag.get_text(" ", strip=True))]

def parse_netkeiba(soup, rid, url):
    horses = []
    win_map = {}
    place_map = {}
    paid_wide = {}
    if soup is None:
        return horses, win_map, place_map, paid_wide, "netkeiba unavailable"
    for row in soup.select("table.RaceTable01 tbody tr.HorseList"):
        cols = row.find_all("td", recursive=False)
        if len(cols) < 11:
            continue
        try:
            no = int(cols[2].get_text(" ", strip=True))
        except ValueError:
            continue
        txt = cols[10].get_text(" ", strip=True).replace(",", "")
        match = re.search(r"\d+(?:\.\d+)?", txt)
        odd = float(match.group()) if match else None
        finish = cols[0].get_text(" ", strip=True)
        name = cols[3].get_text(" ", strip=True)
        horses.append([rid, no, name, finish, odd, None, None, url])
    tr = soup.select_one("tr.Tansho")
    if tr:
        tags = tr.select("td.Result > div")
        n = next((int(t.get_text(" ", strip=True)) for t in tags if t.get_text(" ", strip=True).isdigit()), None)
        payout = nums_payout(tr.select_one("td.Payout"))
        if n is not None and payout:
            win_map[n] = payout[0]
    tr = soup.select_one("tr.Fukusho")
    if tr:
        nos = [int(t.get_text(" ", strip=True)) for t in tr.select("td.Result > div") if t.get_text(" ", strip=True).isdigit()]
        payouts = nums_payout(tr.select_one("td.Payout"))
        for n,p in zip(nos,payouts):
            place_map[n] = p
    tr = soup.select_one("tr.Wide")
    if tr:
        pairs = []
        for ul in tr.select("td.Result > ul"):
            x = [int(z) for z in re.findall(r"\d+", ul.get_text(" ", strip=True))]
            if len(x) == 2:
                pairs.append(tuple(sorted(x)))
        pays = nums_payout(tr.select_one("td.Payout"))
        for p,value in zip(pairs,pays):
            paid_wide[p] = value
    for h in horses:
        h[5] = win_map.get(h[1], 0)
        h[6] = place_map.get(h[1], 0)
    return horses, win_map, place_map, paid_wide, ("OK" if horses else "result horses not parsed")

def parse_final_wide(soup, rid, url, expected_numbers):
    pairs = []
    if soup is None:
        return pairs, "wide page unavailable"
    text = soup.get_text(" ", strip=True)
    if "確定オッズ" not in text:
        return pairs, ("intermediate (excluded)" if "中間オッズ" in text else "no FINAL label")
    for table in soup.select("table.hr-tableLeftTop--oddsW"):
        th = table.select_one("thead th")
        if not th:
            continue
        try:
            a = int(th.get_text(" ", strip=True))
        except ValueError:
            continue
        for tr in table.select("tbody tr"):
            t = tr.find("th")
            d = tr.find("td")
            if not t or not d:
                continue
            try:
                b = int(t.get_text(" ", strip=True))
            except ValueError:
                continue
            value = d.get_text(" ", strip=True)
            m = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", value)
            if not m:
                continue
            lo, hi = float(m.group(1)), float(m.group(2))
            p = sorted((a,b))
            pairs.append([rid,p[0],p[1],lo,hi,url])
    pairs = list({(p[0],p[1],p[2]):p for p in pairs}.values())
    full_count = len(expected_numbers)*(len(expected_numbers)-1)//2
    if not pairs:
        return pairs, "FINAL label but 0 pairs / unavailable"
    if len(pairs) != full_count:
        return pairs, "partial " + str(len(pairs)) + "/" + str(full_count)
    return pairs, "complete"

def worker(rid):
    net_url = "https://race.netkeiba.com/race/result.html?race_id=" + rid
    wide_url = "https://sports.yahoo.co.jp/keiba/race/odds/wide/" + rid[2:] + "?ninki=0"
    soup, net_http = request_page(net_url)
    horses, win_map, place_map, paid_wide, horse_state = parse_netkeiba(soup,rid,net_url)
    time.sleep(0.35)
    wsoup, wide_http = request_page(wide_url)
    odds_wide, wide_state = parse_final_wide(wsoup,rid,wide_url, {h[1] for h in horses})
    # Verify all winning wide values lie in final wide displayed ranges, with rounding tolerance.
    odds_dict={(r[1],r[2]):(r[3],r[4]) for r in odds_wide}
    mismatches=[]
    for pair, money in paid_wide.items():
        bounds=odds_dict.get(pair)
        if bounds and (money/100 < bounds[0]-0.15 or money/100 > bounds[1]+0.15):
            mismatches.append(str(pair)+":"+str(money)+"/"+str(bounds))
    win_mismatches=[]
    for row in horses:
        if row[5] and row[4] is not None and abs(row[5]-row[4]*100)>10.5:
            win_mismatches.append(str(row[1])+":"+str(row[4])+"/"+str(row[5]))
    payouts=[[rid,a,b,value,net_url] for (a,b),value in paid_wide.items()]
    summary=[rid,len(horses),len(odds_wide),horse_state,wide_state,net_http,wide_http,
             len(payouts),";".join(mismatches),";".join(win_mismatches),net_url,wide_url]
    return horses,odds_wide,payouts,summary

def write_csv(path,head,data):
    with (OUT/path).open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f);w.writerow(head);w.writerows(data)

def main():
    horses,pairs,payouts,summary=[],[],[],[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks={pool.submit(worker,rid):rid for rid in RIDS}
        for i,f in enumerate(as_completed(tasks),1):
            rid=tasks[f]
            try:
                hs,ps,paid,s = f.result()
                horses.extend(hs);pairs.extend(ps);payouts.extend(paid);summary.append(s)
                print(str(i).zfill(3)+"/242 "+rid+" win="+str(len(hs))+" wide="+str(len(ps))+" state="+s[4],flush=True)
            except Exception as e:
                summary.append([rid,0,0,"error","error",str(e)[:150],"",0,"","",
                   "https://race.netkeiba.com/race/result.html?race_id="+rid,
                   "https://sports.yahoo.co.jp/keiba/race/odds/wide/"+rid[2:]+"?ninki=0"])
                print("ERROR "+rid+": "+repr(e),flush=True)
    horses.sort(key=lambda x:(x[0],x[1]))
    pairs.sort(key=lambda x:(x[0],x[1],x[2]))
    payouts.sort(key=lambda x:(x[0],x[1],x[2]))
    summary.sort(key=lambda x:x[0])
    write_csv("final_single_and_results_242r.csv",["race_id","horse_no","horse_name","finish","final_win_odds","win_payout_100","place_payout_100","source_url"],horses)
    write_csv("final_wide_all_pairs_242r.csv",["race_id","horse_no_a","horse_no_b","final_wide_low","final_wide_high","source_url"],pairs)
    write_csv("settled_wide_payouts_242r.csv",["race_id","horse_no_a","horse_no_b","wide_payout_100","source_url"],payouts)
    write_csv("coverage_242r.csv",["race_id","horse_count","final_wide_pair_count","result_status","final_wide_status","result_http","wide_http","paying_pairs","wide_payout_mismatches","win_payout_mismatches","result_url","wide_url"],summary)
    manifest={"races":len(RIDS),"horses":len(horses),"wide_pairs":len(pairs),"coverage_complete_win":sum(x[1]>0 for x in summary),"coverage_complete_wide":sum(x[4]=="complete" for x in summary),"other_wide_states":{state:sum(x[4]==state for x in summary) for state in set(x[4] for x in summary)}}
    (OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL",json.dumps(manifest,ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
