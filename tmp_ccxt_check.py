import os, sys, json
from pprint import pprint

# ensure imports use src package by adding src to sys.path (must happen before imports)
sys.path.insert(0, r'C:\\arbitrage\\src')

from arbitrage.exchanges.ccxt_adapter import CCXTExchange
from arbitrage.scanner import find_executable_opportunities

key = os.environ.get('BINANCE_API_KEY')
secret = os.environ.get('BINANCE_API_SECRET')
print('BINANCE key present:', bool(key))
print('BINANCE secret present:', bool(secret))

# pass conservative network options to ccxt to avoid long blocking calls
options = {'timeout': 5000, 'enableRateLimit': True}
cex = CCXTExchange('binance', key, secret, options=options)
print('CCXT client created:', getattr(cex.client, 'id', None))

found = False
for sym in ['BTC-USD', 'BTC/USD', 'BTC/USDT', 'ETH-USD', 'ETH/USDT']:
    try:
        ob = cex.get_order_book(sym, depth=10)
        print(f'orderbook for {sym}: asks[0..3], bids[0..3]')
        pprint({'asks': ob['asks'][:3], 'bids': ob['bids'][:3]})
        found = True
        break
    except Exception as e:
        print(f'failed {sym}: {e}')

if not found:
    print('No orderbook candidate succeeded')

# run CCXT-only scan
try:
    # prefer to run the blocking scan in a thread with a timeout to avoid hangs
    from concurrent.futures import ThreadPoolExecutor, TimeoutError

    tickers = cex.get_tickers()
    if not tickers:
        print('No tickers returned from CCXTExchange; skipping scan')
    else:
        with ThreadPoolExecutor(max_workers=1) as ex_thread:
            fut = ex_thread.submit(find_executable_opportunities, [cex], 0.01, 0.0001)
            try:
                opps = fut.result(timeout=8)
                print('opportunities found (count):', len(opps))
                for o in opps[:10]:
                    print(o)
            except TimeoutError:
                print('find_executable_opportunities timed out')
                fut.cancel()
            except Exception as e:
                print('scan failed:', type(e).__name__, str(e))
except Exception as e:
    print('scan wrapper failed:', type(e).__name__, str(e))
