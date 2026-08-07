from __future__ import annotations

from pathlib import Path

import streamlit as st

from core.daily_summary import load_nar_daily_summary, summary_counts, summary_date, summary_venues


ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / "assets" / "analysis" / "nar_daily_summary.json"


st.set_page_config(page_title="NAR Daily", page_icon="🏇", layout="centered")


def main() -> None:
    st.title("NAR Daily")
    st.caption("地方競馬・当日の全開催場を表示するためのDashboardページです。")

    summary = load_nar_daily_summary(SUMMARY_PATH)
    if summary is None:
        st.info("データがありません")
        return

    date = summary_date(summary)
    if date:
        st.subheader(date.replace("-", "/"))

    buy, hold, skip = summary_counts(summary)
    buy_col, hold_col, skip_col = st.columns(3)
    buy_col.metric("買い", f"{buy}R")
    hold_col.metric("保留", f"{hold}R")
    skip_col.metric("見送り", f"{skip}R")

    venues = summary_venues(summary)
    if venues:
        st.write("開催場：" + " / ".join(venues))

    st.caption("レース一覧と詳細遷移は次のPhaseで実装します。")


if __name__ == "__main__":
    main()
