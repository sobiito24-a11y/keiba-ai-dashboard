"""Folded review of the *same visible all-runner table*, with post-race columns.

This intentionally calls columns(view), records(view) and _cell(horse, cells, key)
from the normal explorer.  It does not reconstruct historical predictions or
change any indexes, positions, comments, or marks.
"""
from __future__ import annotations

from html import escape

from .prediction_table_ui import number
from .race_explorer_columns import columns, records
from .race_explorer_common import number_badge, value
from .race_result_review import LABELS
from .race_explorer_ui import _cell, comparison_widths


def _plain(value):
    return escape(str(value), quote=True)


def _result_value(item, key):
    if item is None:
        return "未取得"
    if key == "finish":
        val = item.get("finish")
        return str(val) + "着" if isinstance(val, int) else str(val) if val else "未取得"
    if key == "final_win_odds":
        val = item.get("final_win_odds")
        return f"{val:g}倍" if val is not None else "未取得"
    if key == "final_popularity":
        val = item.get("final_popularity")
        return str(val) + "番人気" if val is not None else "未取得"
    val = item.get("corner4")
    return str(val) + "番手" if val is not None else "未取得"


def review_html(view, review):
    """Mirror every *visible* normal column in exact order, then append results.

    No primary-table IDs, data-horse, data-column-sort or data-horse-open
    controls are emitted: existing browser code must operate only on the
    pre-race table.  The review stays closed by default.
    """
    if not view or not isinstance(review, dict):
        return ""
    race_id = str(review.get("race_id") or "")
    if not race_id:
        return ""
    schema = [spec for spec in columns(view) if not spec.get("table_hidden")]
    cols, cells = [s["key"] for s in schema], records(view)
    by_no = {str(r["horse_no"]): r for r in review.get("runners", [])
             if isinstance(r, dict) and r.get("horse_no") is not None}
    widths, mobile_widths = comparison_widths()
    extra_widths = (100, 116, 102, 98)
    width = sum(widths.get(key, 88) for key in cols) + sum(extra_widths)
    mobile_width = sum(mobile_widths.get(key, 72) for key in cols) + sum(extra_widths)
    headers = [
        '<th scope="col" class="col-'+_plain(spec["key"])+'">'+_plain(spec["label"])+"</th>"
        for spec in schema
    ] + [
        '<th scope="col" class="review-actual">'+label+"</th>"
        for label in ("実着順", "最終単勝", "最終人気", "実4角")
    ]
    rows = []
    for horse in sorted(view, key=lambda h: (number(h.get("no")) is None,
                                             number(h.get("no")) or 0)):
        no = str(horse.get("no") or "")
        info = cells.get(no, {})
        parts = []
        for key in cols:
            if key == "user":
                # Manual ✓ belongs only to the interactive prediction table.
                contents = '<span class="missing-cell">―</span>'
            elif key == "name":
                contents = ('<span class="horse-name-age"><strong>'+
                            value(info.get("name"))+'</strong><span class="horse-age">'+
                            value(info.get("age"), "―")+"</span></span>")
            else:
                contents = _cell(horse, info, key)
            parts.append('<td class="col-'+_plain(key)+'">'+contents+"</td>")
        actual = by_no.get(no)
        for key in ("finish", "final_win_odds", "final_popularity", "corner4"):
            text = _result_value(actual, key)
            label = ' review-placed' if key == 'finish' and actual and actual.get('finish') in (1, 2, 3) else ''
            parts.append('<td class="review-actual'+label+'">'+_plain(text)+"</td>")
        rows.append("<tr>"+''.join(parts)+"</tr>")
    payout_rows = []
    for payment in review.get("payouts", []):
        kind = LABELS.get(payment.get("bet_type"), payment.get("bet_type") or "不明")
        payout_rows.append(
            "<tr><td>"+_plain(kind)+"</td><td>"+_plain(payment.get("selection"))+
            "</td><td>"+_plain(f'{payment["payout_yen"]:,}円')+
            "</td><td>"+_plain(f'{payment["stake_yen"]:,}円あたり')+"</td></tr>"
        )
    if payout_rows:
        payouts = ('<div class="review-payout-scroll"><table class="review-payout-table">'
                   '<thead><tr><th>式別</th><th>的中組合せ</th><th>払戻金</th><th>基準額</th></tr></thead>'
                   '<tbody>'+''.join(payout_rows)+'</tbody></table></div>')
    else:
        payouts = '<p class="help">払戻金未取得（取得していない式別は推測しません）。</p>'

    return (
        '<details class="overview-accordion" id="postrace-review" data-persist-panel>'
        '<summary><span class="overview-title">レース振り返り</span>'
        '<span class="overview-description">予想時の横一覧をそのまま再掲し、実着順・最終単勝・払戻を追加</span></summary>'
        '<div class="overview-body"><p class="help">元の予想指数・順位・クラス注目・過去走は変更していません。'
        '右端に確定結果を追加しています。結果がない馬は未取得のまま表示します。'
        'ここでの最終単勝は発走前の購入可能オッズではありません。'
        '馬券ごとの払戻は入力された公表値で、購入履歴や回収率ではありません。</p>'
        '<div class="explorer-table-scroll postrace-review-scroll">'
        '<table class="explorer-table" style="--comparison-width:'+str(width)+
        'px;--comparison-mobile-width:'+str(mobile_width)+'px">'
        '<thead><tr>'+''.join(headers)+'</tr></thead><tbody>'+
        ''.join(rows)+'</tbody></table></div>'
        '<h3>馬券種別の払戻金</h3>'+payouts+
        '<p class="help">参照元：'+_plain(review.get("source") or "未取得")+
        '｜結果・払戻は元の予想とは別保存</p></div></details>'
    )
