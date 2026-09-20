"""Compact Dashboard-only HTML presentation; no prediction or classification."""
from __future__ import annotations

from html import escape
from typing import Any, Mapping


def jra_purchase_navigation_html(navigation: Mapping[str, Any]) -> str:
    if not navigation.get("show"):
        return ""
    def text(value: Any) -> str:
        return escape(str(value), quote=True)

    def horses(items) -> str:
        return " / ".join(
            f'<span style="display:inline-block;max-width:100%;">{text(h["number"])}番 {text(h["name"])}</span>'
            for h in items
        ) or "該当なし"

    parts = ['<section class="ka-dashboard-card" aria-label="JRA 買い方ナビ" style="overflow-wrap:anywhere;">',
             '<div class="ka-dashboard-title">JRA 買い方ナビ</div>']
    status = navigation["status"]
    if status in {"対象外", "判定材料不足"}:
        parts.append(f'<p><strong>{text(navigation["description"] if status == "対象外" else status)}</strong></p>')
    else:
        parts += [f'<p><strong style="font-size:1.1rem;">レース判定：{text(status)}</strong><br>{text(navigation["description"])}</p>']
        if status == "評価分裂":
            parts.append('<p><strong>見送り優先</strong>：印順購入は非推奨。買う場合は少額で候補を広めに確認。</p>')
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
        parts.append('<div class="ka-note">◎は現行Top5の最上位評価、強軸はレース構造の判定です。◎でも上位混戦・評価分裂になる場合があります。</div>')
    parts.append('</section>')
    return ''.join(parts)
