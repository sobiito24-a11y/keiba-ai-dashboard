"""JRA graded-race history note ONLY, never an AI ranking adjustment.

Aggregates contain 2021-2025 official JRA graded calendar (695) and
293 race results matched against a public official-result-derived dataset.
Historical outcomes are date-gated to STRICTLY before the displayed race.
No corner positions, race popularity, quinella payouts or post-race feature
engineering is claimed. No impact on NAR, marks or SABCD.
"""
from functools import lru_cache
from html import escape
import json
from pathlib import Path
import re
import unicodedata

DATA = Path(__file__).resolve().parents[1] / "data/jra_graded_trends_2021_2025.json"


def _clean(value):
    s=unicodedata.normalize("NFKC", str(value or ""))
    s=re.sub(r"\s+", "",s)
    s=re.sub(r"^第\d+回","",s)
    s=re.sub(r"[(（][JG\dIVX・]+[)）]$", "",s,flags=re.I)
    return s.replace("ステークス","S").replace("カップ","C")


@lru_cache(maxsize=1)
def _data():
    return json.loads(DATA.read_text(encoding="utf-8"))


def tendency(title, *, mode, race_date, venue="", distance="", surface=""):
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
    if not annual:
        return None
    n=len(annual)
    win10=sum(x["win_payout_yen"]>=1000 for x in annual)
    win20=sum(x["win_payout_yen"]>=2000 for x in annual)
    return dict(name=race_name,grade=entry["grade"],n=n,
                years=sorted(x["year"] for x in annual),
                winner_10x=win10,winner_20x=win20,
                missing_years=[y for y in range(max(2021,year-5),year)
                               if y not in {x["year"] for x in annual}],
                scoring_effect=0, rank_effect=0,
                verified_corner=False, verified_quinella=False,
                history_coverage_pct=_data().get("coverage_pct"))


def render(title, *, mode, race_date, venue="", distance="", surface=""):
    fact=tendency(title,mode=mode,race_date=race_date,venue=venue,
                  distance=distance,surface=surface)
    if not fact:
        return ""
    years="・".join(str(x) for x in fact["years"])
    absent="・".join(str(x) for x in fact["missing_years"])
    note=("※未収録年 " + absent + "。 " if absent else "")
    return ('<p class="graded-history-note" role="note">'
            '<strong>JRA重賞・過去の参考傾向（研究／ランク未反映）</strong> '
            +escape(years)+'年の一致条件 '+str(fact["n"])+'開催｜'
            +'単勝10倍以上の勝ち馬 '+str(fact["winner_10x"])+'／'+str(fact["n"])+'開催、'
            +'20倍以上 '+str(fact["winner_20x"])+'／'+str(fact["n"])+'開催。'
            +escape(note)
            +'4角・脚質・馬連/ワイドの荒れは未検証。'
            +'過去の勝馬配当だけで今回の馬を加点しません。</p>')
