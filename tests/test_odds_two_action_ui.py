"""Guard against odds-page UI regressions: two main JRA buttons, other tools collapsed.

The live JRA page is never scraped automatically: only a user click triggers
JRA official and then the free fallback; prior archived observations stay
selectable and do not become same-day quotes.
"""
from pathlib import Path

def test_jra_odds_has_two_primary_actions_and_collapsed_backups():
    path = Path(__file__).parents[1] / "core" / "race_odds_ui_live.py"
    code = path.read_text(encoding="utf-8")
    assert "st.button('過去オッズ取得'" in code
    assert "st.button('当日リアルオッズ取得'" in code
    assert "st.button('過去単複をAIへ反映（優馬JAPAN）'" not in code
    assert "st.button('オッズ更新（無料・試験）'" not in code
    assert "st.button('JRA公式から単複取得（試験）'" not in code
    assert "disabled=not is_past" in code
    assert "disabled=not is_today" in code
    assert "from .jra_historical_odds_failover import fetch_once as fetch_historical" in code
    assert "historical_links['sportsnavi']" in code
    assert "quote.get('fallback_used')" in code
    assert "quote.get('fallback_used')" in code
    assert "{quote['source']}" in code
    assert "from .jra_netkeiba_odds import fetch_once as fetch_free" in code
    assert "with st.expander('その他の取込・履歴保存', expanded=False)" in code
    assert "with st.expander('取得した全頭の照合表・保存', expanded=False)" in code
    assert "with st.expander('オッズ履歴の切替', expanded=False)" in code

def test_paper_rank_and_six_research_are_not_overwritten_by_price_actions():
    path=Path(__file__).parents[1] / "core" / "race_odds_ui_live.py"
    code=path.read_text(encoding="utf-8")
    assert "state['history'] = history" in code
    assert "activate_observation(quote)" in code
    assert "return odds.overlay(view, quote, label)" in code
