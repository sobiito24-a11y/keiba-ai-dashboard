"""One-shot transport diagnostics for three PUBLIC JRA historical providers.

Run in a separate CI runner. This only verifies the CI runner's outbound
access, not Streamlit Cloud's distinct network. No retries, cookies, login,
proxy, access restrictions workarounds, or raw page logging.
"""
from datetime import datetime
import json
import requests

from core.jra_historical_odds_links import archived_odds_urls
from core.jra_odds_connection_errors import describe_connection

IDENTITY = dict(mode="jra", race_id="202605050211")
INFO = dict(race_date="2026-11-08")
HEADERS = {"Accept": "text/html,application/xhtml+xml"}

urls=archived_odds_urls(IDENTITY,INFO)
results=[]
for label in ("yuma_win","yuma_place","keibalab","sportsnavi"):
    url=urls[label]
    started=datetime.now()
    result=dict(source=label,status="unknown")
    try:
        resp=requests.get(url,timeout=8,allow_redirects=False,headers=HEADERS)
        result.update(status=f"HTTP {resp.status_code}",
                      content_bytes=len(resp.content),
                      redirected_to_login=False)
        # Do not print HTML, source URL, response headers or content.
        if resp.status_code==200:
            result["html_candidate"]=(
                "html" in resp.headers.get("Content-Type","").lower()
                and len(resp.content)>200)
            if label == "sportsnavi" and result["html_candidate"]:
                # This is a separately bounded parser smoke; only public odds,
                # with the historical 18-horse Tokyo 11R research fixture.
                try:
                    from core.jra_sportsnavi_odds import parse_sportsnavi_html
                    from tests.test_jra_sportsnavi_odds import ID, INFO
                    from core.race_odds import JST, overlay
                    quote=parse_sportsnavi_html(
                        resp.content,ID,INFO,now=datetime.now(JST))
                    result["parsed_race_matched"]=True
                    result["parsed_win_count"]=quote["coverage"]["win"]["count"]
                    result["parsed_place_count"]=quote["coverage"]["place"]["count"]
                    shown=overlay([dict(no=str(i)) for i in range(1,19)],quote,
                                  "CI公開HTML検証")
                    result["overlaid_win_count"]=sum(x["odds"]!="—" for x in shown)
                except Exception as exc:
                    result["parsed_race_matched"]=False
                    # Restrict output to error type and first safe diagnostic.
                    result["parse_failure"]=(
                        type(exc).__name__ + "：" +
                        str(exc).split("\n")[0][:140])
    except Exception as exc:
        result["status"]=describe_connection(exc)
    result["elapsed_seconds"]=round((datetime.now()-started).total_seconds(),2)
    results.append(result)
print("JRA_PUBLIC_PROVIDER_TRANSPORT:"+json.dumps(results,ensure_ascii=False))
print("NOTE: CI runner results do not establish Streamlit Cloud connectivity.")
