"""Quick test: start GateDepthFeeder for hotcoins and print last prices.

Run this script from repository root. It requires the `websockets` package
and internet access to Gate.io.
"""
import time
import os
import sys

sys.path.insert(0, os.path.abspath('src'))

from arbitrage.hotcoins import _binance_top_by_volume
from arbitrage.exchanges.gate_depth_feeder import GateDepthFeeder


def main():
    # Obtain hotcoins via Binance REST helper and extract symbols
    top = _binance_top_by_volume(top_n=20)
    if not top:
        print('No hotcoins from find_hot_coins(); aborting')
        return

    symbols = []
    for it in top[:20]:
        sym = it.get('symbol') or it.get('base')
        if not sym:
            continue
        # convert Binance style (BTCUSDT or BTC/USDT) to Gate form BTC_USDT
        s = sym.upper().replace('/', '_').replace('-', '_')
        # If symbol looks like BASEQUOTE without separator, try insertion of underscore
        if '_' not in s:
            # naive split: assume last 4 or 3 chars are quote
            if len(s) > 4 and s.endswith('USDT'):
                s = s[:-4] + '_' + s[-4:]
            elif len(s) > 3:
                s = s[:-3] + '_' + s[-3:]
        symbols.append(s)

    print('Testing Gate tickers for symbols:', symbols)

    feeder = GateDepthFeeder([sym.replace('_', '/') for sym in symbols])
    feeder.start()
    try:
        # wait a bit for subscriptions to be sent in chunks and messages to arrive
        import math
        chunk_size = 5
        chunk_count = math.ceil(len(symbols) / float(chunk_size)) if symbols else 1
        # feeder sends chunked subscriptions for spot.tickers and then for
        # spot.book_ticker, each with a 3s pause between chunks. Account for
        # both passes when choosing a warm-up time.
        wait_time = int(chunk_count * 3 * 2 + 5)  # two passes (tickers + book_ticker)
        print(f'Waiting {wait_time}s for feeder warm-up (chunks={chunk_count})')
        time.sleep(wait_time)
        tk = feeder.get_tickers()
        # Print last price for each requested symbol in the repo form BASE/QUOTE
        out = {}
        for s in symbols:
            key = s.replace('_', '/')
            info = tk.get(key)
            last = info.get('last') if isinstance(info, dict) else None
            out[key] = last
        print('Gate last prices for hotcoins:')
        for k, v in out.items():
            print(f'  {k}: {v}')
    finally:
        feeder.stop()


if __name__ == '__main__':
    main()
