"""JRA graded-race history note ONLY, never an AI ranking adjustment.

Aggregates contain 2021-2025 official JRA graded calendar (695) and
293 race results matched against a public official-result-derived dataset.
Historical outcomes are date-gated to STRICTLY before the displayed race.
Only selected JRA-verified races additionally contain historical corner, pace,
popularity and going. Unverified fields stay unknown. No impact on NAR, marks or SABCD.
"""
from functools import lru_cache
from html import escape
import json
from pathlib import Path
import re
import unicodedata

DATA = Path(__file__).resolve().parents[1] / "data/jra_graded_trends_2021_2025.json"
VERIFIED = Path(__file__).resolve().parents[1] / "data/jra_graded_verified_examples.json"


def _clean(value):
    s=unicodedata.normalize("NFKC", str(value or ""))
    s=re.sub(r"\s+", "",s)
    s=re.sub(r"^第\d+回","",s)
    s=re.sub(r"[(（][JG\dIVX・]+[)）]$", "",s,flags=re.I)
    return s.replace("ステークス","S").replace("カップ","C")


@lru_cache(maxsize=1)
def _data():
    return json.loads(DATA.read_text(encoding="utf-8"))

@lru_cache(maxsize=1)
def _verified():
    return json.loads(VERIFIED.read_text(encoding="utf-8")).get("races", {})


def tendency(title, *, mode, race_date, venue="", distance="", surface="", going=""):
    """Date-safe and course-aware race history. No score or odds alteration."""
    if str(mode or "").lower()!="jra":
        return None
    race_name = _clean(title)
    if not race_name:
        return None
    # Never assign a generic course trend to a named non-graded race.
    by_name = {x["name"]:x for x in _data()["race_tendencies"]}
    entry = by_name.get(race_name)
    if entry is None:
        return None
    try:
        year=int(str(race_date)[:4])
    except (TypeError,ValueError):
        return None
    location=_clean(venue).replace("競馬場","")
    length=str(distance or "")
    match=re.search(r"(\d[\d,]{2,4})\s*(?:m|メートル)?",length)
    meters=int(match.group(1).replace(",","")) if match else None
    condition=_clean(surface)
    if "ダート" in condition or condition.startswith("ダ"):condition="ダ"
    elif "芝" in condition:condition="芝"
    elif "障" in condition:condition="障"
    else:condition=""
    # Filter the 2021-2025 results to the exact current course. Relocated
    # events must never be treated as identical pace/corner conditions.
    annual=[x for x in entry["annual"] if x["year"]<year
            and (not location or x["venue"]==location)
            and (not meters or x["distance"]==meters)
            and (not condition or x["surface"]==condition)]
    example=_verified().get(race_name)
    # Verified year-by-year records are authoritative for their OWN venue,
    # distance and surface. A relocated running is NOT a course match.
    verified_corner=False
    nonmatch_years=[]
    if example:
        all_verified=[dict(x) for x in example.get("annual", ())
                      if x["year"] < year]
        compatible=(not location or _clean(example.get("venue"))==location) and (
            not meters or example.get("distance")==meters) and (
            not condition or example.get("surface")==condition)
        if compatible:
            annual=[x for x in all_verified if
                    (not location or x.get("venue", example.get("venue"))==location)
                    and (not meters or x.get("distance", example.get("distance"))==meters)
                    and (not condition or x.get("surface", example.get("surface"))==condition)]
            nonmatch_years=sorted({x["year"] for x in all_verified if x not in annual})
            verified_corner=bool(annual) and all(isinstance(x.get("winner_corner4"), int) for x in annual)
    if not annual:
        return None
    n=len(annual)
    win10=sum(x["win_payout_yen"]>=1000 for x in annual)
    win20=sum(x["win_payout_yen"]>=2000 for x in annual)
    grounds=("良","稍重","重","不良")
    goings={g:sum(x.get("going")==g for x in annual) for g in grounds}
    goings={g:count for g,count in goings.items() if count}
    going_observations=sum(goings.values())
    current_going=str(going or "").strip()
    current_going=current_going if current_going in grounds else ""
    ages=[x["winner_age"] for x in annual if isinstance(x.get("winner_age"),int)]
    pace=[x for x in annual if isinstance(x.get("first_1000_sec"),(int,float))
          and isinstance(x.get("last_1000_sec"),(int,float))]
    past_years={x["year"] for x in annual}
    expected={y for y in range(max(2021,year-5),year)}
    return dict(name=race_name,grade=entry["grade"],n=n,
                years=sorted(past_years),winner_10x=win10,winner_20x=win20,
                winner_popularity_max=max((x.get("winner_popularity") or 0 for x in annual),default=0) if verified_corner else None,
                front3=sum(x.get("winner_corner4",999)<=3 for x in annual) if verified_corner else None,
                rear10=sum(x.get("winner_corner4",0)>=10 for x in annual) if verified_corner else None,
                going_counts=goings,going_observations=going_observations,
                going_unknown=n-going_observations,current_going=current_going,
                matching_going=goings.get(current_going,0) if current_going else None,
                young_winner_count=sum(x<=4 for x in ages) if ages else None,
                age_observations=len(ages),
                late_faster=sum(x["last_1000_sec"]<x["first_1000_sec"] for x in pace) if pace else None,
                pace_observations=len(pace),
                relocated_years=nonmatch_years,
                missing_years=sorted(expected - past_years - set(nonmatch_years)),
                scoring_effect=0,rank_effect=0,
                verified_corner=verified_corner,verified_quinella=False,
                history_coverage_pct=_data().get("coverage_pct"))

def render(title, *, mode, race_date, venue="", distance="", surface="", going=""):
    """Display observed historical context without changing model ranks."""
    fact=tendency(title,mode=mode,race_date=race_date,venue=venue,
                  distance=distance,surface=surface,going=going)
    if not fact:
        return ""
    years="・".join(str(x) for x in fact["years"])
    parts=[escape(years)+"年の同一開催条件 "+str(fact["n"])+"開催"]
    if fact["verified_corner"] and fact["winner_popularity_max"]:
        parts.append("勝ち馬の最高人気 "+str(fact["winner_popularity_max"])+"番人気")
    else:
        parts.append("勝ち馬10倍以上 "+str(fact["winner_10x"])+"／"+str(fact["n"])+"開催")
    if fact["going_observations"]:
        grounds="・".join(f"{g}{v}回" for g,v in fact["going_counts"].items())
        parts.append("馬場 "+grounds+"（確認"+str(fact["going_observations"])+
                     "／"+str(fact["n"])+"）")
        if fact["current_going"]:
            parts.append("今回"+fact["current_going"]+"と同馬場 "+
                         str(fact["matching_going"])+"／"+str(fact["n"])+"回")
        if not any(g in fact["going_counts"] for g in ("稍重","重","不良")):
            parts.append("道悪実績なし・道悪傾向は未検証")
    else:
        parts.append("過去の馬場状態は未取得・馬場傾向は未検証")
    if fact["verified_corner"]:
        parts.append("勝ち馬4角3番手以内 "+str(fact["front3"])+"／"+
                     str(fact["n"])+"、10番手以下 "+str(fact["rear10"])+"／"+
                     str(fact["n"]))
    else:
        parts.append("4角・脚質は未検証")
    if fact["pace_observations"]:
        parts.append("後半1000mが速い "+str(fact["late_faster"])+"／"+
                     str(fact["pace_observations"])+"開催")
    else:
        parts.append("ラップ・ペースは未検証")
    if fact["age_observations"]:
        parts.append("勝ち馬4歳以下 "+str(fact["young_winner_count"])+
                     "／"+str(fact["age_observations"])+"開催")
    if fact["relocated_years"]:
        parts.append("別競馬場開催 "+ "・".join(str(y) for y in fact["relocated_years"])+"年は除外")
    if fact["missing_years"]:
        parts.append("未収録年 "+ "・".join(str(y) for y in fact["missing_years"]))
    parts.append("過去実績は参考情報。今回の順位・印・加点には未反映")
    return ('<p class="graded-history-note" role="note">'
            '<strong>JRA重賞・過去の参考傾向（研究／ランク未反映）</strong> '
            + "。".join(escape(part) for part in parts) + "。</p>")
