#!/usr/bin/env python3
"""Fetch 15m OHLCV for ALPINEUSDT from Binance using ccxt and save to var/alpineusdt_15m.csv
Matches format used by existing CSVs: header timestamp,open,high,low,close,volume where timestamp is ms since epoch.

Note: requires `ccxt` (already in requirements.txt)."""
import ccxt
from datetime import datetime, timezone
import time
import csv
import os

symbol = 'ALPINE/USDT'
exchange = ccxt.binance()

# from 2025-09-30 00:00:00 UTC
since_dt = datetime(2025, 9, 30, 0, 0, tzinfo=timezone.utc)
since_ms = int(since_dt.timestamp() * 1000)

# timeframe and filename
tf = '15m'
outfile = 'var/alpineusdt_15m.csv'

os.makedirs('var', exist_ok=True)

all_ohlcv = []
limit = 1000

print('Fetching', symbol, 'from Binance since', since_dt.isoformat())

after = since_ms
while True:
    # ccxt expects timeframe like '15m'
    ohlcv = exchange.fetch_ohlcv(symbol.replace('/',''), tf, since=after, limit=limit)
    if not ohlcv:
        break
    all_ohlcv.extend(ohlcv)
    print('Fetched', len(ohlcv), 'candles, total', len(all_ohlcv))
    # last candle timestamp
    last = ohlcv[-1][0]
    # advance one ms to avoid repeating last candle
    after = last + 1
    # avoid hammering
    time.sleep(0.5)
    # stop if we reached now
    if last >= int(time.time() * 1000):
        break

# filter to >= since_ms (fetch_ohlcv may return a little earlier)
all_ohlcv = [c for c in all_ohlcv if c[0] >= since_ms]
all_ohlcv.sort(key=lambda c: c[0])

with open(outfile, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['timestamp','open','high','low','close','volume'])
    for c in all_ohlcv:
        writer.writerow([c[0], str(c[1]), str(c[2]), str(c[3]), str(c[4]), str(c[5])])

print('Wrote', outfile, 'rows=', len(all_ohlcv))
