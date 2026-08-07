from __future__ import annotations

from pathlib import Path

import streamlit as st

from core.dashboard_ui import apply_mobile_styles, render_best_five, render_summary_dashboard
from core.summary_loader import SummaryLoadError, load_summary
from core.upload_pipeline import UploadProcessingError, detect_archive_mode, process_html_zip


ROOT = Path(__file__).resolve().parent
ANALYSIS_DIR = ROOT / "assets" / "analysis"


st.set_page_config(page_title="Keiba AI Dashboard", page_icon="🏇", layout="centered")


def main() -> None:
    apply_mobile_styles()
    st.title("Keiba AI Dashboard")
    st.caption("その日の買うべきレース一覧を確認するための独立Dashboard")

    render_today_best_five()
    render_html_zip_upload()

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


def render_today_best_five() -> None:
    summaries: list[tuple[str, dict, Path]] = []
    for source, path in (
        ("JRA Weekend", ANALYSIS_DIR / "weekend_summary.json"),
        ("NAR Daily", ANALYSIS_DIR / "nar_daily_summary.json"),
    ):
        try:
            summary = load_summary(path)
        except SummaryLoadError:
            continue
        if summary is not None:
            summaries.append((source, summary, ANALYSIS_DIR))
    render_best_five(summaries)


def render_html_zip_upload() -> None:
    st.subheader("HTML ZIPアップロード")
    st.caption("collected_html_jra_xxxxx.zip または collected_html_nar_xxxxx.zip を選択してください。")

    flash = st.session_state.pop("dashboard_upload_flash", None)
    if flash:
        level, message = flash
        getattr(st, level)(message)

    uploaded = st.file_uploader("HTML ZIP", type=["zip"], key="dashboard_html_zip")
    if uploaded is None:
        return
    try:
        mode = detect_archive_mode(uploaded.name)
        st.write("判定：" + ("JRA Weekend" if mode == "jra" else "NAR Daily"))
    except UploadProcessingError as exc:
        st.error(str(exc))
        return

    if not st.button("アップロードして解析", type="primary", use_container_width=True):
        return
    try:
        with st.spinner("HTMLを解析してSummaryを生成しています…"):
            result = process_html_zip(uploaded.name, uploaded.getvalue(), ANALYSIS_DIR)
    except Exception as exc:
        st.error(f"解析に失敗しました: {exc}")
        return

    target = "JRA Weekend" if result.mode == "jra" else "NAR Daily"
    message = f"{target}を更新しました（{result.analyzed_races}R解析）"
    if result.errors:
        message += f" / {len(result.errors)}Rは解析エラー"
    st.session_state.dashboard_upload_flash = ("success", message)
    st.rerun()


def render_summary_section(title: str, caption: str, path: Path) -> None:
    try:
        summary = load_summary(path)
    except SummaryLoadError as exc:
        st.divider()
        st.subheader(title)
        st.caption(caption)
        st.error(str(exc))
        return
    if summary is None:
        st.divider()
        st.subheader(title)
        st.caption(caption)
        st.info("データがありません")
        return
    render_summary_dashboard(title, caption, summary, ANALYSIS_DIR, source=title)


if __name__ == "__main__":
    main()
