from __future__ import annotations

from pathlib import Path

import streamlit as st

from core.dashboard_ui import apply_mobile_styles, render_summary_dashboard
from core.summary_loader import SummaryLoadError, load_summary


ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / "assets" / "analysis" / "weekend_summary.json"


st.set_page_config(page_title="JRA Weekend", page_icon="🏇", layout="centered")


def main() -> None:
    apply_mobile_styles()
    st.title("JRA Weekend")

    try:
        summary = load_summary(SUMMARY_PATH)
    except SummaryLoadError as exc:
        st.error(str(exc))
        return
    if summary is None:
        st.info("データがありません")
        return
    render_summary_dashboard(
        "JRA Weekend",
        "中央競馬・土曜／日曜",
        summary,
        SUMMARY_PATH.parent,
        source="JRA Weekend",
        show_heading=False,
    )


if __name__ == "__main__":
    main()
