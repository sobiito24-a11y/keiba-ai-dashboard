"""Fresh NAR odds UI module; isolate from cached legacy odds panel imports.

Intentionally loads through a new module path so a running Streamlit session
cannot reuse the disabled, old connector-only button implementation.
"""
from datetime import datetime
import json
from . import race_odds as odds


def render(result, view):
    import streamlit as st
    def caption(value):
        st.caption(str(value))
    from .independent_ai_odds import provider
    try:
        identity = odds.identity_from_result(result)
        initial = odds.state_for(result)
    except (ValueError, TypeError, KeyError):
        caption('オッズ更新不可：レース・出走馬情報を照合できません。保存時表示を維持します。')
        return view
    key = 'race_prices_' + odds.digest(dict(identity=identity, saved=initial))
    state = st.session_state.setdefault(key, initial)
    # Session-only display state is deliberately separate from archive odds.
    # History restored from .keiba is available for an explicit choice, but it
    # does not prove that the user has imported current prices in this session.
    runtime_key = key + '_observation_runtime_v3'
    runtime = st.session_state.setdefault(runtime_key, dict(
        seen_history_ids=[q['observation_id'] for q in state['history']],
        active_observation=None, revision=0))

    def activate_observation(quote):
        runtime['active_observation'] = quote['observation_id']
        runtime['seen_history_ids'] = [q['observation_id'] for q in state['history']]
        # A duplicate import is still an explicit request to display that
        # observation, even though merge correctly retains its original clock.
        runtime['revision'] += 1
    try:
        config = dict(st.secrets.get('race_odds', st.secrets.get('independent_ai_odds', {})))
    except Exception:
        config = {}
    try:
        connection = provider(config)
    except (ValueError, TypeError):
        connection = provider()
    st.markdown('#### オッズ')
    st.caption('単勝・複勝｜保存済みの評価・順位は変更しません。')
    is_nar = identity['mode'] == 'nar'
    if not is_nar:
        jra_id = identity['race_id']
        # Both flows are read-only and user-triggered; details stay collapsed.
        # Historical observations remain on third-party race archives even when
        # the JRA current-meeting selector no longer lists that race.
        from .jra_historical_odds_links import archived_odds_urls
        historical_links = archived_odds_urls(identity, result.race_info or {})
        if historical_links:
            with st.container():
                from .jra_yuma_odds import fetch_once as fetch_historical
                from .jra_historical_odds import parse_keibalab_html
                now_historical = datetime.now(odds.JST)
                try:
                    from datetime import date as _date
                    race_date = str((result.race_info or {}).get('race_date')
                                    or (result.race_info or {}).get('date') or '').replace('/', '-')
                    is_past = _date.fromisoformat(race_date) < now_historical.date()
                except ValueError:
                    is_past = False
                if st.button('過去オッズ取得',
                             key=key+'_historical_fetch', disabled=not is_past):
                    previous = st.session_state.get(key+'_historical_last_request')
                    across = st.session_state.get('_jra_historical_global_last_request')
                    if previous and (now_historical-previous).total_seconds() < 180:
                        st.session_state[key+'_status'] = '同じ過去レースの再取得は180秒以上あけてください。'
                    elif across and (now_historical-across).total_seconds() < 15:
                        st.session_state[key+'_status'] = '過去オッズへの連続アクセスを抑制しています。15秒以上あけてください。'
                    else:
                        st.session_state[key+'_historical_last_request'] = now_historical
                        st.session_state['_jra_historical_global_last_request'] = now_historical
                        stage = '単勝・複勝ページへの接続と解析'
                        try:
                            with st.spinner('優馬JAPANの過去単勝・複勝を取得中…'):
                                quote = fetch_historical(identity, result.race_info or {}, now=now_historical)
                                stage = '保存済みの馬番・馬名との照合'
                                history = odds.merge(state['history'], [quote], identity)
                            stage = 'AI一覧への反映'
                            state['history'] = history
                            activate_observation(quote)
                            st.session_state[key+'_status'] = (
                                f"取得：{quote['horse_count']}／{quote['expected_horses']}頭。"
                                f"優馬JAPAN掲載値（単勝{quote['coverage']['win']['count']}頭／"
                                f"複勝{quote['coverage']['place']['count']}頭）を表示に反映。"
                                "最終確定オッズ・更新時刻は未確認です。")
                        except ValueError as exc:
                            st.session_state[key+'_status'] = (
                                f'JRA過去オッズ未取得（{stage}）：{exc}')
                        except Exception as exc:
                            # Avoid showing raw external HTML or user-supplied URLs.
                            st.session_state[key+'_status'] = (
                                f'JRA過去オッズ未取得（{stage}）：'
                                f'{type(exc).__name__}。取得値は表示へ反映していません。')
                # Past-date availability is expressed through the disabled button.
                with st.expander('過去オッズの予備取込・掲載元', expanded=False):
                    st.caption('優馬JAPANの単勝・複勝HTMLをそれぞれ保存して読み込めます。'
                               '競馬ラボの単複HTMLも別方式で取込できます。')
                    yuma_win = st.file_uploader(
                        '優馬JAPANの単勝ページHTML', type=['html', 'htm'],
                        key=key+'_yuma_win_file')
                    yuma_place = st.file_uploader(
                        '優馬JAPANの複勝ページHTML', type=['html', 'htm'],
                        key=key+'_yuma_place_file')
                    if st.button('保存した優馬JAPANの単複をAIに取込',
                                 key=key+'_yuma_import', disabled=not (yuma_win or yuma_place)):
                        try:
                            from .jra_yuma_odds import parse_yuma_pages
                            payload = {}
                            for flag, item in (('tan', yuma_win), ('fuk', yuma_place)):
                                if item is not None:
                                    raw = item.getvalue()
                                    if len(raw) > 3_000_000:
                                        raise ValueError('HTMLは3MB以下にしてください')
                                    payload[flag] = raw
                            quote = parse_yuma_pages(payload, identity, result.race_info or {})
                            history = odds.merge(state['history'], [quote], identity)
                            state['history'] = history
                            activate_observation(quote)
                            st.session_state[key+'_status'] = (
                                f"取得：{quote['horse_count']}／{quote['expected_horses']}頭。"
                                "優馬JAPANの保存HTMLからAIへ反映しました。")
                        except (ValueError, TypeError) as exc:
                            st.session_state[key+'_status'] = 'JRA過去オッズ未取得：' + str(exc)
                    st.markdown('[競馬ラボ：単勝・複勝一覧](' + historical_links['keibalab'] + ')')
                    st.markdown('[優馬JAPAN：単勝一覧](' + historical_links['yuma_win'] + ')')
                    st.markdown('[優馬JAPAN：複勝一覧](' + historical_links['yuma_place'] + ')')
                    archived_file = st.file_uploader(
                        '競馬ラボの過去単複ページ（HTML）', type=['html', 'htm'],
                        key=key+'_historical_file')
                    if st.button('保存HTMLの単複をAIへ反映',
                                 key=key+'_historical_import', disabled=archived_file is None):
                        try:
                            data = archived_file.getvalue()
                            if len(data) > 3_000_000:
                                raise ValueError('HTMLが3MBを超えています')
                            quote = parse_keibalab_html(data, identity, result.race_info or {})
                            history = odds.merge(state['history'], [quote], identity)
                            state['history'] = history
                            activate_observation(quote)
                            st.session_state[key+'_status'] = (
                                f"取得：{quote['horse_count']}／{quote['expected_horses']}頭。"
                                "保存HTMLの過去単複をAIの表示に反映しました。")
                        except (ValueError, TypeError) as exc:
                            st.session_state[key+'_status'] = 'JRA過去オッズ未取得：' + str(exc)
                # The matching source pages are available only inside the
                # collapsed backup panel above; the main UI has two actions.
        with st.expander('当日の掲載元・利用上の注意', expanded=False):
            st.markdown('[JRA公式オッズ](https://www.jra.go.jp/)'
                        '（公式サイトの「オッズ」から選択）')
            st.markdown(
                '[netkeiba・このレースのオッズ](https://race.netkeiba.com/odds/index.html?race_id='
                + jra_id + '&type=b1)'
                '（単勝・複勝を確認）')
            st.caption('実際の投票価格は購入直前にJRA公式の販売画面で再確認。'
                       'アクセスが制限された場合はスクショ・HTML取込を使用。'
                       '自動巡回や更新回数の上限制限回避は行いません。')
    if not is_nar:
        from datetime import date as _date
        now_live = datetime.now(odds.JST)
        date_text = str((result.race_info or {}).get('race_date')
                        or (result.race_info or {}).get('date') or '').replace('/', '-')
        try:
            is_today = _date.fromisoformat(date_text) == now_live.date()
        except ValueError:
            is_today = False
        if st.button('当日リアルオッズ取得',
                     key=key+'_live_fetch', disabled=not is_today):
            last = st.session_state.get(key+'_live_last_request')
            global_last = st.session_state.get('_jra_free_odds_global_request')
            if last and (now_live-last).total_seconds() < 180:
                st.session_state[key+'_status'] = '同じレースの再取得は180秒以上あけてください。'
            elif global_last and (now_live-global_last).total_seconds() < 30:
                st.session_state[key+'_status'] = '当日の連続取得は30秒以上あけてください。'
            else:
                st.session_state[key+'_live_last_request'] = now_live
                st.session_state['_jra_free_odds_global_request'] = now_live
                quote = None
                failures = []
                try:
                    import asyncio
                    from .jra_official_odds import fetch_once as fetch_jra_official
                    with st.spinner('JRA公式で当日の単勝・複勝を確認中…'):
                        quote = asyncio.run(fetch_jra_official(
                            identity, result.race_info or {}, now=now_live))
                except (ValueError, RuntimeError, OSError, TimeoutError) as exc:
                    failures.append('JRA公式：' + str(exc)[:140])
                except Exception as exc:
                    failures.append('JRA公式：' + type(exc).__name__)
                if quote is None:
                    try:
                        with st.spinner('別の無料配信で単勝・複勝を確認中…'):
                            if connection.available:
                                quote = odds.validate(connection.fetch(identity['race_id']), identity)
                                quote['acquisition_method'] = 'authorized_json'
                            else:
                                from .jra_netkeiba_odds import fetch_once as fetch_free
                                quote = fetch_free(identity, result.race_info or {}, now=now_live)
                    except (ValueError, RuntimeError, OSError, TimeoutError) as exc:
                        failures.append('無料配信：' + str(exc)[:140])
                    except Exception as exc:
                        failures.append('無料配信：' + type(exc).__name__)
                if quote is None:
                    st.session_state[key+'_status'] = ('JRAオッズ未取得：' + '／'.join(failures)
                                                       + '。保存オッズは代用しません。')
                else:
                    try:
                        history = odds.merge(state['history'], [quote], identity)
                        state['history'] = history
                        activate_observation(quote)
                        st.session_state[key+'_status'] = (
                            f"取得：単勝{quote['coverage']['win']['count']}頭／"
                            f"複勝{quote['coverage']['place']['count']}頭。"
                            "掲載価格であり、購入可能な直前価格の保証はありません。")
                    except (ValueError, TypeError, KeyError) as exc:
                        st.session_state[key+'_status'] = 'JRAオッズ未取得（照合）：' + str(exc)
    if is_nar:
        st.caption('地方競馬：NAR公式の当日掲載値（配信に遅れがあります）。')
        with st.expander('NAR公式・データ掲載元', expanded=False):
            st.markdown('[NAR公式オッズ](https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/TodayRaceInfoTop)')
    if getattr(result, '_race_odds_error', None): st.warning(result._race_odds_error)
    if is_nar and st.button('当日リアルオッズ取得', key=key+'_fetch'):
        now = datetime.now(odds.JST)
        from .nar_official_odds import fetch_daily, parse_daily_zip, locator
        try:
            venue, day, _ = locator(identity, result.race_info or {})
            cached = st.session_state.get('_nar_zip_last_private_fetch')
            # A single user's session reuses the SAME ZIP for all races.
            # This also avoids 12 network calls for a 12R venue.
            if cached and cached['day'] == day and (now - cached['received']).total_seconds() < 120:
                filename, payload = cached['name'], cached['data']
            elif (cached and (now - cached['received']).total_seconds() < 120):
                st.session_state[key+'_status'] = '公式への再アクセスを抑制中。約2分後に更新してください。'
                filename, payload = None, None
            else:
                with st.spinner('NAR公式の当日オッズZIPを取得中…'):
                    filename, payload = fetch_daily()
                st.session_state['_nar_zip_last_private_fetch'] = dict(
                    day=day, received=now, name=filename, data=payload)
            if filename is not None:
                with st.spinner('保存済み出走馬とオッズを照合中…'):
                    quote = parse_daily_zip(
                        payload, filename, identity, result.race_info or {}, now=now)
                    history = odds.merge(state['history'], [quote], identity)
                added = len(history) - len(state['history'])
                state['history'] = history
                activate_observation(quote)
                st.session_state[key+'_status'] = (
                    f"NAR公式ZIPから{quote['horse_count']}／{quote['expected_horses']}頭を照合。"
                    + ('更新済みの同一ZIPです。' if not added else '単複・馬連・ワイドの価格を反映。')
                    + ' 発表時刻ではなくZIP作成時刻の参考情報です。')
        except ValueError as exc:
            st.session_state[key+'_status'] = 'NAR公式オッズ未取得：' + str(exc)
        except Exception:
            st.session_state[key+'_status'] = '公式オッズの取得・照合に失敗。保存時の予想を維持します。'
    # Show the outcome immediately below the button, not below several long
    # import / screenshot widgets.  Otherwise a valid click appears inert
    # on narrow mobile screens.
    notice = st.session_state.get(key+'_status')
    if notice:
        if notice.startswith(('JRAオッズ未取得', 'JRAオッズ取得に失敗', 'JRA過去オッズ未取得',
                               'NAR公式オッズ未取得', '公式オッズの取得・照合に失敗')):
            st.error('オッズ更新結果：' + notice)
        elif ('再取得' in notice or '抑制' in notice or '連続' in notice):
            st.warning('オッズ更新結果：' + notice)
        else:
            st.success('オッズ更新結果：' + notice)
        # A successful fetch gets a compact, verifiable source quote sample.
        # Do not show stale saved quote examples as if a new fetch succeeded.
        current_id = runtime.get('active_observation')
        active = next((x for x in reversed(state['history'])
                       if x.get('observation_id') == current_id), None)
        with st.expander('取得した全頭の照合表・保存', expanded=False):
            if (active is not None and ('取得：' in notice or '照合。' in notice
                                       or notice.startswith('NAR公式ZIPから'))):
                st.caption('取得元：' + str(active.get('source') or '不明') +
                           '｜配信元更新：' + odds.format_time(active.get('observed_at')) +
                           '｜' + odds.freshness(active, odds.start_from_result(result)))
                names = {int(h['horse_no']): h['name'] for h in identity['horses']}
                win_prices = {p['horses'][0]: odds.price_text(p) for p in active['prices']
                              if p['kind'] == 'win'}
                place_prices = {p['horses'][0]: odds.price_text(p) for p in active['prices']
                                if p['kind'] == 'place'}
                singles = [dict(馬番=no, 馬名=name,
                                単勝=(win_prices.get(no, '—') + '倍' if no in win_prices else '—'),
                                複勝=(place_prices.get(no, '—') + '倍' if no in place_prices else '—'))
                           for no, name in sorted(names.items())]
                if singles:
                    st.dataframe(singles, hide_index=True, use_container_width=True)
                    st.caption('保存レースの全頭を表示。未取得の価格は「—」で、古い価格を補完しません。')
                    if active.get('acquisition_method') in ('keibalab_historical_html', 'yuma_historical_html'):
                        source_archive = (st.session_state.get('game_archive_upload')
                                          or st.session_state.get('dashboard_saved_prediction'))
                        if source_archive is not None:
                            try:
                                copied_archive = odds.export_copy(source_archive.getvalue(), identity, state)
                                st.download_button('過去単複を反映した.keibaコピーを保存',
                                                   data=copied_archive,
                                                   file_name=identity['race_id']+'_with_historical_odds.keiba',
                                                   key=key+'_historical_copy_quick')
                            except (ValueError, TypeError, KeyError, AttributeError):
                                st.caption('元の.keibaが確認できないため、この画面ではコピーを作成できません。')
                        else:
                            st.caption('反映内容はセッション内です。必要なら下の履歴JSONを保存してください。')
                else:
                    st.warning('単勝オッズが未取得です。取得できた券種のみ下の詳細で確認してください。')
    elif not is_nar:
        st.caption('更新ボタンを押すと、ここに成功／失敗と取得元更新時刻を表示します。'
                   '終了レースの場合は過去の参考オッズになります。')

    with st.expander('その他の取込・履歴保存', expanded=False):
        show_extra = st.checkbox('手動入力・スクショ・ファイル取込を使う',
                                 value=False, key=key+'_show_extra')
    if show_extra:
        with st.expander("直前オッズを数行で手入力（外部サイトを見ながら）", expanded=False):
            st.caption("例：『単勝 3 5.2』『馬連 3-7 14.8』『ワイド 3-7 4.5-5.8』。"
                       "複勝・ワイドは範囲を指定可能。同じレースの馬番と馬名、表示倍率を確認してください。")
            with st.form(key + "_manual_form"):
                source_name = st.text_input("確認元のサイト名", value="外部サイト", key=key+"_manual_source")
                typed = st.text_area("表示オッズを1行ずつ入力",
                                     placeholder="単勝 3 5.2\\nワイド 3-7 4.5-5.8\\n馬連 3-7 14.8",
                                     key=key+"_manual_text", height=100)
                checked = st.checkbox(
                    "対象レース・馬番・馬名・倍率を今この外部サイトで目視確認した",
                    value=False, key=key+"_manual_checked")
                submit_manual = st.form_submit_button("確認したオッズを反映")
            if submit_manual:
                from .race_odds_manual import build_observation
                try:
                    quote = build_observation(typed, identity, source=source_name,
                                              seen_now=checked)
                    state['history'] = odds.merge(state['history'], [quote], identity)
                    activate_observation(quote)
                    st.session_state[key+'_status'] = (
                        f"入力 {len(quote['prices'])}点。"
                        "確認時刻は利用者の目視確認時刻で、提供元の価格更新時刻ではありません。"
                        "新しい入力に古い価格を補完しません。"
                    )
                except (ValueError, TypeError, KeyError) as exc:
                    st.error(str(exc))
            st.caption("券種ごとの正確な表示オッズを入力してください。馬連の倍率をワイドへ転用しません。"
                       "オッズは締切まで動くので、購入直前に再確認してください。")
        from .race_odds_screenshot_ui import render as render_screenshot
        render_screenshot(identity, state, key)
        with st.expander('オッズファイルを一括取込・履歴を保存', expanded=False):
            files = st.file_uploader('同じレースのHTML／JSON、またはNAR公式の当日オッズZIP',
                                     type=['html','htm','json','zip'],
                                     accept_multiple_files=True, key=key+'_files')
            if st.button('全頭分をまとめて取り込む', disabled=not files, key=key+'_import'):
                try:
                    incoming = []
                    # Validate every file before committing anything to session.
                    for file in files:
                        if file.name.lower().endswith('.zip'):
                            if not is_nar:
                                raise ValueError('NAR公式ZIPは地方競馬のレースでのみ取込できます')
                            from .nar_official_odds import parse_daily_zip
                            incoming.append(parse_daily_zip(
                                file.getvalue(), file.name, identity, result.race_info or {}))
                        else:
                            incoming.extend(odds.import_files([(file.name, file.getvalue())], identity))
                    history = odds.merge(state['history'], incoming, identity)
                    added = len(history)-len(state['history'])
                    state['history'] = history
                    if incoming:
                        activate_observation(incoming[-1])
                    st.session_state[key+'_status'] = f'照合済み観測を{added}件追加。有効価格なしの観測は未取得として記録します。'
                except (ValueError, TypeError, KeyError, UnicodeError) as exc:
                    st.session_state[key+'_status'] = '取込失敗：' + str(exc) + '。全ファイルの反映を中止しました。'
            caption('セッション内の履歴はCloudへ永続保存されません。必要な履歴を含むコピーをダウンロードしてください。元ファイルは上書きしません。')
            source = st.session_state.get('game_archive_upload') or st.session_state.get('dashboard_saved_prediction')
            if source is not None and state['history']:
                try:
                    copied = odds.export_copy(source.getvalue(), identity, state)
                    st.download_button('オッズ履歴付き.keibaコピーを保存', copied,
                                       file_name=identity['race_id']+'_with_odds.keiba', key=key+'_copy')
                except (ValueError, TypeError, KeyError):
                    caption('現在の読込元と一致する.keibaが確認できないため、コピー出力を保留しています。')
            st.download_button('オッズ履歴JSONを保存', json.dumps(dict(odds_history=state['history']), ensure_ascii=False, indent=2),
                               file_name=identity['race_id']+'_odds.json', key=key+'_json')
    unseen = [q for q in state['history']
              if q['observation_id'] not in runtime['seen_history_ids']]
    if unseen:
        activate_observation(unseen[-1])
    choices = [('未取得', None)]
    choices += [('保存時オッズ', q) for q in state['saved']] + [('更新オッズ', q) for q in state['history']]
    # A saved prediction's price is not the current pre-race observation.
    # Keep it selectable, but require an explicit choice until new data exists.
    def observation_label(i):
        label, quote = choices[i]
        return label if quote is None else (
            f"{i}. {label} · {odds.received_label(quote)} {odds.format_time(quote.get('received_at'))}")
    active_index = next((i for i in range(len(choices)-1, 0, -1)
                         if choices[i][1]['observation_id'] == runtime['active_observation']), 0)
    with st.expander('オッズ履歴の切替', expanded=False):
        index = st.selectbox('表示するオッズ観測', range(len(choices)),
                             index=active_index,
                             format_func=observation_label,
                             key=key+'_observation_v3_'+str(runtime['revision'])+'_'+str(len(choices)))
        label, quote = choices[index]
    runtime['active_observation'] = quote['observation_id'] if quote is not None else None
    if quote is None:
        return odds.overlay(view, None, 'オッズ未取得')
    start_at = odds.start_from_result(result)
    st.caption(f"取得元：{quote.get('source','不明')}｜"
               f"単勝{quote['coverage']['win']['count']}頭・"
               f"複勝{quote['coverage']['place']['count']}頭｜"
               f"更新時刻：{odds.format_time(quote.get('observed_at'))}")
    with st.expander('オッズの詳細・注意事項', expanded=False):
        start_at = odds.start_from_result(result)
        caption(f"{label}｜{odds.received_label(quote)}：{odds.format_time(quote.get('received_at'))}｜提供元更新：{odds.format_time(quote.get('observed_at'))}｜情報源：{quote['source']}")
        if quote.get('acquisition_method') == 'manual_html':
            caption('HTML取込日時はサイトから価格を取得した日時ではありません。価格の鮮度はHTML内の提供元更新時刻で確認します。')
        if quote.get('acquisition_method') in ('keibalab_historical_html', 'yuma_historical_html'):
            caption('過去掲載オッズです。配信元の価格発表時刻は未確認の場合があります。'
                    '確定最終オッズと一致する保証はありません。'
                    'AIの順位・スコアは変更せず、価格だけ上書き表示します。')
        if quote.get('acquisition_method') == 'netkeiba_free_json':
            caption('配信元表示時刻を使用。JRA公式との直接接続ではなく、'
                    '無料版の更新制限・遅延があります。取得できた券種だけ表示し、'
                    '他の時刻の価格で補完しません。購入直前は公式で確認してください。')
        if quote.get('acquisition_method') == 'nar_official_zip':
            caption('公式CSVには馬名・個別オッズ更新日時がありません。保存出走馬の馬番とZIP作成時刻で照合。'
                    '発売開始前・欠損・締切後の価格を最新として扱わないでください。')
        caption(f"{quote['horse_count']}／{quote['expected_horses']}頭（単勝または複勝）｜" + odds.freshness(quote, start_at))
        caption(' · '.join(f"{odds.LABELS[k]} {v['count']}／{v['expected']}件" for k,v in quote['coverage'].items()))
        pairs = [dict(券種=odds.LABELS[p['kind']], 馬番='－'.join(map(str,p['horses'])), オッズ=odds.price_text(p))
                 for p in quote['prices'] if p['kind'] in ('wide','quinella')]
        if pairs:
            with st.expander('馬連・ワイドの組み合わせオッズ', expanded=False):
                st.dataframe(pairs, hide_index=True, use_container_width=True)
    return odds.overlay(view, quote, label)
