"""Current race-odds panel contract: usable JRA/NAR buttons and truthful quotes.

Old 2026-11-13 JRA試験版 labels and one-source-only assertions were stale.
The actual UI now offers JRA same-day three-source fallback and NAR ZIP.
Tests must guard behavior rather than pin a retired UI caption.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _panel():
    text = (ROOT / "core" / "race_odds_ui_live.py").read_text(encoding="utf-8")
    ast.parse(text)
    return text


def test_warm_streamlit_session_imports_current_panel_not_cached_legacy():
    page = (ROOT / "app.py").read_text(encoding="utf-8")
    text = _panel()
    assert "from core import race_odds_ui_live as odds_ui_module" in page
    assert "importlib.reload(odds_ui_module).render" in page
    assert "from core.race_odds_ui_live import render as render_prices" not in page
    assert "from core.race_odds_ui import render as render_prices" not in page
    assert "is_nar = identity['mode'] == 'nar'" in text
    assert "取得した全頭の照合表・保存" in text


def test_jra_today_price_fetch_is_enabled_for_actual_race_date_only():
    text = _panel()
    assert "if st.button('当日リアルオッズ取得'" in text
    assert "disabled=not is_today" in text
    assert "date.fromisoformat" in text or "_date.fromisoformat" in text
    assert "180" in text  # One race: delayed repeated reads.
    assert "'_jra_free_odds_global_request'" in text
    assert "30" in text  # Minimum global cooldown for public sources.
    assert "保存オッズは代用しません" in text
    assert "quote['coverage']['win']['count']" in text
    assert "quote['coverage']['place']['count']" in text


def test_jra_sources_in_declared_fallback_order_with_own_race_links():
    text = _panel()
    assert "https://www.jra.go.jp/" in text
    assert "https://race.netkeiba.com/odds/index.html?race_id=" in text
    assert "jra_id = identity['race_id']" in text
    first = text.index("fetch_live_once as fetch_sports_live")
    official = text.index("fetch_once as fetch_jra_official")
    alternative = text.index("from .jra_netkeiba_odds import fetch_once as fetch_free")
    assert first < official < alternative
    assert "JRA公式の直接取得ではありません" not in text  # May use official after Sports Navi.
    assert "アクセスが制限された場合はスクショ・HTML取込を使用" in text


def test_nar_official_zip_is_kept_separate_from_jra_public_live():
    text = _panel()
    assert "fetch_daily, parse_daily_zip, locator" in text
    assert "fetch_monthly, parse_monthly_zip" in text
    assert "if is_nar:" in text
    assert "NAR公式ZIP" in text


def test_result_and_price_rows_display_near_buttons_and_before_manual_form():
    text = _panel()
    live = text.index("if st.button('当日リアルオッズ取得")
    notice = text.index("notice = st.session_state.get(key+'_status')")
    manual = text.index('with st.expander("直前オッズを数行')
    assert live < notice < manual
    assert "st.error('オッズ更新結果：" in text
    assert "st.warning('オッズ更新結果：" in text
    assert "st.success('オッズ更新結果：" in text
    assert "st.dataframe(singles, hide_index=True" in text
    assert "配信元更新：" in text
    assert "active_observation" in text
    assert text.count("notice = st.session_state.get(key+'_status')") == 1
