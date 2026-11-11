"""Post-race-only result/payout overlay for .keiba; frozen predictions stay unchanged.

Result and payout records must be sourced separately from pre-race observations.
No final odds, finish, or dividend is ever copied into prediction_result.
"""
from __future__ import annotations

import copy
import csv
import io
import math
import re
import unicodedata
from collections.abc import Mapping

KEY = "race_results_v1"
LABELS = {
    "win": "単勝", "place": "複勝", "bracket_quinella": "枠連",
    "quinella": "馬連", "wide": "ワイド", "exacta": "馬単",
    "trio": "3連複", "trifecta": "3連単", "bracket_exacta": "枠単",
}
ALIASES = {v: k for k, v in LABELS.items()}
ALIASES.update({"３連複": "trio", "３連単": "trifecta"})
LENGTHS = {"win": 1, "place": 1, "bracket_quinella": 2,
           "quinella": 2, "wide": 2, "exacta": 2,
           "trio": 3, "trifecta": 3, "bracket_exacta": 2}
UNORDERED = {"quinella", "wide", "trio", "bracket_quinella"}
BRACKET = {"bracket_quinella", "bracket_exacta"}
STATUSES = {"取消", "除外", "中止", "失格", "競走中止", "出走取消", "発走除外", "不成立"}
RESULT_COLUMNS = ["馬番", "馬名", "着順", "最終単勝", "最終人気", "実4角"]
PAYOUT_COLUMNS = ["式別", "組合せ", "払戻金", "基準額"]


def _horse_key(value):
    if isinstance(value, bool):
        raise ValueError("馬番に真偽値は使えません")
    s = str(value or "").strip()
    if not s.isdigit() or not 1 <= int(s) <= 99:
        raise ValueError("馬番は1～99の整数で入力してください")
    return str(int(s))


def _name(value):
    return "".join(unicodedata.normalize("NFKC", str(value or "")).split())


def _money(value, label, *, allow_zero=False):
    if isinstance(value, bool):
        raise ValueError(f"{label}が不正です")
    v = str(value).replace(",", "").replace("円", "").strip()
    if not re.fullmatch(r"\d+", v) or int(v) < (0 if allow_zero else 1):
        raise ValueError(f"{label}には正の整数を入力してください")
    return int(v)


def _int_optional(value, label):
    v = str(value if value is not None else "").strip()
    if not v or v in ("未取得", "―", "—"):
        return None
    if not re.fullmatch(r"\d+", v) or int(v) < 1:
        raise ValueError(f"{label}は1以上の整数です")
    return int(v)


def _finish(value):
    v = str(value if value is not None else "").strip()
    if v in ("", "未取得", "―", "—"):
        return None
    if v in STATUSES:
        return v
    m = re.fullmatch(r"(\d+)着?", v)
    if m and int(m[1]) >= 1:
        return int(m[1])
    raise ValueError(f"着順が不正です: {v}")


def _odds(value):
    if value is None or str(value).strip() in ("", "未取得", "―", "—"):
        return None
    if isinstance(value, bool):
        raise ValueError("最終単勝オッズが不正です")
    try:
        f = float(str(value).strip().removesuffix("倍"))
    except (TypeError, ValueError) as exc:
        raise ValueError("最終単勝オッズが数値ではありません") from exc
    if not math.isfinite(f) or f < 1:
        raise ValueError("最終単勝オッズは1倍以上の有限数です")
    return f


def identity(race):
    if not isinstance(race, Mapping) or race.get("race_mode") not in ("jra", "nar"):
        raise ValueError("保存レースの主催が不正です")
    rid = str(race.get("race_id") or "")
    if not re.fullmatch(r"\d{12}", rid):
        raise ValueError("保存レースIDが不正です")
    horses = {}
    for raw in race.get("horses") or []:
        key = _horse_key(raw.get("horse_no"))
        name = _name(raw.get("horse_name"))
        if not name or key in horses:
            raise ValueError("元の馬番・馬名が重複または未取得です")
        horses[key] = name
    if not horses:
        raise ValueError("保存馬一覧がありません")
    return rid, race["race_mode"], horses


def validate(race, raw):
    """Check an entire overlay before writing any changed archive bytes."""
    rid, mode, horses = identity(race)
    if not isinstance(raw, Mapping) or raw.get("schema_version") != 1:
        raise ValueError("未対応の結果形式です")
    if raw.get("race_id") != rid or raw.get("mode") != mode:
        raise ValueError("結果と保存予想のレースID／主催が一致しません")
    source = str(raw.get("source") or "").strip()
    if not source:
        raise ValueError("結果の確認元を記載してください")
    runners = raw.get("runners")
    payouts = raw.get("payouts")
    if not isinstance(runners, list) or not isinstance(payouts, list):
        raise ValueError("馬別結果・払戻一覧の形式が不正です")
    if not runners and not payouts:
        raise ValueError("結果・払戻のどちらかを入力してください")
    if len(runners) > len(horses) or len(payouts) > 300:
        raise ValueError("結果または払戻の件数が多すぎます")
    valid_runners = []
    seen = set()
    for item in runners:
        if not isinstance(item, Mapping):
            raise ValueError("馬別結果の行形式が不正です")
        no = _horse_key(item.get("horse_no"))
        if no not in horses or _name(item.get("horse_name")) != horses[no] or no in seen:
            raise ValueError(f"馬番{no}の馬名が保存予想と不一致、または重複しています")
        seen.add(no)
        finish = _finish(item.get("finish"))
        final_odds = _odds(item.get("final_win_odds"))
        pop = _int_optional(item.get("final_popularity"), "最終人気")
        corner = _int_optional(item.get("corner4"), "実4角")
        if pop is not None and pop > len(horses):
            raise ValueError("最終人気が出走馬数を超えています")
        if corner is not None and corner > len(horses):
            raise ValueError("実4角が出走馬数を超えています")
        valid_runners.append(dict(horse_no=no, horse_name=str(item["horse_name"]),
                                  finish=finish, final_win_odds=final_odds,
                                  final_popularity=pop, corner4=corner))
    valid_payouts = []
    payout_seen = set()
    for item in payouts:
        if not isinstance(item, Mapping):
            raise ValueError("払戻行が不正です")
        kind = ALIASES.get(str(item.get("bet_type") or ""), str(item.get("bet_type") or ""))
        if kind not in LENGTHS:
            raise ValueError("未対応の式別です: " + str(item.get("bet_type")))
        raw_selection = str(item.get("selection") or "").strip()
        parts = [p for p in re.split(r"[-－―–ー→\s]+", raw_selection) if p]
        if len(parts) != LENGTHS[kind]:
            raise ValueError(f"{LABELS[kind]}の組合せが不正です: {raw_selection}")
        numbers = [str(int(_horse_key(v))) for v in parts]
        if kind in BRACKET:
            if any(int(n) > 8 for n in numbers):
                raise ValueError("枠番は1～8です")
        elif any(n not in horses for n in numbers):
            raise ValueError("払戻の馬番が保存予想に存在しません")
        if kind not in BRACKET and len(set(numbers)) != len(numbers):
            raise ValueError("同一の馬番を重複して指定できません")
        if kind in UNORDERED:
            numbers.sort(key=int)
        selection = "-".join(numbers)
        key = (kind, selection)
        if key in payout_seen:
            raise ValueError("払戻の式別・組合せが重複しています")
        payout_seen.add(key)
        payment = _money(item.get("payout_yen"), "払戻金")
        unit = _money(item.get("stake_yen", 100), "払戻の基準額")
        valid_payouts.append(dict(bet_type=kind, selection=selection,
                                  payout_yen=payment, stake_yen=unit))
    return dict(schema_version=1, race_id=rid, mode=mode, source=source,
                runners=valid_runners, payouts=valid_payouts,
                status="post_race_verified_input")


def _csv_rows(data, required):
    if len(data) > 1_000_000:
        raise ValueError("CSVは1MB以下にしてください")
    decoded = None
    for encoding in ("utf-8-sig", "cp932"):
        try:
            decoded = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if decoded is None:
        raise ValueError("CSVの文字コードが不明です（UTF-8またはCP932）")
    rows = list(csv.DictReader(io.StringIO(decoded)))
    if not rows or not set(required).issubset(set(rows[0])):
        raise ValueError("CSVの見出しが不正です。テンプレートを確認してください")
    return rows


def parse_results_csv(data):
    rows = _csv_rows(data, RESULT_COLUMNS[:3])
    return [dict(horse_no=r.get("馬番"), horse_name=r.get("馬名"),
                 finish=r.get("着順"), final_win_odds=r.get("最終単勝"),
                 final_popularity=r.get("最終人気"), corner4=r.get("実4角"))
            for r in rows]


def parse_payouts_csv(data):
    rows = _csv_rows(data, PAYOUT_COLUMNS[:3])
    return [dict(bet_type=r.get("式別"), selection=r.get("組合せ"),
                 payout_yen=r.get("払戻金"), stake_yen=r.get("基準額") or 100)
            for r in rows]


def _csv_bytes(rows, keys):
    out = io.StringIO()
    writer = csv.DictWriter(out, keys)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8-sig")


def template_results(race):
    identity(race)
    return _csv_bytes(
        [dict(zip(RESULT_COLUMNS, [h["horse_no"], h["horse_name"], "", "", "", ""]))
         for h in race["horses"]], RESULT_COLUMNS)


def template_payouts():
    return _csv_bytes([], PAYOUT_COLUMNS)


def export_copy(raw_bytes, race_id, incoming):
    """Return normal .keiba with new post-race sidecar; never mutate predictions."""
    from .prediction_snapshot import load_keiba, keiba_bytes
    event = load_keiba(raw_bytes)
    out = copy.deepcopy(event)
    targets = [r for r in out["races"] if r.get("race_id") == race_id]
    if len(targets) != 1:
        raise ValueError("対象レースを一意に照合できません")
    race = targets[0]
    previous = race.get(KEY)
    safe = validate(race, incoming)
    if previous is not None:
        prior = validate(race, previous)
        if prior != safe:
            raise ValueError("保存済みの確定結果は上書きしません。元の予想から別コピーを作成してください")
    race[KEY] = safe
    return keiba_bytes(out)
