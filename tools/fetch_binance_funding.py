#!/usr/bin/env python3
"""Fetch Binance USDT-M futures funding rates for the last 24 hours for given symbols.

Usage: python tools/fetch_binance_funding.py [SYMBOL ...]
If no symbols are provided a small default set will be used.
"""
from __future__ import annotations
import sys
import json
import time
import urllib.request
import urllib.parse
import ssl
from typing import List, Dict

API = 'https://fapi.binance.com/fapi/v1/fundingRate'

DEFAULT_SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'NEARUSDT', 'XRPUSDT', 'ADAUSDT', 'SOLUSDT', 'DOGEUSDT', 'BCHUSDT'
]

TICKER_API = 'https://fapi.binance.com/fapi/v1/ticker/24hr'
EXCHANGE_INFO = 'https://fapi.binance.com/fapi/v1/exchangeInfo'

def fetch_funding(symbol: str, start_ms: int, end_ms: int) -> List[Dict]:
    q = {'symbol': symbol, 'startTime': str(start_ms), 'endTime': str(end_ms), 'limit': '1000'}
    url = API + '?' + urllib.parse.urlencode(q)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(url, context=ctx, timeout=20) as resp:
        data = resp.read().decode('utf8')
    return json.loads(data)

def summarize(symbol: str, records: List[Dict]) -> Dict:
    # Each record has 'fundingRate' string and 'fundingTime'
    total = 0.0
    count = 0
    last = None
    for r in records:
        try:
            fr = float(r.get('fundingRate', '0') )
        except Exception:
            fr = 0.0
        total += fr
        count += 1
        last = r
    avg = total / count if count else 0.0
    return {'symbol': symbol, 'count': count, 'total': total, 'avg': avg, 'last': last}

def human(x: float) -> str:
    # format as percentage per funding interval and as approx bps-day
    return f"{x:.6f} ({x*100:.4f}% per interval)"

def main(argv: List[str]):
    # usage: python tools/fetch_binance_funding.py [SYMBOL ...] [--top N]
    args = argv[1:]
    top_n = None
    if '--top' in args:
        i = args.index('--top')
        try:
            top_n = int(args[i+1])
            del args[i:i+2]
        except Exception:
            top_n = None
    symbols = args or None
    # If no explicit symbols provided, discover top USDT pairs by volume
    if not symbols:
        # fetch tickers and pick top by quoteVolume for USDT perpetuals
        try:
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(TICKER_API, context=ctx, timeout=20) as resp:
                data = resp.read().decode('utf8')
            tickers = json.loads(data)
            usdt = [t for t in tickers if t.get('symbol','').endswith('USDT')]
            # sort by quoteVolume (string) descending
            usdt_sorted = sorted(usdt, key=lambda t: float(t.get('quoteVolume') or 0.0), reverse=True)
            pick = usdt_sorted[: top_n or 200]
            symbols = [p['symbol'] for p in pick]
            print(f"Discovered {len(symbols)} USDT symbols (top by volume)")
        except Exception as e:
            print('Failed to discover tickers, falling back to defaults:', e)
            symbols = DEFAULT_SYMBOLS
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - 24 * 3600 * 1000
    results = []
    for idx, s in enumerate(symbols):
        try:
            recs = fetch_funding(s, start_ms, end_ms)
            summary = summarize(s, recs)
            results.append(summary)
        except Exception as e:
            results.append({'symbol': s, 'count': 0, 'total': 0.0, 'avg': 0.0, 'last': None, 'error': str(e)})
        # be gentle on API rate limits
        if (idx + 1) % 20 == 0:
            time.sleep(0.2)
        else:
            time.sleep(0.06)

    # pick best candidates by absolute cumulative funding
    candidates = [r for r in results if r.get('count',0) > 0]
    candidates_sorted = sorted(candidates, key=lambda r: abs(r['total']), reverse=True)
    best = candidates_sorted[0] if candidates_sorted else None

    # print table
    print('Funding summary (last 24h):')
    print(f"{'SYMBOL':10} {'#':>3} {'TOTAL':>14} {'AVG':>18} {'LAST_TIME':>22}")
    for r in results:
        if r.get('error'):
            print(f"{r['symbol']:10} ERR {r['error']}")
            continue
        last_time = '-' if not r['last'] else time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(r['last']['fundingTime']/1000))
        print(f"{r['symbol']:10} {r['count']:3d} {r['total']:14.8f} {r['avg']:18.8f} {last_time:>22}")

    if best:
        direction = 'short earns funding' if best['total'] > 0 else 'long earns funding'
        print('\nTop candidates by |cumulative funding|:')
        for b in candidates_sorted[:10]:
            dirb = 'short earns funding' if b['total'] > 0 else 'long earns funding'
            print(f"  {b['symbol']:10} cumulative={b['total']:.8f} ({dirb}) intervals={b['count']}")
        print('\nBest candidate overall:')
        print(f"  {best['symbol']}  cumulative={best['total']:.8f} ({direction})  intervals={best['count']}")
    else:
        print('\nNo funding data available for the given symbols.')

if __name__ == '__main__':
    main(sys.argv)
