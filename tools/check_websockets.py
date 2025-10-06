import time
try:
    import websockets
    WS_OK = True
except Exception as e:
    print('websockets import failed:', type(e).__name__, e)
    WS_OK = False

if not WS_OK:
    print('websockets not available')
    raise SystemExit(2)

print('websockets available:', websockets.__version__ if hasattr(websockets, '__version__') else 'unknown')

# try to import the MexcDepthFeeder if present
try:
    from arbitrage.exchanges.mexc_depth_feeder import MexcDepthFeeder
except Exception as e:
    print('MexcDepthFeeder import failed:', type(e).__name__, e)
    raise SystemExit(3)

# start a feeder for a short time and print tickers
symbols = ['BTC/USDT', 'ETH/USDT']
feeder = MexcDepthFeeder(symbols)
print('starting feeder...')
try:
    feeder.start()
    # wait a short while to allow connections (if possible)
    time.sleep(5)
    tk = feeder.get_tickers()
    print('tickers snapshot:', tk)
finally:
    feeder.stop()
    print('stopped feeder')
