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
    latest = book.get(rid)
    expected = {str(h["horse_no"]): bw._norm(h["name"]) for h in identity["horses"]}
    if latest and (latest.get("mode") != "jra" or latest.get("race_id") != rid
                   or {str(h["horse_no"]): h["name"] for h in latest.get("rows", [])} != expected):
        latest = None

    note_key = "jra_body_weight_note_" + rid
    now = datetime.now(race_odds.JST)
    if st.button("当日馬体重を更新", key=rid + "_jra_weight_fetch", disabled=not today):
        previous = st.session_state.get(rid + "_jra_weight_last")
        if previous and (now - previous).total_seconds() < 120:
            st.session_state[note_key] = ("warning", "同じレースの馬体重更新は2分間隔でお願いします。")
        else:
            st.session_state[rid + "_jra_weight_last"] = now
            try:
                with st.spinner("JRA公式の当日出馬表を照合しています…"):
                    observed = asyncio.run(bw.fetch_once(identity, result.race_info or {}, now=now))
                    # Never replace a previous observation with a different race.
                    book[rid] = observed
                    st.session_state[book_key] = book
                    latest = observed
                available = sum(h["current_kg"] is not None for h in latest["rows"])
                st.session_state[note_key] = (
                    "success", f"当日馬体重を{available}/{len(latest['rows'])}頭確認しました。"
                    "連対時体重がない馬も当日体重・増減は表示します。")
            except (ValueError, TypeError, KeyError) as exc:
                st.session_state[note_key] = ("warning", "JRA馬体重を取得できません：" + str(exc))
            except Exception as exc:
                st.session_state[note_key] = (
                    "warning", "JRA公式の当日出馬表を取得できません（"
                    + type(exc).__name__ + "）。予想と以前の観測は維持します。")

    feedback = st.session_state.get(note_key)
    if feedback:
        status, message = feedback
        getattr(st, status)(message)
    return bw.overlay(view, latest)
