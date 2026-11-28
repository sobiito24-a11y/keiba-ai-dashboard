"""Single JRA bodyweight update button and read-only table overlay."""
from __future__ import annotations

import asyncio
from datetime import datetime

from . import jra_body_weight as bw
from . import race_odds


def render(result, view, *, compact=False):
    import streamlit as st
    if getattr(result, "race_mode", None) != "jra":
        return view
    try:
        identity = race_odds.identity_from_result(result)
        rid, _, _, _, _, _ = bw.race_facts(identity, result.race_info or {})
        today = bw.is_today(identity, result.race_info or {})
    except (TypeError, ValueError, KeyError) as exc:
        st.warning("馬体重更新不可：" + str(exc))
        return view

    book_key = "jra_body_weight_observations_v1"
    book = st.session_state.setdefault(book_key, {})
    career_cache = st.session_state.setdefault("jra_paired_career_cache_v1", {})
    latest = book.get(rid)
    expected = {str(h["horse_no"]): bw._norm(h["name"]) for h in identity["horses"]}
    if latest and (latest.get("mode") != "jra" or latest.get("race_id") != rid
                   or {str(h["horse_no"]): h["name"] for h in latest.get("rows", [])} != expected):
        latest = None

    note_key = "jra_body_weight_note_" + rid
    now = datetime.now(race_odds.JST)
    if st.button("当日馬体重を更新", key=rid + "_jra_weight_fetch", disabled=not today):
        previous = st.session_state.get(rid + "_jra_weight_last")
        if previous and (now - previous).total_seconds() < 30:
            st.session_state[note_key] = ("warning", "JRA公式への再確認は30秒間隔でお願いします。")
        else:
            st.session_state[rid + "_jra_weight_last"] = now
            try:
                with st.spinner("JRA公式の出馬表から馬体重を照合しています…"):
                    observed = asyncio.run(bw.fetch_once(
                        identity, result.race_info or {}, now=now,
                        history_cache=career_cache))
                st.session_state["jra_paired_career_cache_v1"] = career_cache
                available = observed["current_count"]
                prior_count = (sum(x.get("current_kg") is not None for x in latest.get("rows", []))
                               if isinstance(latest, dict) else 0)
                # Never replace already confirmed weights with a prepublication
                # empty page, but keep zero-weight observations for past ranges.
                if available >= prior_count:
                    book[rid] = observed
                    st.session_state[book_key] = book
                    latest = observed
                total = len(observed["rows"])
                career_checked = observed.get("paired_career_checked", 0)
                if career_checked == total:
                    history_note = "過去全走の連対時体重を確認しました。"
                elif career_checked:
                    history_note = (f"過去全走を{career_checked}/{total}頭確認。"
                                    "残りはJRA公式の直近4走から確認した範囲です。")
                else:
                    history_note = ("過去全走の連対時体重を取得できず、"
                                    "JRA公式の直近4走のみ参照しています。"
                                    "「-」は過去に連対がないことを示すとは限りません。")
                provider = {
                    "sportsnavi": "スポーツナビ",
                    "netkeiba": "netkeiba",
                    "http": "JRA公式",
                    "browser": "JRA公式（ブラウザ）",
                }.get(observed.get("verified_by"), "取得元")
                if observed["publication_status"] == "unpublished":
                    st.session_state[note_key] = (
                        "warning", f"JRA公式・補助サイトを確認しましたが、取得結果に当日馬体重がありません（0/{total}頭）。"
                        "公式で既に発表されていても、取得元のキャッシュ・配信遅延の可能性があります。"
                        "発走約60分前以降なら30秒以上空けて再更新してください。"
                        + history_note)
                elif available < total:
                    st.session_state[note_key] = (
                        "warning", f"{provider}で{available}/{total}頭の当日馬体重を取得しました。"
                        "未取得の馬は未発表・除外等の可能性があります。" + history_note)
                else:
                    st.session_state[note_key] = (
                        "success", f"{provider}から当日馬体重を{available}/{total}頭取得しました。"
                        "連対時体重がない馬も当日馬体重・増減は表示します。" + history_note)
            except (ValueError, TypeError, KeyError) as exc:
                st.session_state[note_key] = ("warning", "JRA馬体重の取得に失敗：" + str(exc))
            except Exception as exc:
                st.session_state[note_key] = (
                    "warning", "JRA公式出馬表の取得処理で"
                    + type(exc).__name__ + "が発生しました。予想と以前の観測は維持します。")

    feedback = st.session_state.get(note_key)
    if feedback:
        status, message = feedback
        getattr(st, status)(message)
    return bw.overlay(view, latest)
