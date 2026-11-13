"""Research ALL 2021--2025 JRA graded races, without inventing pace or odds.

Graded event dates, venues, names, grade and winners are sourced from the five
JRA official annual graded-race tables, retained as
data/jra_graded_calendar_2021_2025.json.
CSV of official-result-derived runner outcomes/solo winner win payouts:
https://github.com/whitedogk/jra-condition-app

The public CSV does NOT contain raceClass, raceName, popularity, corner
positions or quinella. Match each event to the winner by date + venue +
horse name, then use date + venue + race number to count the complete field.
Never use an event's own outcome to produce a same-year prediction.
This is race-level retrospective research, NOT a horse-specific score.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import io
import json
from pathlib import Path
import re
import unicodedata
from urllib.request import Request, urlopen

SOURCE_URL = "https://raw.githubusercontent.com/whitedogk/jra-condition-app/main/jra-results-actual.csv"
CALENDAR = Path(__file__).resolve().parents[1] / "data/jra_graded_calendar_2021_2025.json"
MAX_BYTES = 40_000_000
YEARS = range(2021, 2026)


def normalize(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or "")))


def scalar(value):
    try:
        n = Decimal(str(value or "").replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    return float(n) if n.is_finite() and n >= 0 else None


def load_csv(url=SOURCE_URL, *, local=None):
    if local:
        blob = Path(local).read_bytes()
    else:
        request = Request(url, headers={"User-Agent": "JRA-Five-Year-Aggregate/1.0"})
        with urlopen(request, timeout=45) as response:
            if response.status != 200:
                raise ValueError(f"公開実績CSVがHTTP {response.status}を返しました")
            blob = response.read(MAX_BYTES + 1)
    if len(blob) > MAX_BYTES:
        raise ValueError("研究用CSVが40MBを超えています")
    return csv.DictReader(io.StringIO(blob.decode("utf-8-sig")))


def summary(rows, calendar):
    required = ("date", "course", "surface", "distance", "race", "finish",
                "horseNumber", "horse", "winPayout")
    fields = rows.fieldnames or []
    if not all(x in fields for x in required):
        raise ValueError("公開CSVに必要な列がありません: " +
                         ",".join(x for x in required if x not in fields))
    events = calendar["events"]
    if len(events) < 600 or set(calendar.get("years", [])) != set(YEARS):
        raise ValueError("JRA公式5年間の重賞暦が不完全です")
    runners = defaultdict(list)
    winners = defaultdict(list)
    for row in rows:
        day = row.get("date","")
        try:
            year=int(day[:4])
        except (ValueError,TypeError):
            continue
        if year not in YEARS: continue
        number=str(row.get("race") or "")
        if not number.isdecimal():continue
        course=str(row.get("course") or "").strip()
        key=(day,course,int(number))
        runners[key].append(row)
        finish=normalize(row.get("finish"))
        if finish in ("1","1.0"):
            winners[(day,course,normalize(row.get("horse")))].append(key)
    matched=[]
    unmatched=[]
    ambiguity=[]
    for event in events:
        day,venue=event["date"],event["venue"]
        win_names=event["winners"]
        match_keys=set()
        for name in win_names:
            match_keys.update(winners.get((day,venue,normalize(name)),[]))
        if not match_keys:
            unmatched.append(dict(date=day,venue=venue,title=event["title"],winners=win_names))
            continue
        if len(match_keys)>1:
            ambiguity.append(dict(date=day,venue=venue,title=event["title"],candidate_races=sorted(k[2] for k in match_keys)))
            continue
        key=next(iter(match_keys))
        field=runners[key]
        if not field: continue
        actual_winners=[r for r in field if normalize(r.get("finish")) in ("1","1.0")]
        if not all(normalize(name) in [normalize(x.get("horse")) for x in actual_winners] for name in win_names):
            ambiguity.append(dict(date=day,venue=venue,title=event["title"],reason="勝ち馬の一致不完全"))
            continue
        if any(normalize(r.get("surface"))!=normalize(event["surface"]) or
               int(float(r.get("distance") or 0))!=event["distance"] for r in field):
            ambiguity.append(dict(date=day,venue=venue,title=event["title"],reason="芝ダート・距離不一致"))
            continue
        amounts=[scalar(r.get("winPayout")) for r in actual_winners]
        if not amounts or any(x is None for x in amounts):
            unmatched.append(dict(date=day,venue=venue,title=event["title"],reason="単勝払戻不明"))
            continue
        matched.append(dict(date=day,venue=venue,title=event["title"],
                            grade=event["grade"],jump=event["jump"],
                            surface=event["surface"],distance=event["distance"],
                            field_size=len(field),
                            winner_win_payouts_yen=amounts,
                            any_winner_10x=any(v>=1000 for v in amounts),
                            any_winner_20x=any(v>=2000 for v in amounts),
                            any_winner_50x=any(v>=5000 for v in amounts)))
    flats=[e for e in matched if not e["jump"]]
    year_count=Counter(int(x["date"][:4]) for x in matched)
    calendar_count=Counter(int(x["date"][:4]) for x in events)
    by_name=defaultdict(list)
    by_condition=defaultdict(list)
    for event in flats:
        by_name[event["title"]].append(event)
        by_condition[(event["venue"],event["surface"],event["distance"],event["grade"])].append(event)
    def stats(group):
        n=len(group)
        if n==0: return dict(n=0)
        return dict(n=n, years=sorted({int(x["date"][:4]) for x in group}),
                    winner_10x=sum(x["any_winner_10x"] for x in group),
                    winner_20x=sum(x["any_winner_20x"] for x in group),
                    winner_50x=sum(x["any_winner_50x"] for x in group),
                    # A race with two first-place finishers is still ONE event.
                    median_winner_payout_yen=sorted(max(x["winner_win_payouts_yen"]) for x in group)[(n-1)//2])
    per_race=[]
    for name, group in sorted(by_name.items()):
        group.sort(key=lambda x:x["date"])
        entry=stats(group)
        entry.update(name=name,grade=group[-1]["grade"],
                     conditions=sorted({f"{e['venue']}/{e['surface']}{e['distance']}" for e in group}),
                     annual=[dict(year=int(e["date"][:4]),venue=e["venue"],
                                  surface=e["surface"],distance=e["distance"],
                                  win_payout_yen=max(e["winner_win_payouts_yen"]),
                                  upset10=e["any_winner_10x"],upset20=e["any_winner_20x"])
                             for e in group])
        per_race.append(entry)
    pooled=[]
    for (venue,surface,distance,grade),group in sorted(by_condition.items()):
        if len(group)<8:continue
        entry=stats(group)
        entry.update(venue=venue,surface=surface,distance=distance,grade=grade)
        pooled.append(entry)
    train=[e for e in flats if e["date"][:4]<"2025"]
    holdout=[e for e in flats if e["date"][:4]=="2025"]
    prior_rate=sum(e["any_winner_10x"] for e in train)/len(train) if train else 0
    by_name_train=defaultdict(list)
    for x in train:by_name_train[x["title"]].append(x)
    # Shrink four observations per title toward the global G1-3 frequency.
    # Report holdout Brier error: useful to judge predictive value as an
    # upset-frequency descriptor, NOT proof of a horse-specific ranking edge.
    base_sq=0; local_sq=0
    for race in holdout:
        past=by_name_train.get(race["title"],[])
        posterior=(sum(x["any_winner_10x"] for x in past)+20*prior_rate)/(len(past)+20)
        y=int(race["any_winner_10x"])
        base_sq+=(prior_rate-y)**2
        local_sq+=(posterior-y)**2
    return dict(schema_version=1,period="2021-2025",source="JRA公式重賞一覧 × JRA公式レース結果由来の公開CSV",
                calendar_url="https://www.jra.go.jp/datafile/seiseki/replay/",
                outcomes_url=SOURCE_URL, source_csv_fields=fields,
                all_graded_calendar_events=len(events),
                matched_graded_events=len(matched),
                matched_flat_events=len(flats),
                year_calendar_counts={str(y):calendar_count[y] for y in YEARS},
                year_matched_counts={str(y):year_count[y] for y in YEARS},
                coverage_pct=round(100*len(matched)/len(events),2),
                missing_events=unmatched[:30],
                ambiguous_events=ambiguity[:30],
                has_corner_positions=False, has_horse_popularity=False,
                has_quinella_payouts=False,
                flat_graded_overall=stats(flats),
                brier_2025_winner10=dict(n=len(holdout),
                     global_prior=round(prior_rate,5),
                     baseline=round(base_sq/len(holdout),6) if holdout else None,
                     title_shrunk=round(local_sq/len(holdout),6) if holdout else None),
                race_tendencies=per_race, pooled_conditions=pooled,
                research_limitations=[
                    "4角位置、ラップ・ペースは公開CSVにないため、展開や前残りは未検証",
                    "人気順位・馬連/ワイド配当は元CSVにないため、人気別的中や馬連荒れは未検証",
                    "単勝1000円以上の勝ち馬がいるレースを「10倍以上勝利」と数える",
                    "単勝払戻だけでは3着内の穴馬率・荒れ確率の確率校正はできない",
                    "同名レースでも開催場・距離が変わる年は表示で分離する",
                    "2025年ホールドアウト評価が有利でも馬別評価への加点根拠にはならない",
                ])


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--file")
    p.add_argument("--calendar",default=str(CALENDAR))
    p.add_argument("--output",default="-")
    args=p.parse_args()
    calendar=json.loads(Path(args.calendar).read_text(encoding="utf-8"))
    output=summary(load_csv(local=args.file),calendar)
    raw=json.dumps(output,ensure_ascii=False,separators=(",",":"),sort_keys=True)
    if args.output=="-":
        print("RESEARCH_COUNTS:"+json.dumps({k:output[k] for k in
              ("all_graded_calendar_events","matched_graded_events",
               "matched_flat_events","coverage_pct","year_calendar_counts",
               "year_matched_counts","brier_2025_winner10")},ensure_ascii=False))
        print("BEGIN_JRA_GRADED_JSON:")
        for i in range(0,len(raw),3000):
            print("RESEARCH_JSON_PART:"+str(i//3000)+":"+raw[i:i+3000])
        print(":END_JRA_GRADED_JSON")
    else:
        Path(args.output).write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


if __name__=="__main__":
    main()
