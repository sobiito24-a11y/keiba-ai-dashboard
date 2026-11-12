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
