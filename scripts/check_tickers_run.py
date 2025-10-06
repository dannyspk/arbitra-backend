import sys, time
sys.path.insert(0, 'src')
import os
os.environ['ARB_ENABLE_ARBITRAGE'] = '1'
from arbitrage.feeder_utils import start_all, stop_all
from arbitrage.exchanges.ws_feed_manager import get_feeder

fs = start_all(exchanges=['binance','kucoin'])
print('started:', list(fs.keys()))
try:
    time.sleep(8)
    ku = get_feeder('kucoin')
    print('ku present:', ku is not None)
    if ku:
        try:
            tk = ku.get_tickers()
            print('tickers count:', len(tk))
            for k in list(tk.keys())[:20]:
                print(k, tk[k])
        except Exception as e:
            print('get_tickers error', e)
finally:
    stop_all(fs)
