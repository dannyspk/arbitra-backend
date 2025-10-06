"""Lightweight CoinGecko enrichment helper.

This module uses the public CoinGecko API (no external deps) to map a base
symbol (e.g. 'BTC') to a CoinGecko id and fetch market cap and 24h volume in USD.
It provides a small file-backed cache to avoid repeated network calls.

Enable usage by setting ARB_USE_COINGECKO=1. Cache location and TTL are
configurable via TMP_COINGECKO_CACHE and TMP_COINGECKO_CACHE_TTL_S.
"""
from __future__ import annotations

import json
import os
import time
from typing import Tuple, Optional
from urllib import request, parse


_CACHE: dict = {}
_CACHE_TS: float = 0.0


def _cache_path() -> str:
    path = os.environ.get('TMP_COINGECKO_CACHE', os.path.join('.cache', 'coingecko_cache.json'))
    # ensure directory exists
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass
    return path


def _load_cache() -> None:
    global _CACHE, _CACHE_TS
    path = _cache_path()
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                _CACHE = json.load(f)
                _CACHE_TS = time.time()
                return
    except Exception:
        pass
    _CACHE = {}
    _CACHE_TS = time.time()


def _save_cache() -> None:
    path = _cache_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(_CACHE, f)
    except Exception:
        pass


def _http_get_json(url: str, timeout: float = 5.0) -> Optional[dict]:
    try:
        req = request.Request(url, headers={"User-Agent": "arb-bot/1.0 (+https://example)"})
        with request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return json.loads(data.decode('utf-8'))
    except Exception:
        return None


def get_metrics_for_base(base: str) -> Tuple[Optional[float], Optional[float]]:
    """Return (market_cap_usd, total_volume_24h_usd) for base token using CoinGecko.

    Returns (None, None) if not found or on error.
    """
    try:
        use_cg = os.getenv('ARB_USE_COINGECKO', '0') == '1'
        if not use_cg:
            return None, None
    except Exception:
        return None, None

    base_key = (base or '').strip()
    if not base_key:
        return None, None

    # load cache if empty
    if not _CACHE:
        _load_cache()

    # TTL for local cache validity
    try:
        ttl = int(os.getenv('TMP_COINGECKO_CACHE_TTL_S', '86400'))
    except Exception:
        ttl = 86400

    entry = _CACHE.get(base_key.upper())
    if entry:
        ts = entry.get('ts', 0)
        if (time.time() - ts) < ttl:
            return entry.get('market_cap_usd'), entry.get('total_volume_usd')

    # need to query CoinGecko: first map symbol -> id using /coins/list
    list_url = 'https://api.coingecko.com/api/v3/coins/list'
    coins = _http_get_json(list_url, timeout=5.0)
    if not isinstance(coins, list):
        return None, None

    base_lower = base_key.lower()
    matched_id = None
    # prefer exact symbol match; if several, choose the one whose id contains base
    candidates = [c for c in coins if isinstance(c, dict) and c.get('symbol', '').lower() == base_lower]
    if candidates:
        # try to find best candidate
        if len(candidates) == 1:
            matched_id = candidates[0].get('id')
        else:
            # prefer id that startswith base or contains base
            for c in candidates:
                cid = c.get('id')
                if cid and cid.lower().startswith(base_lower):
                    matched_id = cid
                    break
            if matched_id is None:
                matched_id = candidates[0].get('id')
    else:
        # last-resort: try name match
        for c in coins:
            if isinstance(c, dict) and str(c.get('id', '')).lower() == base_lower:
                matched_id = c.get('id')
                break

    if not matched_id:
        return None, None

    # fetch coin market data
    url = f'https://api.coingecko.com/api/v3/coins/{parse.quote(matched_id)}?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false&sparkline=false'
    data = _http_get_json(url, timeout=5.0)
    if not isinstance(data, dict):
        return None, None
    md = data.get('market_data', {}) if isinstance(data.get('market_data'), dict) else {}
    mc = None
    vol = None
    try:
        mc = md.get('market_cap', {}).get('usd') if isinstance(md.get('market_cap'), dict) else None
    except Exception:
        mc = None
    try:
        vol = md.get('total_volume', {}).get('usd') if isinstance(md.get('total_volume'), dict) else None
    except Exception:
        vol = None

    # cache result
    try:
        _CACHE[base_key.upper()] = {'id': matched_id, 'market_cap_usd': mc, 'total_volume_usd': vol, 'ts': time.time()}
        _save_cache()
    except Exception:
        pass

    return mc, vol


def get_metrics_for_bases(bases: list[str]) -> dict:
    """Batch fetch metrics for multiple bases. Returns a map base_upper -> (mc, vol).

    This function maps symbols to CoinGecko ids using /coins/list once, then
    queries /coins/markets in batches to fetch market cap and 24h volume.
    """
    res: dict = {}
    try:
        use_cg = os.getenv('ARB_USE_COINGECKO', '0') == '1'
        if not use_cg:
            return {b.upper(): (None, None) for b in bases}
    except Exception:
        return {b.upper(): (None, None) for b in bases}

    # normalize bases
    uniq = sorted({(b or '').strip().upper() for b in bases if b})
    if not uniq:
        return {}

    if not _CACHE:
        _load_cache()

    # fast-path: return cached where possible
    to_query = []
    for b in uniq:
        e = _CACHE.get(b)
        if e and (time.time() - e.get('ts', 0)) < int(os.getenv('TMP_COINGECKO_CACHE_TTL_S', '86400')):
            res[b] = (e.get('market_cap_usd'), e.get('total_volume_usd'))
        else:
            to_query.append(b)

    if not to_query:
        return res

    # get coins list once
    list_url = 'https://api.coingecko.com/api/v3/coins/list'
    coins = _http_get_json(list_url, timeout=10.0)
    if not isinstance(coins, list):
        # return None for those we couldn't resolve
        for b in to_query:
            res[b] = (None, None)
        return res

    # build symbol->ids map (symbols may map to multiple ids)
    sym_map: dict[str, list[str]] = {}
    for c in coins:
        try:
            sym = (c.get('symbol') or '').upper()
            if not sym:
                continue
            sym_map.setdefault(sym, []).append(c.get('id'))
        except Exception:
            continue

    # collect candidate ids (prefer ids that startwith the symbol)
    id_map: dict[str, list[str]] = {}
    for b in to_query:
        cand = sym_map.get(b)
        if not cand:
            id_map[b] = []
            continue
        # reorder to prefer those that start with base
        ordered = sorted([cid for cid in cand if cid], key=lambda x: (0 if x.lower().startswith(b.lower()) else 1, x))
        id_map[b] = ordered

    # flatten ids to query in /coins/markets (in batches)
    ids_to_query = []
    id_to_base = {}
    for b, ids in id_map.items():
        for cid in ids:
            if cid not in id_to_base:
                id_to_base[cid] = b
                ids_to_query.append(cid)

    # CoinGecko /coins/markets supports vs_currency and ids param
    batch_size = 250
    for i in range(0, len(ids_to_query), batch_size):
        batch = ids_to_query[i:i+batch_size]
        ids_param = ','.join(batch)
        url = f'https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={parse.quote(ids_param)}&order=market_cap_desc&per_page=250&page=1&price_change_percentage=24h'
        data = _http_get_json(url, timeout=10.0)
        if not isinstance(data, list):
            continue
        for item in data:
            try:
                cid = item.get('id')
                base = id_to_base.get(cid)
                if not base:
                    continue
                mc = item.get('market_cap')
                vol = item.get('total_volume')
                res[base] = (mc if mc is not None else None, vol if vol is not None else None)
                # cache
                _CACHE[base] = {'id': cid, 'market_cap_usd': mc, 'total_volume_usd': vol, 'ts': time.time()}
            except Exception:
                continue

    # for any not returned, put None
    for b in to_query:
        if b not in res:
            res[b] = (None, None)

    try:
        _save_cache()
    except Exception:
        pass

    return res
