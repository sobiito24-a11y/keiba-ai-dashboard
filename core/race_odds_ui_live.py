"""Fresh NAR odds UI module; isolate from cached legacy odds panel imports.

Intentionally loads through a new module path so a running Streamlit session
cannot reuse the disabled, old connector-only button implementation.
"""
from datetime import datetime
import json
from . import race_odds as odds


def render(result, view):
    import streamlit as st
    from html import escape
    def caption(value):
        st.markdown('<p style="color:#bbcee5;font-size:13px;line-height:1.5;overflow-wrap:anywhere">'+escape(str(value))+'</p>', unsafe_allow_html=True)
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
    is_nar = identity['mode'] == 'nar'
    if not is_nar:
        jra_id = identity['race_id']
        st.caption('JRAオッズ更新（試験）：netkeibaの無料配信から単勝・複勝・'
                   '馬連・ワイドの取得を試みます。JRA公式の直接取得ではありません。'
                   '無料版には更新間隔・利用制限があり、最新の購入可能価格とは限りません。')
        with st.expander('JRA公式／netkeibaの元画面を確認', expanded=False):
            st.markdown('[JRA公式オッズ](https://www.jra.go.jp/)'
                        '（公式サイトの「オッズ」から選択）')
            st.markdown(
                '[netkeiba・このレースのオッズ](https://race.netkeiba.com/odds/index.html?race_id='
                + jra_id + '&type=b1)'
                '（単勝・複勝／馬連・ワイドへ切替）')
            st.caption('実際の投票価格は購入直前にJRA公式の販売画面で再確認。'
                       'アクセスが制限された場合はスクショ・HTML取込を使用。'
                       '自動巡回や更新回数の上限制限回避は行いません。')
    if is_nar:
        st.caption('NAR公式ZIPモード：無料の単勝・複勝・馬連・ワイド取得を試せます。'
                   '約2分間隔の配布です。ZIP作成時刻は実際のオッズ発表時刻ではありません。'
                   '個人確認用の表示に限定し、転載・再配布しません。')
        st.markdown('[NAR公式データダウンロード](https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/TodayRaceInfoTop)'
                    '（取得できない場合は公式ZIPを手動で保存して下から取込）')
    if getattr(result, '_race_odds_error', None): st.warning(result._race_odds_error)
    if st.button('オッズ更新（無料・試験）' if not is_nar and not connection.available
                 else 'オッズ更新', key=key+'_fetch', disabled=False):
        now = datetime.now(odds.JST)
        if is_nar:
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
        else:
            # Licensed JSON bridge, when configured, takes priority.
            # Otherwise only one explicit user-triggered read of the FREE
            # netkeiba action=init feed (three ticket-kind requests).
            last = st.session_state.get(key+'_last_request')
            min_delay = 30 if connection.available else 180
            global_last = st.session_state.get('_jra_free_odds_global_request')
            if last and (now-last).total_seconds() < min_delay:
                st.session_state[key+'_status'] = (
                    f'同じレースの再取得は{min_delay}秒以上あけてください。'
                    '保存済みの最新観測は下から選べます。')
            elif (not connection.available and global_last and
                  (now-global_last).total_seconds() < 30):
                st.session_state[key+'_status'] = (
                    '無料配信への連続アクセスを抑制しています。'
                    '他レースは30秒以上あけて更新してください。')
            else:
                st.session_state[key+'_last_request'] = now
                if not connection.available:
                    st.session_state['_jra_free_odds_global_request'] = now
                try:
                    with st.spinner('JRAオッズを取得し、保存した馬番と照合中…'):
                        if connection.available:
                            quote = odds.validate(connection.fetch(identity['race_id']), identity)
                            quote['acquisition_method'] = 'authorized_json'
                        else:
                            from .jra_netkeiba_odds import fetch_once
                            quote = fetch_once(identity, result.race_info or {}, now=now)
                        history = odds.merge(state['history'], [quote], identity)
                    added = len(history)-len(state['history'])
                    state['history'] = history
                    activate_observation(quote)
                    st.session_state[key+'_status'] = (
                        f"取得：{quote['horse_count']}／{quote['expected_horses']}頭。"
                        + ('有効価格未取得。' if not quote['prices'] else
                           ('netkeiba無料配信の観測値を表示。' if not connection.available
                            else '接続元のオッズを表示。'))
                        + ('同じ配信時刻のため追加更新なし。' if not added else '')
                    )
                except ValueError as exc:
                    st.session_state[key+'_status'] = (
                        'JRAオッズ未取得：' + str(exc) +
                        '。取得できない時は予想オッズを代用しません。')
                except Exception:
                    st.session_state[key+'_status'] = (
                        'JRAオッズ取得に失敗。無料配信の利用制限・応答変更・通信状態を確認してください。'
                        '保存時の予想と旧オッズ履歴は保持しています。')

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
    unseen = [q for q in state['history']
              if q['observation_id'] not in runtime['seen_history_ids']]
    if unseen:
        activate_observation(unseen[-1])
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
    if st.session_state.get(key+'_status'):
        st.info(st.session_state[key+'_status'])
    choices = [('未取得：新しいHTMLを取り込んでください', None)]
    choices += [('保存時オッズ', q) for q in state['saved']] + [('更新オッズ', q) for q in state['history']]
    # A saved prediction's price is not the current pre-race observation.
    # Keep it selectable, but require an explicit choice until new data exists.
    def observation_label(i):
        label, quote = choices[i]
        return label if quote is None else (
            f"{i}. {label} · {odds.received_label(quote)} {odds.format_time(quote.get('received_at'))}")
    active_index = next((i for i in range(len(choices)-1, 0, -1)
                         if choices[i][1]['observation_id'] == runtime['active_observation']), 0)
    index = st.selectbox('表示するオッズ観測', range(len(choices)),
                         index=active_index,
                         format_func=observation_label,
                         key=key+'_observation_v3_'+str(runtime['revision'])+'_'+str(len(choices)))
    label, quote = choices[index]
    runtime['active_observation'] = quote['observation_id'] if quote is not None else None
    if quote is None:
        return odds.overlay(view, None, 'オッズ未取得')
    start_at = odds.start_from_result(result)
    caption(f"{label}｜{odds.received_label(quote)}：{odds.format_time(quote.get('received_at'))}｜提供元更新：{odds.format_time(quote.get('observed_at'))}｜情報源：{quote['source']}")
    if quote.get('acquisition_method') == 'manual_html':
        caption('HTML取込日時はサイトから価格を取得した日時ではありません。価格の鮮度はHTML内の提供元更新時刻で確認します。')
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
