import sys, traceback
sys.path.insert(0, 'src')

try:
    from arbitrage.exchanges.kucoin_depth_feeder import KucoinDepthFeeder, websockets
    print('import ok, websockets is', 'present' if websockets is not None else 'MISSING')
    try:
        f = KucoinDepthFeeder(['BTC/USDT'])
        print('feeder instantiated, starting...')
        f.start()
        import time
        time.sleep(2)
        print('started ok, running state:', getattr(f, '_running', None))
        f.stop()
    except Exception as e:
        print('start error:')
        traceback.print_exc()
except Exception as e:
    print('import error')
    traceback.print_exc()
