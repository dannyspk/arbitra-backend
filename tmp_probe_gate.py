import sys, os, traceback
ROOT = os.path.abspath('.')
src = os.path.join(ROOT, 'src')
if src not in sys.path:
    sys.path.insert(0, src)
from arbitrage.exchanges.ccxt_adapter import CCXTExchange
try:
    print('ccxt probe gate with timeout=5000ms')
    ex = CCXTExchange('gate', options={'timeout':5000, 'enableRateLimit': True})
    tickers = ex.get_tickers()
    print('success, tickers:', len(tickers))
except Exception as e:
    print('probe exception:')
    traceback.print_exc()
