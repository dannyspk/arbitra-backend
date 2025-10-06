#!/usr/bin/env python3
"""Fetch 15m OHLCV for a symbol from Binance using ccxt and save to var/<symbol>_15m.csv
Usage: python tools/fetch_binance_symbol_15m.py SYMBOL
"""
import ccxt
import sys
from datetime import datetime, timezone
import time
import csv
import os

if len(sys.argv) < 2:
    print('Usage: python tools/fetch_binance_symbol_15m.py SYMBOL')
    raise SystemExit(2)

symbol = sys.argv[1]  # expecting e.g. ZEC/USDT or ZECUSDT
if '/' not in symbol:
    symbol = symbol.replace('USDT','/USDT')
exchange = ccxt.binance()

# from 2025-09-30 00:00:00 UTC
since_dt = datetime(2025, 9, 30, 0, 0, tzinfo=timezone.utc)
since_ms = int(since_dt.timestamp() * 1000)

# timeframe and filename
tf = '15m'
outfile = f'var/{symbol.replace("/","").lower()}_15m.csv'

os.makedirs('var', exist_ok=True)

all_ohlcv = []
limit = 1000

print('Fetching', symbol, 'from Binance since', since_dt.isoformat())

after = since_ms
while True:
    ohlcv = exchange.fetch_ohlcv(symbol.replace('/',''), tf, since=after, limit=limit)
    if not ohlcv:
        break
    all_ohlcv.extend(ohlcv)
    print('Fetched', len(ohlcv), 'candles, total', len(all_ohlcv))
    last = ohlcv[-1][0]
    after = last + 1
    time.sleep(0.5)
    if last >= int(time.time() * 1000):
        break

all_ohlcv = [c for c in all_ohlcv if c[0] >= since_ms]
all_ohlcv.sort(key=lambda c: c[0])

with open(outfile, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['timestamp','open','high','low','close','volume'])
    for c in all_ohlcv:
        writer.writerow([c[0], str(c[1]), str(c[2]), str(c[3]), str(c[4]), str(c[5])])

print('Wrote', outfile, 'rows=', len(all_ohlcv))
