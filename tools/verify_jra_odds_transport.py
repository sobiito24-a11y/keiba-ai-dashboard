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
    except Exception as exc:
        result["status"]=describe_connection(exc)
    result["elapsed_seconds"]=round((datetime.now()-started).total_seconds(),2)
    results.append(result)
print("JRA_PUBLIC_PROVIDER_TRANSPORT:"+json.dumps(results,ensure_ascii=False))
print("NOTE: CI runner results do not establish Streamlit Cloud connectivity.")
