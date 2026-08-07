from __future__ import annotations

from pathlib import Path

import streamlit as st

from core.summary_loader import SummaryLoadError, load_summary, summary_counts, summary_date


ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / "assets" / "analysis" / "weekend_summary.json"


st.set_page_config(page_title="JRA Weekend", page_icon="🏇", layout="centered")


def main() -> None:
    st.title("JRA Weekend")
    st.caption("中央競馬・土曜／日曜の全レースを表示するためのDashboardページです。")

    try:
        summary = load_summary(SUMMARY_PATH)
    except SummaryLoadError as exc:
        st.error(str(exc))
        return
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
    st.caption("土曜／日曜のレース一覧は次のPhaseで実装します。")


if __name__ == "__main__":
    main()
