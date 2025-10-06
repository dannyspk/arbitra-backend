#!/usr/bin/env python3
"""Start a KuCoinDepthFeeder locally and show registration / snapshot info.

Run this from the repo root where PYTHONPATH='src' so imports resolve:

PowerShell:
$env:PYTHONPATH='src'; python scripts/start_kucoin_local.py

This prints whether the feeder started, what symbols it has snapshots for, and
sample orderbook entries.
"""

import time
import sys

try:
    from arbitrage.exchanges.kucoin_depth_feeder import KucoinDepthFeeder
    from arbitrage.exchanges.ws_feed_manager import register_feeder, get_feeder, unregister_feeder
except Exception as e:
    print('import_failed', str(e))
    sys.exit(2)

# Tokens from your screenshot (use USDT quote where appropriate)
symbols = [
    'XPLUS/USDT', 'ALPINE/USDT', 'SOMI/USDT', 'PUMP/USDT', 'BARD/USDT',
    'AVNT/USDT', 'EDEN/USDT', 'FF/USDT', 'ZEC/USDT', 'PEPE/USDT'
]

print('starting kucoin feeder for symbols:', symbols)
feeder = KucoinDepthFeeder(symbols)
try:
    feeder.start()
    register_feeder('kucoin', feeder)
    print('feeder started and registered as "kucoin"')
except Exception as e:
    print('feeder_start_failed', str(e))
    sys.exit(3)

# Give the feeder a few seconds to fetch snapshots / receive ws messages
print('waiting 8 seconds for snapshots...')
for i in range(8):
    time.sleep(1)
    print('.', end='', flush=True)
print('\n')

# Inspect internal state
try:
    f = get_feeder('kucoin')
    if not f:
        print('feeder not registered after start (get_feeder returned None)')
        sys.exit(4)
    books = getattr(f, '_books', {}) or {}
    ts = getattr(f, '_ts', None)
    print('last_update_ts:', ts)
    print('symbols with snapshots (sample up to 50):', list(books.keys())[:50])
    # Show sample orderbook for each requested symbol normalized
    for s in symbols:
        key = s.replace('/', '').replace('-', '').upper()
        ob = f.get_order_book(s, depth=5)
        print('\n==', s, '==')
        print('order_book:', ob)
except Exception as e:
    print('inspect_failed', str(e))

print('\nunregistering feeder and stopping')
try:
    unregister_feeder('kucoin')
    feeder.stop()
except Exception:
    pass

print('done')
