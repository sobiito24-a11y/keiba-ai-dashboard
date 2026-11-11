"""Read-only annotations below the saved race-interval cell.

The bounds are hypotheses for visual review, not calibrated betting
probabilities or ability penalties.  Requires a verified numerical interval;
JRA uses only the saved A/B/C/D training category, NAR never assumes one.
"""
from __future__ import annotations

import math


def attention(days, mode, training=None):
    """A short visual note + explanation; no ability / formal score mutation.

    None means no exceptional interval note or a missing/invalid input.
    """
    if isinstance(days, bool) or not isinstance(days, (int, float)):
        return None
    if not math.isfinite(days) or not 0 <= days <= 10000:
        return None
    if mode not in ("jra", "nar"):
        return None
    if mode == "nar":
        if days >= 365:
            return ("1年以上・状態確認", "info",
                    "地方は休養日数だけで消さず、転入・休養前クラス・同場実績と状態を再確認")
        if days >= 180:
            return ("半年超・条件確認", "info",
                    "地方の長期休養は日数による一律減点なし。今回のクラスと同場実績を再確認")
        if days >= 90:
            return ("3ヶ月超・条件確認", "info",
                    "地方では3ヶ月以上を休養だけで軽視せず、今回の条件を再確認")
        return None
    if days < 70:
        return None
    grade = str(training or "").strip().upper()
    if days >= 365:
        interval = "1年以上"
    elif days >= 180:
        interval = "半年超"
    else:
        interval = "70日超"
    if grade in ("C", "D"):
        label = "長休×調教C/D" if days >= 180 else "調教C/D注意"
        return (label, "caution",
                f"中央{interval}かつ保存調教{grade}。休養と調教を組み合わせて再確認（機械的減点なし）")
    if grade in ("A", "B"):
        label = "長休×調教A/B" if days >= 180 else "調教A/B確認"
        return (label, "info",
                f"中央{interval}・保存調教{grade}。休養だけで消さず、他条件も確認（加点なし）")
    label = "長休・調教未取得" if days >= 180 else "調教未取得"
    return (label, "info",
            f"中央{interval}だが保存調教A/B/C/Dが未取得。仕上がりを判定できません")
