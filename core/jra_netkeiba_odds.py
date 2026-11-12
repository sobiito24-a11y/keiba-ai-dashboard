"""One-shot personal JRA odds import from the free netkeiba page's JSON feed.

The endpoint is **not an official public API** and may stop working or
limit refresh. No credentials, paid functions, scraping of historical races,
automatic polling, action=update or rate-limit bypass. Only an explicitly
pressed button invokes this adapter. JRA official remains a separate source.

"yoso" is a prediction and MUST NEVER be shown as a real betting price.
Only response status="result" with dated odds is accepted. Dates are the
source's displayed update times, not timestamps asserted by this program.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import math
import re

from .race_odds import JST, validate

ENDPOINT = "https://race.netkeiba.com/api/api_get_jra_odds.html"
TYPES = {"1": ("win", "place"), "4": ("quinella",), "5": ("wide",)}
SOURCE = "netkeiba無料オッズ（取得試験）"
MAX_RESPONSE_BYTES = 700_000


def _odds_number(value):
    if value is None or isinstance(value, bool):
        return None
    s = str(value).replace(",", "").strip()
    if not re.fullmatch(r"\d{1,6}(?:\.\d{1,2})?", s):
        return None
    n = float(s)
    return n if math.isfinite(n) and 1 <= n <= 100000 else None


def _positive_int(raw):
    if not isinstance(raw, str) or not re.fullmatch(r"\d{1,3}", raw):
        return None
    n = int(raw)
    return n if n > 0 else None


def _key(raw, size):
    if not isinstance(raw, str) or len(raw) != 2 * size or not raw.isascii() or not raw.isdigit():
        return None
    horses = tuple(int(raw[i:i+2]) for i in range(0, 2 * size, 2))
    if not all(1 <= n <= 20 for n in horses) or len(set(horses)) != len(horses):
        return None
    return list(sorted(horses))


def _datetime(value):
    if not isinstance(value, str):
        return None
    try:
        value = value.strip()
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=JST)
    except (ValueError, OverflowError):
        return None


def _source_date_bounds(race_info):
    date = str((race_info or {}).get("race_date") or (race_info or {}).get("date") or "")
    try:
        date = datetime.strptime(date.replace("/", "-")[:10], "%Y-%m-%d").replace(tzinfo=JST)
    except ValueError:
        return None
    # 前日発売も許容する。異なる開催日のオッズは取り込まない。
    return date - timedelta(days=1), date + timedelta(days=1)


def parse_responses(payloads, identity, race_info, *, now=None):
    """One non-mutating quote for exact saved race ID and horse numbers.

    payloads: dict type "1"/"4"/"5" to JSON per endpoint.
    Numeric entries are keyed by two-digit horse numbers or 4-digit pairs.
    The API does not return names or an independent race ID: URLs and source
    identities must be verified in the fetch layer; only expected saved
    horse numbers are accepted here. This limitation is explicitly reported.
    """
    now = now or datetime.now(JST)
    rid = str(identity.get("race_id") or "")
    if identity.get("mode") != "jra" or not re.fullmatch(r"20\d{10}", rid):
        raise ValueError("JRAの12桁レースIDが必要です")
    saved = {int(h["horse_no"]): str(h["name"]) for h in identity["horses"]}
    if not saved:
        raise ValueError("保存済み出走馬がありません")
    if not isinstance(payloads, dict) or "1" not in payloads:
        raise ValueError("単勝・複勝の取得応答がありません")
    fields = set(saved)
    quote_prices, popularity = [], {}
    source_times = {}
    missing_kinds = []
    for kind, names in TYPES.items():
        obj = payloads.get(kind)
        if obj is None:
            missing_kinds.extend(names)
            continue
        if not isinstance(obj, dict):
            raise ValueError("オッズのJSON形式が不正です")
        status = obj.get("status")
        if kind == "1" and status == "yoso":
            raise ValueError("発売前の予想オッズです。実際の発売オッズとして反映しません")
        if status != "result":
            missing_kinds.extend(names)
            continue
        data = obj.get("data")
        if not isinstance(data, dict):
            raise ValueError("配信データの形式を確認できません")
        updated = _datetime(data.get("official_datetime"))
        if updated is None:
            raise ValueError("配信元のオッズ更新時刻を確認できません")
        if updated > now + timedelta(minutes=5):
            raise ValueError("配信元の時刻が未来のため取込を中止しました")
        bounds = _source_date_bounds(race_info)
        if bounds is None:
            raise ValueError("保存レースの開催日が未取得のため安全に照合できません")
        if not (bounds[0] <= updated < bounds[1]):
            raise ValueError("保存レースの開催日とオッズ更新日が一致しません")
        groups = data.get("odds")
        if not isinstance(groups, dict) or kind not in groups or not isinstance(groups[kind], dict):
            missing_kinds.extend(names)
            continue
        source_times[kind] = updated
        group = groups[kind]
        for rawkey, values in group.items():
            ns = _key(rawkey, 1 if kind == "1" else 2)
            if ns is None or not isinstance(values, list) or len(values) < 1:
                continue
            if not set(ns).issubset(fields):
                # A changed entry list / wrong race is never silently mapped.
                raise ValueError("オッズ馬番と保存された出走馬が一致しません")
            if kind == "1":
                win = _odds_number(values[0])
                if win is not None:
                    quote_prices.append(dict(kind="win", horses=ns, low=win, high=win))
                    if len(values) >= 3:
                        p = _positive_int(str(values[2]))
                        if p is not None and p <= len(saved):
                            popularity[str(ns[0])] = p
            elif kind == "4":
                win = _odds_number(values[0])
                if win is not None:
                    quote_prices.append(dict(kind="quinella", horses=ns, low=win, high=win))
            else:
                low = _odds_number(values[0])
                high = _odds_number(values[1] if len(values) > 1 else None)
                if low is not None and high is not None and low <= high:
                    quote_prices.append(dict(kind="wide", horses=ns, low=low, high=high))
        if kind == "1":
            # The type=1 response also carries the independent place table.
            second = groups.get("2")
            if isinstance(second, dict):
                for rawkey, values in second.items():
                    ns = _key(rawkey, 1)
                    if ns is None or not isinstance(values, list) or len(values) < 2:
                        continue
                    if not set(ns).issubset(fields):
                        raise ValueError("複勝馬番と保存出走馬が一致しません")
                    low, high = _odds_number(values[0]), _odds_number(values[1])
                    if low is not None and high is not None and low <= high:
                        quote_prices.append(dict(kind="place", horses=ns, low=low, high=high))
            else:
                missing_kinds.append("place")

    if not quote_prices or "1" not in source_times:
        raise ValueError("発売中の実売オッズを確認できません。予想オッズは表示しません")
    # Avoid mixing independently updated kinds far apart in age.
    newest = max(source_times.values())
    fresh_types = {t for t, timestamp in source_times.items() if newest - timestamp <= timedelta(minutes=10)}
    if len(fresh_types) != len(source_times):
        quote_prices = [p for p in quote_prices if {"win": "1", "place": "1", "quinella": "4", "wide": "5"}[p["kind"]] in fresh_types]
        source_times = {t: source_times[t] for t in fresh_types}
        for t in TYPES:
            if t not in fresh_types:
                missing_kinds.extend(TYPES[t])
    # Oldest retained type is the safe observed timestamp for this batch.
    observed_at = min(source_times.values())
    quote = dict(
        race_id=rid, mode="jra",
        identities={str(n): name for n, name in saved.items()},
        prices=quote_prices, popularity=popularity,
        observed_at=observed_at.isoformat(), received_at=now.isoformat(),
        source=SOURCE, acquisition_method="netkeiba_free_json",
        price_status="published_odds",
        source_url="https://race.netkeiba.com/odds/index.html?race_id=" + rid,
        per_type_observed_at={k: v.isoformat() for k,v in source_times.items()},
        warnings=[
            "JRA公式サイトの直接配信ではなく、netkeibaの無料配信です",
            "券種別の更新時刻が異なる可能性があり、最も古い時刻を一覧に表示します",
            "JSONは馬名を返さないため、保存済みレースID・馬番と照合しています",
            "無償配信の更新間隔・利用上限があり、最新オッズとは限りません",
            "発売前の予想オッズ・未取得券種を流用しません",
        ],
        missing_kinds=sorted(set(missing_kinds)),
    )
    return validate(quote, identity)


def fetch_once(identity, race_info, *, get=None, now=None):
    """Explicit button only: THREE cached-free action=init reads, no polling."""
    rid = str(identity.get("race_id") or "")
    if identity.get("mode") != "jra" or not re.fullmatch(r"20\d{10}", rid):
        raise ValueError("JRAの12桁レースIDを確認できません")
    if get is None:
        import requests
        get = requests.get
    raw = {}
    for kind in TYPES:
        try:
            response = get(ENDPOINT, params=dict(race_id=rid, type=kind, action="init"),
                           timeout=10, allow_redirects=False,
                           headers={"Accept": "application/json"})
            if response.status_code != 200:
                # Only safe HTTP codes; do not echo URLs, cookies or raw HTML.
                status = response.status_code
                if status in (401, 403):
                    raise ValueError(f"配信元からHTTP {status}（外部アプリのアクセスが制限されています）")
                if status == 429:
                    raise ValueError("配信元からHTTP 429（アクセス回数制限）。再取得を繰り返さないでください")
                raise ValueError(f"配信元からHTTP {status}。接続元が利用できません")
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise ValueError("配信データが大きすぎます")
            try:
                result = response.json()
            except ValueError as exc:
                raise ValueError("配信元がJSON以外の応答を返しました（アクセス制限や仕様変更の可能性）") from exc
            if not isinstance(result, dict):
                raise ValueError("配信データのJSON形式が不正です")
            raw[kind] = result
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("無料オッズ配信に接続できません") from exc
        if kind == "1" and raw[kind].get("status") == "yoso":
            # Never hit the other endpoints for a non-on-sale race.
            raise ValueError("まだ予想オッズのみです。発売開始後に更新してください")
    return parse_responses(raw, identity, race_info, now=now)
