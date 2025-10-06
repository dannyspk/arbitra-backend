#!/usr/bin/env python3
"""Compute multi-day funding revenue estimates for Binance USDT perpetuals.

This script fetches fundingRate entries from Binance futures API for the last N days
(default 3), computes cumulative funding rate per symbol, converts that into an
estimated USD revenue for a given notional (default 10_000 USDT) using the same
assumption Binance appears to use: revenue shown relative to total capital where
half the capital is used for the perpetual leg (so we divide the notional by 2
when mapping funding % to shown PNL).

Usage: python tools/binance_3day_revenue.py [SYMBOL ...]
Options:
  --days N        Number of days to look back (default: 3)
  --notional X    Position size in USDT to compute revenue for (default: 10000)
  --top N         Show only top N results (default: 30)

If no symbols are provided the script discovers top USDT pairs by 24h quoteVolume
(similar to our other scripts).

Output: ranking table sorted by absolute cumulative funding (largest potential PnL)

"""
from __future__ import annotations
import sys
import time
import json
import ssl
import urllib.request
import urllib.parse
from typing import List, Dict

API = 'https://fapi.binance.com/fapi/v1/fundingRate'
TICKER_API = 'https://fapi.binance.com/fapi/v1/ticker/24hr'

DEFAULT_SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'NEARUSDT', 'XRPUSDT', 'ADAUSDT', 'SOLUSDT', 'DOGEUSDT', 'BCHUSDT'
]


def fetch_funding(symbol: str, start_ms: int, end_ms: int) -> List[Dict]:
    q = {'symbol': symbol, 'startTime': str(start_ms), 'endTime': str(end_ms), 'limit': '1000'}
    url = API + '?' + urllib.parse.urlencode(q)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(url, context=ctx, timeout=20) as resp:
        data = resp.read().decode('utf8')
    return json.loads(data)


def summarize(symbol: str, records: List[Dict]) -> Dict:
    total = 0.0
    count = 0
    last = None
    for r in records:
        try:
            fr = float(r.get('fundingRate', '0'))
        except Exception:
            fr = 0.0
        total += fr
        count += 1
        last = r
    avg = total / count if count else 0.0
    return {'symbol': symbol, 'count': count, 'total': total, 'avg': avg, 'last': last}


def discover_top_usdt(limit: int = 200) -> List[str]:
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(TICKER_API, context=ctx, timeout=20) as resp:
            data = resp.read().decode('utf8')
        tickers = json.loads(data)
        usdt = [t for t in tickers if t.get('symbol','').endswith('USDT')]
        usdt_sorted = sorted(usdt, key=lambda t: float(t.get('quoteVolume') or 0.0), reverse=True)
        pick = usdt_sorted[: limit]
        return [p['symbol'] for p in pick]
    except Exception:
        return DEFAULT_SYMBOLS


def human_pct(x: float) -> str:
    return f"{x*100:.4f}%"


def main(argv: List[str]):
    args = argv[1:]
    days = 3
    notional = 10000.0
    top_n = 30
    if '--days' in args:
        i = args.index('--days')
        try:
            days = int(args[i+1]); del args[i:i+2]
        except Exception:
            days = 3
    if '--notional' in args:
        i = args.index('--notional')
        try:
            notional = float(args[i+1]); del args[i:i+2]
        except Exception:
            notional = 10000.0
    if '--top' in args:
        i = args.index('--top')
        try:
            top_n = int(args[i+1]); del args[i:i+2]
        except Exception:
            top_n = 30

    symbols = args or None
    if not symbols:
        symbols = discover_top_usdt(limit=200)
        print(f"Discovered {len(symbols)} USDT symbols (top by volume)")

    end_ms = int(time.time() * 1000)
    start_ms = end_ms - days * 24 * 3600 * 1000

    results = []
    for idx, s in enumerate(symbols):
        try:
            recs = fetch_funding(s, start_ms, end_ms)
            summary = summarize(s, recs)
            results.append(summary)
        except Exception as e:
            results.append({'symbol': s, 'count': 0, 'total': 0.0, 'avg': 0.0, 'last': None, 'error': str(e)})
        # gentle rate limit
        if (idx + 1) % 20 == 0:
            time.sleep(0.2)
        else:
            time.sleep(0.06)

    # Compute revenue estimate and APR
    out = []
    for r in results:
        if r.get('error'):
            continue
        total = r.get('total', 0.0)  # cumulative funding rate over the period (sum of intervals)
        # Binance UI seems to show revenue relative to a notional where only half the capital
        # is allocated to the perp leg (so shown PnL = notional * |total| / 2).
        revenue = abs(total) * notional / 2.0
        # APR normalized by days
        try:
            apr = (total / max(1, days)) * 365.0 * 100.0
        except Exception:
            apr = 0.0
        out.append({'symbol': r['symbol'], 'count': r['count'], 'cumulative_pct': total * 100.0, 'revenue_usdt': revenue, 'apr_pct': apr, 'last': r.get('last')})

    # sort by revenue descending
    out_sorted = sorted(out, key=lambda x: x['revenue_usdt'], reverse=True)

    print(f"\nTop funding-based revenue candidates (last {days} days) for notional={notional} USDT:\n")
    print(f"{'SYMBOL':12} {'REV_USDT':>10} {'CUM_%':>12} {'APR%':>10} {'INTERVALS':>10}")
    for e in out_sorted[: top_n]:
        print(f"{e['symbol']:12} {e['revenue_usdt']:10.2f} {e['cumulative_pct']:12.4f} {e['apr_pct']:10.2f} {e['count']:10d}")

    # show top 5 with direction
    if out_sorted:
        print('\nTop 5 detailed:')
        for e in out_sorted[:5]:
            dirn = 'short earns funding' if e['cumulative_pct'] > 0 else 'long earns funding'
            last_str = '-'
            if e['last']:
                try:
                    ts = int(e['last'].get('fundingTime') or e['last'].get('time') or 0)
                    last_str = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(ts/1000))
                except Exception:
                    last_str = str(e['last'])
            print(f"  {e['symbol']:8} revenue={e['revenue_usdt']:.2f}usdt ({dirn}) cumulative={e['cumulative_pct']:.4f}% apr={e['apr_pct']:.2f}% last={last_str}")


if __name__ == '__main__':
    main(sys.argv)
