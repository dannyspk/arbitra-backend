#!/usr/bin/env python3
"""Find KuCoin pair names for a list of base symbols.

Usage: run from repo root with PYTHONPATH='src'

$env:PYTHONPATH='src'; python scripts/find_kucoin_pairs.py

This will print candidate kucoin symbols and attempt to fetch a small
level2 snapshot for each candidate to indicate whether an orderbook exists.
"""
import urllib.request
import json
import time

COMMON_QUOTES = ['USDT', 'USDC', 'BUSD', 'BTC', 'ETH', 'USD']

CANDIDATES = [
    'XPLUS', 'ALPINE', 'SOMI', 'PUMP', 'BARD',
    'AVNT', 'EDEN', 'FF', 'ZEC', 'PEPE'
]

KU_SYMBOLS_URL = 'https://api.kucoin.com/api/v1/symbols'
ORDERBOOK_URL = 'https://api.kucoin.com/api/v1/market/orderbook/level2?symbol={}&limit=5'


def fetch_json(url, timeout=8.0):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'arb-find-kucoin/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return {'error': str(e)}


def build_symbol_index():
    obj = fetch_json(KU_SYMBOLS_URL)
    data = obj.get('data') if isinstance(obj, dict) else None
    if not isinstance(data, list):
        print('Failed to fetch symbols list:', obj)
        return {}
    idx = {}
    for it in data:
        try:
            sym = (it.get('symbol') or '').upper()
            base = (it.get('baseCurrency') or '').upper()
            quote = (it.get('quoteCurrency') or '').upper()
            active = (it.get('enableTrading') is True) or (it.get('enableTrading') == 'true')
            if not sym:
                continue
            idx.setdefault(base, []).append({'symbol': sym, 'base': base, 'quote': quote, 'active': active})
        except Exception:
            continue
    return idx


def try_orderbook(symbol):
    url = ORDERBOOK_URL.format(symbol)
    res = fetch_json(url, timeout=6.0)
    # consider found if we got a data dict with asks/bids
    if not isinstance(res, dict):
        return False, res
    d = res.get('data')
    if isinstance(d, dict) and (d.get('asks') or d.get('bids')):
        return True, d
    # sometimes API returns top-level error / code
    return False, res


def main():
    print('Fetching KuCoin symbols...')
    idx = build_symbol_index()
    print('Known bases on KuCoin (sample):', list(idx.keys())[:30])

    results = {}
    for base in CANDIDATES:
        b = base.upper()
        candidates = idx.get(b) or []
        # Also attempt fuzzy matches: symbols where symbol startswith base
        fuzzy = []
        for k, arr in idx.items():
            for entry in arr:
                if entry['symbol'].startswith(b + '-') or entry['symbol'].startswith(b):
                    fuzzy.append(entry)
        # dedupe
        allc = {e['symbol']: e for e in (candidates + fuzzy)}
        cand_list = list(allc.values())
        print('\n===', b, '=== found candidates:', len(cand_list))
        if not cand_list:
            print(' no direct matches on KuCoin for base', b)
            results[b] = []
            continue
        out = []
        for e in cand_list:
            sym = e['symbol']
            print(' checking', sym, 'quote=', e['quote'], 'active=', e.get('active'))
            ok, ob = try_orderbook(sym)
            if ok:
                print('  -> orderbook available (asks/bids length):', len(ob.get('asks') or []), len(ob.get('bids') or []))
            else:
                print('  -> no orderbook or error:', ob)
            out.append({'symbol': sym, 'quote': e['quote'], 'active': e.get('active'), 'orderbook': ok})
            # small throttle
            time.sleep(0.05)
        results[b] = out

    print('\nSummary:')
    for k, v in results.items():
        print(k, '->', [f"{it['symbol']}({'ok' if it['orderbook'] else 'no'})" for it in v])


if __name__ == '__main__':
    main()
