import time
import sys

# Run with: PYTHONPATH=src python tools/test_mexc_feeder.py
try:
    from arbitrage.exchanges.mexc_depth_feeder import MexcDepthFeeder
except Exception as e:
    print('import fail', e)
    sys.exit(1)

symbols = ['BTC/USDT', 'ETH/USDT']
print('creating MexcDepthFeeder for', symbols)
feeder = MexcDepthFeeder(symbols)
try:
    feeder.start()
except Exception as e:
    print('start failed:', e)
    sys.exit(1)

print('started, sleeping 10s to collect messages...')
for i in range(10):
    time.sleep(1)
    tks = feeder.get_tickers()
    print(f'[{i+1}] tickers sample count:', len(tks))
    if tks:
        from pprint import pprint
        pprint(tks)

print('\nOrder book BTC/USDT:', feeder.get_order_book('BTC/USDT'))
print('\nOrder book ETH/USDT:', feeder.get_order_book('ETH/USDT'))
feeder.stop()
print('stopped')
