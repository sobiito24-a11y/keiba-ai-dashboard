"""Folded review of the *same visible all-runner table*, with post-race columns.

This intentionally calls columns(view), records(view) and _cell(horse, cells, key)
from the normal explorer.  It does not reconstruct historical predictions or
change any indexes, positions, comments, or marks.
"""
from __future__ import annotations

from html import escape

from .prediction_table_ui import number
from .race_explorer_columns import columns, records
from .race_explorer_common import value
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
    # Keep ALL original fields; bring pure ability beside horse name in the
    # review ONLY so the three important columns can remain sticky together.
    # The live prediction table keeps its original column order and controls.
    original_schema = [spec for spec in columns(view) if not spec.get("table_hidden")]
    if any(spec["key"] == "ability" for spec in original_schema):
        schema = [spec for spec in original_schema if spec["key"] != "ability"]
        name_at = next(i for i, spec in enumerate(schema) if spec["key"] == "name")
        ability_spec = next(spec for spec in original_schema if spec["key"] == "ability")
        schema.insert(name_at + 1, ability_spec)
    else:
        schema = original_schema
    cols, cells = [spec["key"] for spec in schema], records(view)
    by_no = {str(r["horse_no"]): r for r in review.get("runners", [])
             if isinstance(r, dict) and r.get("horse_no") is not None}
    widths, mobile_widths = comparison_widths()
    # Explicitly reserve room for the pinned ability cell; all other
    # predictions preserve their original width settings.
    widths = dict(widths, ability=104)
    mobile_widths = dict(mobile_widths, ability=94)
    # All original prediction columns retain the exact same width classes
    # (particularly "col-number" for the third sticky column on mobile).
    # Only the six factual post-race columns are appended.
    extra = [
        ("finish", "実着順", 88, 72),
        ("final_win_odds", "最終単勝", 112, 95),
        ("final_popularity", "最終人気", 94, 78),
        ("corner4", "実4角", 84, 72),
        ("win_payout", "単勝払戻", 118, 98),
        ("place_payout", "複勝払戻", 118, 98),
    ]
    width = sum(widths.get(key, 88) for key in cols) + sum(item[2] for item in extra)
    mobile_width = sum(mobile_widths.get(key, 72) for key in cols) + sum(item[3] for item in extra)
    headers = [
        '<th scope="col" class="col-'+_plain(spec["key"])+
        (' col-number' if spec["key"] == "no" else '')+'"><span class="column-label">'+
        _plain(spec["label"])+"</span></th>"
        for spec in schema
    ] + [
        '<th scope="col" class="review-actual review-'+key+'">'+label+"</th>"
        for key, label, _, _ in extra
    ]
    payouts_by_horse = {
        (str(payment.get("selection")), payment.get("bet_type")): payment.get("payout_yen")
        for payment in review.get("payouts", [])
        if payment.get("bet_type") in ("win", "place")
    }
    payouts_available = bool(review.get("payouts"))
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
                # Match the original horse-select visual structure without
                # emitting an interactive button / duplicate event target.
                contents = ('<div class="horse-select"><span class="horse-name-age"><strong>'+
                            value(info.get("name"))+'</strong><span class="horse-age">'+
                            value(info.get("age"), "―")+"</span></span></div>")
            else:
                contents = _cell(horse, info, key)
            cls = 'col-'+_plain(key)+(' col-number' if key == "no" else '')
            parts.append('<td class="'+cls+'" data-label="'+_plain(
                next(spec["label"] for spec in schema if spec["key"] == key)
            )+'">'+contents+"</td>")
        actual = by_no.get(no)
        for key, _, _, _ in extra:
            if key in ("win_payout", "place_payout"):
                kind = "win" if key == "win_payout" else "place"
                yen = payouts_by_horse.get((no, kind))
                text = f"{yen:,}円" if yen is not None else ("―" if payouts_available else "未取得")
            else:
                text = _result_value(actual, key)
            label = ' review-placed' if key == 'finish' and actual and actual.get('finish') in (1, 2, 3) else ''
            parts.append('<td class="review-actual review-'+key+label+'">'+_plain(text)+"</td>")
        rank = info.get("ability_rank")
        try:
            rank = int(rank) if rank is not None and not isinstance(rank, bool) else None
            if rank is not None and rank < 1:
                rank = None
        except (ValueError, TypeError, OverflowError):
            rank = None
        score = info.get("ability")
        try:
            score = float(score) if score is not None and not isinstance(score, bool) else None
            if score is not None and not (-1e8 < score < 1e8):
                score = None
        except (ValueError, TypeError, OverflowError):
            score = None
        rows.append(
            '<tr data-review-no="'+_plain(no)+
            '" data-review-rank="'+_plain(rank if rank is not None else "")+
            '" data-review-score="'+_plain(score if score is not None else "")+
            '">'+''.join(parts)+"</tr>")
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
        '<h3 class="review-heading">馬券種別の払戻金 <small>（表示額は保存された基準額あたり）</small></h3>'+payouts+
        '<h3 class="review-heading">予想時の全頭一覧 ＋ 確定結果</h3>'
        '<div class="review-order-toolbar"><label for="postrace-order">並び順</label>'
        '<select id="postrace-order" aria-label="振り返りの並び順">'
        '<option value="number">馬番順</option><option value="ability">純能力順</option>'
        '</select><span>馬番・馬名・純能力は左右スクロールしても固定</span></div>'
        '<p class="help">予想時の列・値は全て保持。振り返りでは純能力を馬名の直後に移動し'
        '3列を固定表示しています。右へスクロールすると実着順・最終単勝・'
        '実4角・単勝／複勝払戻を比較できます。</p>'
        '<div class="explorer-table-scroll postrace-review-scroll" tabindex="0"'
        ' aria-label="結果照合・縦横スクロール">'
        '<table class="explorer-table" style="--comparison-width:'+str(width)+
        'px;--comparison-mobile-width:'+str(mobile_width)+'px">'
        '<thead><tr>'+''.join(headers)+'</tr></thead><tbody>'+
        ''.join(rows)+'</tbody></table></div>'
        '<p class="help">参照元：'+_plain(review.get("source") or "未取得")+
        '｜結果・払戻は元の予想とは別保存</p></div></details>'
    )
