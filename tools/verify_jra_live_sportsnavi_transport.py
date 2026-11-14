"""One-shot, date-gated, public Sports Navi JRA intermediate quote smoke.

2026-11-14 Tokyo 11R (16 horses). No credentials, headers impersonation,
proxy, retries, private API or repeated polling. Executed on CI runner only,
NOT proof of Streamlit Cloud connectivity.
"""
from datetime import datetime

from core.race_odds import JST
from core.jra_sportsnavi_odds import fetch_live_once

NAMES = (
    "ダノンフィーゴ", "クールブロン", "バトルクライ", "アピーリングルック",
    "オメガギネス", "ドンインザムード", "ヘニーガイスト", "エンペラーワケア",
    "トリリオンボーイ", "ジェイパームス", "ドンエレクトス",
    "ロックターミガン", "ライノ", "ハセドン",
    "ルヴァレドクール", "ジャスティンアース",
)
IDENTITY = dict(mode="jra", race_id="202605050311",
                horses=[dict(horse_no=i, name=name)
                        for i, name in enumerate(NAMES, 1)])
RACE_INFO = dict(race_date="2026-11-14")


def main():
    now = datetime.now(JST)
    if now.date().isoformat() != "2026-11-14":
        print("LIVE_SPORTSNAVI_SMOKE:skipped_not_2026_11_14")
        return
    quote = fetch_live_once(IDENTITY, RACE_INFO, now=now)
    assert quote["coverage"]["win"]["count"] == 16
    assert quote["coverage"]["place"]["count"] == 16
    assert quote["availability"] == "unknown"
    assert quote["source_url"].endswith("/2605050311")
    print("LIVE_SPORTSNAVI_SMOKE:success;16_wins;16_places;source_time=" +
          ("present" if quote["observed_at"] else "unknown"))
    print("NOTE: CI runner is not the Streamlit Cloud instance; no guarantee of current prices.")


if __name__ == "__main__":
    main()
