"""One-click NAR bodyweight research panel, completely separate from ranking."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from html import escape
import json

from . import nar_body_weight as bw
from . import race_odds


def _bodyweight_table(observation):
    records = []
    for h in observation.get("rows", []):
        low, high = h.get("paired_min_kg"), h.get("paired_max_kg")
        weight = h.get("current_kg")
        change = h.get("change_kg")
        diff = h.get("distance_from_range_kg")
        records.append(dict(
            馬番=h["horse_no"], 馬名=h["name"], 新SABCD=h.get("sabcd") or "未照合",
            今回馬体重=(str(weight)+"kg") if weight is not None else "未発表",
            前走比=(f"{change:+d}kg" if change is not None else "未取得"),
            連対時体重=(f"{low}〜{high}kg" if low is not None and high is not None else "未取得"),
            範囲判定=h["band"],
            範囲からの差=(f"{diff}kg" if diff is not None else "—"),
        ))
    return records


def _weight_detail(h):
    bw_data = h.get("nar_body_weight_research")
    if not isinstance(bw_data, dict):
        return ""
    low, high = bw_data.get("paired_min_kg"), bw_data.get("paired_max_kg")
    current = bw_data.get("current_kg")
    delta = bw_data.get("change_kg")
    band = bw_data.get("band")
    prestart = bw_data.get("prestart_observed")
    parts = [
        ("今回馬体重", str(current)+"kg" if current is not None else "未発表"),
        ("前走からの増減", (f"{delta:+d}kg" if delta is not None else "未取得")),
        ("過去の連対時馬体重", (f"{low}〜{high}kg" if low is not None and high is not None else "未取得")),
        ("連対時の範囲と比較", band or "判定不能"),
        ("観測の位置づけ", "発走前に取得" if prestart else "発走前と未確認・研究成績から除外"),
    ]
    return (
        '<section class="detail-nar-bodyweight" style="margin:12px 0;padding:12px;'
        'border:1px solid #cbd8e3;border-radius:10px">'
        '<h4>馬体重コンディション（研究のみ）</h4><dl>'
        + "".join("<dt>"+escape(label)+"</dt><dd>"+escape(value)+"</dd>"
                  for label, value in parts) +
        '</dl><p>馬体重は新SABCD・順位・印・買い目に一切反映していません。'
        '連対時馬体重は楽天競馬の掲載範囲であり、医学的・生理的な最適体重ではありません。</p></section>'
    )


def horse_detail_html(horse):
    return _weight_detail(horse) if horse.get("mode") == "nar" else ""


def _overlay(view, observation):
    out = deepcopy(view)
    if observation is None:
        return out
    rows = {str(h["horse_no"]): h for h in observation["rows"]}
    for h in out:
        row = rows.get(str(h.get("no")))
        if row is None or bw._norm(h.get("name")) != bw._norm(row["name"]):
            continue
        h["nar_body_weight_research"] = dict(row, prestart_observed=observation["prestart_observed"],
                                            retrieved_at=observation["retrieved_at"],
                                            source_url=observation["source_url"])
    return out


def _summary_display(st, book):
    rows = bw.cohort_rows(book)
    n_races = len({r["race_id"] for r in rows})
    st.caption(f"発走前取得・独立AI照合・楽天結果照合が完了した対象：{n_races}R／{len(rows)}頭。"
               "取消・除外、範囲未取得、発走後取得、ランク未検証は分母から除外します。")
    data = []
    for x in bw.grade_summary(rows):
        n = x["count"]
        data.append({
            "新SABCD": x["sabcd"], "連対時体重": x["band"], "対象頭数": n,
            "1着": f"{x['win']}/{n} ({100*x['win']/n:.1f}%)" if n else "未集計",
            "2着以内": f"{x['top2']}/{n} ({100*x['top2']/n:.1f}%)" if n else "未集計",
            "3着以内": f"{x['top3']}/{n} ({100*x['top3']/n:.1f}%)" if n else "未集計",
        })
    st.dataframe(data, use_container_width=True, hide_index=True)
    if not rows:
        st.info("検証用データはまだありません。発走前の馬体重更新と、レース後の結果照合を重ねると自動集計します。")
    elif any(x["count"] < 30 for x in bw.grade_summary(rows)):
        st.warning("ランク×体重範囲の各群に30頭未満のものがあります。見かけの率の差を過信しないでください。")
    gate = bw.heldout_value(rows)
    if gate["status"] != "evaluated":
        st.caption("追加価値の未使用期間検証：未判定。" + gate["message"])
    else:
        st.caption("未使用期間の連対率予測Brier（低いほどよい）："
                   f"ランクのみ {gate['base_brier']:.5f} ／ ランク＋馬体重 {gate['weight_brier']:.5f}。"
                   f"変化 {gate['improvement_pct']:+.2f}%、"
                   f"学習{gate['train_horses']}頭・検証{gate['test_horses']}頭。")
        st.caption(gate["message"] + " 結果が一度良くても、ランク補正を採用する証明にはなりません。")


def render(result, view, *, compact=False):
    """Streamlit panel; always returns a display-only copy of the input view."""
    import streamlit as st

    if getattr(result, "race_mode", None) != "nar":
        return view
    if not compact:
        st.markdown("**⚖️ NAR馬体重更新**")
        st.caption("更新すると、すぐ下の全頭比較一覧で人気の右に"
                   "「今回馬体重（前走比）」と小さな「連対時体重範囲」を表示します。"
                   "既存の新SABCD・印・買い目は変更しません。")

    try:
        identity = race_odds.identity_from_result(result)
        url = bw.racecard_url(identity, result.race_info or {})
        results_url = bw.result_url(identity, result.race_info or {})
    except (ValueError, KeyError, TypeError) as exc:
        st.warning("馬体重更新不可：" + str(exc))
        return view

    rid = identity["race_id"]
    key = "nar_body_weight_book_v1"
    book = st.session_state.setdefault(key, bw.empty_book())
    latest = bw.latest_observation(book, rid)
    now = datetime.now(race_odds.JST)
    day = rid[:4] + rid[6:10]
    is_today = now.strftime("%Y%m%d") == day
    start, prestart = bw._prestart(result, now)
    notice_key = "nar_body_weight_note_" + rid

    if not compact:
        st.caption(f"[楽天競馬・対象出走表]({url}) ｜ {day}｜取得時刻はアプリ受信時刻（JST）。"
                   " 発走前と確認できない観測は研究用集計から除外します。")

    if st.button("当日馬体重を更新（楽天競馬）", key=rid+"_weight_fetch",
                 disabled=not is_today):
        last = st.session_state.get("_nar_weight_last_global")
        previous = st.session_state.get(rid+"_weight_last")
        if last and (now-last).total_seconds() < 30:
            st.session_state[notice_key] = ("warning", "他のレースも含めて30秒以内の再取得は抑制しています。")
        elif previous and (now-previous).total_seconds() < 120:
            st.session_state[notice_key] = ("warning", "同じレースの連続取得は2分間隔でお願いします。")
        else:
            st.session_state["_nar_weight_last_global"] = now
            st.session_state[rid+"_weight_last"] = now
            try:
                with st.spinner("楽天競馬の公開出走表を1回だけ取得して照合しています…"):
                    html = bw.fetch_page(url)
                    quote = bw.make_observation(result, view, url, html, now=now)
                    book = bw.add_observation(book, quote)
                    st.session_state[key] = book
                    latest = bw.latest_observation(book, rid)
                coverage = sum(h["current_kg"] is not None for h in quote["rows"])
                st.session_state[notice_key] = (
                    "success", f"馬体重を{coverage}/{len(quote['rows'])}頭確認。"
                    + ("発走前観測として保存。" if quote["prestart_observed"]
                       else "発走前の確認ができないため、予測精度の研究対象から除外。"))
            except (ValueError, TypeError, KeyError) as exc:
                st.session_state[notice_key] = ("error", "自動更新できません：" + str(exc))
            except Exception:
                st.session_state[notice_key] = (
                    "error", "公開出走表に接続できません。保存HTML取込を利用してください。")

    # Keep observational research and its JSON tools in the module, but the
    # ordinary prediction screen has only the refresh button and its result.
    # This path still overlays every previously verified session observation.
    if compact:
        feedback = st.session_state.get(notice_key)
        if feedback:
            status, message = feedback
            getattr(st, status)(message)
        return _overlay(view, latest)

    with st.expander("更新できないとき：出走表HTMLを取り込む", expanded=False):
        uploaded = st.file_uploader("楽天競馬の対象出走表HTML（横の出馬表）",
                                    type=["html", "htm"], key=rid+"_weight_html")
        if st.button("保存HTMLを照合して反映", disabled=uploaded is None,
                     key=rid+"_weight_import") and uploaded is not None:
            try:
                data = uploaded.getvalue()
                if len(data) > 4_000_000:
                    raise ValueError("HTMLが4MBを超えています")
                for enc in ("utf-8-sig", "cp932", "euc-jp"):
                    try:
                        html = data.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    raise ValueError("HTMLの文字コードを読み取れません")
                quote = bw.make_observation(result, view, url, html, now=datetime.now(race_odds.JST),
                                            method="saved_rakuten_html_imported_now")
                book = bw.add_observation(book, quote)
                st.session_state[key] = book
                latest = bw.latest_observation(book, rid)
                st.session_state[notice_key] = (
                    "success", "保存HTMLから馬体重を照合しました。"
                    "ファイルの保存時刻そのものは証明できず、取込時刻を記録します。")
            except (ValueError, TypeError, KeyError) as exc:
                st.session_state[notice_key] = ("error", "HTML取込失敗：" + str(exc))

    if st.session_state.get(notice_key):
        status, message = st.session_state[notice_key]
        getattr(st, status)(message)

    if latest:
        confirmed = sum(h.get("current_kg") is not None for h in latest["rows"])
        st.caption(f"全頭比較一覧に{confirmed}/{len(latest['rows'])}頭分の馬体重を反映 "
                   f"｜観測 {latest['retrieved_at']} "
                   + ("（発走前取得）" if latest["prestart_observed"]
                      else "（発走前未確認・検証には使いません）")
                   + "｜未発表の馬は未取得のまま")
    else:
        st.caption("未取得。馬体重が発表されたら更新ボタンを押してください。")

    # Outcome is attached only to the separate study book and only after
    # the race. No prior prediction, view or observation is rewritten.
    with st.expander("任意：レース後の結果照合・研究データ管理", expanded=False):
        st.caption("この欄は馬体重一覧とは別の研究記録用です。")
        settled = ((book.get("races") or {}).get(rid) or {}).get("result")
        if settled:
            st.success("確定着順を保存済み。発走前の体重観測には上書きしていません。")
        else:
            st.caption("競走成績は発走後にだけ照合します。")
            if st.button("楽天競馬の確定着順を取得", key=rid+"_weight_result",
                         disabled=(not latest or (start is not None and now <= start)
                                   or now.strftime("%Y%m%d") < day)):
                try:
                    with st.spinner("楽天競馬の確定着順を照合中…"):
                        html = bw.fetch_page(results_url)
                        finishes = bw.parse_result(html, results_url, identity, result.race_info or {})
                        book = bw.attach_result(book, rid, finishes, source_url=results_url,
                                                now=datetime.now(race_odds.JST))
                        st.session_state[key] = book
                    st.success(f"確定着順{len(finishes)}頭を別記録として保存しました。")
                except (ValueError, KeyError, TypeError) as exc:
                    st.warning("確定結果の照合は未完了：" + str(exc))
                except Exception:
                    st.warning("確定着順に接続できません。研究データはそのまま保持しています。")

    with st.expander("任意：新SABCD×馬体重の1着／2着以内／3着以内率", expanded=False):
        _summary_display(st, book)
        st.caption("1レースにつき最後の発走前観測を使用。複数回の更新を重複サンプルにはしません。"
                   "発走後に取得した過去の連対時範囲は、過去予測を知っていたことにはしません。")
        raw = json.dumps(book, ensure_ascii=False, sort_keys=True, indent=2)
        st.download_button("研究用の全レース馬体重・結果JSONを保存",
                           data=raw.encode("utf-8"), file_name="nar_body_weight_research_v1.json",
                           mime="application/json", key=rid+"_weight_book_download")
        source = st.file_uploader("別の日に保存した研究用JSONを追加する",
                                  type=["json"], key=rid+"_weight_book_file")
        if st.button("保存研究JSONを統合", disabled=source is None,
                     key=rid+"_weight_book_merge") and source is not None:
            try:
                book = bw.merge_book(book, json.loads(source.getvalue().decode("utf-8-sig")))
                st.session_state[key] = book
                st.success("既存の観測を上書きせず統合しました。")
            except (ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
                st.error("JSON照合エラー：" + str(exc))

    return _overlay(view, latest)
