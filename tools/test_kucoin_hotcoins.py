"""Quick test: start KucoinDepthFeeder for hotcoins and print last prices.

Run this script from repository root. It requires the `websockets` package
and internet access to KuCoin.
"""
import time
import os
import sys

sys.path.insert(0, os.path.abspath('src'))

from arbitrage.hotcoins import _binance_top_by_volume
from arbitrage.exchanges.kucoin_depth_feeder import KucoinDepthFeeder


def main():
    top = _binance_top_by_volume(top_n=20)
    if not top:
        print('No hotcoins from Binance REST; aborting')
        return

    symbols = []
    for it in top[:20]:
        sym = it.get('symbol') or it.get('base')
        if not sym:
            continue
        # convert Binance style (BTCUSDT or BTC/USDT) to KuCoin hyphenated form BTC-USDT
        s = sym.upper().replace('/', '-').replace('_', '-')
        if '-' not in s:
            # naive split: prefer USDT 4-char quote else last 3
            if len(s) > 4 and s.endswith('USDT'):
                s = s[:-4] + '-' + s[-4:]
            elif len(s) > 3:
                s = s[:-3] + '-' + s[-3:]
        symbols.append(s)

    print('Testing KuCoin tickers for symbols:', symbols)

    # KucoinDepthFeeder expects symbols like BTCUSDT (no separator) in constructor
    feeder_syms = [sym.replace('-', '') for sym in symbols]
    feeder = KucoinDepthFeeder(feeder_syms)
    try:
        feeder.start()
    except Exception as e:
        print('Failed to start feeder:', e)
        return

    try:
        # warm up
        import math
        chunk_size = 5
        chunk_count = math.ceil(len(symbols) / float(chunk_size)) if symbols else 1
        wait_time = int(chunk_count * 3 + 8)
        print(f'Waiting {wait_time}s for feeder warm-up (chunks={chunk_count})')
        time.sleep(wait_time)
        tk = feeder.get_tickers()
        out = {}
        for s in feeder_syms:
            key_slash = s[:-4] + '/' + s[-4:] if len(s) > 4 and s.endswith('USDT') else s
            info = tk.get(s) or tk.get(key_slash)
            last = info.get('last') if isinstance(info, dict) else None
            out[s] = last
        print('KuCoin last prices for hotcoins:')
        for k, v in out.items():
            print(f'  {k}: {v}')
    finally:
        feeder.stop()


if __name__ == '__main__':
    main()
