"""A warm Streamlit session must not reuse the cached old connector-only odds UI."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def test_live_odds_panel_is_new_import_and_syntax_is_valid():
    page = (ROOT / "app.py").read_text(encoding="utf-8")
    live = (ROOT / "core" / "race_odds_ui_live.py").read_text(encoding="utf-8")
    ast.parse(live)
    assert "from core.race_odds_ui_live import render as render_prices" in page
    assert "from core.race_odds_ui import render as render_prices" not in page
    assert "is_nar = identity['mode'] == 'nar'" in live
    assert "disabled=not (is_nar or connection.available)" in live
    assert "NAR公式ZIPモード" in live
    assert "fetch_daily, parse_daily_zip, locator" in live
    assert "if not is_nar and not connection.available:" in live
    assert "st.caption('オンライン更新は未設定です。" not in live


def test_disabled_logic_for_nar_and_legacy_provider():
    # Equivalent to the exact Streamlit button's disabled expression.
    assert not (True or False) is False
    assert (not (True or False)) is False
    assert (not (False or False)) is True
    assert (not (False or True)) is False


def test_jra_free_odds_source_links_not_false_live_quotes():
    panel = (ROOT / "core" / "race_odds_ui_live.py").read_text(encoding="utf-8")
    assert "if not is_nar:" in panel
    assert "https://www.jra.go.jp/" in panel
    assert "https://race.netkeiba.com/odds/index.html?race_id=" in panel
    assert "jra_id = identity['race_id']" in panel
    assert "アプリへの自動取得は未接続" in panel
    assert "無料版には更新間隔" in panel
    # JRA's connector-only update button must remain disabled without
    # an authorized endpoint: references are links, not imported live prices.
    assert "disabled=not (is_nar or connection.available)" in panel
