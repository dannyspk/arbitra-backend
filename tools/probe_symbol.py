#!/usr/bin/env python3
"""Probe a Binance USDT perpetual symbol: funding, depth, 24h stats, open interest, recent trades.

Usage: python tools/probe_symbol.py [SYMBOL]
"""
from __future__ import annotations
import sys, time, json, ssl, urllib.request, urllib.parse

API_FUND = 'https://fapi.binance.com/fapi/v1/fundingRate'
API_DEPTH = 'https://fapi.binance.com/fapi/v1/depth'
API_TICKER = 'https://fapi.binance.com/fapi/v1/ticker/24hr'
API_OI = 'https://fapi.binance.com/fapi/v1/openInterest'
API_TRADES = 'https://fapi.binance.com/fapi/v1/trades'

def fetch_url(url, params=None, timeout=20):
    if params:
        url = url + '?' + urllib.parse.urlencode(params)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(url, context=ctx, timeout=timeout) as resp:
        data = resp.read().decode('utf8')
    return json.loads(data)

def summarize_funding(symbol, start_ms, end_ms):
    recs = fetch_url(API_FUND, {'symbol': symbol, 'startTime': start_ms, 'endTime': end_ms, 'limit': 1000})
    total = 0.0
    count = 0
    for r in recs:
        try:
            fr = float(r.get('fundingRate') or 0.0)
        except Exception:
            fr = 0.0
        total += fr
        count += 1
    avg = total / count if count else 0.0
    return {'count': count, 'total': total, 'avg': avg, 'records': recs}

def main(argv):
    sym = (argv[1] if len(argv) > 1 else 'MYXUSDT').upper()
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - 24*3600*1000
    print(f"Probing {sym} on Binance USDT-M futures")
    print('Fetching funding history...')
    try:
        fund = summarize_funding(sym, start_ms, now_ms)
        print(f"Funding: intervals={fund['count']} total={fund['total']:.8f} avg={fund['avg']:.8f}")
    except Exception as e:
        print('Funding fetch error:', e)
        fund = None

    print('Fetching depth (top 50)...')
    try:
        depth = fetch_url(API_DEPTH, {'symbol': sym, 'limit': 50})
        bids = depth.get('bids', [])
        asks = depth.get('asks', [])
        print(f"Top bids ({len(bids)}):")
        for b in bids[:5]:
            print('  ', b[0], b[1])
        print(f"Top asks ({len(asks)}):")
        for a in asks[:5]:
            print('  ', a[0], a[1])
    except Exception as e:
        print('Depth fetch error:', e)
        depth = None

    print('Fetching 24h ticker...')
    try:
        ticker = fetch_url(API_TICKER, {'symbol': sym})
        print('Last price:', ticker.get('lastPrice'), '24h vol:', ticker.get('quoteVolume'), 'priceChangePercent:', ticker.get('priceChangePercent'))
    except Exception as e:
        print('Ticker fetch error:', e)
        ticker = None

    print('Fetching open interest...')
    try:
        oi = fetch_url(API_OI, {'symbol': sym})
        print('Open interest:', oi.get('openInterest'))
    except Exception as e:
        print('Open interest fetch error:', e)
        oi = None

    print('Fetching recent trades (limit 50)...')
    try:
        trades = fetch_url(API_TRADES, {'symbol': sym, 'limit': 50})
        print('Recent trades sample (last 5):')
        for t in trades[-5:]:
            print('  ', t.get('price'), t.get('qty'), t.get('isBuyerMaker'))
    except Exception as e:
        print('Trades fetch error:', e)

    print('\nProbe complete.')

if __name__ == '__main__':
    main(sys.argv)
