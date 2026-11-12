"""Static historical link tests: no third-party network requests."""
from core.jra_historical_odds_links import archived_odds_urls


def test_historical_odds_links_for_saved_kyoto_race():
    identity = {"race_id":"202608050201","mode":"jra"}
    urls = archived_odds_urls(identity, {"race_date":"2026-11-08"})
    assert urls["keibalab"] == "https://www.keibalab.jp/db/race/202611080801/odds.html"
    assert urls["yuma_place"] == "https://www.keiba.jp/db/race/202611080801/odds.html?kind=fuk"


def test_historical_urls_require_valid_identifiers():
    assert not archived_odds_urls({"race_id":"bad","mode":"jra"}, {"race_date":"2026-11-08"})
    assert not archived_odds_urls({"race_id":"202608050201","mode":"nar"}, {"race_date":"2026-11-08"})
    assert not archived_odds_urls({"race_id":"202608050201","mode":"jra"}, {"race_date":"2025-11-08"})
    assert not archived_odds_urls({"race_id":"202608050201","mode":"jra"}, {"race_date":"no date"})
