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
    assert "disabled=False" in live
    assert "from .jra_netkeiba_odds import fetch_once" in live
    assert "180" in live  # per-race free odds cooldown
    assert "NAR公式ZIPモード" in live
    assert "fetch_daily, parse_daily_zip, locator" in live
    assert "JRAオッズ更新（試験）" in live
    assert "JRA公式ZIP" not in live
    assert "st.caption('オンライン更新は未設定です。" not in live


def test_new_manual_update_is_available_for_both_circuits():
    panel = (ROOT / "core" / "race_odds_ui_live.py").read_text(encoding="utf-8")
    assert "disabled=False" in panel
    assert "fetch_daily" in panel and "fetch_once" in panel
    assert "connection.available" in panel  # preferred when configured
    assert "min_delay = 30 if connection.available else 180" in panel
    assert "'_jra_free_odds_global_request'" in panel


def test_jra_free_odds_source_links_not_false_live_quotes():
    panel = (ROOT / "core" / "race_odds_ui_live.py").read_text(encoding="utf-8")
    assert "if not is_nar:" in panel
    assert "https://www.jra.go.jp/" in panel
    assert "https://race.netkeiba.com/odds/index.html?race_id=" in panel
    assert "jra_id = identity['race_id']" in panel
    assert "JRAオッズ更新（試験）" in panel
    assert "無料版には更新間隔" in panel
    # Free type=init observations are not official JRA realtime prices.
    assert "JRA公式の直接取得ではありません" in panel
    assert "予想オッズを代用しません" in panel
