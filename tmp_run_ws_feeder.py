import os, sys
ROOT = os.path.abspath(os.path.dirname(__file__))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from arbitrage.exchanges.binance_ws_feeder import BinanceWSFeeder
import time

f = BinanceWSFeeder(['BTCUSDT','ETHUSDT'])
try:
    f.start()
    print('Feeder started, sleeping 5 seconds to collect updates...')
    time.sleep(5)
    t = f.get_tickers()
    print('Tickers snapshot:', t)
finally:
    f.stop()
    print('Feeder stopped')
