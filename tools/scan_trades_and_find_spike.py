"""Fetch trade-level history from CCXT for two exchanges, resample to 1s, and find the largest cross-exchange price gap in a target window.

Saves CSVs to tools/ccxt_out and prints a small report.

Usage: python tools/scan_trades_and_find_spike.py
"""
from datetime import datetime, timezone, timedelta
import time
import os
import sys

try:
    import ccxt
    import pandas as pd
except Exception as e:
    print('Missing dependency:', e)
    print('Please run: python -m pip install ccxt pandas')
    sys.exit(2)

OUT_DIR = 'tools/ccxt_out'
os.makedirs(OUT_DIR, exist_ok=True)

EXCHANGES = ['binance', 'gate']
BASE = 'ALPINE'
QUOTE = 'USDT'
# primary analysis window (UTC)
WINDOW_START = datetime(2025, 9, 30, 16, 40, tzinfo=timezone.utc)
WINDOW_END = datetime(2025, 9, 30, 16, 50, tzinfo=timezone.utc)
# fetch a slightly wider range to ensure context
FETCH_PAD = timedelta(minutes=5)
FETCH_START = WINDOW_START - FETCH_PAD
FETCH_END = WINDOW_END + FETCH_PAD

start_ms = int(FETCH_START.timestamp() * 1000)
end_ms = int(FETCH_END.timestamp() * 1000)


def find_symbol_for_pair(exchange, base, quote):
    try:
        exchange.load_markets()
    except Exception:
        pass
    markets = getattr(exchange, 'markets', {}) or {}
    candidates = [k for k in markets.keys() if k.upper() == f'{base}/{quote}' or k.upper() == f'{base}{quote}']
    if candidates:
        return candidates[0]
    for k, m in markets.items():
        if m.get('base', '').upper() == base.upper() and m.get('quote', '').upper() == quote.upper():
            return k
    return f'{base}/{quote}'


def fetch_trades_range(exchange, symbol, since_ms, until_ms):
    all_trades = []
    since = since_ms
    limit = 1000
    attempts = 0
    while since < until_ms:
        try:
            # MEXC requires an 'until' param when 'since' is provided. Page in 5-minute windows to be safe.
            if getattr(exchange, 'id', '').lower() == 'mexc':
                page_ms = 5 * 60 * 1000
                until_param = min(until_ms, since + page_ms)
                trades = exchange.fetch_trades(symbol, since=since, limit=limit, params={'until': until_param})
            else:
                trades = exchange.fetch_trades(symbol, since=since, limit=limit)
        except Exception as e:
            print('fetch_trades error for', exchange.id, symbol, e)
            attempts += 1
            if attempts > 3:
                break
            time.sleep(1)
            continue
        if not trades:
            break
        all_trades += trades
        last_ts = trades[-1]['timestamp']
        if last_ts >= until_ms:
            break
        since = last_ts + 1
        time.sleep(getattr(exchange, 'rateLimit', 200) / 1000.0)
    # filter
    filtered = [t for t in all_trades if t['timestamp'] >= since_ms and t['timestamp'] <= until_ms]
    return filtered


def fetch_trades_fallback(exchange, symbol, since_ms, until_ms, max_rounds=50):
    """Fallback for exchanges that don't support ranged fetches: repeatedly call fetch_trades() (no since)
    and accumulate until we've covered the window or hit max_rounds."""
    seen_ids = set()
    acc = []
    rounds = 0
    while rounds < max_rounds:
        try:
            trades = exchange.fetch_trades(symbol, limit=1000)
        except Exception as e:
            # give up on repeated failures
            break
        if not trades:
            break
        new = 0
        for t in trades:
            tid = str(t.get('id') or t.get('tradeId') or t.get('orderId') or t.get('timestamp'))
            if tid in seen_ids:
                continue
            seen_ids.add(tid)
            acc.append(t)
            new += 1
        # if no new trades, break
        if new == 0:
            break
        # check coverage
        ts_vals = [t['timestamp'] for t in acc if t.get('timestamp')]
        if ts_vals and min(ts_vals) <= since_ms:
            break
        rounds += 1
        time.sleep(getattr(exchange, 'rateLimit', 200) / 1000.0)
    # filter to window
    filtered = [t for t in acc if t.get('timestamp') and t['timestamp'] >= since_ms and t['timestamp'] <= until_ms]
    # sort by timestamp
    filtered.sort(key=lambda x: x.get('timestamp', 0))
    return filtered


def trades_to_df(trades):
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame(trades)
    # ensure timestamp and price
    df = df[['timestamp', 'price', 'amount']].copy()
    df['dt'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    df.set_index('dt', inplace=True)
    return df


def fetch_ohlcv_range(exchange, symbol, timeframe, since_ms, until_ms):
    all_rows = []
    since = since_ms
    limit = 1000
    while since < until_ms:
        try:
            chunk = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
        except Exception as e:
            # try without since as a fallback
            try:
                chunk = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            except Exception:
                break
        if not chunk:
            break
        all_rows += chunk
        last_ts = chunk[-1][0]
        if last_ts >= until_ms:
            break
        since = last_ts + 1
        time.sleep(getattr(exchange, 'rateLimit', 200) / 1000.0)
    rows = [r for r in all_rows if r[0] >= since_ms and r[0] <= until_ms]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=['ts','open','high','low','close','volume'])
    df['dt'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
    df.set_index('dt', inplace=True)
    return df


results = {}
for ex_id in EXCHANGES:
    print('Fetching', ex_id)
    try:
        Ex = getattr(ccxt, ex_id)
    except Exception as e:
        print('Exchange not found in ccxt:', ex_id, e)
        continue
    ex = Ex({'enableRateLimit': True})
    symbol = find_symbol_for_pair(ex, BASE, QUOTE)
    # MEXC often uses symbols without '/', prefer that format
    if getattr(ex, 'id', '').lower() == 'mexc' and '/' in symbol:
        symbol = symbol.replace('/', '')
    print('  symbol:', symbol)
    trades = fetch_trades_range(ex, symbol, start_ms, end_ms)
    if not trades:
        # try fallback method that polls recent trades without since/until
        trades = fetch_trades_fallback(ex, symbol, start_ms, end_ms)
    df = trades_to_df(trades)
    if df.empty:
        # try OHLCV minute candles as fallback
        print('  trying OHLCV fallback for', ex_id)
        try:
            df = fetch_ohlcv_range(ex, symbol, '1m', start_ms, end_ms)
            if not df.empty:
                print('  OHLCV fallback saved rows=', len(df))
        except Exception as e:
            print('  ohlcv fallback failed for', ex_id, e)
    out_csv = os.path.join(OUT_DIR, f'{ex_id}_{symbol.replace("/","")}_trades.csv')
    if not df.empty:
        df.to_csv(out_csv)
        print('  saved', out_csv, 'rows=', len(df))
    else:
        print('  no trades fetched for', ex_id, symbol)
    results[ex_id] = {'symbol': symbol, 'df': df}

# Resample to 1-minute resolution using last trade price per minute
min_start = WINDOW_START
min_end = WINDOW_END
index = pd.date_range(min_start, min_end, freq='1min', tz=timezone.utc)
combined = pd.DataFrame(index=index)

for ex_id in EXCHANGES:
    df = results.get(ex_id, {}).get('df')
    if df is None or df.empty:
        combined[ex_id] = None
        continue
    # last price per minute — support both trade-frame ('price') and ohlcv-frame ('close')
    if 'price' in df.columns:
        last = df['price'].resample('1min').last()
    elif 'close' in df.columns:
        last = df['close'].resample('1min').last()
    else:
        last = pd.Series(index=index, dtype=float)
    last = last.reindex(index).ffill()
    combined[ex_id] = last.values

# compute percent diff and find largest gap
if combined.isnull().all(axis=1).all():
    print('No per-second prices for comparison in window')
    sys.exit(0)

combined['pct_diff'] = (combined[EXCHANGES[0]] - combined[EXCHANGES[1]]) / combined[EXCHANGES[1]] * 100.0
combined.to_csv(os.path.join(OUT_DIR, f'persec_comparison_{BASE}{QUOTE}_{WINDOW_START.strftime("%Y%m%dT%H%M")}.csv'))

# find max absolute diff in the core window (minute-level)
core = combined
core_nonnull = core.dropna(subset=EXCHANGES)
if core_nonnull.empty:
    print('No overlapping per-second prices')
    sys.exit(0)
max_row = core_nonnull['pct_diff'].abs().idxmax()
max_val = core_nonnull.loc[max_row, 'pct_diff']
print('\nLargest absolute percent diff in window (minute-level):')
print(' time:', max_row, ' pct_diff:', max_val)

# print 3-minute context around the spike
ctx_start = max_row - pd.Timedelta(minutes=1)
ctx_end = max_row + pd.Timedelta(minutes=1)
ctx = core.loc[ctx_start:ctx_end]
print('\nContext (3 minutes) around spike:')
print(ctx[[EXCHANGES[0], EXCHANGES[1], 'pct_diff']].to_string())

print('\nDone')
