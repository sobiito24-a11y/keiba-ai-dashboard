"""Five complete years of JRA graded-race RESULT research (2021--2025).

Public research CSV: https://github.com/whitedogk/jra-condition-app
Provider describes extraction from JRA official race-result pages.
Not a source of pre-race features, corner positions or exact race quinella.
Only aggregated non-identifying derived statistics are emitted; raw dataset is
never stored in this repository. No model scores/marks are adjusted here.

Run:
    python tools/research_jra_graded_history.py --source-url ... --output -
Output includes begin/end sentinels for GitHub Actions log collection.
"""
import argparse
import collections
import csv
import io
import json
import re
import sys
import urllib.request
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

SOURCE_URL = "https://raw.githubusercontent.com/whitedogk/jra-condition-app/main/jra-results-actual.csv"
GRADE = {"G1":"G1","GI":"G1","GⅠ":"G1",
         "G2":"G2","GII":"G2","GⅡ":"G2",
         "G3":"G3","GIII":"G3","GⅢ":"G3"}
MAX_BYTES = 40_000_000
YEARS = frozenset(range(2021, 2026))
START, END = "BEGIN_JRA_GRADED_JSON:", ":END_JRA_GRADED_JSON"


def normalize_grade(value):
    raw = str(value or "").upper().replace(" ", "").replace("Ｇ","G")
    if raw.startswith(("J-G","J・G","J.G","JG","障")):
        return None  # jump results need an independent pace model
    return GRADE.get(raw)


def to_num(value):
    try:
        d = Decimal(str(value or "").replace(",","").replace("倍","").strip())
    except (InvalidOperation, ValueError):
        return None
    return float(d) if d.is_finite() and d >= 0 else None


def clean_name(value):
    return re.sub(r"[\s　]+", "", str(value or "").replace("ステークス","S").replace("カップ","C"))


def load_csv(url, *, local=None):
    if local:
        blob = Path(local).read_bytes()
    else:
        req = urllib.request.Request(url,headers={"User-Agent":"JRA-Graded-Research/1.0 (research aggregate)"})
        with urllib.request.urlopen(req,timeout=35) as response:
            if response.status != 200:
                raise RuntimeError("Public results CSV returned HTTP " + str(response.status))
            blob = response.read(MAX_BYTES + 1)
    if len(blob) > MAX_BYTES:
        raise RuntimeError("Research CSV exceeds 40MB limit")
    return csv.DictReader(io.StringIO(blob.decode("utf-8-sig")))


def summarize(reader):
    headers = reader.fieldnames or []
    required = ("date","course","surface","distance","race","raceName","raceClass","finish","horseNumber","winPayout")
    missing = [x for x in required if x not in headers]
    if missing:
        raise ValueError("Missing required research columns: "+",".join(missing))
    keys = ["finalOdds","winOdds","odds","popularity","corner4","fourthCorner","raceNumber"]
    present = [k for k in keys if k in headers]
    grouped = collections.defaultdict(list)
    for row in reader:
        daytext = (row.get("date") or "").strip()
        try:
            d = date.fromisoformat(daytext)
        except ValueError:
            continue
        if d.year not in YEARS:
            continue
        grade = normalize_grade(row.get("raceClass"))
        if not grade:
            continue
        course = str(row.get("course") or "").strip()
        no = str(row.get("race") or "").strip()
        race_name = clean_name(row.get("raceName"))
        if not course or not no.isdecimal() or not race_name:
            continue
        grouped[(daytext,course,int(no))].append(row)
    events = []
    wrong_grade, missing_winner, duplicate_winner = [], [], []
    for (day, course, no), rows in sorted(grouped.items()):
        grades = {normalize_grade(r.get("raceClass")) for r in rows}
        titles = {clean_name(r.get("raceName")) for r in rows}
        if len(grades)!=1 or len(titles)!=1:
            wrong_grade.append((day,course,no));continue
        winners=[r for r in rows if str(r.get("finish") or "").strip() in ("1","1.0")]
        if not winners:
            missing_winner.append((day,course,no));continue
        if len(winners)>1:
            duplicate_winner.append((day,course,no));continue
        win=winners[0]
        payout=to_num(win.get("winPayout"))
        try: distance=int(float(str(win.get("distance")).replace(",","")))
        except (ValueError,TypeError): distance=0
        odds_key=next((k for k in ("finalOdds","winOdds","odds") if k in headers),None)
        popularity_key=next((k for k in ("popularity","popularityRank") if k in headers),None)
        popularity=None
        if popularity_key and (val:=to_num(win.get(popularity_key))):
            if int(val)==val and val>0: popularity=int(val)
        elif odds_key:
            valid=[to_num(r.get(odds_key)) for r in rows]
            own=to_num(win.get(odds_key))
            if own is not None and all(v is not None and v>0 for v in valid):
                # Tied odds have a shared rank, not a guaranteed betting popularity.
                popularity=1+sum(v<own for v in valid)
        surface=str(win.get("surface") or "").strip()
        if not surface or not distance or payout is None:
            missing_winner.append((day,course,no));continue
        events.append(dict(date=day,course=course,race_no=no,title=next(iter(titles)),
                           grade=next(iter(grades)),surface=surface,distance=distance,
                           runners=len(rows),winner_win_payout_yen=payout,
                           winner_popularity=popularity))
    year_counts=collections.Counter(int(e["date"][:4]) for e in events)
    grade_counts=collections.Counter(e["grade"] for e in events)
    by_title=collections.defaultdict(list)
    for e in events:
        by_title[e["title"]].append(e)

    def statistics(subset):
        n=len(subset)
        if not n:return dict(n=0)
        amounts=[e["winner_win_payout_yen"] for e in subset]
        known_pop=[e["winner_popularity"] for e in subset if e["winner_popularity"] is not None]
        return dict(n=n,years=sorted(set(int(e["date"][:4]) for e in subset)),
                    winner_10x=sum(v>=1000 for v in amounts),
                    winner_20x=sum(v>=2000 for v in amounts),
                    winner_50x=sum(v>=5000 for v in amounts),
                    median_winning_odds_yen=sorted(amounts)[(n-1)//2],
                    winner_popularity_known=len(known_pop),
                    winner_popularity_6plus=sum(v>=6 for v in known_pop),
                    winner_popularity_10plus=sum(v>=10 for v in known_pop),
                    winners_with_corner4=0)
    summaries=[]
    for name, group in sorted(by_title.items()):
        group.sort(key=lambda e:e["date"])
        s=statistics(group)
        s.update(name=name, grade=group[-1]["grade"],
                 courses=sorted(set(e["course"] for e in group)),
                 conditions=sorted(set(f"{e['course']}/{e['surface']}{e['distance']}" for e in group)),
                 annual=[dict(year=e["date"][:4],winner_popularity=e["winner_popularity"],
                              winner_win_payout_yen=e["winner_win_payout_yen"],
                              venue=e["course"],distance=e["distance"],
                              surface=e["surface"]) for e in group])
        summaries.append(s)
    groups=collections.defaultdict(list)
    for e in events:
        groups[(e["course"],e["surface"],e["distance"],e["grade"])].append(e)
    comparable=[dict(course=k[0],surface=k[1],distance=k[2],grade=k[3],
                     **statistics(group)) for k,group in groups.items() if len(group)>=4]
    return dict(schema_version=1,period="2021–2025",
                data_source="JRA公式結果から作成された公開研究CSV（whitedogk/jra-condition-app）",
                source_url=SOURCE_URL, complete_full_years=True,
                fields=list(headers), available_optional_fields=present,
                methodological_notes=[
                   "全重賞の結果から勝ち馬の単勝払戻・人気を調べる。4角通過順位や馬連配当は元CSVにないため、この集計では推定しない",
                   "重賞名の統合では短縮表記だけ統一。名称変更・施行条件変更は分けて解釈する",
                   "勝ち馬の単勝払戻が1000円以上を10倍以上と数える。馬連・ワイドが荒れた保証ではない",
                   "対象年の結果を同年の予想根拠として使わない。原則2021–24学習・2025年独立検証",
                   "集計値だけで馬ごとのSABCDランクを調整しない。予測4角・適性との条件付き相関を検証してから採用する",
                ],
                total_graded_races=len(events),
                year_counts={str(k):year_counts[k] for k in sorted(YEARS)},
                grade_counts=dict(grade_counts),
                invalid_event_counts=dict(mixed_grade=len(wrong_grade),
                                          missing_winner_or_data=len(missing_winner),
                                          duplicate_winner=len(duplicate_winner)),
                total_distinct_names=len(summaries),
                winner_10x_all=sum(e["winner_win_payout_yen"]>=1000 for e in events),
                winner_20x_all=sum(e["winner_win_payout_yen"]>=2000 for e in events),
                winners_with_popularity=sum(e["winner_popularity"] is not None for e in events),
                winners_with_corner4=0,
                by_race=summaries,
                by_condition=comparable)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-url",default=SOURCE_URL)
    parser.add_argument("--file",default=None)
    parser.add_argument("--output",default="-")
    args=parser.parse_args()
    report=summarize(load_csv(args.source_url,local=args.file))
    raw=json.dumps(report,ensure_ascii=False,separators=(",",":"),sort_keys=True)
    if args.output=="-":
        print("RESEARCH_HEADERS:"+",".join(report["fields"]))
        print("RESEARCH_COVERAGE:"+json.dumps({k:report[k] for k in
              ("year_counts","grade_counts","total_graded_races","total_distinct_names",
               "winner_10x_all","winner_20x_all","winners_with_popularity","winners_with_corner4",
               "invalid_event_counts")},ensure_ascii=False))
        print(START)
        for i in range(0, len(raw), 3000):
            print("RESEARCH_JSON_PART:" + str(i//3000) + ":" + raw[i:i+3000])
        print(END)
    else:
        Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",
                                     encoding="utf-8")


if __name__=="__main__":
    main()
