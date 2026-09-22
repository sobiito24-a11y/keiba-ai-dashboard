"""Compact Dashboard-only HTML presentation; no prediction or classification."""
from __future__ import annotations

from html import escape
from typing import Any, Mapping


def jra_purchase_navigation_html(navigation: Mapping[str, Any]) -> str:
    if not navigation.get("show"):
        return ""
    def text(value: Any) -> str:
        return escape(str(value), quote=True)

    def horses(items, empty="該当なし") -> str:
        return " / ".join(
            f'<span style="display:inline-block;max-width:100%;">{text(h["number"])}番 {text(h["name"])}</span>'
            for h in items
        ) or empty

    parts = ['<section class="ka-dashboard-card" aria-label="JRA 買い方ナビ" style="overflow-wrap:anywhere;">',
             '<div class="ka-dashboard-title">JRA 買い方ナビ</div>']
    status = navigation["status"]
    if status in {"対象外", "判定材料不足"}:
        parts.append(f'<p><strong>{text(navigation["description"] if status == "対象外" else status)}</strong></p>')
    else:
        display_status = {"強軸": "軸あり", "上位混戦": "複数候補", "評価分裂": "見送り寄り"}[status]
        buying = {"強軸": "中心を軸候補に、本線・狙いから相手を選ぶ", "上位混戦": "1頭固定せず、本線・押さえ・狙いから絞る", "評価分裂": "評価が割れているため、無理に買わない"}[status]
        title = "今回の判断" if status == "評価分裂" else "今回の買い候補"
        roles = ("中心", "本線", "狙い", "押さえ参考")
        parts.append(f'<p><strong style="font-size:1.1rem;">{title}</strong> ― {display_status}</p>')
        for role in roles:
            parts.append(f'<p><strong>{role}</strong>：{horses(navigation["buy_groups"][role], empty="なし" if role == "狙い" else "該当なし")}</p>')
        parts.append(f'<p><strong>穴注意</strong>：{horses(navigation["hole_attention"], empty="なし")}</p>')
        visible_numbers = {h["number"] for role in roles for h in navigation["buy_groups"][role]} | {h["number"] for h in navigation["hole_attention"]}
        for horse in navigation.get("layoff_warnings", []):
            if horse["number"] not in visible_numbers:
                continue
            parts.append(f'<p>⚠️ {horses([horse])} 長期休養明け：{horse["days"]}日</p>')
            if horse['is_top1']:
                parts.append('<p class="ka-note">軸評価は高いが、休養明けのため固定は慎重</p>')
        parts.append(f'<p><strong>買い方</strong>：{buying}</p>')
        parts.append('<details><summary>詳細を見る</summary>')
        parts.append(f'<p>{text(navigation["description"])}</p>')
        parts += [
                  '<div class="ka-note" style="display:flex;flex-wrap:wrap;gap:.35rem 1rem;">',
                  '<span>純能力1位とTop5 1位：'+('一致' if navigation['leaders_match'] else '不一致')+'</span>',
                  f'<span>Top5 2位差：{navigation["top5_score_gap"]:.2f}</span>',
                  f'<span>純能力2位差：{navigation["ability_gap"]:.2f}</span>',
                  f'<span>Top5入替：{navigation["swap_count"]}頭</span></div>']
        if navigation['axis']:
            parts += [f'<p><strong>軸候補</strong>：{horses([navigation["axis"]])}<br>',
                      f'<strong>相手候補</strong>：{horses(navigation["partners"])}</p>']
        labels = {'CORE': '純能力・今回評価とも上位の本線候補',
                  'ABILITY': 'Top5外でも純能力上位。機械的に消さない相手候補',
                  'SETUP': '今回上昇馬。展開・調教など今回条件で浮上した相手候補'}
        for role, label in labels.items():
            parts.append(f'<p><strong>{role}</strong> <span class="ka-note">{label}</span><br>{horses(navigation["groups"][role])}</p>')
        parts.append('<strong>運用ガイド</strong><ul>'+''.join(f'<li>{text(g)}</li>' for g in navigation['guides'])+'</ul>')
        parts.append('<div class="ka-note">買い候補は詳細分析表のJRA最終印が◎・○・▲・✔︎の馬です。△は押さえ参考、✓は穴注意として別表示します。見送り寄りは参考情報です。Top5は評価位置の確認とグループ内の並び順に使用し、役割は変更しません。休養注意も順位・スコア・印を変更しません。</div></details>')
    parts.append('</section>')
    return ''.join(parts)
