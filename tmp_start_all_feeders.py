"""Start lightweight feeders for common exchanges and register them with the
ws_feed_manager so adapters can prefer in-memory snapshots.

This demo starts one feeder per exchange (binance, bitrue, kucoin, okx, gate, mexc)
and prints a small snapshot after a few seconds. It also demonstrates toggling
ARB_USE_WS_FEED for the environment so adapters will adopt the fast-path.
"""
import time
import os
import sys

ROOT = os.path.abspath(os.path.dirname(__file__))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from arbitrage.feeder_utils import start_all, stop_all  # type: ignore


if __name__ == '__main__':
    feeders = start_all(interval=1.0, symbols=['BTC-USD', 'ETH-USD', 'BTC/USDT', 'ETH/USDT'])
    try:
        print('warming feeders for 5 seconds...')
        time.sleep(5.0)
        for ex, f in feeders.items():
            try:
                snap = f.get_tickers()
                print(f'[{ex}] snapshot size={len(snap)} examples={list(snap.keys())[:5]}')
            except Exception as e:
                print(f'[{ex}] snapshot failed: {e}')
        print('feeders running; press Ctrl-C to stop')
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print('shutting down feeders...')
        stop_all(feeders)