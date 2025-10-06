"""Start feeders, run the full scanner against live adapters (if available), then stop feeders.

This is a convenience runner so you can exercise the full scanner with feeders enabled
without manually starting/stopping feeders in separate shells.
"""
import os
import sys
import time

ROOT = os.path.abspath(os.path.dirname(__file__))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import tmp_start_all_feeders as starter
import tmp_compare_mexc_binance as scanner
try:
    # prefer the real scanner implementation
    from arbitrage.scanner import find_executable_opportunities as real_find_executable_opportunities
except Exception:
    real_find_executable_opportunities = None
from pprint import pprint


def main():
    print('Starting feeders...')
    feeders = starter.start_all(interval=1.0, symbols=None)
    try:
        print('Warming feeders for 5 seconds...')
        time.sleep(5.0)

        print('Probing live exchanges...')
        exs = None
        try:
            exs = scanner.live_mode(fast=False)
        except Exception as e:
            print('live_mode() raised:', e)
        if not exs:
            print('Falling back to mock mode')
            exs = scanner.mock_mode()

        print('Running full scanner (this may take a while)...')
        try:
            if real_find_executable_opportunities is not None:
                opps = real_find_executable_opportunities(exs, amount=0.01, min_profit_pct=0.05)
            else:
                opps = scanner.find_executable_opportunities(exs, amount=0.01, min_profit_pct=0.05)
        except Exception as e:
            import traceback
            print('Full scanner raised exception:')
            traceback.print_exc()
            opps = []

        print('\nFound opportunities:')
        if not opps:
            print('No opportunities found')
        else:
            for o in opps[:50]:
                pprint(o.__dict__ if hasattr(o, '__dict__') else o)

    finally:
        print('Stopping feeders...')
        try:
            starter.stop_all(feeders)
        except Exception:
            pass


if __name__ == '__main__':
    main()
