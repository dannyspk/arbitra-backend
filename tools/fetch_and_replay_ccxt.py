"""Fetch OHLCV/trades for a symbol on two exchanges and report cross-exchange price divergence.

Assumptions:
- Times are UTC unless you change the timezone conversions below.
- Symbol base/quote is ALPINE/USDT (common mapping). If the exchange uses a different id, the script will try to find a matching market.

Usage: run from repo root (no PYTHONPATH needed):
  python tools/fetch_and_replay_ccxt.py

It will save CSVs and print a small divergence report for the 2025-09-30 16:40-16:50 window.
"""
from datetime import datetime, timezone, timedelta
import time
import json
import sys

try:
    import ccxt
    import pandas as pd
except Exception as e:
    print('Missing dependency:', e)
    print('Please run: python -m pip install ccxt pandas')
    sys.exit(2)

# Parameters (modify if needed)
EXCHANGES = ['binance', 'mexc']
BASE = 'ALPINE'
QUOTE = 'USDT'
# Event window (UTC)
START = datetime(2025, 9, 30, 16, 40, tzinfo=timezone.utc)
END = datetime(2025, 9, 30, 16, 50, tzinfo=timezone.utc)
TIMEFRAME = '1m'
OUT_DIR = 'tools/ccxt_out'

import os
os.makedirs(OUT_DIR, exist_ok=True)

start_ms = int(START.timestamp() * 1000)
end_ms = int(END.timestamp() * 1000)


def find_symbol_for_pair(exchange, base, quote):
    # load markets and try to find a market symbol matching base/quote
    try:
        exchange.load_markets()
    except Exception:
        # some exchanges may need no load
        pass
    markets = getattr(exchange, 'markets', {}) or {}
    # prefer exact match key like 'ALPINE/USDT'
    candidates = [k for k in markets.keys() if k.upper() == f'{base}/{quote}' or k.upper() == f'{base}{quote}']
    if candidates:
        return candidates[0]
    # fallback: find by base and quote fields
    for k, m in markets.items():
        if m.get('base', '').upper() == base.upper() and m.get('quote', '').upper() == quote.upper():
            return k
    # last resort: try common formatted symbol
    return f'{base}/{quote}'


def fetch_ohlcv_range(exchange, symbol, timeframe, since_ms, until_ms):
    all_rows = []
    since = since_ms
    limit = 1000
    while since < until_ms:
        try:
            chunk = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
        except Exception as e:
            print('fetch_ohlcv error for', exchange.id, symbol, e)
            break
        if not chunk:
            break
        all_rows += chunk
        last_ts = chunk[-1][0]
        if last_ts >= until_ms:
            break
        # advance: next ms after last timestamp
        since = last_ts + 1
        # respect rate limit
        time.sleep(getattr(exchange, 'rateLimit', 200) / 1000.0)
    # trim to until_ms
    rows = [r for r in all_rows if r[0] >= since_ms and r[0] <= until_ms]
    return rows


def df_from_ohlcv(rows):
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
    df['dt'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
    df.set_index('dt', inplace=True)
    return df


results = {}
for ex_id in EXCHANGES:
    print('-> Connecting to', ex_id)
    try:
        Ex = getattr(ccxt, ex_id)
    except Exception as e:
        print('Exchange not in ccxt:', ex_id, e)
        continue
    ex = Ex({'enableRateLimit': True})
    # Some exchanges require setting options; leave defaults
    symbol = find_symbol_for_pair(ex, BASE, QUOTE)
    print('  trying symbol', symbol)
    ohlcv = fetch_ohlcv_range(ex, symbol, TIMEFRAME, start_ms, end_ms)
    df = df_from_ohlcv(ohlcv)
    out_csv = os.path.join(OUT_DIR, f'{ex_id}_{symbol.replace("/","")}_{TIMEFRAME}.csv')
    if not df.empty:
        df.to_csv(out_csv)
        print('  saved', out_csv, 'rows=', len(df))
    else:
        print('  no ohlcv returned for', ex_id, symbol)
    results[ex_id] = {'symbol': symbol, 'df': df}

# Align minute buckets and compute percent differences between first two exchanges if both present
if EXCHANGES[0] in results and EXCHANGES[1] in results:
    df0 = results[EXCHANGES[0]]['df']
    df1 = results[EXCHANGES[1]]['df']
    if df0.empty or df1.empty:
        print('\nNot enough data to compute divergence between exchanges')
        sys.exit(0)
    # reindex to union of timestamps
    idx = sorted(set(df0.index).union(set(df1.index)))
    s0 = df0['close'].reindex(idx).ffill()
    s1 = df1['close'].reindex(idx).ffill()
    comp = pd.DataFrame({'t': idx, f'{EXCHANGES[0]}': s0.values, f'{EXCHANGES[1]}': s1.values})
    comp['t'] = pd.to_datetime(comp['t'])
    comp.set_index('t', inplace=True)
    comp['pct_diff'] = (comp[EXCHANGES[0]] - comp[EXCHANGES[1]]) / comp[EXCHANGES[1]] * 100.0
    out_comp = os.path.join(OUT_DIR, f'comparison_{BASE}{QUOTE}_{START.strftime("%Y%m%dT%H%M")}.csv')
    comp.to_csv(out_comp)
    print('\nComparison saved to', out_comp)
    # print rows where abs diff > 0.5% (tunable)
    thr = 0.5
    sig = comp[comp['pct_diff'].abs() >= thr]
    if sig.empty:
        print(f'No spans with abs percent diff >= {thr}%')
    else:
        print(f'Found {len(sig)} timestamps with abs percent diff >= {thr}%:')
        print(sig[['pct_diff', EXCHANGES[0], EXCHANGES[1]]].to_string())
else:
    print('Not enough exchanges fetched to compare')

print('\nDone')
