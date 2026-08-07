from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

import streamlit as st

from .dashboard_cards import RaceCard, format_strategy_score, prepare_race_cards, today_best_five
from .summary_loader import summary_counts, summary_date, summary_venues


DETAIL_PAGE = "pages/3_Race_Detail.py"


def apply_mobile_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {max-width: 760px; padding-top: 1rem; padding-bottom: 3rem;}
        h1 {font-size: 1.8rem !important;}
        h2 {font-size: 1.45rem !important;}
        h3 {font-size: 1.2rem !important;}
        div[data-testid="stMetric"] {background: #f7f8fa; border-radius: 12px; padding: .55rem;}
        div[data-testid="stMetricValue"] {font-size: 1.35rem;}
        .race-meta {color: #5f6368; font-size: .88rem; margin-top: -.4rem;}
        .race-ticket {font-size: 1.04rem; font-weight: 700; margin: .45rem 0;}
        @media (max-width: 640px) {
          .block-container {padding-left: .75rem; padding-right: .75rem;}
          div[data-testid="stHorizontalBlock"] {gap: .45rem;}
          button[kind="secondary"], button[kind="primary"] {min-height: 2.75rem;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_best_five(
    summaries: Iterable[tuple[str, Mapping[str, Any], str | Path]],
) -> None:
    st.subheader("今日のBEST5")
    cards = today_best_five(summaries)
    if not cards:
        st.info("今日のBUY対象データはありません")
        return
    for rank, card in enumerate(cards, start=1):
        render_buy_card(card, key_prefix=f"best-{rank}", rank=rank)


def render_summary_dashboard(
    title: str,
    caption: str,
    summary: Mapping[str, Any],
    analysis_dir: str | Path,
    *,
    source: str,
    show_heading: bool = True,
) -> None:
    if show_heading:
        st.divider()
        st.subheader(title)
        st.caption(caption)
    date = summary_date(summary)
    if date:
        st.write(f"対象日：{date.replace('-', '/')}")

    buy_count, hold_count, skip_count = summary_counts(summary)
    buy_col, hold_col, skip_col = st.columns(3)
    buy_col.metric("BUY", f"{buy_count}R")
    hold_col.metric("HOLD", f"{hold_count}R")
    skip_col.metric("SKIP", f"{skip_count}R")

    venues = summary_venues(summary)
    if venues:
        st.caption("開催場：" + " / ".join(venues))

    buy_cards = prepare_race_cards(summary, analysis_dir, source=source, decision="buy")
    st.markdown("#### BUY")
    if not buy_cards:
        st.caption("BUY対象レースはありません。")
    for index, card in enumerate(buy_cards):
        render_buy_card(card, key_prefix=f"{source}-buy-{index}")

    hold_cards = prepare_race_cards(summary, analysis_dir, source=source, decision="hold")
    with st.expander(f"HOLD {hold_count}R", expanded=False):
        if not hold_cards:
            st.caption("HOLD対象レースはありません。")
        for index, card in enumerate(hold_cards):
            render_hold_row(card, key_prefix=f"{source}-hold-{index}")

    st.caption(f"SKIP {skip_count}R（件数のみ表示）")


def render_buy_card(card: RaceCard, *, key_prefix: str, rank: int | None = None) -> None:
    with st.container(border=True):
        prefix = f"#{rank} " if rank is not None else ""
        st.markdown(f"### {prefix}{card.venue} {card.race_number}")
        st.caption(
            f"{card.source} ・ 発走 {card.post_time} ・ "
            f"strategy_score {format_strategy_score(card.strategy_score)}"
        )
        st.markdown(f"**{card.ticket}**")
        roi_col, rank_col = st.columns(2)
        roi_col.metric("期待回収率", card.roi)
        rank_col.metric("投資ランク", card.investment_rank)

        st.markdown("**買う理由**")
        st.write(f"条件一致：{card.condition_match}")
        st.write(f"採用された戦略：{card.adopted_strategy}")
        st.write(f"期待回収率：{card.roi}")
        st.write(f"strategy_score：{format_strategy_score(card.strategy_score)}")
        if card.buy_reasons:
            st.caption("BUYになった理由")
            for reason in card.buy_reasons:
                st.write(f"✓ {reason}")
        else:
            st.caption("BUYになった理由：既存Summaryに記録なし")

        if card.horses:
            for horse in card.horses:
                st.markdown(
                    f"**{horse.mark} {horse.number} {horse.name}**  \n"
                    f"AI点 **{horse.ai_score}** ｜ 能力評価 **{horse.ability}**"
                )
        else:
            st.caption("◎○▲の馬データは詳細JSONにありません。")

        _render_detail_button(card, key=f"{key_prefix}-{card.race_id or 'race'}")


def render_hold_row(card: RaceCard, *, key_prefix: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{card.venue} {card.race_number}**　発走 {card.post_time}")
        st.caption(
            f"{card.ticket} ｜ strategy_score {format_strategy_score(card.strategy_score)} ｜ 期待回収率 {card.roi}"
        )
        _render_detail_button(card, key=f"{key_prefix}-{card.race_id or 'race'}")


def _render_detail_button(card: RaceCard, *, key: str) -> None:
    if not card.detail_available:
        st.button("詳細データなし", key=key, disabled=True, use_container_width=True)
        return
    if st.button("詳細を見る", key=key, use_container_width=True):
        st.session_state.dashboard_detail_path = card.detail_path
        st.session_state.dashboard_detail_title = f"{card.venue} {card.race_number}"
        st.session_state.dashboard_detail_source = card.source
        st.switch_page(DETAIL_PAGE)
