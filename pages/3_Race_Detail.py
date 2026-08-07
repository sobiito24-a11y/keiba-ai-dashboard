from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import streamlit as st

from core.dashboard_cards import DashboardDetailError, load_detail_json
from core.dashboard_ui import apply_mobile_styles


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DIR = ROOT / "assets" / "analysis"


st.set_page_config(page_title="レース詳細", page_icon="🏇", layout="centered")


def main() -> None:
    apply_mobile_styles()
    title = str(st.session_state.get("dashboard_detail_title") or "レース詳細")
    source = str(st.session_state.get("dashboard_detail_source") or "")
    detail_path = str(st.session_state.get("dashboard_detail_path") or "")

    st.title(title)
    if source:
        st.caption(source)
    if not detail_path:
        st.info("一覧の「詳細を見る」からレースを選択してください。")
        return

    try:
        detail = load_detail_json(ANALYSIS_DIR, detail_path)
    except DashboardDetailError as exc:
        st.error(str(exc))
        return
    if detail is None:
        st.error("詳細JSONが見つかりません。")
        return

    race_info = detail.get("race_info")
    if isinstance(race_info, Mapping) and race_info:
        with st.expander("レース情報", expanded=True):
            for key, value in race_info.items():
                if value not in (None, ""):
                    st.write(f"**{key}**：{value}")

    _render_table("総合テーブル", detail.get("overall_table"))
    _render_table("馬別評価", detail.get("horse_evaluation"))
    _render_text("注目馬", detail.get("attention_horses"))
    _render_text("AIレースレビュー", detail.get("ai_race_review"))
    _render_text("買い目構成", detail.get("betting_structure"))

    with st.expander("監査情報", expanded=False):
        st.write({
            "race_mode": detail.get("race_mode"),
            "version": detail.get("version"),
            "created_at": detail.get("created_at"),
            "status": detail.get("status"),
            "message": detail.get("message"),
            "source_files": detail.get("source_files"),
        })


def _render_table(title: str, value: Any) -> None:
    if not isinstance(value, list) or not value:
        return
    st.subheader(title)
    st.dataframe(value, use_container_width=True, hide_index=True)


def _render_text(title: str, value: Any) -> None:
    if value in (None, "", []):
        return
    st.subheader(title)
    if isinstance(value, list):
        for item in value:
            st.write(f"・{item}")
    else:
        st.write(value)


if __name__ == "__main__":
    main()
