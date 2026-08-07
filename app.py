from __future__ import annotations

from pathlib import Path

import streamlit as st

from core.summary_loader import SummaryLoadError, load_summary, summary_counts, summary_date, summary_venues


ROOT = Path(__file__).resolve().parent
ANALYSIS_DIR = ROOT / "assets" / "analysis"


st.set_page_config(page_title="Keiba AI Dashboard", page_icon="🏇", layout="centered")


def main() -> None:
    st.title("Keiba AI Dashboard")
    st.caption("その日の買うべきレース一覧を確認するための独立Dashboard")

    render_summary_section(
        "JRA Weekend",
        "中央競馬・土曜／日曜",
        ANALYSIS_DIR / "weekend_summary.json",
    )
    render_summary_section(
        "NAR Daily",
        "地方競馬・当日の全開催場",
        ANALYSIS_DIR / "nar_daily_summary.json",
    )


def render_summary_section(title: str, caption: str, path: Path) -> None:
    st.divider()
    st.subheader(title)
    st.caption(caption)
    try:
        summary = load_summary(path)
    except SummaryLoadError as exc:
        st.error(str(exc))
        return
    if summary is None:
        st.info("データがありません")
        return

    date = summary_date(summary)
    if date:
        st.write(f"対象日：{date.replace('-', '/')}")
    buy, hold, skip = summary_counts(summary)
    buy_col, hold_col, skip_col = st.columns(3)
    buy_col.metric("買い", f"{buy}R")
    hold_col.metric("保留", f"{hold}R")
    skip_col.metric("見送り", f"{skip}R")
    venues = summary_venues(summary)
    if venues:
        st.caption("開催場：" + " / ".join(venues))


if __name__ == "__main__":
    main()
