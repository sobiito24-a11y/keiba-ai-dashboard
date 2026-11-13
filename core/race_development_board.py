"""Read-only three-tab formation board beneath the JRA/NAR horse table.

The visual language follows the user's reference: cyan sky, bright turf,
a dotted race-path header, and tapered, staggered clusters of horse silhouettes.
The artwork is an original inline SVG; it is not taken from netkeiba.
"""
from html import escape

from .race_development_positions import STAGES, layout

_LABELS = {
    "start": "スタート後",
    "third": "3コーナー",
    "fourth": "4コーナー",
}

# Original small galloping silhouette. No third-party SVG/image assets.
_HORSE = (
    '<svg class="ka-pace-horse-svg" viewBox="0 0 80 39" aria-hidden="true" focusable="false">'
    '<path d="M15 16c8-5 21-8 33-4l9-6 8-2 3 4 8 2-1 6-9 2-6-3-5 9-6 2'
    '-1 7 7 3-4 3-10-7-6-8-8 1-6 8-5 1 4-12-2-9-9 2-6-1 6-4'
    ' 9-1 6 3z" fill="#703819" stroke="#3c2418" stroke-width="1.2" stroke-linejoin="round"/>'
    '<path d="M12 17 4 12 2 17 8 21M29 23l-7 11-7 1M45 21l3 8 12 4" '
    'fill="none" stroke="#35251b" stroke-width="3.2" stroke-linecap="round"/>'
    '<path d="m53 12 1-7 4 2 2-5 3 5" fill="#4a2c1b"/>'
    '<circle cx="68" cy="11" r="1.25" fill="#1e170f"/>'
    '</svg>'
)


def _short_names(names, limit=5):
    """Keep source spelling; identical abbreviations remain distinguishable by number."""
    return {name: name if len(name) <= limit else name[:limit] for name in names}


def _runner_html(horse, stage, short):
    no, frame = horse["no"], horse["frame"]
    name = horse["name"]
    start = str(horse["start"]) + "番手" if horse["start"] is not None else "未取得"
    fourth = str(horse["fourth"]) + "番手" if horse["fourth"] is not None else "未取得"
    position = f'{horse["rank_display"]}番手'
    kind = "補間による参考位置" if stage == "third" else "保存予測"
    detail = (f'馬番{no} {name}｜{_LABELS[stage]}：{position}（{kind}）'
              f'｜序盤：{start}｜4角：{fourth}')
    label = short[name]
    return (
        '<button type="button" class="ka-pace-runner" data-pace-runner="'
        + escape(str(no), quote=True) + '"'
        + ' data-pace-full-name="' + escape(name, quote=True) + '"'
        + ' data-pace-description="' + escape(detail, quote=True) + '"'
        + ' style="--px:' + f'{horse["x"]:.2f}' + '%;--py:' + f'{horse["y"]:.2f}' + '%"'
        + ' title="' + escape(detail, quote=True) + '"'
        + ' aria-label="' + escape(detail, quote=True) + '">'
        + '<span class="ka-pace-runner-figure">'
        + _HORSE
        + '<span class="ka-pace-number ka-pace-frame-' + str(frame or 0) + '">'
        + str(no) + '</span></span>'
        + '<span class="ka-pace-horse-name">' + escape(label) + '</span>'
        + '</button>'
    )


def board_html(view):
    """Return one tabbed section; the live DOM only toggles precomputed panels."""
    formations = layout(view)
    first = formations["start"]
    names = {h["name"] for stage in STAGES for h in formations[stage]["runners"]}
    short = _short_names(names)
    html = [
        '<section id="ka-pace-board" class="ka-pace-board" aria-labelledby="ka-pace-title">',
        '<header class="ka-pace-heading"><span class="ka-pace-kicker">RACE POSITION MAP</span>',
        '<h2 id="ka-pace-title">AI展開予測</h2>',
        '<p>スタート後・3角・4角の馬群を比較</p></header>',
        '<div class="ka-pace-stage-tabs" role="tablist" aria-label="展開位置">',
    ]
    for stage in STAGES:
        selected = stage == "start"
        html.append(
            '<button type="button" class="ka-pace-tab" role="tab"'
            ' id="ka-pace-tab-' + stage + '" aria-controls="ka-pace-scene-' + stage + '"'
            ' aria-selected="' + str(selected).lower() + '" tabindex="'
            + ("0" if selected else "-1") + '" data-pace-stage="' + stage + '">'
            + _LABELS[stage] + '</button>'
        )
    html += ['</div>', '<div class="ka-pace-stage-rail" aria-hidden="true">'
             '<i></i><i></i><i></i></div>']
    for stage in STAGES:
        group = formations[stage]
        hidden = '' if stage == "start" else ' hidden'
        html.append(
            '<div class="ka-pace-scene" role="tabpanel" id="ka-pace-scene-' + stage
            + '" aria-labelledby="ka-pace-tab-' + stage + '"'
            + hidden + '><div class="ka-pace-turf" aria-label="' + _LABELS[stage] + 'の予測隊列">'
        )
        if group["runners"]:
            for horse in group["runners"]:
                html.append(_runner_html(horse, stage, short))
        else:
            html.append('<p class="ka-pace-no-runners">この区間の位置予測は未取得です。</p>')
        html.append('</div>')
        if group["missing"]:
            html.append(
                '<p class="ka-pace-unavailable">位置未取得：'
                + '・'.join(escape(str(h["no"])) + ' ' + escape(short.get(h["name"], h["name"]))
                           for h in group["missing"])
                + '（図内に推定配置しません）</p>'
            )
        else:
            html.append('<p class="ka-pace-unavailable">位置予測のある馬をすべて表示しています。</p>')
        html.append('</div>')
    html += [
        '<p class="ka-pace-selected" id="ka-pace-selected" role="status" aria-live="polite">'
        '馬をタップすると馬名と位置予測を確認できます。</p>',
        '<p class="ka-pace-disclaimer">スタート後・4角は保存された発走前の予測順位。'
        '3角は両者の補間であり実測ではありません。馬群の左右位置や間隔は'
        '重なりを避けるための配置で、内外の進路・馬身差を表しません。'
        'AIランク・印・純能力には一切加点しません。</p>',
        '</section>'
    ]
    return ''.join(html)
